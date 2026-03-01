from __future__ import annotations

from typing import Any

import pandas as pd

from bug_resolution_radar.ui.components import issues


class _FakeColumnConfig:
    @staticmethod
    def TextColumn(label: str, width: str | None = None) -> dict[str, str | None]:
        return {"label": label, "width": width}


class _FakeStreamlit:
    def __init__(self) -> None:
        self.column_config = _FakeColumnConfig()
        self.session_state: dict[str, Any] = {}
        self.captured_data = None
        self.captured_kwargs: dict[str, Any] | None = None
        self.next_event: dict[str, object] = {"selection": {"rows": [], "columns": [], "cells": []}}

    def dataframe(self, data: Any, **kwargs: Any) -> dict[str, object]:
        self.captured_data = data
        self.captured_kwargs = kwargs
        return self.next_event

    def warning(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def rerun(self) -> None:
        return None


def test_render_issue_table_native_sanitizes_status_and_priority_with_reset_index(
    monkeypatch: Any,
) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(issues, "st", fake_st)
    monkeypatch.setattr(issues, "open_url_in_configured_browser", lambda *_a, **_k: True)

    display_df = pd.DataFrame(
        {
            "key": ["MEX-1", "MEX-2"],
            "summary": ["A", "B"],
            "description": ["detalle", None],
            "status": ["New", "Blocked"],
            "priority": ["High", "Medium"],
            "url": ["https://jira.local/browse/MEX-1", "https://jira.local/browse/MEX-2"],
            "source_type": ["jira", "jira"],
            "source_id": ["jira:mx", "jira:mx"],
        },
        index=[11, 99],
    )

    issues._render_issue_table_native(
        display_df,
        ["key", "summary", "description", "status", "priority"],
        settings=None,
        table_key="issues_table_test",
        sort_state_prefix="issues",
    )

    assert fake_st.captured_data is not None
    rendered = fake_st.captured_data.data

    assert "__jira_key_display__" in rendered.columns
    assert rendered["__jira_key_display__"].tolist() == ["MEX-1", "MEX-2"]
    assert "key" not in rendered.columns
    assert rendered["status"].tolist() == ["New", "Blocked"]
    assert rendered["priority"].tolist() == ["High", "Medium"]
    assert rendered["description"].tolist() == ["detalle", "—"]
    assert fake_st.captured_kwargs is not None
    assert fake_st.captured_kwargs.get("selection_mode") == ["single-cell", "single-column"]


def test_render_issue_table_native_opens_issue_when_alias_key_cell_is_selected(
    monkeypatch: Any,
) -> None:
    fake_st = _FakeStreamlit()
    fake_st.next_event = {"selection": {"cells": [{"row": 0, "column": "__jira_key_display__"}]}}
    monkeypatch.setattr(issues, "st", fake_st)

    opened: list[tuple[str, str, bool]] = []

    def _fake_open(url: str, browser: str, *, allow_system_default_fallback: bool) -> bool:
        opened.append((url, browser, allow_system_default_fallback))
        return True

    monkeypatch.setattr(issues, "open_url_in_configured_browser", _fake_open)

    display_df = pd.DataFrame(
        {
            "key": ["MEX-1"],
            "summary": ["A"],
            "description": ["detalle"],
            "status": ["New"],
            "priority": ["High"],
            "url": ["https://jira.local/browse/MEX-1"],
            "source_type": ["jira"],
            "source_id": ["jira:mx"],
        }
    )

    issues._render_issue_table_native(
        display_df,
        ["key", "summary", "description", "status", "priority"],
        settings=None,
        table_key="issues_table_test_open",
        sort_state_prefix="issues",
    )

    assert opened == [("https://jira.local/browse/MEX-1", "chrome", False)]


def test_native_link_cell_style_marks_issue_key_as_clickable() -> None:
    style = issues._native_link_cell_style("INCG-123")

    assert f"color: {issues.BBVA_LIGHT.electric_blue};" in style
    assert "text-decoration: underline;" in style
    assert "font-weight: 800;" in style


def test_native_link_cell_style_uses_dark_token_in_dark_mode() -> None:
    style = issues._native_link_cell_style("INCG-123", dark_mode=True)

    assert f"color: {issues.BBVA_DARK.serene_blue};" in style
