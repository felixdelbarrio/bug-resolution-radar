"""Synchronous ingestion orchestration for API-triggered actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List

from bug_resolution_radar.common.utils import now_iso
from bug_resolution_radar.config import Settings
from bug_resolution_radar.ingest.helix_ingest import ingest_helix
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.issues_store import load_issues_doc, save_issues_doc

SourceProgressCallback = Callable[[bool, str, int, int], None]


def _get_helix_path(settings: Settings) -> str:
    path = str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip()
    return path or "data/helix.json"


def _issue_merge_key(issue: NormalizedIssue) -> str:
    sid = str(issue.source_id or "").strip().lower()
    key = str(issue.key or "").strip().upper()
    return f"{sid}::{key}" if sid else key


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


def run_jira_ingest(
    settings: Settings,
    *,
    selected_sources: List[Dict[str, str]],
    on_source_result: SourceProgressCallback | None = None,
) -> dict[str, Any]:
    work_doc = load_issues_doc(settings.DATA_PATH)
    messages: list[dict[str, Any]] = []
    success_count = 0
    total_sources = len(list(selected_sources or []))
    completed_sources = 0
    for src in list(selected_sources or []):
        ok, msg, new_doc = ingest_jira(
            settings=settings, dry_run=False, existing_doc=work_doc, source=src
        )
        if ok and new_doc is not None:
            work_doc = new_doc
            success_count += 1
        source_message = str(msg or "").strip()
        messages.append({"ok": bool(ok), "message": source_message})
        completed_sources += 1
        if on_source_result is not None:
            on_source_result(bool(ok), source_message, int(completed_sources), int(total_sources))

    if success_count > 0:
        save_issues_doc(settings.DATA_PATH, work_doc)

    return {
        "state": "success"
        if success_count == total_sources and total_sources > 0
        else ("partial" if success_count > 0 else "error"),
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
    total_sources = len(list(selected_sources or []))
    completed_sources = 0
    for src in list(selected_sources or []):
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
        if new_helix_doc is not None and new_helix_doc.items:
            has_partial_updates = True
            merged_helix = _merge_helix_items(merged_helix, new_helix_doc.items)
            merged_helix.ingested_at = new_helix_doc.ingested_at
            merged_helix.helix_base_url = new_helix_doc.helix_base_url
            merged_helix.query = "multi-source"
            issues_doc = _merge_issues(
                issues_doc, [_helix_item_to_issue(item) for item in new_helix_doc.items]
            )
        if ok:
            success_count += 1
        source_message = str(msg or "").strip()
        messages.append({"ok": bool(ok), "message": source_message})
        completed_sources += 1
        if on_source_result is not None:
            on_source_result(bool(ok), source_message, int(completed_sources), int(total_sources))

    if success_count > 0 or has_partial_updates:
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
