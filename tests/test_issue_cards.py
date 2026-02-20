from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.components.issues import prepare_issue_cards_df


def test_prepare_issue_cards_df_includes_closed_rows_for_filtered_coherence() -> None:
    df = pd.DataFrame(
        {
            "key": ["A-1", "A-2", "A-3"],
            "summary": ["open high", "closed high", "open low"],
            "status": ["New", "Done", "In Progress"],
            "priority": ["High", "High", "Low"],
            "assignee": ["ana", "ana", "ana"],
            "created": ["2025-01-01", "2025-01-01", "2025-01-01"],
            "updated": ["2025-01-10", "2025-01-09", "2025-01-08"],
            "resolved": [pd.NaT, pd.Timestamp("2025-01-03"), pd.NaT],
            "url": ["u1", "u2", "u3"],
        }
    )
    out = prepare_issue_cards_df(df, max_cards=10)
    assert len(out) == 3
    assert int((~out["__is_open"]).sum()) == 1


def test_prepare_issue_cards_df_respects_max_cards() -> None:
    df = pd.DataFrame(
        {
            "key": [f"A-{i}" for i in range(20)],
            "summary": ["x"] * 20,
            "status": ["New"] * 20,
            "priority": ["High"] * 20,
            "assignee": ["ana"] * 20,
            "created": ["2025-01-01"] * 20,
            "updated": ["2025-01-10"] * 20,
            "resolved": [pd.NaT] * 20,
            "url": ["u"] * 20,
        }
    )
    out = prepare_issue_cards_df(df, max_cards=7)
    assert len(out) == 7


def test_prepare_issue_cards_df_treats_accepted_as_closed_without_resolved() -> None:
    df = pd.DataFrame(
        {
            "key": ["A-1", "A-2"],
            "summary": ["open", "accepted sin resolved"],
            "status": ["New", "Accepted"],
            "priority": ["High", "Medium"],
            "assignee": ["ana", "ana"],
            "created": ["2025-01-01", "2025-01-01"],
            "updated": ["2025-01-10", "2025-01-10"],
            "resolved": [pd.NaT, pd.NaT],
            "url": ["u1", "u2"],
        }
    )
    out = prepare_issue_cards_df(df, max_cards=10)
    is_open_by_key = dict(zip(out["key"].astype(str), out["__is_open"].astype(bool)))
    assert is_open_by_key["A-1"] is True
    assert is_open_by_key["A-2"] is False
