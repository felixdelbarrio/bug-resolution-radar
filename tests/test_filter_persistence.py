from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.dashboard import state as dashboard_state


def test_bootstrap_filters_from_env_hydrates_canonical_state(monkeypatch: Any) -> None:
    fake_state: dict[str, Any] = {}
    monkeypatch.setattr(dashboard_state, "st", SimpleNamespace(session_state=fake_state))

    settings = Settings(
        DASHBOARD_FILTER_STATUS_JSON='["New","Analysing","Ready"]',
        DASHBOARD_FILTER_PRIORITY_JSON='["High","Medium"]',
        DASHBOARD_FILTER_ASSIGNEE_JSON='["ana","luis"]',
    )

    dashboard_state.bootstrap_filters_from_env(settings)

    assert fake_state[dashboard_state.FILTER_STATUS_KEY] == ["New", "Analysing", "Ready"]
    assert fake_state[dashboard_state.FILTER_PRIORITY_KEY] == ["High", "Medium"]
    assert fake_state[dashboard_state.FILTER_ASSIGNEE_KEY] == ["ana", "luis"]
    assert fake_state[dashboard_state.FILTERS_BOOTSTRAPPED_KEY] is True


def test_bootstrap_filters_from_env_keeps_existing_session_values(monkeypatch: Any) -> None:
    fake_state: dict[str, Any] = {
        dashboard_state.FILTER_STATUS_KEY: ["Blocked"],
        dashboard_state.FILTER_PRIORITY_KEY: ["Low"],
        dashboard_state.FILTER_ASSIGNEE_KEY: ["ana"],
    }
    monkeypatch.setattr(dashboard_state, "st", SimpleNamespace(session_state=fake_state))

    settings = Settings(
        DASHBOARD_FILTER_STATUS_JSON='["New"]',
        DASHBOARD_FILTER_PRIORITY_JSON='["High"]',
        DASHBOARD_FILTER_ASSIGNEE_JSON='["luis"]',
    )

    dashboard_state.bootstrap_filters_from_env(settings)

    assert fake_state[dashboard_state.FILTER_STATUS_KEY] == ["Blocked"]
    assert fake_state[dashboard_state.FILTER_PRIORITY_KEY] == ["Low"]
    assert fake_state[dashboard_state.FILTER_ASSIGNEE_KEY] == ["ana"]


def test_persist_filters_in_env_only_saves_when_changed(monkeypatch: Any) -> None:
    fake_state: dict[str, Any] = {
        dashboard_state.FILTER_STATUS_KEY: ["New", "Ready"],
        dashboard_state.FILTER_PRIORITY_KEY: ["High"],
        dashboard_state.FILTER_ASSIGNEE_KEY: ["ana"],
    }
    monkeypatch.setattr(dashboard_state, "st", SimpleNamespace(session_state=fake_state))

    captured: dict[str, Any] = {}

    def _fake_save_settings(updated: Settings) -> None:
        captured["settings"] = updated

    monkeypatch.setattr(dashboard_state, "save_settings", _fake_save_settings)

    same_settings = Settings(
        DASHBOARD_FILTER_STATUS_JSON='["New","Ready"]',
        DASHBOARD_FILTER_PRIORITY_JSON='["High"]',
        DASHBOARD_FILTER_ASSIGNEE_JSON='["ana"]',
    )
    assert dashboard_state.persist_filters_in_env(same_settings) is False
    assert "settings" not in captured

    changed_settings = Settings(
        DASHBOARD_FILTER_STATUS_JSON='["New"]',
        DASHBOARD_FILTER_PRIORITY_JSON="[]",
        DASHBOARD_FILTER_ASSIGNEE_JSON="[]",
    )
    assert dashboard_state.persist_filters_in_env(changed_settings) is True
    saved = captured["settings"]
    assert str(saved.DASHBOARD_FILTER_STATUS_JSON) == '["New","Ready"]'
    assert str(saved.DASHBOARD_FILTER_PRIORITY_JSON) == '["High"]'
    assert str(saved.DASHBOARD_FILTER_ASSIGNEE_JSON) == '["ana"]'
