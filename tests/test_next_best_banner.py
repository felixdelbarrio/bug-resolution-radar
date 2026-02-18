from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.dashboard.next_best_banner import (
    _derive_actionable_status_scope,
    _exclude_terminal_statuses,
    _resolved_copy,
    _select_pending_action,
    _target_issue_count,
)
from bug_resolution_radar.ui.insights.copilot import NextBestAction


def _mk_action(title: str) -> NextBestAction:
    return NextBestAction(title=title, body="", expected_impact="")


def test_resolved_copy_critical_uses_exact_filtered_count() -> None:
    body, impact = _resolved_copy(_mk_action("Asignacion de ownership critico"), matches=4)
    assert "ownership" in body.lower()
    assert "4 incidencias" in impact


def test_resolved_copy_uses_singular_when_one_match() -> None:
    body, impact = _resolved_copy(_mk_action("Revision de bloqueos activos"), matches=1)
    assert "desbloquear" in body.lower()
    assert "1 incidencia" in impact


def test_resolved_copy_generic_still_anchored_to_filtered_count() -> None:
    body, impact = _resolved_copy(_mk_action("Seguimiento operativo"), matches=7)
    assert "revision focalizada" in body.lower()
    assert "7 incidencias" in impact


def test_target_issue_count_matches_issues_tab_semantics_including_closed_rows() -> None:
    df = pd.DataFrame(
        {
            "status": ["New", "Done", "In Progress"],
            "priority": ["High", "High", "Lowest"],
            "assignee": ["", "", "ana"],
            "resolved": [pd.NaT, pd.Timestamp("2025-01-10"), pd.NaT],
        }
    )
    count = _target_issue_count(
        df_all=df,
        status_filters=[],
        priority_filters=["High"],
        assignee_filters=["(sin asignar)"],
    )
    # Must count exactly as Issues tab (all filtered rows), not only open backlog.
    assert count == 2


def test_exclude_terminal_statuses_removes_final_states_even_if_open() -> None:
    df = pd.DataFrame(
        {
            "status": ["New", "Deployed", "Accepted", "Blocked", "Done", "In Progress"],
            "priority": ["High"] * 6,
            "assignee": [""] * 6,
            "resolved": [pd.NaT] * 6,
        }
    )
    out = _exclude_terminal_statuses(df)
    assert list(out["status"]) == ["New", "Blocked", "In Progress"]


def test_derive_actionable_status_scope_excludes_terminal_and_respects_other_filters() -> None:
    df = pd.DataFrame(
        {
            "status": ["New", "Blocked", "In Progress", "Deployed"],
            "priority": ["High", "High", "Low", "High"],
            "assignee": ["(sin asignar)", "(sin asignar)", "ana", "(sin asignar)"],
        }
    )
    open_actionable = _exclude_terminal_statuses(df)
    scope = _derive_actionable_status_scope(
        open_df=open_actionable,
        priority_filters=["High"],
        assignee_filters=["(sin asignar)"],
    )
    assert scope == ["New", "Blocked"]


def test_select_pending_action_rotates_without_marking_reviewed() -> None:
    items = [
        ("a1", _mk_action("A1"), [], [], [], 3),
        ("a2", _mk_action("A2"), [], [], [], 2),
        ("a3", _mk_action("A3"), [], [], [], 1),
    ]
    selected, pending = _select_pending_action(
        actionable_items=items,
        reviewed=set(),
        preview_index=1,
    )
    assert pending == 3
    assert selected is not None and selected[0] == "a2"


def test_select_pending_action_skips_reviewed_and_wraps_index() -> None:
    items = [
        ("a1", _mk_action("A1"), [], [], [], 3),
        ("a2", _mk_action("A2"), [], [], [], 2),
        ("a3", _mk_action("A3"), [], [], [], 1),
    ]
    selected, pending = _select_pending_action(
        actionable_items=items,
        reviewed={"a2"},
        preview_index=3,
    )
    assert pending == 2
    assert selected is not None and selected[0] == "a3"
