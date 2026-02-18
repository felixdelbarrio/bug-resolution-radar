from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pandas as pd

from bug_resolution_radar.config import Settings, build_source_id
from bug_resolution_radar.ui import app


def _settings_with_jira_sources() -> Settings:
    return Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"MX Core","jql":"project = 1"},'
            '{"country":"México","alias":"MX BEX","jql":"project = 2"},'
            '{"country":"España","alias":"ES Core","jql":"project = 3"}]'
        ),
    )


def test_scope_sources_only_include_source_ids_with_results(monkeypatch: Any) -> None:
    settings = _settings_with_jira_sources()
    mx_core_id = build_source_id("jira", "México", "MX Core")
    es_core_id = build_source_id("jira", "España", "ES Core")

    monkeypatch.setattr(
        app,
        "load_issues_df",
        lambda _path: pd.DataFrame(
            [
                {"country": "México", "source_id": mx_core_id},
                {"country": "España", "source_id": es_core_id},
            ]
        ),
    )

    grouped = app._sources_with_results_by_country(settings)
    assert list(grouped.keys()) == ["México", "España"]
    assert [row["source_id"] for row in grouped["México"]] == [mx_core_id]
    assert [row["source_id"] for row in grouped["España"]] == [es_core_id]


def test_scope_sources_fallback_to_country_when_source_id_missing(monkeypatch: Any) -> None:
    settings = _settings_with_jira_sources()

    monkeypatch.setattr(
        app,
        "load_issues_df",
        lambda _path: pd.DataFrame(
            [
                {"country": "México"},
                {"country": "México"},
            ]
        ),
    )

    grouped = app._sources_with_results_by_country(settings)
    assert list(grouped.keys()) == ["México"]
    assert [row["alias"] for row in grouped["México"]] == ["MX Core", "MX BEX"]


def test_scope_sources_empty_when_there_are_no_results(monkeypatch: Any) -> None:
    settings = _settings_with_jira_sources()
    monkeypatch.setattr(app, "load_issues_df", lambda _path: pd.DataFrame())
    assert app._sources_with_results_by_country(settings) == {}


def test_reset_scope_filters_clears_canonical_and_ui_keys(monkeypatch: Any) -> None:
    fake_state = {
        "filter_status": ["Open"],
        "filter_priority": ["High"],
        "filter_assignee": ["Ana"],
        "__filters_action_context": {"label": "test"},
        "dashboard::filter_status_ui": ["Open"],
        "dashboard::filter_priority_ui": ["High"],
        "dashboard::filter_assignee_ui": ["Ana"],
        "filter_status_ui": ["Open"],
        "filter_priority_ui": ["High"],
        "filter_assignee_ui": ["Ana"],
        "other_key": "keep",
    }

    def _fake_clear_all_filters() -> None:
        fake_state["filter_status"] = []
        fake_state["filter_priority"] = []
        fake_state["filter_assignee"] = []

    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=fake_state))
    monkeypatch.setattr(app, "clear_all_filters", _fake_clear_all_filters)

    app._reset_scope_filters()

    assert fake_state["filter_status"] == []
    assert fake_state["filter_priority"] == []
    assert fake_state["filter_assignee"] == []
    assert "__filters_action_context" not in fake_state
    assert "dashboard::filter_status_ui" not in fake_state
    assert "dashboard::filter_priority_ui" not in fake_state
    assert "dashboard::filter_assignee_ui" not in fake_state
    assert "filter_status_ui" not in fake_state
    assert "filter_priority_ui" not in fake_state
    assert "filter_assignee_ui" not in fake_state
    assert fake_state["other_key"] == "keep"
