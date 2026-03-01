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


def test_inject_missing_jira_descriptions_from_summary() -> None:
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

    assert out.loc[0, "description"] == "No se visualiza pantalla"
