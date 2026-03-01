from __future__ import annotations

import re

import pandas as pd

from bug_resolution_radar.ui.common import status_color
from bug_resolution_radar.ui.components.filters import (
    _active_context_label,
    _matrix_header_button_css,
    _semantic_label_tone_map,
    apply_filters,
)
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


def _css_prop(style: str, prop: str) -> str:
    m = re.search(rf"{re.escape(prop)}:([^;]+);", str(style))
    return str(m.group(1)).strip() if m else ""


def test_matrix_header_css_uses_same_tone_for_in_progress_family() -> None:
    base = _matrix_header_button_css(status_color("In Progress"), selected=False)
    for name in ["To Rework", "Test", "Ready To Verify"]:
        got = _matrix_header_button_css(status_color(name), selected=False)
        assert _css_prop(got, "background") == _css_prop(base, "background")
        assert _css_prop(got, "border") == _css_prop(base, "border")
        assert _css_prop(got, "color") == _css_prop(base, "color")


def test_matrix_header_css_selection_keeps_same_base_color() -> None:
    base = _matrix_header_button_css(status_color("Blocked"), selected=False)
    selected = _matrix_header_button_css(status_color("Blocked"), selected=True)
    assert _css_prop(selected, "background") == _css_prop(base, "background")
    assert _css_prop(selected, "border") == _css_prop(base, "border")


def test_semantic_label_tone_map_groups_equivalent_statuses() -> None:
    tones = _semantic_label_tone_map(
        status_labels=[
            "New",
            "Analysing",
            "Blocked",
            "En progreso",
            "To Rework",
            "Test",
            "Ready To Verify",
            "Accepted",
            "Ready to Deploy",
        ],
        priority_labels=["Highest", "High", "Medium", "Low"],
    )
    assert tones["new"]["color"] == tones["analysing"]["color"] == tones["blocked"]["color"]
    assert (
        tones["en progreso"]["color"]
        == tones["to rework"]["color"]
        == tones["test"]["color"]
        == tones["ready to verify"]["color"]
    )
    assert tones["accepted"]["color"] == tones["ready to deploy"]["color"]
