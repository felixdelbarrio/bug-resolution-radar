"""Shared merge and mapping helpers for ingestion snapshots."""

from __future__ import annotations

from collections.abc import Sequence

from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem

_CLOSED_STATUS_TOKENS = frozenset(
    {
        "closed",
        "resolved",
        "done",
        "deployed",
        "accepted",
        "cancelled",
        "canceled",
    }
)


def issue_merge_key(issue: NormalizedIssue) -> str:
    sid = str(issue.source_id or "").strip().lower()
    key = str(issue.key or "").strip().upper()
    return f"{sid}::{key}" if sid else key


def merge_issues(
    doc: IssuesDocument,
    incoming: Sequence[NormalizedIssue],
) -> IssuesDocument:
    if not incoming:
        return doc
    merged = {issue_merge_key(issue): issue for issue in doc.issues}
    for issue in incoming:
        merged[issue_merge_key(issue)] = issue
    doc.issues = list(merged.values())
    return doc


def helix_merge_key(item: HelixWorkItem) -> str:
    sid = str(item.source_id or "").strip().lower()
    item_id = str(item.id or "").strip().upper()
    return f"{sid}::{item_id}" if sid else item_id


def merge_helix_items(
    doc: HelixDocument,
    incoming: Sequence[HelixWorkItem],
) -> HelixDocument:
    if not incoming:
        return doc
    merged = {helix_merge_key(item): item for item in doc.items}
    for item in incoming:
        merged[helix_merge_key(item)] = item
    doc.items = list(merged.values())
    return doc


def is_closed_status(value: str) -> bool:
    return str(value or "").strip().lower() in _CLOSED_STATUS_TOKENS


def helix_item_to_issue(item: HelixWorkItem) -> NormalizedIssue:
    status = str(item.status or "").strip() or "Open"
    created = (
        str(item.start_datetime or item.target_date or item.last_modified or "").strip() or None
    )
    updated = (
        str(item.last_modified or item.closed_date or item.start_datetime or "").strip() or None
    )
    closed_date = str(item.closed_date or "").strip() or None
    resolved = closed_date or (updated if is_closed_status(status) else None)
    label = (
        f"{str(item.matrix_service_n1 or '').strip()} {str(item.source_service_n1 or '').strip()}"
    ).strip()
    impacted = str(item.impacted_service or item.service or "").strip()
    components = [impacted] if impacted else []
    return NormalizedIssue(
        key=str(item.id or "").strip(),
        summary=str(item.summary or "").strip(),
        description=str(item.description or "").strip(),
        helix_executive_description=str(item.executive_description or "").strip(),
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
        helix_lookup_kind=str(item.helix_lookup_kind or "").strip(),
    )
