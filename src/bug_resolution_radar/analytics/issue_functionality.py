"""Centralized issue functionality classification helpers."""

from __future__ import annotations

from typing import Iterable

import pandas as pd

from bug_resolution_radar.analytics.insights import classify_theme

FUNCTIONALITY_COL = "functionality"
HELIX_EXECUTIVE_DESCRIPTION_COL = "helix_executive_description"


def _text(value: object) -> str:
    return str(value or "").strip()


def _series_text(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype=str)
    return df[column].fillna("").astype(str).str.strip()


def _classification_text(row: pd.Series) -> str:
    parts: Iterable[str] = (
        _text(row.get("summary", "")),
        _text(row.get(HELIX_EXECUTIVE_DESCRIPTION_COL, "")),
    )
    return " ".join(part for part in parts if part)


def classify_issue_functionality(row: pd.Series) -> str:
    """Classify an issue row into the shared functionality/theme bucket."""
    return classify_theme(_classification_text(row))


def ensure_issue_functionality_columns(
    df: pd.DataFrame | None,
    *,
    functionality_col: str = FUNCTIONALITY_COL,
    theme_col: str | None = None,
) -> pd.DataFrame:
    """Return a frame with shared functionality columns used by UI and Insights."""
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    if df.empty:
        return df.copy(deep=False)

    work = df.copy(deep=False)
    if HELIX_EXECUTIVE_DESCRIPTION_COL not in work.columns:
        work[HELIX_EXECUTIVE_DESCRIPTION_COL] = ""
    else:
        work[HELIX_EXECUTIVE_DESCRIPTION_COL] = _series_text(
            work,
            HELIX_EXECUTIVE_DESCRIPTION_COL,
        ).to_numpy(copy=False)

    target_col = str(theme_col or functionality_col or FUNCTIONALITY_COL).strip()
    if target_col and target_col in work.columns:
        existing = _series_text(work, target_col)
        if existing.ne("").all():
            if functionality_col and functionality_col not in work.columns:
                work[functionality_col] = existing.to_numpy(copy=False)
            return work

    functionality = work.apply(classify_issue_functionality, axis=1)
    if functionality_col:
        work[functionality_col] = functionality.to_numpy(copy=False)
    if theme_col and theme_col != functionality_col:
        work[theme_col] = functionality.to_numpy(copy=False)
    return work
