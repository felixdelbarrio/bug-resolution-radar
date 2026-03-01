from __future__ import annotations

from typing import Any

import pandas as pd

from bug_resolution_radar.models.schema_helix import HelixWorkItem
from bug_resolution_radar.ui.dashboard.tabs import issues_tab


class _FakeStreamlitState:
    def __init__(self, session_state: dict[str, object]) -> None:
        self.session_state = session_state


def test_extract_helix_item_description_prefers_detailed_text() -> None:
    item = HelixWorkItem(
        id="INC123",
        summary="BBVA Senda",
        raw_fields={
            "Detailed Decription": "Linea 1\nLinea 2   \nLinea 3",
            "Description": "BBVA Senda",
        },
    )

    out = issues_tab._extract_helix_item_description(item)

    assert out == "Linea 1 Linea 2 Linea 3"


def test_inject_helix_descriptions_uses_source_scoped_key(monkeypatch: Any) -> None:
    df = pd.DataFrame(
        [
            {
                "key": "INC000104250722",
                "summary": "BBVA Senda",
                "source_type": "helix",
                "source_id": "helix:mexico:helix-enterprise-web",
            }
        ]
    )

    monkeypatch.setattr(
        issues_tab,
        "_helix_data_path_and_mtime",
        lambda settings: ("/tmp/helix_dump.json", 123),
    )
    monkeypatch.setattr(
        issues_tab,
        "_load_helix_descriptions_cached",
        lambda path, mtime: {
            "helix:mexico:helix-enterprise-web::INC000104250722": "Descripcion extensa del incidente"
        },
    )

    out = issues_tab._inject_helix_descriptions(df, settings=None)

    assert out.loc[0, "description"] == "Descripcion extensa del incidente"


def test_inject_missing_jira_descriptions_from_summary_keeps_empty() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "MEXBMI1-1",
                "source_type": "jira",
                "summary": "(IOS) [MX] SOFTOKENBNC - No se visualiza pantalla",
                "description": "",
            }
        ]
    )

    out = issues_tab._inject_missing_jira_descriptions_from_summary(df)

    assert out.loc[0, "description"] == ""


def test_apply_shared_sort_status_uses_canonical_order() -> None:
    df = pd.DataFrame(
        [
            {"key": "A-1", "status": "Ready To Verify", "updated": "2026-01-01"},
            {"key": "A-2", "status": "New", "updated": "2026-01-02"},
            {"key": "A-3", "status": "Accepted", "updated": "2026-01-03"},
        ]
    )
    out = issues_tab._apply_shared_sort(df, sort_col="status", sort_asc=True)
    assert out["key"].tolist() == ["A-2", "A-1", "A-3"]


def test_sort_columns_for_controls_prioritizes_known_columns_and_hides_url() -> None:
    df = pd.DataFrame(
        [
            {
                "summary": "A",
                "url": "https://jira.local/browse/A-1",
                "status": "New",
                "priority": "High",
                "updated": "2026-01-01",
                "foo_custom": "x",
            }
        ]
    )

    out = issues_tab._sort_columns_for_controls(df)

    assert out[:4] == ["summary", "status", "priority", "updated"]
    assert "url" not in out
    assert "foo_custom" in out


def test_default_issue_sort_col_prefers_first_table_column_id() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "MEXBMI1-1",
                "summary": "A",
                "status": "New",
                "updated": "2026-01-01",
            }
        ]
    )

    out = issues_tab._default_issue_sort_col(df)

    assert out == "key"


def test_ensure_shared_sort_state_falls_back_to_first_option_without_forcing_sort_col(
    monkeypatch: Any,
) -> None:
    fake_state = {"issues::sort_col": "non_existing_col"}
    monkeypatch.setattr(issues_tab, "st", _FakeStreamlitState(fake_state))
    df = pd.DataFrame(
        [
            {"key": "MEXBMI1-1", "summary": "A", "status": "New"},
        ]
    )

    sort_col, _ = issues_tab._ensure_shared_sort_state(df, key_prefix="issues")

    assert sort_col == "key"
    assert fake_state["issues::sort_col"] == "non_existing_col"


def test_apply_shared_like_filter_matches_selected_sort_column_case_insensitive(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        issues_tab,
        "st",
        _FakeStreamlitState({"issues::sort_like_query": "mexbmi1-2834"}),
    )
    df = pd.DataFrame(
        [
            {"key": "MEXBMI1-283490", "summary": "uno"},
            {"key": "ABC-1", "summary": "dos"},
        ]
    )

    out = issues_tab._apply_shared_like_filter(df, sort_col="key", key_prefix="issues")

    assert out["key"].tolist() == ["MEXBMI1-283490"]


def test_apply_shared_like_filter_uses_literal_like_not_regex(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        issues_tab,
        "st",
        _FakeStreamlitState({"issues::sort_like_query": "A.B"}),
    )
    df = pd.DataFrame(
        [
            {"summary": "A.B issue"},
            {"summary": "ACB issue"},
        ]
    )

    out = issues_tab._apply_shared_like_filter(df, sort_col="summary", key_prefix="issues")

    assert out["summary"].tolist() == ["A.B issue"]
