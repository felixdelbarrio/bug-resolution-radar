from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.dashboard.trends import (
    _effective_trends_open_scope,
    available_trend_charts,
)


def test_effective_trends_open_scope_uses_filtered_df_for_terminal_status_filter() -> None:
    dff = pd.DataFrame(
        {
            "status": ["Deployed", "New", "Accepted"],
            "priority": ["High", "High", "Low"],
            "resolved": [
                pd.Timestamp("2025-01-10"),
                pd.NaT,
                pd.Timestamp("2025-01-08"),
            ],
        }
    )
    open_df = dff[dff["resolved"].isna()].copy(deep=False)

    scoped, adapted = _effective_trends_open_scope(
        dff=dff,
        open_df=open_df,
        active_status_filters=["Deployed"],
    )

    assert adapted is True
    assert list(scoped["status"]) == ["Deployed"]


def test_effective_trends_open_scope_keeps_open_df_for_non_terminal_filter() -> None:
    dff = pd.DataFrame(
        {
            "status": ["New", "Blocked", "Deployed"],
            "priority": ["High", "Medium", "Low"],
            "resolved": [pd.NaT, pd.NaT, pd.Timestamp("2025-01-01")],
        }
    )
    open_df = dff[dff["resolved"].isna()].copy(deep=False)

    scoped, adapted = _effective_trends_open_scope(
        dff=dff,
        open_df=open_df,
        active_status_filters=["New"],
    )

    assert adapted is False
    assert len(scoped) == len(open_df)
    assert set(scoped["status"]) == {"New", "Blocked"}


def test_effective_trends_open_scope_keeps_open_df_if_no_matching_status() -> None:
    dff = pd.DataFrame(
        {
            "status": ["Deployed", "Accepted"],
            "priority": ["High", "Low"],
            "resolved": [pd.Timestamp("2025-01-10"), pd.Timestamp("2025-01-11")],
        }
    )
    open_df = pd.DataFrame(columns=dff.columns)

    scoped, adapted = _effective_trends_open_scope(
        dff=dff,
        open_df=open_df,
        active_status_filters=["Blocked"],
    )

    assert adapted is False
    assert scoped.empty


def test_available_trend_chart_labels_do_not_use_abiertas_wording() -> None:
    labels = {cid: label for cid, label in available_trend_charts()}
    assert labels["open_priority_pie"] == "Issues por Priority"
    assert labels["open_status_bar"] == "Issues por Estado"
    assert "abiertas" not in labels["age_buckets"].lower()
