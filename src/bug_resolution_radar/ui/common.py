"""Common data normalization and color mapping helpers for the UI layer."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

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
    try:
        return IssuesDocument.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        # Robust fallback: avoid crashing the UI when the file is temporarily malformed.
        return IssuesDocument.empty()


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
    # Shallow copy avoids mutating cached structure while reducing rerun memory churn.
    return _load_issues_df_cached(str(p.resolve()), mtime_ns).copy(deep=False)


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
        return df.copy(deep=False)
    if "resolved" in df.columns:
        return df[df["resolved"].isna()].copy(deep=False)
    return df.copy(deep=False)


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


def _normalize_token(value: Optional[str]) -> str:
    txt = (value or "").strip().lower()
    txt = txt.replace("_", " ").replace("-", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


_RED_1 = "#B4232A"
_RED_2 = "#D64550"
_RED_3 = "#E85D63"
_ORANGE_1 = "#D97706"
_ORANGE_2 = "#F59E0B"
_YELLOW_1 = "#FBBF24"
_GREEN_1 = "#15803D"
_GREEN_2 = "#22A447"
_GREEN_3 = "#4CAF50"
_NEUTRAL = "#E2E6EE"


_STATUS_COLOR_BY_KEY: Dict[str, str] = {
    "new": _RED_3,
    "analysing": _RED_2,
    "blocked": _RED_1,
    "en progreso": _ORANGE_2,
    "in progress": _ORANGE_2,
    "to rework": _ORANGE_1,
    "rework": _ORANGE_1,
    "test": _YELLOW_1,
    "ready to verify": _ORANGE_2,
    "accepted": _GREEN_3,
    "ready to deploy": _GREEN_2,
    "deployed": _GREEN_1,
    "closed": _GREEN_1,
    "resolved": _GREEN_1,
    "done": _GREEN_1,
    "open": _YELLOW_1,
    "created": _RED_3,
}

_PRIORITY_COLOR_BY_KEY: Dict[str, str] = {
    "supone un impedimento": _RED_1,
    "highest": _RED_1,
    "high": _RED_2,
    "medium": _ORANGE_2,
    "low": _GREEN_2,
    "lowest": _GREEN_1,
}


def status_color(status: Optional[str]) -> str:
    return _STATUS_COLOR_BY_KEY.get(_normalize_token(status), _NEUTRAL)


def priority_color(priority: Optional[str]) -> str:
    return _PRIORITY_COLOR_BY_KEY.get(_normalize_token(priority), _NEUTRAL)


def status_color_map(statuses: Optional[Iterable[str]] = None) -> Dict[str, str]:
    if statuses is None:
        return {}
    return {str(s): status_color(str(s)) for s in statuses}


def flow_signal_color_map() -> Dict[str, str]:
    return {
        "created": _RED_3,
        "closed": _GREEN_2,
        "resolved": _GREEN_2,
        "open": _YELLOW_1,
        "open_backlog_proxy": _YELLOW_1,
    }


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return f"rgba(127,146,178,{alpha:.3f})"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3f})"


def chip_style_from_color(hex_color: str) -> str:
    border = _hex_to_rgba(hex_color, 0.62)
    bg = _hex_to_rgba(hex_color, 0.16)
    return (
        f"color:{hex_color}; border:1px solid {border}; background:{bg}; "
        "border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.80rem;"
    )


def priority_color_map() -> Dict[str, str]:
    """Discrete color map used in charts with semantic traffic-light palette."""
    return {
        "Supone un impedimento": _RED_1,
        "Highest": _RED_1,
        "High": _RED_2,
        "Medium": _ORANGE_2,
        "Low": _GREEN_2,
        "Lowest": _GREEN_1,
        "(sin priority)": _NEUTRAL,
        "": _NEUTRAL,
    }
