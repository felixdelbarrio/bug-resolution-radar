"""Shared issue dataframe helpers for backend logic."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from bug_resolution_radar.analytics.status_semantics import effective_closed_mask


def open_issues_only(df: pd.DataFrame | None) -> pd.DataFrame:
    """Return only open issues using unified closure semantics."""
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    if df.empty:
        return df.copy(deep=False)
    closed_mask = effective_closed_mask(df)
    return df.loc[~closed_mask].copy(deep=False)


def normalize_text_col(series: pd.Series | None, empty_label: str) -> pd.Series:
    """Normalize a text-like column: replace NaN/empty strings with a label."""
    if series is None:
        return pd.Series([], dtype=str)
    return series.fillna(empty_label).astype(str).replace("", empty_label)


def priority_rank(priority: Optional[str]) -> int:
    """Rank priority strings in a stable Jira-friendly order."""
    token = str(priority or "").strip().lower()
    compact = "".join(ch for ch in token if ch.isalnum())
    if token == "p0" or "highest" in token or compact in {"suponeunimpedimento", "impedimento"}:
        return 0
    if token == "p1" or "high" in token:
        return 1
    if token == "p2" or "medium" in token:
        return 2
    if token == "p3" or "low" in token:
        return 3
    if token == "p4" or "lowest" in token:
        return 4
    return 99


def _normalize_status_token(value: object) -> str:
    token = str(value or "").strip().lower()
    token = token.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", token).strip()


def status_progress_rank(status: Optional[str]) -> int:
    """Rank statuses from most finalist to least finalist (New last)."""
    token = _normalize_status_token(status)
    if not token:
        return 99
    ranked_patterns: tuple[tuple[str, ...], ...] = (
        ("accepted",),
        ("ready to deploy",),
        ("deployed",),
        ("ready to verify",),
        ("test",),
        ("to rework", "rework"),
        ("en progreso", "in progress"),
        ("blocked", "bloque"),
        ("ready",),
        ("analysing", "analyzing", "analizando", "analisis"),
        ("new", "nuevo"),
    )
    for rank, patterns in enumerate(ranked_patterns):
        if any(pattern in token for pattern in patterns):
            return rank
    return 98


def sort_issues_for_display(
    df: pd.DataFrame | None,
    *,
    priority_col: str = "priority",
    status_col: str = "status",
    updated_col: str = "updated",
    created_col: str = "created",
    key_col: str = "key",
) -> pd.DataFrame:
    """Sort issues using unified UX order: priority, finalist->new, recency, key."""
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    safe = df.copy(deep=False)
    if safe.empty:
        return safe

    sort_cols: list[str] = []
    ascending: list[bool] = []

    if priority_col in safe.columns:
        safe["__prio_rank"] = safe[priority_col].map(priority_rank)
        sort_cols.append("__prio_rank")
        ascending.append(True)
    if status_col in safe.columns:
        safe["__status_rank"] = safe[status_col].map(status_progress_rank)
        sort_cols.append("__status_rank")
        ascending.append(True)
    if updated_col in safe.columns:
        safe["__updated_sort"] = pd.to_datetime(safe[updated_col], errors="coerce", utc=True)
        sort_cols.append("__updated_sort")
        ascending.append(False)
    if created_col in safe.columns:
        safe["__created_sort"] = pd.to_datetime(safe[created_col], errors="coerce", utc=True)
        sort_cols.append("__created_sort")
        ascending.append(False)
    if key_col in safe.columns:
        sort_cols.append(key_col)
        ascending.append(True)

    if not sort_cols:
        return safe
    return safe.sort_values(
        by=sort_cols,
        ascending=ascending,
        kind="mergesort",
        na_position="last",
    )
