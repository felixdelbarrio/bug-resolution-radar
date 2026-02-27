"""Helpers to enforce a global analysis-depth window over backlog data."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd

from bug_resolution_radar.config import Settings


def _utc_timestamp(value: datetime | None = None) -> pd.Timestamp:
    ts = pd.Timestamp(value or datetime.now(timezone.utc))
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def parse_analysis_lookback_days(settings: Settings) -> int:
    """Return configured lookback in days (0 means auto/max)."""
    raw = getattr(settings, "ANALYSIS_LOOKBACK_DAYS", 0)
    try:
        value = int(str(raw).strip())
    except Exception:
        return 0
    return max(0, value)


def parse_analysis_lookback_months(settings: Settings) -> int:
    """Return configured lookback in months (0 means auto/max)."""
    raw = getattr(settings, "ANALYSIS_LOOKBACK_MONTHS", 0)
    try:
        value = int(str(raw).strip())
    except Exception:
        return 0
    return max(0, value)


def max_available_backlog_days(df: pd.DataFrame, *, now: datetime | None = None) -> int:
    """Return max age in days from oldest `created` row to `now` (at least 1)."""
    if df is None or df.empty or "created" not in df.columns:
        return 1

    created = pd.to_datetime(df["created"], utc=True, errors="coerce").dropna()
    if created.empty:
        return 1

    current = _utc_timestamp(now)
    oldest = created.min()
    delta_sec = max((current - oldest).total_seconds(), 0.0)
    return max(1, int(math.ceil(delta_sec / 86400.0)))


def max_available_backlog_months(df: pd.DataFrame, *, now: datetime | None = None) -> int:
    """Return max age in months (ceil) from oldest `created` to `now` (at least 1)."""
    days = max_available_backlog_days(df, now=now)
    return max(1, int(math.ceil(float(days) / 30.0)))


def effective_analysis_lookback_months(
    settings: Settings,
    *,
    df: pd.DataFrame,
    now: datetime | None = None,
) -> int:
    """Resolve configured monthly lookback, clamped to available backlog window."""
    available = max_available_backlog_months(df, now=now)
    configured_months = parse_analysis_lookback_months(settings)
    if configured_months > 0:
        return max(1, min(configured_months, available))

    # Legacy fallback for environments that still only have days configured.
    configured_days = parse_analysis_lookback_days(settings)
    if configured_days > 0:
        from_days = max(1, int(math.ceil(float(configured_days) / 30.0)))
        return max(1, min(from_days, available))

    return available


def effective_analysis_lookback_days(
    settings: Settings,
    *,
    df: pd.DataFrame,
    now: datetime | None = None,
) -> int:
    """Compatibility helper: convert effective monthly lookback to days."""
    return int(effective_analysis_lookback_months(settings, df=df, now=now) * 30)


def apply_analysis_depth_filter(
    df: pd.DataFrame,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Filter dataset by configured analysis depth (monthly window)."""
    if df is None or df.empty or "created" not in df.columns:
        return pd.DataFrame() if df is None else df.copy(deep=False)

    created = pd.to_datetime(df["created"], utc=True, errors="coerce")
    has_created = created.notna()
    if not has_created.any():
        return df.loc[has_created].copy(deep=False)

    lookback_months = effective_analysis_lookback_months(settings, df=df, now=now)
    available_months = max_available_backlog_months(df, now=now)
    if lookback_months >= available_months:
        return df.loc[has_created].copy(deep=False)

    current = _utc_timestamp(now)
    cutoff = current - pd.DateOffset(months=int(lookback_months))
    mask = has_created & (created >= cutoff)
    return df.loc[mask].copy(deep=False)
