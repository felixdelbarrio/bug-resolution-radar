from __future__ import annotations

from bug_resolution_radar.ingest import jira_ingest


def test_jira_description_to_text_supports_plain_string() -> None:
    out = jira_ingest._jira_description_to_text("Texto simple")
    assert out == "Texto simple"


def test_jira_description_to_text_supports_adf_content_tree() -> None:
    adf = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Linea 1"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Linea 2"}]},
        ],
    }

    out = jira_ingest._jira_description_to_text(adf)

    assert "Linea 1" in out
    assert "Linea 2" in out
