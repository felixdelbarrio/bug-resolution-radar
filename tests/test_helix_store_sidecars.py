from __future__ import annotations

import json
from pathlib import Path

from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.helix_store import (
    load_helix_export_df,
    load_helix_meta,
)


def test_helix_repo_save_creates_export_sidecars(tmp_path: Path) -> None:
    path = tmp_path / "helix_dump.json"
    doc = HelixDocument(
        schema_version="1.0",
        ingested_at="2026-04-16T10:00:00+00:00",
        helix_base_url="https://helix.example.com",
        query="'HPD:Help Desk'",
        items=[
            HelixWorkItem(
                id="INC0001",
                source_id="helix:espana:core",
                source_alias="Helix Core",
                url="https://helix.example.com/INC0001",
                raw_fields={
                    "Status": "Open",
                    "Nested": {"channel": "core"},
                },
            )
        ],
    )

    HelixRepo(path).save(doc)

    export_df = load_helix_export_df(str(path))
    meta = load_helix_meta(str(path))

    assert path.with_suffix(".raw.parquet").exists()
    assert path.with_suffix(".meta.json").exists()
    assert len(export_df) == 1
    assert export_df.loc[0, "merge_key"] == "helix:espana:core::INC0001"
    assert export_df.loc[0, "ID de la Incidencia"] == "INC0001"
    assert export_df.loc[0, "__item_url__"] == "https://helix.example.com/INC0001"
    assert export_df.loc[0, "Nested"] == json.dumps({"channel": "core"}, ensure_ascii=False)
    assert meta["items_count"] == 1
    assert meta["helix_source_count"] == 1
    assert meta["query"] == "'HPD:Help Desk'"
