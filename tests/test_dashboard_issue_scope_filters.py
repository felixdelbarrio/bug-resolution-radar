from __future__ import annotations

from datetime import timezone
from typing import Any

import pandas as pd

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.dashboard import quincenal_scope as quincenal_scope_helpers
from bug_resolution_radar.ui.dashboard import state as dashboard_state
from bug_resolution_radar.ui.dashboard.data_context import build_dashboard_data_context
from bug_resolution_radar.ui.pages import dashboard_page


class _FakeStreamlitState:
    def __init__(self, session_state: dict[str, object]) -> None:
        self.session_state = session_state


def test_apply_issue_scope_like_filter_uses_dashboard_scope_keys(monkeypatch: Any) -> None:
    fake_state = _FakeStreamlitState(
        {
            dashboard_state.ISSUES_SCOPE_SORT_COL_KEY: "key",
            dashboard_state.ISSUES_SCOPE_LIKE_QUERY_KEY: "mexbmi1-28",
        }
    )
    monkeypatch.setattr(dashboard_state, "st", fake_state)

    df = pd.DataFrame(
        [
            {"key": "MEXBMI1-283490"},
            {"key": "ABC-1"},
        ]
    )

    out = dashboard_state.apply_issue_scope_like_filter(df)

    assert out["key"].tolist() == ["MEXBMI1-283490"]


def test_apply_issue_scope_like_filter_applies_explicit_issue_key_subset(
    monkeypatch: Any,
) -> None:
    fake_state = _FakeStreamlitState(
        {
            dashboard_state.ISSUES_SCOPE_KEYS_KEY: ["mexbmi1-2", "MEXBMI1-3", "MEXBMI1-3"],
            dashboard_state.ISSUES_SCOPE_SORT_COL_KEY: "summary",
            dashboard_state.ISSUES_SCOPE_LIKE_QUERY_KEY: "",
        }
    )
    monkeypatch.setattr(dashboard_state, "st", fake_state)

    df = pd.DataFrame(
        [
            {"key": "MEXBMI1-1", "summary": "uno"},
            {"key": "MEXBMI1-2", "summary": "dos"},
            {"key": "MEXBMI1-3", "summary": "tres"},
        ]
    )

    out = dashboard_state.apply_issue_scope_like_filter(df)

    assert out["key"].tolist() == ["MEXBMI1-2", "MEXBMI1-3"]


def test_build_dashboard_data_context_applies_issue_scope_like_filter(monkeypatch: Any) -> None:
    now = pd.Timestamp.now(tz=timezone.utc)
    fake_state = _FakeStreamlitState(
        {
            dashboard_state.ISSUES_SCOPE_SORT_COL_KEY: "summary",
            dashboard_state.ISSUES_SCOPE_LIKE_QUERY_KEY: "dashboard",
        }
    )
    monkeypatch.setattr(dashboard_state, "st", fake_state)

    df = pd.DataFrame(
        [
            {
                "key": "MEXBMI1-283490",
                "summary": "Error en dashboard",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": now.isoformat(),
            },
            {
                "key": "MEXBMI1-100000",
                "summary": "Error en transferencias",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": now.isoformat(),
            },
        ]
    )

    ctx = build_dashboard_data_context(
        df_all=df,
        settings=Settings(ANALYSIS_LOOKBACK_MONTHS=12),
        include_kpis=False,
        include_timeseries_chart=False,
    )

    assert ctx.dff["key"].tolist() == ["MEXBMI1-283490"]


def test_build_dashboard_data_context_applies_quincenal_scope(monkeypatch: Any) -> None:
    now = pd.Timestamp("2026-03-26T00:00:00+00:00")
    fake_state = _FakeStreamlitState(
        {
            dashboard_state.FILTER_STATUS_KEY: [],
            dashboard_state.FILTER_PRIORITY_KEY: [],
            dashboard_state.FILTER_ASSIGNEE_KEY: [],
            dashboard_state.ISSUES_QUINCENAL_SCOPE_KEY: "Nuevas (quincena actual)",
            "workspace_country": "México",
            "workspace_scope_mode": "source",
            "workspace_source_id": "jira:mexico:core",
        }
    )
    monkeypatch.setattr(dashboard_state, "st", fake_state)
    monkeypatch.setattr(quincenal_scope_helpers, "st", fake_state)

    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Nueva actual",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
            {
                "key": "A-2",
                "summary": "Nueva previa",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=20)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
        ]
    )
    settings = Settings(
        ANALYSIS_LOOKBACK_MONTHS=12,
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
    )

    ctx = build_dashboard_data_context(
        df_all=df,
        settings=settings,
        include_kpis=False,
        include_timeseries_chart=False,
    )

    assert ctx.dff["key"].tolist() == ["A-1"]


