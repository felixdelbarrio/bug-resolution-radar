from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from bug_resolution_radar.schema import IssuesDocument

# ----------------------------
# Persistence: IssuesDocument
# ----------------------------


@lru_cache(maxsize=8)
def _load_issues_doc_cached(path: str, mtime_ns: int) -> IssuesDocument:
    del mtime_ns  # cache invalidation key only
    p = Path(path)
    if not p.exists():
        return IssuesDocument.empty()
    return IssuesDocument.model_validate_json(p.read_text(encoding="utf-8"))


def load_issues_doc(path: str) -> IssuesDocument:
    """Load IssuesDocument from JSON file.

    If the file doesn't exist, returns an empty document.
    """
    p = Path(path)
    mtime_ns = p.stat().st_mtime_ns if p.exists() else -1
    # Return a defensive copy to avoid mutable state leaks across callers.
    return _load_issues_doc_cached(str(p.resolve()), mtime_ns).model_copy(deep=True)


def save_issues_doc(path: str, doc: IssuesDocument) -> None:
    """Save IssuesDocument to JSON file (UTF-8, pretty printed)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")


# ----------------------------
# DataFrame helpers
# ----------------------------


def _issues_to_dataframe(doc: IssuesDocument) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = [i.model_dump() for i in doc.issues]
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for col in ["created", "updated", "resolved"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


@lru_cache(maxsize=8)
def _load_issues_df_cached(path: str, mtime_ns: int) -> pd.DataFrame:
    doc = _load_issues_doc_cached(path, mtime_ns)
    return _issues_to_dataframe(doc)


def load_issues_df(path: str) -> pd.DataFrame:
    """Load issues JSON as DataFrame with mtime-based cache invalidation.

    Streamlit reruns frequently (filters, tabs, widgets). Caching avoids
    repeating expensive model->rows->DataFrame conversion on each rerun.
    """
    p = Path(path)
    mtime_ns = p.stat().st_mtime_ns if p.exists() else -1
    # Defensive copy to avoid accidental mutation of cached base dataframe.
    return _load_issues_df_cached(str(p.resolve()), mtime_ns).copy(deep=True)


def df_from_issues_doc(doc: IssuesDocument) -> pd.DataFrame:
    """Convert IssuesDocument into a pandas DataFrame.

    Ensures datetime columns are parsed as UTC timestamps when present.
    """
    return _issues_to_dataframe(doc)


def open_issues_only(df: pd.DataFrame | None) -> pd.DataFrame:
    """Return only open issues (`resolved` is null), or a safe empty DataFrame."""
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    if df.empty:
        return df.copy()
    if "resolved" in df.columns:
        return df[df["resolved"].isna()].copy()
    return df.copy()


def normalize_text_col(series: pd.Series, empty_label: str) -> pd.Series:
    """Normalize a text-like column: replace NaN/empty strings with a label."""
    if series is None:
        return pd.Series([], dtype=str)
    return series.fillna(empty_label).astype(str).replace("", empty_label)


# ----------------------------
# Priority helpers
# ----------------------------


def priority_rank(p: Optional[str]) -> int:
    """Rank priority strings in a stable Jira-friendly order.

    Lower rank = higher priority.

    Known Jira names handled:
      Highest, High, Medium, Low, Lowest
    Everything else gets rank 99.
    """
    order = ["highest", "high", "medium", "low", "lowest"]
    pl = (p or "").strip().lower()
    if pl in order:
        return order.index(pl)
    return 99


def priority_color_map() -> Dict[str, str]:
    """Discrete color map used in charts (traffic-light-ish palette)."""
    return {
        "Highest": "#FF5252",
        "High": "#FFB56B",
        "Medium": "#FFE761",
        "Low": "#88E783",
        "Lowest": "#9CE67E",
        "(sin priority)": "#E2E6EE",
        "": "#E2E6EE",
    }
