from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from bug_resolution_radar.schema import IssuesDocument


# ----------------------------
# Persistence: IssuesDocument
# ----------------------------


def load_issues_doc(path: str) -> IssuesDocument:
    """Load IssuesDocument from JSON file.

    If the file doesn't exist, returns an empty document.
    """
    p = Path(path)
    if not p.exists():
        return IssuesDocument.empty()
    return IssuesDocument.model_validate_json(p.read_text(encoding="utf-8"))


def save_issues_doc(path: str, doc: IssuesDocument) -> None:
    """Save IssuesDocument to JSON file (UTF-8, pretty printed)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")


# ----------------------------
# DataFrame helpers
# ----------------------------


def df_from_issues_doc(doc: IssuesDocument) -> pd.DataFrame:
    """Convert IssuesDocument into a pandas DataFrame.

    Ensures datetime columns are parsed as UTC timestamps when present.
    """
    rows: List[Dict[str, Any]] = [i.model_dump() for i in doc.issues]
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    for col in ["created", "updated", "resolved"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


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