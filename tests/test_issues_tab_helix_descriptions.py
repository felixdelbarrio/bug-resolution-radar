from __future__ import annotations

from typing import Any

import pandas as pd

from bug_resolution_radar.models.schema_helix import HelixWorkItem
from bug_resolution_radar.ui.dashboard.tabs import issues_tab


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

    assert out[:4] == ["updated", "status", "priority", "summary"]
    assert "url" not in out
    assert "foo_custom" in out
