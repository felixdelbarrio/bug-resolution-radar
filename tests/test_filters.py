from __future__ import annotations

import re

import pandas as pd

from bug_resolution_radar.ui.common import status_color
from bug_resolution_radar.ui.components.filters import (
    _active_context_label,
    _inject_semantic_option_runtime_bridge,
    _matrix_header_button_css,
    _semantic_label_tone_map,
    _semantic_tag_css_rules,
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


def test_semantic_runtime_bridge_injects_token_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_components_html(html: str, height: int, width: int) -> None:
        captured["html"] = html
        captured["height"] = height
        captured["width"] = width

    monkeypatch.setattr(
        "bug_resolution_radar.ui.components.filters.components_html",
        _fake_components_html,
    )

    _inject_semantic_option_runtime_bridge(
        status_labels=["New", "Analysing", "Blocked", "En progreso", "Ready to Deploy"],
        priority_labels=["Highest", "High", "Medium", "Low"],
    )

    payload = str(captured.get("html", ""))
    assert "window.parent" in payload
    assert 'setAttribute("data-bbva-semantic", "1")' in payload
    assert 'setAttribute("data-bbva-semantic-key", toneKey)' in payload
    assert "MutationObserver" in payload
    assert "shouldRescan" in payload
    assert "observer.observe(parentDoc.body, { childList: true, subtree: true })" in payload
    assert "scheduleApply()" in payload
    assert '"new"' in payload
    assert '"analysing"' in payload
    assert '"blocked"' in payload
    assert '"en progreso"' in payload
    assert '"ready to deploy"' in payload
    assert captured.get("height") == 0
    assert captured.get("width") == 0


def test_semantic_tag_css_rules_use_tag_aria_label_without_dot() -> None:
    css = _semantic_tag_css_rules(
        status_labels=["New", "Analysing", "Blocked", "En progreso", "Ready to Deploy"],
        priority_labels=["Highest", "High", "Medium", "Low"],
    )
    assert '[data-baseweb="tag"][aria-label^="Analysing" i]' in css
    assert '[data-baseweb="tag"][aria-label^="Highest" i]' in css
    assert "background: #E85D6318 !important;" in css
    assert "border: 1px solid #E85D6378 !important;" in css
    assert "color: #E85D63 !important;" in css
    assert "::before" not in css
