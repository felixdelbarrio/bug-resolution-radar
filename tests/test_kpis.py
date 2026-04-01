from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from bug_resolution_radar.analytics.kpis import (
    build_open_age_priority_payload,
    build_timeseries_daily,
    compute_kpis,
)
from bug_resolution_radar.config import Settings


def test_kpis_basic_counts() -> None:
    now = datetime.now(timezone.utc)
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Bug 1",
                "status": "Open",
                "type": "Bug",
                "priority": "Highest",
                "created": now - timedelta(days=2),
                "updated": now - timedelta(days=1),
                "resolved": pd.NaT,
                "resolution_type": "",
                "assignee": "Alice",
                "components": [],
                "labels": [],
            },
            {
                "key": "A-2",
                "summary": "Bug 2",
                "status": "Closed",
                "type": "Bug",
                "priority": "High",
                "created": now - timedelta(days=10),
                "updated": now - timedelta(days=1),
                "resolved": now - timedelta(days=1),
                "resolution_type": "Done",
                "assignee": "Bob",
                "components": [],
                "labels": [],
            },
        ]
    )
    settings = Settings()
    k = compute_kpis(df, settings=settings)
    assert k["issues_total"] == 2
    assert k["issues_open"] == 1
    assert k["issues_closed"] == 1
    assert k["open_now_total"] == 1
    assert k["mean_resolution_days"] > 0


def test_kpis_empty_dataframe_returns_defaults() -> None:
    settings = Settings()
    k = compute_kpis(pd.DataFrame(), settings=settings)
    assert k["issues_total"] == 0
    assert k["open_now_total"] == 0
    assert list(k["top_open_table"].columns) == ["summary", "open_count"]


def test_kpis_handles_missing_columns_and_bad_settings() -> None:
    df = pd.DataFrame(
        [
            {"key": "M-1", "summary": "issue uno", "priority": "High"},
            {"key": "M-2", "summary": "issue dos", "priority": "Low"},
        ]
    )
    settings = Settings()

    k = compute_kpis(df, settings=settings)
    assert k["issues_total"] == 2
    assert k["issues_open"] == 2
    assert k["issues_closed"] == 0
    assert k["mean_resolution_days"] == 0.0


def test_kpis_top_open_table_is_sorted_by_frequency() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "T-1",
                "summary": "timeout pago",
                "priority": "High",
                "created": "2025-01-19T00:00:00+00:00",
                "resolved": pd.NaT,
            },
            {
                "key": "T-2",
                "summary": "timeout pago",
                "priority": "High",
                "created": "2025-01-18T00:00:00+00:00",
                "resolved": pd.NaT,
            },
            {
                "key": "T-3",
                "summary": "error login",
                "priority": "Medium",
                "created": "2025-01-10T00:00:00+00:00",
                "resolved": "2025-01-12T00:00:00+00:00",
                "resolution_type": "Done",
            },
        ]
    )
    settings = Settings()
    k = compute_kpis(df, settings=settings)

    top = k["top_open_table"]
    assert not top.empty
    assert top.iloc[0]["summary"] == "timeout pago"
    assert int(top.iloc[0]["open_count"]) == 2


def test_kpis_treats_accepted_without_resolved_as_closed() -> None:
    now = datetime.now(timezone.utc)
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Bug abierto",
                "status": "New",
                "priority": "High",
                "created": now - timedelta(days=3),
                "updated": now - timedelta(days=1),
                "resolved": pd.NaT,
            },
            {
                "key": "A-2",
                "summary": "Bug en accepted",
                "status": "Accepted",
                "priority": "Medium",
                "created": now - timedelta(days=5),
                "updated": now - timedelta(days=1),
                "resolved": pd.NaT,
            },
        ]
    )
    k = compute_kpis(df, settings=Settings())
    assert k["issues_total"] == 2
    assert k["issues_open"] == 1
    assert k["issues_closed"] == 1


def test_kpis_can_skip_timeseries_chart_generation() -> None:
    now = datetime.now(timezone.utc)
    df = pd.DataFrame(
        [
            {
                "key": "K-1",
                "summary": "Bug",
                "status": "Open",
                "priority": "High",
                "created": now - timedelta(days=2),
                "updated": now - timedelta(days=1),
                "resolved": pd.NaT,
            }
        ]
    )
    k = compute_kpis(df, settings=Settings(), include_timeseries_chart=False)
    assert k["timeseries_chart"] is None


def test_build_timeseries_daily_returns_dense_window_and_non_negative_backlog() -> None:
    df = pd.DataFrame(
        [
            {
                "created": "2026-01-01T00:00:00+00:00",
                "resolved": "2026-01-03T00:00:00+00:00",
            },
            {
                "created": "2026-01-04T00:00:00+00:00",
                "resolved": pd.NaT,
            },
        ]
    )
    daily = build_timeseries_daily(df, lookback_days=5, include_deployed=False)

    assert list(daily.columns) == ["date", "created", "closed", "open_backlog_proxy"]
    assert len(daily) == 5
    assert int(daily["open_backlog_proxy"].min()) >= 0


def test_build_open_age_priority_payload_keeps_only_open_issues() -> None:
    reference_now = pd.Timestamp("2026-03-01T00:00:00+00:00")
    df = pd.DataFrame(
        [
            {
                "key": "O-1",
                "status": "New",
                "priority": "High",
                "created": "2026-02-28T00:00:00+00:00",
                "resolved": pd.NaT,
            },
            {
                "key": "O-2",
                "status": "Blocked",
                "priority": "Medium",
                "created": "2026-02-10T00:00:00+00:00",
                "resolved": pd.NaT,
            },
            {
                "key": "C-1",
                "status": "Closed",
                "priority": "Low",
                "created": "2026-02-25T00:00:00+00:00",
                "resolved": "2026-02-27T00:00:00+00:00",
            },
            {
                "key": "C-2",
                "status": "Accepted",
                "priority": "Highest",
                "created": "2026-02-20T00:00:00+00:00",
                "resolved": pd.NaT,
                "updated": "2026-02-25T00:00:00+00:00",
            },
        ]
    )

    payload = build_open_age_priority_payload(df, reference_now=reference_now)
    grouped = payload["grouped"]
    opened = payload["open"]

    assert isinstance(grouped, pd.DataFrame)
    assert isinstance(opened, pd.DataFrame)
    assert set(opened["key"].astype(str).tolist()) == {"O-1", "O-2"}

    grouped_map = {
        (str(row.age_bucket), str(row.priority)): int(row.count)
        for row in grouped.itertuples(index=False)
    }
    assert grouped_map.get(("1-2d", "High"), 0) == 1
    assert grouped_map.get(("15-30d", "Medium"), 0) == 1