def test_build_dashboard_data_context_applies_quincenal_scope_new_accumulated(
    monkeypatch: Any,
) -> None:
    now = pd.Timestamp("2026-03-26T00:00:00+00:00")
    fake_state = _FakeStreamlitState(
        {
            dashboard_state.FILTER_STATUS_KEY: [],
            dashboard_state.FILTER_PRIORITY_KEY: [],
            dashboard_state.FILTER_ASSIGNEE_KEY: [],
            dashboard_state.ISSUES_QUINCENAL_SCOPE_KEY: "Nuevas (acumulado)",
            "workspace_country": "México",
            "workspace_scope_mode": "source",
            "workspace_source_id": "jira:mexico:core",
        }
    )
    monkeypatch.setattr(dashboard_state, "st", fake_state)
    monkeypatch.setattr(quincenal_scope_helpers, "st", fake_state)

    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Nueva actual",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
            {
                "key": "A-2",
                "summary": "Nueva acumulada",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=20)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
            {
                "key": "A-3",
                "summary": "Nueva fuera mes",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=45)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
        ]
    )
    settings = Settings(
        ANALYSIS_LOOKBACK_MONTHS=12,
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
    )

    ctx = build_dashboard_data_context(
        df_all=df,
        settings=settings,
        include_kpis=False,
        include_timeseries_chart=False,
    )

    assert ctx.dff["key"].tolist() == ["A-1", "A-2"]


def test_quincenal_scope_options_hide_maestras_and_others_when_split_is_redundant(
    monkeypatch: Any,
) -> None:
    now = pd.Timestamp("2026-03-26T00:00:00+00:00")
    fake_state = _FakeStreamlitState(
        {
            "workspace_country": "México",
            "workspace_scope_mode": "source",
            "workspace_source_id": "jira:mexico:core",
        }
    )
    monkeypatch.setattr(quincenal_scope_helpers, "st", fake_state)

    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Abierta 1",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
            {
                "key": "A-2",
                "summary": "Abierta 2",
                "status": "In Progress",
                "priority": "Medium",
                "assignee": "Luis",
                "created": (now - pd.Timedelta(days=3)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
        ]
    )
    settings = Settings(
        ANALYSIS_LOOKBACK_MONTHS=12,
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
    )

    options = quincenal_scope_helpers.quincenal_scope_options(df, settings=settings)

    assert "Abiertas totales" in options
    assert "Maestras abiertas" not in options
    assert "Otras abiertas" not in options


def test_should_show_open_split_only_when_maestras_others_are_not_redundant() -> None:
    assert not quincenal_scope_helpers.should_show_open_split(
        maestras_total=0,
        others_total=11,
        open_total=11,
    )
    assert quincenal_scope_helpers.should_show_open_split(
        maestras_total=1,
        others_total=10,
        open_total=11,
    )
    assert quincenal_scope_helpers.should_show_open_split(
        maestras_total=0,
        others_total=9,
        open_total=11,
    )


def test_apply_issue_scope_like_filter_migrates_legacy_zoom_to_quincenal_scope(
    monkeypatch: Any,
) -> None:
    now = pd.Timestamp("2026-03-26T00:00:00+00:00")
    fake_state = _FakeStreamlitState(
        {
            dashboard_state.ISSUES_SCOPE_KEYS_KEY: ["A-1"],
            dashboard_state.ISSUES_SCOPE_LABEL_KEY: "Nuevas (quincena actual)",
            dashboard_state.ISSUES_QUINCENAL_SCOPE_KEY: "Todas",
            "workspace_country": "México",
            "workspace_scope_mode": "source",
            "workspace_source_id": "jira:mexico:core",
        }
    )
    monkeypatch.setattr(dashboard_state, "st", fake_state)
    monkeypatch.setattr(quincenal_scope_helpers, "st", fake_state)

    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Nueva actual",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
            {
                "key": "A-2",
                "summary": "Nueva previa",
                "created": (now - pd.Timedelta(days=20)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
            },
        ]
    )
    settings = Settings(
        ANALYSIS_LOOKBACK_MONTHS=12,
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
    )

    out = dashboard_state.apply_issue_scope_like_filter(df, settings=settings)

    assert out["key"].tolist() == ["A-1"]
    assert (
        fake_state.session_state.get(dashboard_state.ISSUES_QUINCENAL_SCOPE_KEY)
        == "Nuevas (quincena actual)"
    )
    assert dashboard_state.ISSUES_SCOPE_KEYS_KEY not in fake_state.session_state
    assert dashboard_state.ISSUES_SCOPE_LABEL_KEY not in fake_state.session_state


