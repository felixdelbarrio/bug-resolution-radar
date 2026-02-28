from __future__ import annotations

from bug_resolution_radar.ui.pages.ingest_page import _pick_test_source


def test_pick_test_source_returns_none_for_empty_list() -> None:
    assert _pick_test_source([]) is None


def test_pick_test_source_returns_first_source_copy() -> None:
    selected = [
        {"source_id": "jira:mx:core", "alias": "Core MX"},
        {"source_id": "jira:es:payments", "alias": "Payments ES"},
    ]

    picked = _pick_test_source(selected)

    assert picked == selected[0]
    assert picked is not selected[0]
