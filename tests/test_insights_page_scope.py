from __future__ import annotations

from typing import Any

import pandas as pd

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
