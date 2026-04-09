from __future__ import annotations

from typing import Any

import pandas as pd

from bug_resolution_radar.analytics.insights_scope import (
    INSIGHTS_VIEW_MODE_ACCUMULATED,
    INSIGHTS_VIEW_MODE_QUINCENAL,
)
from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.dashboard import quincenal_scope
from bug_resolution_radar.ui.pages import insights_page


class _FakeStreamlitState:
    def __init__(self, session_state: dict[str, object]) -> None:
        self.session_state = session_state


def test_insights_quincenal_df_keeps_only_current_fortnight_created_or_closed(
    monkeypatch: Any,
) -> None:
    fake_state = _FakeStreamlitState(
        {
            "workspace_country": "México",
            "workspace_scope_mode": "source",
            "workspace_source_id": "jira:mexico:core",
        }
    )
    monkeypatch.setattr(insights_page, "st", fake_state)
    monkeypatch.setattr(quincenal_scope, "st", fake_state)

    now = pd.Timestamp("2026-03-26T00:00:00+00:00")
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Nueva actual",
                "created": (now - pd.Timedelta(days=3)).isoformat(),
                "resolved": None,
                "updated": now.isoformat(),
                "country": "México",
                "source_id": "jira:mexico:core",
            },
            {
                "key": "A-2",
                "summary": "Cerrada actual",
                "created": (now - pd.Timedelta(days=45)).isoformat(),
                "resolved": (now - pd.Timedelta(days=1)).isoformat(),
                "updated": now.isoformat(),
                "country": "México",
                "source_id": "jira:mexico:core",
            },
            {
                "key": "A-3",
                "summary": "Fuera de quincena",
                "created": (now - pd.Timedelta(days=40)).isoformat(),
                "resolved": (now - pd.Timedelta(days=25)).isoformat(),
                "updated": now.isoformat(),
                "country": "México",
                "source_id": "jira:mexico:core",
            },
        ]
    )

    settings = Settings(
        ANALYSIS_LOOKBACK_MONTHS=12,
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
    )

    out = insights_page._insights_quincenal_df(settings=settings, dff=df)

    assert out["key"].tolist() == ["A-1", "A-2"]


def test_insights_quincenal_df_returns_original_when_date_columns_missing(monkeypatch: Any) -> None:
    fake_state = _FakeStreamlitState({})
    monkeypatch.setattr(insights_page, "st", fake_state)
    monkeypatch.setattr(quincenal_scope, "st", fake_state)

    df = pd.DataFrame([{"key": "A-1", "summary": "sin fechas"}])
    out = insights_page._insights_quincenal_df(settings=Settings(), dff=df)

    assert out.equals(df)


def test_should_reseed_status_defaults_on_first_load() -> None:
    assert insights_page._should_reseed_status_defaults(
        status_key_missing=True,
        status_widget_missing=True,
        status_manual=False,
        previous_view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
        current_view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
    )


def test_should_reseed_status_defaults_when_view_changes_without_manual_override() -> None:
    assert insights_page._should_reseed_status_defaults(
        status_key_missing=False,
        status_widget_missing=False,
        status_manual=False,
        previous_view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
        current_view_mode=INSIGHTS_VIEW_MODE_ACCUMULATED,
    )


def test_should_not_reseed_status_defaults_when_view_changes_with_manual_override() -> None:
    assert not insights_page._should_reseed_status_defaults(
        status_key_missing=False,
        status_widget_missing=False,
        status_manual=True,
        previous_view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
        current_view_mode=INSIGHTS_VIEW_MODE_ACCUMULATED,
    )


def test_should_not_reseed_status_defaults_when_view_does_not_change() -> None:
    assert not insights_page._should_reseed_status_defaults(
        status_key_missing=False,
        status_widget_missing=False,
        status_manual=False,
        previous_view_mode=INSIGHTS_VIEW_MODE_ACCUMULATED,
        current_view_mode=INSIGHTS_VIEW_MODE_ACCUMULATED,
    )
