from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from bug_resolution_radar.analytics.analysis_window import (
    apply_analysis_depth_filter,
    effective_analysis_lookback_months,
    max_available_backlog_days,
    max_available_backlog_months,
)
from bug_resolution_radar.config import Settings


def test_max_available_backlog_days_uses_oldest_created() -> None:
    now = datetime(2026, 2, 20, tzinfo=timezone.utc)
    df = pd.DataFrame(
        {
            "created": [
                now - timedelta(days=1),
                now - timedelta(days=10, hours=1),
            ]
        }
    )

    assert max_available_backlog_days(df, now=now) == 11


def test_effective_analysis_lookback_months_defaults_to_12_then_clamps() -> None:
    now = datetime(2026, 2, 20, tzinfo=timezone.utc)
    df = pd.DataFrame({"created": [now - timedelta(days=7), now - timedelta(days=30)]})
    settings = Settings(ANALYSIS_LOOKBACK_MONTHS=0)

    assert effective_analysis_lookback_months(settings, df=df, now=now) == 1


def test_max_available_backlog_months_is_ceiled() -> None:
    now = datetime(2026, 2, 20, tzinfo=timezone.utc)
    df = pd.DataFrame({"created": [now - timedelta(days=61)]})
    assert max_available_backlog_months(df, now=now) == 3


def test_apply_analysis_depth_filter_filters_old_rows_and_excludes_unknown_created() -> None:
    now = datetime(2026, 2, 20, tzinfo=timezone.utc)
    df = pd.DataFrame(
        [
            {"key": "A", "created": now - timedelta(days=10)},
            {"key": "B", "created": now - timedelta(days=120)},
            {"key": "C", "created": None},
        ]
    )
    settings = Settings(ANALYSIS_LOOKBACK_MONTHS=2)

    out = apply_analysis_depth_filter(df, settings=settings, now=now)

    assert set(out["key"].tolist()) == {"A"}


def test_effective_analysis_lookback_months_clamps_to_available_window() -> None:
    now = datetime(2026, 2, 20, tzinfo=timezone.utc)
    df = pd.DataFrame({"created": [now - timedelta(days=130)]})
    settings = Settings(ANALYSIS_LOOKBACK_MONTHS=99)

    assert effective_analysis_lookback_months(settings, df=df, now=now) == 5
