"""Synchronous ingestion orchestration for API-triggered actions."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Dict, List
from uuid import uuid4

from bug_resolution_radar.analytics.finalist_discrepancies import (
    POST_JQL_LOOKUP_HELIX_KIND,
    POST_JQL_LOOKUP_HELIX_SOURCE_ALIAS,
    extract_helix_ids_from_text,
    is_post_jql_lookup_helix_source,
)
from bug_resolution_radar.analytics.status_semantics import (
    is_finalist_status,
    is_jira_finalist_lookup_status,
)
from bug_resolution_radar.common.utils import now_iso
from bug_resolution_radar.config import (
    Settings,
    build_source_id,
    helix_service_origin_buug_for_country,
    normalize_country_name,
)
from bug_resolution_radar.ingest.helix_ingest import (
    _build_arsql_endpoint,
    ingest_helix,
    lookup_helix_incidents_by_arsql,
)
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.models.schema import IssuesDocument
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.issues_store import load_issues_doc, save_issues_doc
from bug_resolution_radar.services.ingest_merge import (
    helix_item_to_issue,
    merge_helix_items,
    merge_issues,
)

SourceProgressCallback = Callable[[bool, str, int, int], None]
SourceStartCallback = Callable[[str, int, int], None]
MessageCallback = Callable[[bool, str], None]

LOGGER = logging.getLogger(__name__)
_NONINTERACTIVE_HELIX_SESSION_UNAVAILABLE = (
    "Helix session unavailable for non-interactive ARSQL lookup"
)


def _get_helix_path(settings: Settings) -> str:
    path = str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip()
    return path or "data/helix.json"


def _coerce_positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return int(default)
    return parsed if parsed > 0 else int(default)


def _source_progress_label(source: Dict[str, str]) -> str:
    alias = str(source.get("alias", "")).strip()
    country = str(source.get("country", "")).strip()
    if alias and country:
        return f"{alias} ({country})"
    return alias or country or str(source.get("source_id", "")).strip() or "Fuente"


def _lookup_sort_dt(item: HelixWorkItem) -> datetime:
    return (
        _parse_lookup_dt(item.lookup_at)
        or _parse_lookup_dt(item.last_modified)
        or _parse_lookup_dt(item.closed_date)
        or _parse_lookup_dt(item.start_datetime)
        or _parse_lookup_dt(item.target_date)
        or datetime.min.replace(tzinfo=timezone.utc)
    )


def _is_better_historical_lookup_item(
    candidate: HelixWorkItem,
    current: HelixWorkItem | None,
) -> bool:
    if current is None:
        return True
    candidate_rank = (
        _lookup_sort_dt(candidate),
        not _lookup_item_requires_refresh(candidate),
        is_post_jql_lookup_helix_source(
            str(candidate.source_id or "").strip(),
            str(candidate.source_alias or "").strip(),
            str(candidate.helix_lookup_kind or "").strip(),
        ),
        bool(str(candidate.url or "").strip()),
    )
    current_rank = (
        _lookup_sort_dt(current),
        not _lookup_item_requires_refresh(current),
        is_post_jql_lookup_helix_source(
            str(current.source_id or "").strip(),
            str(current.source_alias or "").strip(),
            str(current.helix_lookup_kind or "").strip(),
        ),
        bool(str(current.url or "").strip()),
    )
    return candidate_rank >= current_rank


def _historical_lookup_items_by_incident(
    doc: HelixDocument,
    *,
    country: str,
    service_origin_buug: str,
) -> Dict[str, HelixWorkItem]:
    country_txt = normalize_country_name(country) or str(country or "").strip()
    service_origin_buug_txt = str(service_origin_buug or "").strip()
    out: Dict[str, HelixWorkItem] = {}
    for item in getattr(doc, "items", []) or ():
        item_country = normalize_country_name(item.country) or str(item.country or "").strip()
        if country_txt and item_country != country_txt:
            continue
        item_buug = str(item.service_origin_buug or "").strip()
        if (
            service_origin_buug_txt
            and item_buug
            and item_buug.casefold() != service_origin_buug_txt.casefold()
        ):
            continue
        inc_id = str(item.id or "").strip().upper()
        if not inc_id:
            continue
        if _is_better_historical_lookup_item(item, out.get(inc_id)):
            out[inc_id] = item
    return out


def _lookup_item_requires_refresh(
    item: HelixWorkItem | None,
) -> bool:
    if item is None:
        return True
    return not is_finalist_status(item.status or item.status_raw)


def _jira_incidents_by_country(
    doc: IssuesDocument,
    *,
    selected_sources: List[Dict[str, str]],
) -> Dict[str, Dict[str, List[str]]]:
    """Return ARSQL lookup candidates from non-finalist JIRA descriptions only."""
    selected_source_ids = frozenset(
        str(source.get("source_id") or "").strip()
        for source in list(selected_sources or [])
        if str(source.get("source_id") or "").strip()
    )
    out: Dict[str, Dict[str, List[str]]] = {}
    seen_links: set[tuple[str, str, str]] = set()
    for issue in doc.issues or ():
        if str(issue.source_type or "").strip().lower() != "jira":
            continue
        source_id = str(issue.source_id or "").strip()
        if selected_source_ids and source_id not in selected_source_ids:
            continue
        country = normalize_country_name(issue.country) or str(issue.country or "").strip()
        jira_key = str(issue.key or "").strip().upper()
        if not country or not jira_key:
            continue
        if is_jira_finalist_lookup_status(issue.status):
            continue
        description = str(issue.description or "")
        if not description:
            continue
        for inc_id in extract_helix_ids_from_text(description):
            link_key = (country, inc_id, jira_key)
            if link_key in seen_links:
                continue
            seen_links.add(link_key)
            bucket = out.setdefault(country, {}).setdefault(inc_id, [])
            bucket.append(jira_key)
    return out


def _chunked(values: List[str], *, size: int) -> List[List[str]]:
    safe_size = max(int(size or 0), 1)
    return [values[idx : idx + safe_size] for idx in range(0, len(values), safe_size)]


def _chunk_count(total_values: int, *, size: int) -> int:
    safe_size = max(int(size or 0), 1)
    total = max(int(total_values or 0), 0)
    return (total + safe_size - 1) // safe_size


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


def _parse_lookup_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _finalist_lookup_source_id(country: str) -> str:
    return build_source_id("helix", str(country or "").strip(), POST_JQL_LOOKUP_HELIX_SOURCE_ALIAS)


def _arsql_endpoint_for_logs(settings: Settings) -> str:
    root = str(
        getattr(settings, "HELIX_ARSQL_BASE_URL", "") or os.getenv("HELIX_ARSQL_BASE_URL", "")
    ).strip()
    uid = str(
        getattr(settings, "HELIX_ARSQL_DATASOURCE_UID", "")
        or os.getenv("HELIX_ARSQL_DATASOURCE_UID", "")
    ).strip()
    if not root or not uid:
        return ""
    return _build_arsql_endpoint(root, uid)


def _historical_item_to_finalist_lookup_item(
    item: HelixWorkItem,
    *,
    country: str,
    service_origin_buug: str,
    source_id: str,
    source_alias: str,
    matched_jira_keys: List[str],
    run_id: str,
    lookup_at: str,
) -> HelixWorkItem:
    matched_keys = sorted(
        {
            str(key or "").strip().upper()
            for key in matched_jira_keys or ()
            if str(key or "").strip()
        }
    )
    status = str(item.status or item.status_raw or "").strip()
    return item.model_copy(
        update={
            "status": status,
            "country": str(country or "").strip(),
            "service_origin_buug": str(
                service_origin_buug or item.service_origin_buug or ""
            ).strip(),
            "source_id": str(source_id or "").strip(),
            "source_alias": str(source_alias or "").strip(),
            "helix_lookup_kind": POST_JQL_LOOKUP_HELIX_KIND,
            "matched_jira_keys": matched_keys,
            "lookup_run_id": str(item.lookup_run_id or run_id or "").strip(),
            "lookup_at": str(item.lookup_at or lookup_at or "").strip(),
            "lookup_status": str(item.lookup_status or "cached_finalist").strip(),
            "lookup_error": str(item.lookup_error or "").strip(),
        }
    )


def _lookup_diagnostic_item(
    *,
    inc_id: str,
    country: str,
    service_origin_buug: str,
    source_id: str,
    source_alias: str,
    matched_jira_keys: List[str],
    run_id: str,
    lookup_at: str,
    lookup_status: str,
    lookup_error: str = "",
) -> HelixWorkItem:
    return HelixWorkItem(
        id=str(inc_id or "").strip().upper(),
        country=str(country or "").strip(),
        service_origin_buug=str(service_origin_buug or "").strip(),
        source_id=str(source_id or "").strip(),
        source_alias=str(source_alias or "").strip(),
        helix_lookup_kind=POST_JQL_LOOKUP_HELIX_KIND,
        matched_jira_keys=sorted(
            {
                str(key or "").strip().upper()
                for key in matched_jira_keys or ()
                if str(key or "").strip()
            }
        ),
        lookup_run_id=str(run_id or "").strip(),
        lookup_at=str(lookup_at or "").strip(),
        lookup_status=str(lookup_status or "").strip(),
        lookup_error=str(lookup_error or "").strip(),
    )


def _is_noninteractive_session_unavailable(message: Any) -> bool:
    return _NONINTERACTIVE_HELIX_SESSION_UNAVAILABLE.lower() in str(message or "").lower()


def _run_finalist_status_lookup(
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
    lookup_now = datetime.now(timezone.utc)
    lookup_at = lookup_now.isoformat()
    arsql_endpoint = _arsql_endpoint_for_logs(settings)

    if not inc_by_country:
        message = (
            "Lookup Helix omitido: no se encontraron referencias INC en descripciones "
            "de Jira no finalistas."
        )
        if on_message is not None:
            on_message(True, message)
        return issues_doc, {
            "state": "skipped_no_inc",
            "summary": message,
            "countries": 0,
            "inc_total": 0,
            "total_batches": 0,
            "success_count": 0,
            "total_sources": 0,
            "found_count": 0,
            "missing_count": 0,
            "error_count": 0,
            "messages": [{"ok": True, "message": message}],
        }

    messages: list[dict[str, Any]] = []
    found_total = 0
    missing_total = 0
    error_count = 0
    batch_success_count = 0
    total_batches = 0
    completed_batches = 0
    cached_final_items: list[HelixWorkItem] = []
    cached_final_count = 0

    pending_by_country: Dict[str, Dict[str, List[str]]] = {}
    for country, inc_map in inc_by_country.items():
        country_txt = normalize_country_name(country) or str(country or "").strip()
        service_origin_buug = helix_service_origin_buug_for_country(country_txt)
        source_alias = POST_JQL_LOOKUP_HELIX_SOURCE_ALIAS
        source_id = _finalist_lookup_source_id(country_txt)
        historical_items = _historical_lookup_items_by_incident(
            merged_helix,
            country=country_txt,
            service_origin_buug=service_origin_buug,
        )
        pending: Dict[str, List[str]] = {}
        for inc_id, jira_keys in inc_map.items():
            normalized_inc_id = str(inc_id or "").strip().upper()
            historical_item = historical_items.get(normalized_inc_id)
            if historical_item is not None and not _lookup_item_requires_refresh(historical_item):
                cached_final_items.append(
                    _historical_item_to_finalist_lookup_item(
                        historical_item,
                        country=country_txt,
                        service_origin_buug=service_origin_buug,
                        source_id=source_id,
                        source_alias=source_alias,
                        matched_jira_keys=jira_keys,
                        run_id=run_id,
                        lookup_at=lookup_at,
                    )
                )
                continue
            pending[normalized_inc_id] = jira_keys
        if pending:
            pending_by_country[country_txt] = pending
            total_batches += _chunk_count(len(pending), size=batch_size)

    if cached_final_items:
        cached_ids = {str(item.id or "").strip().upper() for item in cached_final_items}
        cached_final_count = sum(1 for item_id in cached_ids if item_id)
        merged_helix = merge_helix_items(merged_helix, cached_final_items)
        issues_doc = merge_issues(
            issues_doc, [helix_item_to_issue(item) for item in cached_final_items]
        )

    if not pending_by_country:
        message = (
            "Lookup Helix omitido: todos los INC encontrados ya están localizados "
            "en histórico Helix con estado finalista."
        )
        if on_message is not None:
            on_message(True, message)
        if cached_final_items:
            issues_doc.ingested_at = now_iso()
            helix_repo.save(merged_helix)
            save_issues_doc(settings.DATA_PATH, issues_doc)
        return issues_doc, {
            "state": "skipped_cached",
            "summary": message,
            "countries": len(inc_by_country),
            "inc_total": sum(len(v) for v in inc_by_country.values()),
            "total_batches": 0,
            "success_count": 0,
            "total_sources": 0,
            "found_count": 0,
            "cached_final_count": int(cached_final_count),
            "missing_count": 0,
            "error_count": 0,
            "messages": [{"ok": True, "message": message}],
        }

    if on_message is not None:
        on_message(
            True,
            "Iniciando ingesta: Buscar estados finalistas del país.",
        )

    for country, inc_map in pending_by_country.items():
        country_txt = str(country or "").strip()
        service_origin_buug = helix_service_origin_buug_for_country(country_txt)
        source_alias = POST_JQL_LOOKUP_HELIX_SOURCE_ALIAS
        source_id = _finalist_lookup_source_id(country_txt)
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
                ok, msg, lookup_doc = lookup_helix_incidents_by_arsql(
                    settings,
                    country=country_txt,
                    service_origin_buug=service_origin_buug,
                    incident_ids=batch,
                    source_alias=source_alias,
                    source_id=source_id,
                    cache_doc=merged_helix,
                    matched_jira_keys_by_incident_id=inc_map,
                    batch_size=batch_size,
                    allow_interactive_bootstrap=False,
                    lookup_run_id=run_id,
                    lookup_at=lookup_at,
                    helix_lookup_kind=POST_JQL_LOOKUP_HELIX_KIND,
                )
                batch_items = list(getattr(lookup_doc, "items", []) or []) if lookup_doc else []
                found_ids = {str(item.id or "").strip().upper() for item in batch_items}
                found_ids &= {str(inc_id).strip().upper() for inc_id in batch}
                found_count = len(found_ids)
                missing_count = max(len(batch) - found_count, 0)
                if batch_items:
                    merged_helix = merge_helix_items(merged_helix, batch_items)
                    issues_doc = merge_issues(
                        issues_doc, [helix_item_to_issue(item) for item in batch_items]
                    )
                missing_ids = [
                    str(inc_id or "").strip().upper()
                    for inc_id in batch
                    if str(inc_id or "").strip().upper() not in found_ids
                ]
                if missing_ids:
                    merged_helix = merge_helix_items(
                        merged_helix,
                        [
                            _lookup_diagnostic_item(
                                inc_id=inc_id,
                                country=country_txt,
                                service_origin_buug=service_origin_buug,
                                source_id=source_id,
                                source_alias=source_alias,
                                matched_jira_keys=inc_map.get(inc_id, []),
                                run_id=run_id,
                                lookup_at=lookup_at,
                                lookup_status="missing" if ok else "error",
                                lookup_error="" if ok else str(msg or "").strip(),
                            )
                            for inc_id in missing_ids
                        ],
                    )
                message = str(msg or "").strip()
                if missing_count > 0:
                    message = (f"{message} Missing INC: {', '.join(missing_ids)}").strip()
                if not ok:
                    error_count += 1
                    error_text = message or "lookup_batch_failed"
                else:
                    batch_success_count += 1
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
                merged_helix = merge_helix_items(
                    merged_helix,
                    [
                        _lookup_diagnostic_item(
                            inc_id=inc_id,
                            country=country_txt,
                            service_origin_buug=service_origin_buug,
                            source_id=source_id,
                            source_alias=source_alias,
                            matched_jira_keys=inc_map.get(inc_id, []),
                            run_id=run_id,
                            lookup_at=lookup_at,
                            lookup_status="error",
                            lookup_error=error_text,
                        )
                        for inc_id in batch
                    ],
                )

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
                    "interactive_bootstrap": False,
                    "arsql_endpoint": arsql_endpoint,
                },
            )
            messages.append({"ok": bool(ok), "message": message})
            if on_source_result is not None:
                on_source_result(bool(ok), message, completed_batches, total_batches)
            if not ok and _is_noninteractive_session_unavailable(message):
                remaining_ids = [
                    str(inc_id or "").strip().upper()
                    for pending_batch in batches[batch_index:]
                    for inc_id in pending_batch
                    if str(inc_id or "").strip()
                ]
                if remaining_ids:
                    missing_total += len(remaining_ids)
                    merged_helix = merge_helix_items(
                        merged_helix,
                        [
                            _lookup_diagnostic_item(
                                inc_id=inc_id,
                                country=country_txt,
                                service_origin_buug=service_origin_buug,
                                source_id=source_id,
                                source_alias=source_alias,
                                matched_jira_keys=inc_map.get(inc_id, []),
                                run_id=run_id,
                                lookup_at=lookup_at,
                                lookup_status="error",
                                lookup_error=message,
                            )
                            for inc_id in remaining_ids
                        ],
                    )
                    skipped_message = (
                        f"{country_txt}: lookup Helix detenido tras error de sesión; "
                        f"{len(remaining_ids)} INC restantes quedan diagnosticados sin reintentar."
                    )
                    messages.append({"ok": False, "message": skipped_message})
                    if on_message is not None:
                        on_message(False, skipped_message)
                break

    issues_doc.ingested_at = now_iso()
    helix_repo.save(merged_helix)
    save_issues_doc(settings.DATA_PATH, issues_doc)

    state = "success" if error_count == 0 else ("partial" if found_total > 0 else "error")
    summary = (
        "Lookup Helix finalizado: "
        f"{found_total} INC recuperados, {cached_final_count} reutilizados de histórico finalista, "
        f"{missing_total} sin resultado, {error_count} lotes con error."
    )
    return issues_doc, {
        "state": state,
        "summary": summary,
        "countries": len(pending_by_country),
        "inc_total": sum(len(v) for v in pending_by_country.values()),
        "total_batches": int(total_batches),
        "success_count": int(batch_success_count),
        "total_sources": int(total_batches),
        "found_count": int(found_total),
        "cached_final_count": int(cached_final_count),
        "missing_count": int(missing_total),
        "error_count": int(error_count),
        "messages": messages,
    }


def run_finalist_lookup_ingest(
    settings: Settings,
    *,
    selected_sources: List[Dict[str, str]],
    on_source_result: SourceProgressCallback | None = None,
    on_source_start: SourceStartCallback | None = None,
    on_message: MessageCallback | None = None,
) -> dict[str, Any]:
    issues_doc = load_issues_doc(settings.DATA_PATH)
    _, result = _run_finalist_status_lookup(
        settings,
        selected_sources=list(selected_sources or []),
        issues_doc=issues_doc,
        on_source_result=on_source_result,
        on_source_start=on_source_start,
        on_message=on_message,
    )
    normalized = dict(result or {})
    normalized["success_count"] = int(normalized.get("success_count") or 0)
    normalized["total_sources"] = int(normalized.get("total_sources") or 0)
    return normalized


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

    state = (
        "success"
        if success_count == total_sources and total_sources > 0
        else ("partial" if success_count > 0 else "error")
    )
    return {
        "state": state,
        "summary": f"Reingesta Jira finalizada: {success_count}/{total_sources} fuentes OK.",
        "success_count": int(success_count),
        "total_sources": int(total_sources),
        "messages": messages,
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
            merged_helix = merge_helix_items(merged_helix, new_helix_doc.items)
            issues_doc = merge_issues(
                issues_doc, [helix_item_to_issue(item) for item in new_helix_doc.items]
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
