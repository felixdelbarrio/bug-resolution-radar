"""Synchronous ingestion orchestration for API-triggered actions."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Dict, List
from uuid import uuid4

from bug_resolution_radar.analytics.finalist_discrepancies import (
    extract_helix_ids_from_text,
    is_country_finalist_status_lookup_mode,
)
from bug_resolution_radar.common.utils import now_iso
from bug_resolution_radar.config import (
    Settings,
    build_source_id,
    helix_service_origin_buug_for_country,
)
from bug_resolution_radar.ingest.helix_ingest import ingest_helix
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.issues_store import load_issues_doc, save_issues_doc

SourceProgressCallback = Callable[[bool, str, int, int], None]
SourceStartCallback = Callable[[str, int, int], None]
MessageCallback = Callable[[bool, str], None]

LOGGER = logging.getLogger(__name__)


def _get_helix_path(settings: Settings) -> str:
    path = str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip()
    return path or "data/helix.json"


def _coerce_positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return int(default)
    return parsed if parsed > 0 else int(default)


def _issue_merge_key(issue: NormalizedIssue) -> str:
    sid = str(issue.source_id or "").strip().lower()
    key = str(issue.key or "").strip().upper()
    return f"{sid}::{key}" if sid else key


def _source_progress_label(source: Dict[str, str]) -> str:
    alias = str(source.get("alias", "")).strip()
    country = str(source.get("country", "")).strip()
    if alias and country:
        return f"{alias} ({country})"
    return alias or country or str(source.get("source_id", "")).strip() or "Fuente"


def _merge_issues(doc: IssuesDocument, incoming: List[NormalizedIssue]) -> IssuesDocument:
    merged: Dict[str, NormalizedIssue] = {_issue_merge_key(issue): issue for issue in doc.issues}
    for issue in incoming:
        merged[_issue_merge_key(issue)] = issue
    doc.issues = list(merged.values())
    return doc


def _helix_merge_key(item: HelixWorkItem) -> str:
    sid = str(item.source_id or "").strip().lower()
    item_id = str(item.id or "").strip().upper()
    return f"{sid}::{item_id}" if sid else item_id


def _merge_helix_items(doc: HelixDocument, incoming: List[HelixWorkItem]) -> HelixDocument:
    merged: Dict[str, HelixWorkItem] = {_helix_merge_key(item): item for item in doc.items}
    for item in incoming:
        merged[_helix_merge_key(item)] = item
    doc.items = list(merged.values())
    return doc


def _existing_helix_ids_by_country(doc: HelixDocument, *, country: str) -> set[str]:
    country_txt = str(country or "").strip()
    out: set[str] = set()
    for item in list(getattr(doc, "items", []) or []):
        if country_txt and str(item.country or "").strip() != country_txt:
            continue
        item_id = str(item.id or "").strip().upper()
        if item_id:
            out.add(item_id)
    return out


def _jira_incidents_by_country(
    doc: IssuesDocument,
    *,
    selected_sources: List[Dict[str, str]],
) -> Dict[str, Dict[str, List[str]]]:
    selected_source_ids = {
        str(source.get("source_id") or "").strip()
        for source in list(selected_sources or [])
        if str(source.get("source_id") or "").strip()
    }
    out: Dict[str, Dict[str, List[str]]] = {}
    for issue in list(doc.issues or []):
        if str(issue.source_type or "").strip().lower() != "jira":
            continue
        source_id = str(issue.source_id or "").strip()
        if selected_source_ids and source_id not in selected_source_ids:
            continue
        country = str(issue.country or "").strip()
        jira_key = str(issue.key or "").strip().upper()
        if not country or not jira_key:
            continue
        text_parts = [
            str(issue.summary or ""),
            str(issue.description or ""),
            str(issue.resolution or ""),
            " ".join(str(label or "") for label in list(issue.labels or [])),
            " ".join(str(component or "") for component in list(issue.components or [])),
        ]
        for inc_id in extract_helix_ids_from_text("\n".join(text_parts)):
            bucket = out.setdefault(country, {}).setdefault(inc_id, [])
            if jira_key not in bucket:
                bucket.append(jira_key)
    return out


def _chunked(values: List[str], *, size: int) -> List[List[str]]:
    safe_size = max(int(size or 0), 1)
    return [values[idx : idx + safe_size] for idx in range(0, len(values), safe_size)]


def _lookup_batch_size(settings: Settings) -> int:
    env_value = os.getenv("HELIX_INC_LOOKUP_BATCH_SIZE", "")
    return min(
        100,
        max(
            1,
            _coerce_positive_int(
                env_value or getattr(settings, "HELIX_INC_LOOKUP_BATCH_SIZE", 25),
                default=25,
            ),
        ),
    )


def _is_closed_status(value: str) -> bool:
    token = str(value or "").strip().lower()
    return token in {"closed", "resolved", "done", "deployed", "accepted", "cancelled", "canceled"}


def _helix_item_to_issue(item: HelixWorkItem) -> NormalizedIssue:
    status = str(item.status or "").strip() or "Open"
    created = (
        str(item.start_datetime or item.target_date or item.last_modified or "").strip() or None
    )
    updated = (
        str(item.last_modified or item.closed_date or item.start_datetime or "").strip() or None
    )
    closed_date = str(item.closed_date or "").strip() or None
    resolved = closed_date or (updated if _is_closed_status(status) else None)
    label = f"{str(item.matrix_service_n1 or '').strip()} {str(item.source_service_n1 or '').strip()}".strip()
    impacted = str(item.impacted_service or item.service or "").strip()
    components = [impacted] if impacted else []
    return NormalizedIssue(
        key=str(item.id or "").strip(),
        summary=str(item.summary or "").strip(),
        description=str(item.description or "").strip(),
        status=status,
        type=str(item.incident_type or "").strip() or "Helix",
        priority=str(item.priority or "").strip(),
        created=created,
        updated=updated,
        resolved=resolved,
        assignee=str(item.assignee or "").strip(),
        reporter=str(item.customer_name or "").strip(),
        labels=[label] if label else [],
        components=components,
        resolution="",
        resolution_type="",
        url=str(item.url or "").strip(),
        country=str(item.country or "").strip(),
        source_type="helix",
        source_alias=str(item.source_alias or "").strip(),
        source_id=str(item.source_id or "").strip(),
    )


def _run_post_jql_helix_lookup(
    settings: Settings,
    *,
    selected_sources: List[Dict[str, str]],
    issues_doc: IssuesDocument,
    on_source_result: SourceProgressCallback | None = None,
    on_source_start: SourceStartCallback | None = None,
    on_message: MessageCallback | None = None,
) -> tuple[IssuesDocument, dict[str, Any]]:
    run_id = uuid4().hex[:12]
    helix_path = _get_helix_path(settings)
    helix_repo = HelixRepo(Path(helix_path))
    merged_helix = helix_repo.load() or HelixDocument.empty()
    inc_by_country = _jira_incidents_by_country(issues_doc, selected_sources=selected_sources)
    batch_size = _lookup_batch_size(settings)

    if not inc_by_country:
        message = "Lookup Helix post-JQL omitido: no se encontraron referencias INC en Jira."
        if on_message is not None:
            on_message(True, message)
        return issues_doc, {
            "state": "skipped",
            "summary": message,
            "countries": 0,
            "inc_total": 0,
            "found_count": 0,
            "missing_count": 0,
            "error_count": 0,
            "messages": [{"ok": True, "message": message}],
        }

    helix_browser = (
        str(getattr(settings, "HELIX_BROWSER", "chrome") or "chrome").strip() or "chrome"
    )
    helix_proxy = str(getattr(settings, "HELIX_PROXY", "") or "").strip()
    helix_ssl_verify = str(getattr(settings, "HELIX_SSL_VERIFY", "") or "").strip()
    messages: list[dict[str, Any]] = []
    found_total = 0
    missing_total = 0
    error_count = 0
    total_batches = 0
    completed_batches = 0

    pending_by_country: Dict[str, Dict[str, List[str]]] = {}
    for country, inc_map in inc_by_country.items():
        existing = _existing_helix_ids_by_country(merged_helix, country=country)
        pending = {
            inc_id: jira_keys
            for inc_id, jira_keys in inc_map.items()
            if str(inc_id).strip().upper() not in existing
        }
        if pending:
            pending_by_country[country] = pending
            total_batches += len(_chunked(list(pending.keys()), size=batch_size))

    if not pending_by_country:
        message = (
            "Lookup Helix post-JQL omitido: todos los INC encontrados ya existen en cache Helix."
        )
        if on_message is not None:
            on_message(True, message)
        return issues_doc, {
            "state": "skipped",
            "summary": message,
            "countries": len(inc_by_country),
            "inc_total": sum(len(v) for v in inc_by_country.values()),
            "found_count": 0,
            "missing_count": 0,
            "error_count": 0,
            "messages": [{"ok": True, "message": message}],
        }

    if on_message is not None:
        on_message(
            True,
            "JQL terminado. Iniciando fase post-JQL: Buscar estados finalistas del país.",
        )

    for country, inc_map in pending_by_country.items():
        country_txt = str(country or "").strip()
        service_origin_buug = helix_service_origin_buug_for_country(country_txt)
        source_alias = "Lookup estados finalistas Jira"
        source_id = build_source_id("helix", country_txt, source_alias)
        inc_ids = list(inc_map.keys())
        batches = _chunked(inc_ids, size=batch_size)
        for batch_index, batch in enumerate(batches, start=1):
            completed_batches += 1
            label = (
                f"Buscar estados finalistas del país · {country_txt} "
                f"lote {batch_index}/{len(batches)}"
            )
            if on_source_start is not None:
                on_source_start(label, completed_batches, total_batches)
            started = monotonic()
            found_count = 0
            missing_count = len(batch)
            error_text = ""
            ok = False
            try:
                ok, msg, lookup_doc = ingest_helix(
                    browser=helix_browser,
                    country=country_txt,
                    source_alias=source_alias,
                    source_id=source_id,
                    proxy=helix_proxy,
                    ssl_verify=helix_ssl_verify,
                    service_origin_buug=service_origin_buug,
                    service_origin_n1=getattr(settings, "HELIX_ARSQL_SOURCE_SERVICE_N1", ""),
                    service_origin_n2=getattr(settings, "HELIX_ARSQL_SOURCE_SERVICE_N2", ""),
                    chunk_size=batch_size,
                    dry_run=False,
                    existing_doc=HelixDocument.empty(),
                    cache_doc=merged_helix,
                    incident_ids=batch,
                    incident_ids_only=True,
                    matched_jira_keys_by_incident_id=inc_map,
                )
                batch_items = list(getattr(lookup_doc, "items", []) or []) if lookup_doc else []
                found_ids = {str(item.id or "").strip().upper() for item in batch_items}
                found_ids &= {str(inc_id).strip().upper() for inc_id in batch}
                found_count = len(found_ids)
                missing_count = max(len(batch) - found_count, 0)
                if batch_items:
                    merged_helix = _merge_helix_items(merged_helix, batch_items)
                    issues_doc = _merge_issues(
                        issues_doc, [_helix_item_to_issue(item) for item in batch_items]
                    )
                message = str(msg or "").strip()
                if missing_count > 0:
                    message = (
                        f"{message} Missing INC: "
                        f"{', '.join([inc for inc in batch if inc not in found_ids])}"
                    ).strip()
                if not ok:
                    error_count += 1
                    error_text = message or "lookup_batch_failed"
                found_total += found_count
                missing_total += missing_count
            except Exception as exc:
                ok = False
                error_count += 1
                error_text = f"{type(exc).__name__}: {exc}"
                message = (
                    f"{country_txt}: fallo en lookup Helix lote {batch_index}/{len(batches)}: "
                    f"{error_text}"
                )
                missing_total += len(batch)

            duration_ms = int((monotonic() - started) * 1000.0)
            LOGGER.info(
                "helix_inc_lookup_batch",
                extra={
                    "run_id": run_id,
                    "country": country_txt,
                    "service_origin_buug": service_origin_buug,
                    "inc_total": len(inc_ids),
                    "inc_batch_size": batch_size,
                    "batch_index": batch_index,
                    "batch_count": len(batches),
                    "inc_ids": list(batch),
                    "found_count": int(found_count),
                    "missing_count": int(missing_count),
                    "error": error_text,
                    "duration_ms": duration_ms,
                },
            )
            messages.append({"ok": bool(ok), "message": message})
            if on_source_result is not None:
                on_source_result(bool(ok), message, completed_batches, total_batches)

    issues_doc.ingested_at = now_iso()
    helix_repo.save(merged_helix)
    save_issues_doc(settings.DATA_PATH, issues_doc)

    state = "success" if error_count == 0 else ("partial" if found_total > 0 else "error")
    summary = (
        "Lookup Helix post-JQL finalizado: "
        f"{found_total} INC recuperados, {missing_total} sin resultado, {error_count} lotes con error."
    )
    return issues_doc, {
        "state": state,
        "summary": summary,
        "countries": len(pending_by_country),
        "inc_total": sum(len(v) for v in pending_by_country.values()),
        "found_count": int(found_total),
        "missing_count": int(missing_total),
        "error_count": int(error_count),
        "messages": messages,
    }


def run_jira_ingest(
    settings: Settings,
    *,
    selected_sources: List[Dict[str, str]],
    on_source_result: SourceProgressCallback | None = None,
    on_source_start: SourceStartCallback | None = None,
    on_message: MessageCallback | None = None,
    persist_each_source: bool = True,
) -> dict[str, Any]:
    work_doc = load_issues_doc(settings.DATA_PATH)
    messages: list[dict[str, Any]] = []
    success_count = 0
    checkpoints_saved = 0
    sources = list(selected_sources or [])
    total_sources = len(sources)
    completed_sources = 0
    for position, src in enumerate(sources, start=1):
        if on_source_start is not None:
            on_source_start(_source_progress_label(src), int(position), int(total_sources))
        ok, msg, new_doc = ingest_jira(
            settings=settings, dry_run=False, existing_doc=work_doc, source=src
        )
        source_ok = bool(ok)
        source_message = str(msg or "").strip()
        if source_ok and new_doc is not None:
            work_doc = new_doc
            if persist_each_source:
                save_issues_doc(settings.DATA_PATH, work_doc)
                checkpoints_saved += 1
            success_count += 1
        elif source_ok and new_doc is None:
            source_ok = False
            if not source_message:
                source_message = (
                    "Ingesta Jira sin documento resultado; no se pudo confirmar persistencia."
                )
        messages.append({"ok": bool(source_ok), "message": source_message})
        completed_sources += 1
        if on_source_result is not None:
            on_source_result(
                bool(source_ok),
                source_message,
                int(completed_sources),
                int(total_sources),
            )

    if success_count > 0 and (not persist_each_source or checkpoints_saved <= 0):
        save_issues_doc(settings.DATA_PATH, work_doc)

    lookup_result: dict[str, Any] | None = None
    if success_count > 0 and is_country_finalist_status_lookup_mode(settings):
        work_doc, lookup_result = _run_post_jql_helix_lookup(
            settings,
            selected_sources=sources,
            issues_doc=work_doc,
            on_source_result=on_source_result,
            on_source_start=on_source_start,
            on_message=on_message,
        )
        messages.extend(list(lookup_result.get("messages") or []))

    base_state = (
        "success"
        if success_count == total_sources and total_sources > 0
        else ("partial" if success_count > 0 else "error")
    )
    lookup_state = str((lookup_result or {}).get("state") or "").strip().lower()
    state = base_state
    if lookup_state in {"partial", "error"}:
        state = "partial" if base_state in {"success", "partial"} else "error"
    return {
        "state": state,
        "summary": (
            f"Reingesta Jira finalizada: {success_count}/{total_sources} fuentes OK."
            + (f" {lookup_result.get('summary')}" if lookup_result else "")
        ),
        "success_count": int(success_count),
        "total_sources": int(total_sources),
        "messages": messages,
        "post_jql_lookup": lookup_result,
    }


def run_helix_ingest(
    settings: Settings,
    *,
    selected_sources: List[Dict[str, str]],
    on_source_result: SourceProgressCallback | None = None,
    on_source_start: SourceStartCallback | None = None,
    persist_each_source: bool = True,
) -> dict[str, Any]:
    helix_path = _get_helix_path(settings)
    helix_repo = HelixRepo(Path(helix_path))
    merged_helix = helix_repo.load() or HelixDocument.empty()
    issues_doc = load_issues_doc(settings.DATA_PATH)
    helix_browser = (
        str(getattr(settings, "HELIX_BROWSER", "chrome") or "chrome").strip() or "chrome"
    )
    helix_proxy = str(getattr(settings, "HELIX_PROXY", "") or "").strip()
    helix_ssl_verify = str(getattr(settings, "HELIX_SSL_VERIFY", "") or "").strip()

    messages: list[dict[str, Any]] = []
    success_count = 0
    has_partial_updates = False
    checkpoints_saved = 0
    sources = list(selected_sources or [])
    total_sources = len(sources)
    completed_sources = 0
    for position, src in enumerate(sources, start=1):
        if on_source_start is not None:
            on_source_start(_source_progress_label(src), int(position), int(total_sources))
        ok, msg, new_helix_doc = ingest_helix(
            browser=helix_browser,
            country=str(src.get("country", "")).strip(),
            source_alias=str(src.get("alias", "")).strip(),
            source_id=str(src.get("source_id", "")).strip(),
            proxy=helix_proxy,
            ssl_verify=helix_ssl_verify,
            service_origin_buug=src.get("service_origin_buug"),
            service_origin_n1=src.get("service_origin_n1"),
            service_origin_n2=src.get("service_origin_n2"),
            dry_run=False,
            existing_doc=HelixDocument.empty(),
            cache_doc=merged_helix,
        )
        source_ok = bool(ok)
        source_message = str(msg or "").strip()
        checkpoint_required = False
        if new_helix_doc is not None:
            checkpoint_required = True
            merged_helix.ingested_at = new_helix_doc.ingested_at
            merged_helix.helix_base_url = new_helix_doc.helix_base_url
            merged_helix.query = "multi-source"
        if new_helix_doc is not None and new_helix_doc.items:
            has_partial_updates = True
            merged_helix = _merge_helix_items(merged_helix, new_helix_doc.items)
            issues_doc = _merge_issues(
                issues_doc, [_helix_item_to_issue(item) for item in new_helix_doc.items]
            )
        if persist_each_source and checkpoint_required:
            issues_doc.ingested_at = now_iso()
            helix_repo.save(merged_helix)
            save_issues_doc(settings.DATA_PATH, issues_doc)
            checkpoints_saved += 1
        if source_ok:
            success_count += 1
        messages.append({"ok": bool(source_ok), "message": source_message})
        completed_sources += 1
        if on_source_result is not None:
            on_source_result(
                bool(source_ok),
                source_message,
                int(completed_sources),
                int(total_sources),
            )

    if (success_count > 0 or has_partial_updates) and (
        not persist_each_source or checkpoints_saved <= 0
    ):
        issues_doc.ingested_at = now_iso()
        helix_repo.save(merged_helix)
        save_issues_doc(settings.DATA_PATH, issues_doc)

    return {
        "state": "success"
        if success_count == total_sources and total_sources > 0
        else ("partial" if success_count > 0 else "error"),
        "summary": f"Reingesta Helix finalizada: {success_count}/{total_sources} fuentes OK.",
        "success_count": int(success_count),
        "total_sources": int(total_sources),
        "messages": messages,
    }
