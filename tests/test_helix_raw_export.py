from __future__ import annotations

import pandas as pd

from bug_resolution_radar.models.schema_helix import HelixWorkItem
from bug_resolution_radar.services.helix_raw_export import (
    build_helix_raw_export_frame,
)


def test_build_helix_raw_export_frame_returns_none_for_mixed_scope() -> None:
    df = pd.DataFrame(
        [
            {"key": "INC-1", "source_type": "helix", "source_id": "helix:mx:web"},
            {"key": "JIRA-1", "source_type": "jira", "source_id": "jira:mx:web"},
        ]
    )

    out = build_helix_raw_export_frame(df, helix_items_by_merge_key={})

    assert out is None


def test_build_helix_raw_export_frame_builds_raw_rows_and_front_columns() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "INC-1",
                "source_type": "helix",
                "source_id": "helix:mx:web",
                "url": "https://smartit/inc-1",
            }
        ]
    )
    item = HelixWorkItem(
        id="INC-1",
        source_id="helix:mx:web",
        url="https://smartit/inc-1",
        raw_fields={
            "Status": "Open",
            "Submit Date": "2026-02-25T10:44:24+00:00",
            "Nested": {"a": 1},
        },
    )

    out = build_helix_raw_export_frame(
        df,
        helix_items_by_merge_key={"helix:mx:web::INC-1": item},
    )

    assert isinstance(out, pd.DataFrame)
    assert list(out.columns[:2]) == ["ID de la Incidencia", "__item_url__"]
    assert out.loc[0, "ID de la Incidencia"] == "INC-1"
    assert out.loc[0, "__item_url__"] == "https://smartit/inc-1"
    assert out.loc[0, "Status"] == "Open"
    assert out.loc[0, "Nested"] == '{"a": 1}'


def test_build_helix_raw_export_frame_keeps_row_when_raw_fields_are_empty() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "INC-2",
                "source_type": "helix",
                "source_id": "helix:mx:web",
                "url": "https://smartit/inc-2",
            }
        ]
    )
    item = HelixWorkItem(
        id="INC-2",
        source_id="helix:mx:web",
        url="https://smartit/inc-2",
        raw_fields={},
    )

    out = build_helix_raw_export_frame(
        df,
        helix_items_by_merge_key={"helix:mx:web::INC-2": item},
    )

    assert isinstance(out, pd.DataFrame)
    assert len(out) == 1
    assert out.loc[0, "ID de la Incidencia"] == "INC-2"
