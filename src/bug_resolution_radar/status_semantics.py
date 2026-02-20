"""Shared status semantics helpers for open/closed partitioning."""

from __future__ import annotations

import re
from typing import Final

import pandas as pd

FINALIST_STATUS_TOKENS: Final[tuple[str, ...]] = (
    "accepted",
    "ready to deploy",
    "deployed",
    "closed",
    "resolved",
    "done",
    "cancelled",
    "canceled",
)


def _normalize_status_token(value: object) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    token = token.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", token).strip()


def is_finalist_status(value: object) -> bool:
    token = _normalize_status_token(value)
    if not token:
        return False
    return any(part in token for part in FINALIST_STATUS_TOKENS)


def effective_closed_mask(
    df: pd.DataFrame,
    *,
    resolved_col: str = "resolved",
    status_col: str = "status",
) -> pd.Series:
    """Return mask where an issue is considered closed.

    A row is closed when:
    - it has a non-null resolved timestamp, or
    - its status is finalist (Accepted/Ready to deploy/Deployed/etc).
    """
    if not isinstance(df, pd.DataFrame):
        return pd.Series(dtype=bool)
    if df.empty:
        return pd.Series(False, index=df.index)

    resolved_closed = pd.Series(False, index=df.index)
    if resolved_col in df.columns:
        resolved_closed = pd.to_datetime(df[resolved_col], utc=True, errors="coerce").notna()

    status_closed = pd.Series(False, index=df.index)
    if status_col in df.columns:
        status_closed = df[status_col].map(is_finalist_status).fillna(False).astype(bool)

    return resolved_closed | status_closed
