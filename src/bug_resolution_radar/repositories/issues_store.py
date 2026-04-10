"""Persistence helpers for the normalized issues document."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from bug_resolution_radar.models.schema import IssuesDocument


@lru_cache(maxsize=8)
def _load_issues_doc_cached(path: str, mtime_ns: int) -> IssuesDocument:
    del mtime_ns  # cache invalidation key only
    resolved = Path(path)
    if not resolved.exists():
        return IssuesDocument.empty()
    try:
        return IssuesDocument.model_validate_json(resolved.read_text(encoding="utf-8"))
    except Exception:
        return IssuesDocument.empty()


def load_issues_doc(path: str) -> IssuesDocument:
    """Load `IssuesDocument` from JSON file or return an empty document."""
    resolved = Path(path)
    mtime_ns = resolved.stat().st_mtime_ns if resolved.exists() else -1
    return _load_issues_doc_cached(str(resolved.resolve()), mtime_ns).model_copy(deep=True)


def save_issues_doc(path: str, doc: IssuesDocument) -> None:
    """Save `IssuesDocument` to JSON file (UTF-8, pretty printed)."""
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(doc.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_datetime_utc_mixed(series: pd.Series) -> pd.Series:
    """Parse mixed Jira/Helix datetime strings into UTC timestamps."""
    try:
        return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(series, utc=True, errors="coerce")


def _issues_to_dataframe(doc: IssuesDocument) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = [issue.model_dump() for issue in doc.issues]
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for column in ["created", "updated", "resolved"]:
        if column in df.columns:
            df[column] = _parse_datetime_utc_mixed(df[column])
    return df


@lru_cache(maxsize=8)
def _load_issues_df_cached(path: str, mtime_ns: int) -> pd.DataFrame:
    doc = _load_issues_doc_cached(path, mtime_ns)
    return _issues_to_dataframe(doc)


def load_issues_df(path: str) -> pd.DataFrame:
    """Load issues JSON as DataFrame with mtime-based cache invalidation."""
    resolved = Path(path)
    mtime_ns = resolved.stat().st_mtime_ns if resolved.exists() else -1
    return _load_issues_df_cached(str(resolved.resolve()), mtime_ns).copy(deep=False)


def df_from_issues_doc(doc: IssuesDocument) -> pd.DataFrame:
    """Convert `IssuesDocument` into a pandas DataFrame."""
    return _issues_to_dataframe(doc)
