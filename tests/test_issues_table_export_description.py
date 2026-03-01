from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.dashboard.exports.downloads import make_table_export_df


def test_table_export_df_keeps_description_when_present() -> None:
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

    assert "description" in table_df.columns
    assert str(table_df.loc[0, "description"]) == "Descripcion larga"
