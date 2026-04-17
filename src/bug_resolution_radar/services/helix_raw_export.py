"""Helix raw export helpers shared by API and legacy UI surfaces."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import pandas as pd

from bug_resolution_radar.models.schema_helix import HelixWorkItem

_HELIX_FRONT_EXPORT_FIELDS: tuple[str, ...] = (
    "id",
    "priority",
    "summary",
    "status",
    "assignee",
    "incidentType",
    "service",
    "customerName",
    "bbva_matrixservicen1",
    "bbva_sourceservicen1",
    "bbva_startdatetime",
    "bbva_closeddate",
    "lastModifiedDate",
    "targetDate",
    "workItemId",
)


def _jsonable_text(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _coerce_export_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return ""
        return value.tz_convert("UTC").isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc).isoformat()
            if value.tzinfo is not None
            else value.isoformat()
        )
    return _jsonable_text(value)


def _preferred_issue_value(
    issue_row: Mapping[str, Any], item: HelixWorkItem, *candidates: str, fallback: Any = ""
) -> Any:
    for candidate in candidates:
        if candidate in issue_row:
            value = issue_row.get(candidate)
            if value not in (None, ""):
                return value
    if fallback not in (None, ""):
        return fallback
    return ""


def _front_export_fields(issue_row: Mapping[str, Any], item: HelixWorkItem) -> dict[str, Any]:
    raw_fields = item.raw_fields if isinstance(item.raw_fields, Mapping) else {}
    work_item_id = (
        raw_fields.get("workItemId")
        or raw_fields.get("workItemID")
        or raw_fields.get("InstanceId")
        or raw_fields.get("instanceId")
        or ""
    )
    return {
        "id": _preferred_issue_value(issue_row, item, "id", "key", fallback=item.id),
        "priority": _preferred_issue_value(issue_row, item, "priority", fallback=item.priority),
        "summary": _preferred_issue_value(issue_row, item, "summary", fallback=item.summary),
        "status": _preferred_issue_value(issue_row, item, "status", fallback=item.status),
        "assignee": _preferred_issue_value(issue_row, item, "assignee", fallback=item.assignee),
        "incidentType": _preferred_issue_value(
            issue_row,
            item,
            "incidentType",
            fallback=item.incident_type or raw_fields.get("incidentType") or "",
        ),
        "service": _preferred_issue_value(issue_row, item, "service", fallback=item.service),
        "customerName": _preferred_issue_value(
            issue_row,
            item,
            "customerName",
            fallback=item.customer_name or raw_fields.get("customerName") or "",
        ),
        "bbva_matrixservicen1": _preferred_issue_value(
            issue_row,
            item,
            "bbva_matrixservicen1",
            fallback=item.matrix_service_n1 or raw_fields.get("bbva_matrixservicen1") or "",
        ),
        "bbva_sourceservicen1": _preferred_issue_value(
            issue_row,
            item,
            "bbva_sourceservicen1",
            fallback=item.source_service_n1 or raw_fields.get("bbva_sourceservicen1") or "",
        ),
        "bbva_startdatetime": _preferred_issue_value(
            issue_row,
            item,
            "bbva_startdatetime",
            fallback=item.start_datetime or raw_fields.get("bbva_startdatetime") or "",
        ),
        "bbva_closeddate": _preferred_issue_value(
            issue_row,
            item,
            "bbva_closeddate",
            fallback=item.closed_date or raw_fields.get("bbva_closeddate") or "",
        ),
        "lastModifiedDate": _preferred_issue_value(
            issue_row,
            item,
            "lastModifiedDate",
            fallback=item.last_modified or raw_fields.get("lastModifiedDate") or "",
        ),
        "targetDate": _preferred_issue_value(
            issue_row,
            item,
            "targetDate",
            fallback=item.target_date or raw_fields.get("targetDate") or "",
        ),
        "workItemId": _preferred_issue_value(
            issue_row,
            item,
            "workItemId",
            fallback=work_item_id,
        ),
    }


def build_helix_raw_export_frame(
    filtered_issues_df: pd.DataFrame,
    *,
    helix_items_by_merge_key: Mapping[str, HelixWorkItem],
) -> Optional[pd.DataFrame]:
    """Build a raw Helix sheet for the filtered scope.

    Returns None when input is empty, mixed-source, or no matching Helix items are found.
    """
    if filtered_issues_df is None or filtered_issues_df.empty:
        return None
    if "source_type" not in filtered_issues_df.columns or "key" not in filtered_issues_df.columns:
        return None

    src_types = (
        filtered_issues_df["source_type"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .unique()
        .tolist()
    )
    src_types = [s for s in src_types if s]
    if not src_types or any(s != "helix" for s in src_types):
        return None

    issue_columns = list(filtered_issues_df.columns)
    raw_rows: list[dict[str, Any]] = []

    for row_values in filtered_issues_df.itertuples(index=False, name=None):
        issue_row = dict(zip(issue_columns, row_values))
        source_id = str(issue_row.get("source_id") or "").strip().lower()
        key = str(issue_row.get("key") or "").strip().upper()
        if not key:
            continue
        merge_key = f"{source_id}::{key}" if source_id else key
        item = helix_items_by_merge_key.get(merge_key) or helix_items_by_merge_key.get(key)
        if item is None:
            continue

        raw_fields = item.raw_fields or {}
        raw_row: dict[str, Any] = {
            "ID de la Incidencia": str(issue_row.get("key") or item.id or "").strip()
        }
        raw_row.update(
            {
                column: _coerce_export_scalar(value)
                for column, value in _front_export_fields(issue_row, item).items()
            }
        )
        raw_row["__item_url__"] = str(item.url or issue_row.get("url") or "").strip()
        for key, value in raw_fields.items():
            normalized_key = str(key)
            if normalized_key in raw_row:
                continue
            raw_row[normalized_key] = _coerce_export_scalar(value)
        raw_rows.append(raw_row)

    if not raw_rows:
        return None

    raw_df = pd.DataFrame(raw_rows)
    front = [
        c
        for c in ("ID de la Incidencia", *_HELIX_FRONT_EXPORT_FIELDS, "__item_url__")
        if c in raw_df.columns
    ]
    rest = [c for c in raw_df.columns if c not in front]
    return raw_df[front + rest].copy()
