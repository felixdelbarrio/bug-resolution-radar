from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.repositories.issues_store import (
    load_issues_df,
    load_issues_workspace_index,
    save_issues_doc,
)


def test_save_issues_doc_refreshes_workspace_index_and_parquet(tmp_path: Path) -> None:
    data_path = tmp_path / "issues.json"
    source_id = "jira:espana:core"
    now = datetime.now(timezone.utc).isoformat()

    save_issues_doc(
        str(data_path),
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="RAD-1",
                    summary="Error en login",
                    status="Open",
                    type="Bug",
                    priority="High",
                    created=now,
                    updated=now,
                    assignee="Alice",
                    country="España",
                    source_alias="Core",
                    source_id=source_id,
                    source_type="jira",
                    url="https://jira.example.com/browse/RAD-1",
                )
            ]
        ),
    )

    assert data_path.exists()
    assert data_path.with_suffix(".parquet").exists()
    assert data_path.with_suffix(".workspace.json").exists()

    df = load_issues_df(str(data_path))
    index_payload = load_issues_workspace_index(str(data_path))

    assert len(df) == 1
    assert str(df.iloc[0]["source_id"]) == source_id
    assert index_payload["hasData"] is True
    assert index_payload["rowCount"] == 1
    assert index_payload["countries"] == [{"country": "España", "sourceCount": 1}]
    assert index_payload["sourcesByCountry"]["España"][0]["source_id"] == source_id
