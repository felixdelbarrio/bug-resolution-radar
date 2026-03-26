from __future__ import annotations

from typing import Any

import pandas as pd

from bug_resolution_radar.ui.pages import ingest_page


class _FakeStreamlitState:
    def __init__(self, session_state: dict[str, object]) -> None:
        self.session_state = session_state


def test_effective_disabled_source_ids_keeps_session_state_across_reruns(monkeypatch: Any) -> None:
    fake_state = _FakeStreamlitState({})
    monkeypatch.setattr(ingest_page, "st", fake_state)

    first = ingest_page._effective_disabled_source_ids(
        "jira",
        valid_source_ids=["jira:a", "jira:b"],
        persisted_disabled_source_ids=["jira:a"],
    )
    assert first == ["jira:a"]

    # Simulate stale persisted values from a concurrent save; UI should keep session value.
    second = ingest_page._effective_disabled_source_ids(
        "jira",
        valid_source_ids=["jira:a", "jira:b"],
        persisted_disabled_source_ids=["jira:b"],
    )
    assert second == ["jira:a"]


def test_effective_disabled_source_ids_resets_when_source_signature_changes(
    monkeypatch: Any,
) -> None:
    fake_state = _FakeStreamlitState({})
    monkeypatch.setattr(ingest_page, "st", fake_state)

    ingest_page._effective_disabled_source_ids(
        "helix",
        valid_source_ids=["helix:a", "helix:b"],
        persisted_disabled_source_ids=["helix:a"],
    )
    out = ingest_page._effective_disabled_source_ids(
        "helix",
        valid_source_ids=["helix:c", "helix:d"],
        persisted_disabled_source_ids=["helix:d"],
    )
    assert out == ["helix:d"]


def test_selected_source_ids_from_selector_df_falls_back_to_row_order_when_hidden_ids() -> None:
    selector_df = pd.DataFrame(
        [
            {"__ingest__": True},
            {"__ingest__": False},
            {"__ingest__": "true"},
        ]
    )
    out = ingest_page._selected_source_ids_from_selector_df(
        selector_df,
        valid_source_ids=["A-1", "A-2", "A-3"],
    )
    assert out == ["A-1", "A-3"]


def test_disabled_source_ids_from_selected_preserves_valid_order() -> None:
    out = ingest_page._disabled_source_ids_from_selected(
        valid_source_ids=["A-1", "A-2", "A-3"],
        selected_source_ids=["A-3", "A-1"],
    )
    assert out == ["A-2"]
