from __future__ import annotations

from datetime import timezone
from typing import Any

import pandas as pd

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.dashboard import state as dashboard_state
from bug_resolution_radar.ui.dashboard.data_context import build_dashboard_data_context


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
