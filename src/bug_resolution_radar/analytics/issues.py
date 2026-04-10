"""Shared issue dataframe helpers for backend logic."""

from __future__ import annotations

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
    order = ["highest", "high", "medium", "low", "lowest"]
    token = str(priority or "").strip().lower()
    if token in order:
        return order.index(token)
    return 99
