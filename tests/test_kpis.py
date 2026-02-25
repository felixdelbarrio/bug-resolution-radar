from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from bug_resolution_radar.analytics import kpis as kpis_module
from bug_resolution_radar.config import Settings
from bug_resolution_radar.analytics.kpis import compute_kpis


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


def test_kpis_handles_missing_columns_and_bad_settings(monkeypatch: Any) -> None:
    fixed_now = datetime(2025, 1, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(kpis_module, "_utcnow", lambda: fixed_now)

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


def test_kpis_top_open_table_is_sorted_by_frequency(monkeypatch: Any) -> None:
    fixed_now = datetime(2025, 1, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(kpis_module, "_utcnow", lambda: fixed_now)

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
