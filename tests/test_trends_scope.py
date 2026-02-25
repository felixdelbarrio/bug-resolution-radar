from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.dashboard.registry import (
    ChartContext,
    _render_age_buckets,
    _render_open_priority_pie,
)
from bug_resolution_radar.ui.dashboard.tabs.trends_tab import (
    _effective_trends_open_scope,
    _exclude_terminal_status_rows,
    _open_status_payload,
    _timeseries_daily_from_filtered,
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


def test_available_trend_chart_labels_are_executive_and_consistent() -> None:
    labels = {cid: label for cid, label in available_trend_charts()}
    assert labels["open_priority_pie"] == "Issues abiertos por prioridad"
    assert labels["open_status_bar"] == "Issues por Estado"
    assert "abiertas" not in labels["age_buckets"].lower()


def test_exclude_terminal_status_rows_removes_deployed_for_open_priority_scope() -> None:
    df = pd.DataFrame(
        {
            "status": ["New", "Blocked", "Deployed", "Accepted", "In Progress"],
            "priority": ["High", "Medium", "Low", "Low", "High"],
        }
    )
    out = _exclude_terminal_status_rows(df)
    assert set(out["status"].astype(str).tolist()) == {"New", "Blocked", "In Progress"}


def test_open_status_payload_keeps_deployed_in_status_aggregation() -> None:
    df = pd.DataFrame(
        {
            "status": ["New", "In Progress", "Deployed", "Accepted"],
            "priority": ["High", "Medium", "Low", "Low"],
        }
    )
    payload = _open_status_payload(df)
    grouped = payload.get("grouped")
    assert isinstance(grouped, pd.DataFrame)
    assert "Deployed" in grouped["status"].astype(str).unique().tolist()


def test_timeseries_daily_from_filtered_includes_deployed_series() -> None:
    df = pd.DataFrame(
        {
            "status": ["New", "Deployed", "Deployed", "Closed"],
            "created": [
                pd.Timestamp("2025-01-01"),
                pd.Timestamp("2025-01-02"),
                pd.Timestamp("2025-01-02"),
                pd.Timestamp("2025-01-02"),
            ],
            "resolved": [
                pd.NaT,
                pd.Timestamp("2025-01-03"),
                pd.NaT,
                pd.Timestamp("2025-01-03"),
            ],
            "updated": [
                pd.Timestamp("2025-01-01"),
                pd.Timestamp("2025-01-03"),
                pd.Timestamp("2025-01-04"),
                pd.Timestamp("2025-01-03"),
            ],
        }
    )
    daily = _timeseries_daily_from_filtered(df)
    assert "deployed" in daily.columns
    by_day = {
        pd.Timestamp(row.date).normalize(): int(row.deployed)
        for row in daily[["date", "deployed"]].itertuples(index=False)
    }
    assert by_day.get(pd.Timestamp("2025-01-03"), 0) == 1
    assert by_day.get(pd.Timestamp("2025-01-04"), 0) == 1


def test_render_open_priority_pie_excludes_deployed_rows() -> None:
    open_df = pd.DataFrame(
        {
            "status": ["Deployed", "New", "Accepted"],
            "priority": ["Low", "High", "Medium"],
        }
    )
    ctx = ChartContext(dff=open_df.copy(deep=False), open_df=open_df, kpis={})
    fig = _render_open_priority_pie(ctx)
    assert fig is not None
    labels = [str(x) for x in list(fig.data[0]["labels"])]
    assert set(labels) == {"High"}


def test_render_age_buckets_renders_issue_level_distribution() -> None:
    now = pd.Timestamp.utcnow()
    open_df = pd.DataFrame(
        {
            "status": ["New", "Analysing", "Blocked", "En progreso", "To Rework", "Ready"],
            "priority": ["Highest", "High", "Medium", "Low", "Lowest", "High"],
            "created": [
                now - pd.Timedelta(days=1),
                now - pd.Timedelta(days=5),
                now - pd.Timedelta(days=10),
                now - pd.Timedelta(days=18),
                now - pd.Timedelta(days=40),
                now - pd.Timedelta(days=65),
            ],
        }
    )
    ctx = ChartContext(dff=open_df.copy(deep=False), open_df=open_df, kpis={})
    fig = _render_age_buckets(ctx)
    assert fig is not None
    assert (
        str(getattr(getattr(fig.layout, "xaxis", None), "title", None).text)
        == "Rango de antigüedad (días)"
    )
    assert str(getattr(getattr(fig.layout, "yaxis", None), "title", None).text) == "Criticidad"
    marker_points = 0
    for trace in list(fig.data):
        if str(getattr(trace, "type", "") or "").strip().lower() != "scatter":
            continue
        mode = str(getattr(trace, "mode", "") or "").strip().lower()
        if "markers" not in mode:
            continue
        marker_points += len(list(getattr(trace, "x", []) or []))
    assert marker_points == len(open_df)