def test_clear_all_filters_clears_issue_zoom_scope(monkeypatch: Any) -> None:
    fake_state = _FakeStreamlitState(
        {
            dashboard_state.FILTER_STATUS_KEY: ["New"],
            dashboard_state.FILTER_PRIORITY_KEY: ["High"],
            dashboard_state.FILTER_ASSIGNEE_KEY: ["Ana"],
            dashboard_state.ISSUES_SCOPE_KEYS_KEY: ["A-1"],
            dashboard_state.ISSUES_SCOPE_LABEL_KEY: "Maestras",
            dashboard_state.ISSUES_SCOPE_SORT_COL_KEY: "key",
            dashboard_state.ISSUES_SCOPE_LIKE_QUERY_KEY: "a-1",
            dashboard_state.ISSUES_QUINCENAL_SCOPE_KEY: "Nuevas (quincena actual)",
        }
    )
    monkeypatch.setattr(dashboard_state, "st", fake_state)

    dashboard_state.clear_all_filters()

    assert fake_state.session_state[dashboard_state.FILTER_STATUS_KEY] == []
    assert fake_state.session_state[dashboard_state.FILTER_PRIORITY_KEY] == []
    assert fake_state.session_state[dashboard_state.FILTER_ASSIGNEE_KEY] == []
    assert dashboard_state.ISSUES_SCOPE_KEYS_KEY not in fake_state.session_state
    assert dashboard_state.ISSUES_SCOPE_LABEL_KEY not in fake_state.session_state
    assert dashboard_state.ISSUES_QUINCENAL_SCOPE_KEY not in fake_state.session_state


def test_dashboard_data_cache_signature_ignores_section_label_when_shape_and_flags_match(
    monkeypatch: Any,
) -> None:
    fake_state = _FakeStreamlitState(
        {
            "workspace_country": "México",
            "workspace_source_id": "jira:mexico:core",
            dashboard_state.FILTER_STATUS_KEY: ["New"],
            dashboard_state.FILTER_PRIORITY_KEY: ["High"],
            dashboard_state.FILTER_ASSIGNEE_KEY: [],
            dashboard_state.ISSUES_SCOPE_SORT_COL_KEY: "summary",
            dashboard_state.ISSUES_SCOPE_LIKE_QUERY_KEY: "dashboard",
        }
    )
    monkeypatch.setattr(dashboard_page, "st", fake_state)

    df = pd.DataFrame(
        [
            {"key": "A-1", "summary": "x", "status": "New", "priority": "High", "assignee": "ana"},
            {"key": "A-2", "summary": "y", "status": "New", "priority": "High", "assignee": "ana"},
        ]
    )
    settings = Settings(DATA_PATH="data/issues.json", ANALYSIS_LOOKBACK_MONTHS=12)

    sig_overview = dashboard_page._dashboard_data_cache_signature(
        settings=settings,
        section="overview",
        scoped_df=df,
        include_kpis=True,
        include_timeseries_chart=True,
    )
    sig_trends = dashboard_page._dashboard_data_cache_signature(
        settings=settings,
        section="trends",
        scoped_df=df,
        include_kpis=True,
        include_timeseries_chart=True,
    )

    assert sig_overview == sig_trends


def test_apply_workspace_source_scope_uses_country_rollup_in_country_mode(monkeypatch: Any) -> None:
    fake_state = _FakeStreamlitState(
        {
            "workspace_country": "México",
            "workspace_source_id": "jira:mexico:core",
            "workspace_scope_mode": "country",
        }
    )
    monkeypatch.setattr(dashboard_page, "st", fake_state)

    settings = Settings(
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"Core","jql":"project = CORE"},'
            '{"country":"México","alias":"Retail","jql":"project = RET"}]'
        ),
        COUNTRY_ROLLUP_SOURCES_JSON='[{"country":"México","source_ids":["jira:mexico:retail"]}]',
    )
    df = pd.DataFrame(
        [
            {"key": "A-1", "country": "México", "source_id": "jira:mexico:core"},
            {"key": "A-2", "country": "México", "source_id": "jira:mexico:retail"},
        ]
    )

    out = dashboard_page._apply_workspace_source_scope(df, settings=settings)

    assert out["key"].tolist() == ["A-2"]
