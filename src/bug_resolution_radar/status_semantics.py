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

CORE_FINAL_STATUS_TOKENS: Final[tuple[str, ...]] = (
    "accepted",
    "ready to deploy",
    "deployed",
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


def is_core_final_status(value: object) -> bool:
    """Return True for the main pipeline end-states we use across the product.

    Note: we intentionally keep this narrower than FINALIST_STATUS_TOKENS so that
    "cancelled/done/closed" don't silently become "final" in metrics unless they
    also have an explicit resolved timestamp.
    """
    token = _normalize_status_token(value)
    if not token:
        return False
    return any(part in token for part in CORE_FINAL_STATUS_TOKENS)


def _to_dt_naive_utc(value: pd.Series) -> pd.Series:
    """Coerce to datetime and strip timezone (UTC->naive)."""
    if value is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(value, utc=True, errors="coerce")
    try:
        # tz-aware -> naive in local (UTC) timeline
        out = out.dt.tz_convert(None)
    except Exception:
        try:
            out = out.dt.tz_localize(None)
        except Exception:
            pass
    return out


def effective_finalized_at(
    df: pd.DataFrame,
    *,
    created_col: str = "created",
    updated_col: str = "updated",
    resolved_col: str = "resolved",
    status_col: str = "status",
) -> pd.Series:
    """Return an effective 'finalized at' timestamp for issues.

    We consider an issue finalized when:
    - it has a non-null resolved timestamp, OR
    - its current status is one of the core final states (Accepted / Ready to deploy / Deployed).

    Timestamp selection priority:
    1) resolved (most precise for closure)
    2) updated (proxy for reaching the final state)
    3) created (last-resort to avoid dropping rows when status is final but dates are sparse)
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.Series([], dtype="datetime64[ns]")
    if created_col not in df.columns:
        return pd.Series([pd.NaT] * len(df), index=df.index, dtype="datetime64[ns]")

    created = _to_dt_naive_utc(df[created_col])
    resolved = (
        _to_dt_naive_utc(df[resolved_col])
        if resolved_col in df.columns
        else pd.Series([pd.NaT] * len(df), index=df.index, dtype="datetime64[ns]")
    )
    updated = (
        _to_dt_naive_utc(df[updated_col])
        if updated_col in df.columns
        else pd.Series([pd.NaT] * len(df), index=df.index, dtype="datetime64[ns]")
    )

    core_final = (
        df[status_col].map(is_core_final_status).fillna(False).astype(bool)
        if status_col in df.columns
        else pd.Series(False, index=df.index)
    )
    closed_for_metric = resolved.notna() | core_final

    finalized = resolved.copy()
    # If it's in a core final state but lacks resolved, use updated/created as best-effort proxy.
    missing = finalized.isna() & core_final
    if missing.any():
        finalized.loc[missing] = updated.loc[missing]
    missing = finalized.isna() & core_final
    if missing.any():
        finalized.loc[missing] = created.loc[missing]

    return finalized.where(closed_for_metric)


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
