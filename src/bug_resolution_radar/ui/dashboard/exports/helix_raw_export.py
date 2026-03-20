"""Helix Excel export helpers focused on the raw ARSQL payload.

The generated workbook contains a single sheet: `Helix Raw`.
No "official" mapped sheet is produced.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

import pandas as pd

from bug_resolution_radar.models.schema_helix import HelixWorkItem


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
        raw_row: dict[str, Any] = {str(k): _coerce_export_scalar(v) for k, v in raw_fields.items()}
        raw_row["ID de la Incidencia"] = str(issue_row.get("key") or item.id or "").strip()
        raw_row["__item_url__"] = str(item.url or issue_row.get("url") or "").strip()
        raw_rows.append(raw_row)

    if not raw_rows:
        return None

    raw_df = pd.DataFrame(raw_rows)
    front = [c for c in ("ID de la Incidencia", "__item_url__") if c in raw_df.columns]
    rest = [c for c in raw_df.columns if c not in front]
    return raw_df[front + rest].copy()
