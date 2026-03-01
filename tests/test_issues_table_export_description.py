from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.dashboard.exports.downloads import make_table_export_df


def test_table_df_can_include_description_but_export_can_drop_it() -> None:
    src = pd.DataFrame(
        [
            {
                "key": "INC0001",
                "summary": "Titulo",
                "description": "Descripcion larga",
                "status": "New",
                "priority": "High",
                "url": "https://example.com/INC0001",
            }
        ]
    )

    table_df = make_table_export_df(
        src, preferred_cols=["key", "summary", "description", "status", "url"]
    )
    export_df = table_df.drop(columns=["description"], errors="ignore")

    assert "description" in table_df.columns
    assert "description" not in export_df.columns
