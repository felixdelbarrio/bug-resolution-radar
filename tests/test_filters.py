from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.components.filters import _active_context_label, apply_filters
from bug_resolution_radar.ui.dashboard.state import FilterState


def test_apply_filters_matches_unassigned_assignee_label() -> None:
    df = pd.DataFrame(
        {
            "status": ["New", "In Progress"],
            "priority": ["High", "Medium"],
            "assignee": ["", "ana"],
        }
    )
    fs = FilterState(status=[], priority=[], assignee=["(sin asignar)"])
    out = apply_filters(df, fs)
    assert len(out) == 1
    assert str(out.iloc[0]["status"]) == "New"


def test_active_context_label_returns_label_on_exact_filter_match() -> None:
    label = _active_context_label(
        {
            "label": "Incidencias criticas sin owner",
            "status": [],
            "priority": ["High", "Supone un impedimento"],
            "assignee": ["(sin asignar)"],
        },
        status=[],
        priority=["Supone un impedimento", "High"],
        assignee=["(sin asignar)"],
    )
    assert label == "Incidencias criticas sin owner"


def test_active_context_label_returns_none_if_filters_changed() -> None:
    label = _active_context_label(
        {
            "label": "Incidencias criticas sin owner",
            "status": [],
            "priority": ["High"],
            "assignee": ["(sin asignar)"],
        },
        status=[],
        priority=["High"],
        assignee=[],
    )
    assert label is None
