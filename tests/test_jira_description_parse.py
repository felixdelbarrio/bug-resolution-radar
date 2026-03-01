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


def test_jira_description_to_text_supports_rendered_html() -> None:
    html = "<p>SO: Android</p><p>Path:</p><ol><li>Paso 1</li><li>Paso 2</li></ol>"
    out = jira_ingest._jira_description_to_text(html)
    assert "SO: Android" in out
    assert "Path:" in out
    assert "Paso 1" in out
    assert "Paso 2" in out
