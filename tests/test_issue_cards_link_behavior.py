from __future__ import annotations

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.components import issues


def test_build_issue_open_href_encodes_url_and_source_type() -> None:
    href = issues.build_issue_open_href(
        "https://jira.example.com/browse/ABC-123?x=1&y=2",
        "jira",
    )

    assert href.startswith("?")
    assert (
        "br_open_issue_url=https%3A%2F%2Fjira.example.com%2Fbrowse%2FABC-123%3Fx%3D1%26y%3D2"
        in href
    )
    assert "br_open_issue_source=jira" in href


def test_build_issue_open_href_can_embed_key_label_for_link_text() -> None:
    href = issues.build_issue_open_href(
        "https://jira.example.com/browse/ABC-123",
        "jira",
        key_label="ABC-123",
    )

    assert "br_open_issue_key=ABC-123" in href
    assert "br_open_issue_source=jira" in href


def test_issue_key_link_html_renders_anchor_with_encoded_query() -> None:
    html = issues._issue_key_link_html(
        url="https://jira.example.com/browse/ABC-123?x=1&y=2",
        source_type="jira",
        key_label="ABC-123",
    )

    assert 'class="issue-key-anchor"' in html
    assert "href=\"?br_open_issue_key=ABC-123&amp;br_open_issue_url=" in html
    assert "br_open_issue_source=jira" in html
    assert ">ABC-123<" in html


def test_issue_key_link_html_renders_disabled_label_when_url_missing() -> None:
    html = issues._issue_key_link_html(url="", source_type="jira", key_label="ABC-123")

    assert "issue-key-anchor-disabled" in html
    assert "<a " not in html
    assert ">ABC-123<" in html


def test_title_and_description_from_row_prefers_explicit_description() -> None:
    title, description = issues._title_and_description_from_row(
        {"summary": "Titulo", "description": "Descripción extendida"}
    )

    assert title == "Titulo"
    assert description == "Descripción extendida"


def test_title_and_description_from_row_splits_summary_when_possible() -> None:
    title, description = issues._title_and_description_from_row(
        {"summary": "(IOS) [MX] SOFTOKENBNC - No se tiene funcionalidad en operaciones pendientes"}
    )

    assert title == "(IOS) [MX] SOFTOKENBNC"
    assert description == "No se tiene funcionalidad en operaciones pendientes"


def test_browser_for_source_type_uses_configured_browser() -> None:
    settings = Settings(JIRA_BROWSER="edge", HELIX_BROWSER="chrome")

    assert issues._browser_for_source_type(settings, "jira") == "edge"
    assert issues._browser_for_source_type(settings, "helix") == "chrome"


def test_title_and_description_from_row_without_description_avoids_duplication() -> None:
    title, description = issues._title_and_description_from_row({"summary": "BBVA Senda"})

    assert title == "BBVA Senda"
    assert description == ""


def test_selected_cell_from_event_supports_dict_shape() -> None:
    row, col = issues._selected_cell_from_event(
        {"selection": {"cells": [{"row": 3, "column": "key"}]}}
    )

    assert row == 3
    assert col == "key"


def test_jira_label_from_row_fallbacks_to_summary_key_pattern() -> None:
    label = issues._jira_label_from_row(
        {
            "key": "",
            "url": "",
            "summary": "MEXBMI1-283384 - Error de dashboard",
            "source_type": "jira",
        }
    )

    assert label == "MEXBMI1-283384"


def test_handle_issue_link_open_request_noops_without_query_params(monkeypatch) -> None:
    class _FakeStNoQuery:
        pass

    monkeypatch.setattr(issues, "st", _FakeStNoQuery())
    issues.handle_issue_link_open_request(settings=Settings())
