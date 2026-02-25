from __future__ import annotations

import pandas as pd

from bug_resolution_radar.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.ui.common import df_from_issues_doc


def test_df_from_issues_doc_parses_mixed_jira_and_helix_datetime_formats() -> None:
    doc = IssuesDocument(
        issues=[
            NormalizedIssue(
                key="JIRA-1",
                summary="Jira issue",
                status="Analysing",
                type="Bug",
                priority="High",
                created="2026-01-01T20:05:17.000+0000",
                updated="2026-01-07T22:46:15.000+0000",
                resolved="2026-01-08T10:00:00.000+0000",
            ),
            NormalizedIssue(
                key="INC000104226433",
                summary="Helix issue",
                status="Closed",
                type="Incident",
                priority="Low",
                created="2026-01-01T20:05:17+00:00",
                updated="2026-01-07T22:46:15+00:00",
                resolved="2026-01-08T10:00:00+00:00",
                source_type="helix",
            ),
        ]
    )

    df = df_from_issues_doc(doc)

    assert isinstance(df["created"].dtype, pd.DatetimeTZDtype)
    assert isinstance(df["updated"].dtype, pd.DatetimeTZDtype)
    assert isinstance(df["resolved"].dtype, pd.DatetimeTZDtype)

    helix_row = df.loc[df["key"] == "INC000104226433"].iloc[0]
    assert pd.notna(helix_row["created"])
    assert pd.notna(helix_row["updated"])
    assert pd.notna(helix_row["resolved"])
    assert helix_row["created"] == pd.Timestamp("2026-01-01T20:05:17Z")
