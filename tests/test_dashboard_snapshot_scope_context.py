from __future__ import annotations

from typing import Any

import pandas as pd

from bug_resolution_radar.analytics.filtering import FilterState
from bug_resolution_radar.config import Settings
from bug_resolution_radar.services import dashboard_snapshot
from bug_resolution_radar.services.dashboard_snapshot import DashboardQuery, build_issue_rows
from bug_resolution_radar.services.workspace import WorkspaceSelection


def test_build_issue_rows_skips_kpi_computation(monkeypatch: Any, tmp_path) -> None:
    settings = Settings(DATA_PATH=str(tmp_path / "issues.json"))
    query = DashboardQuery(
        workspace=WorkspaceSelection(country="México", source_id="jira:mexico:core"),
        filters=FilterState(status=[], priority=[], assignee=[]),
    )
    scoped_df = pd.DataFrame(
        [
            {
                "key": "MEX-2",
                "summary": "Segunda",
                "description": "Detalle",
                "status": "New",
                "type": "Bug",
                "priority": "High",
                "assignee": "Ana",
                "created": "2026-04-01T10:00:00Z",
                "updated": "2026-04-03T10:00:00Z",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
                "url": "https://jira.local/browse/MEX-2",
            },
            {
                "key": "MEX-1",
                "summary": "Primera",
                "description": "Detalle",
                "status": "Blocked",
                "type": "Bug",
                "priority": "Medium",
                "assignee": "Luis",
                "created": "2026-04-01T10:00:00Z",
                "updated": "2026-04-02T10:00:00Z",
                "resolved": "",
                "source_type": "jira",
                "source_alias": "Core",
                "source_id": "jira:mexico:core",
                "country": "México",
                "url": "https://jira.local/browse/MEX-1",
            },
        ]
    )

    monkeypatch.setattr(
        dashboard_snapshot,
        "load_workspace_dataframe",
        lambda settings, *, query: scoped_df,
    )

    def _fail_compute_kpis(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("build_issue_rows no debe calcular KPIs")

    monkeypatch.setattr(dashboard_snapshot, "compute_kpis", _fail_compute_kpis)
    dashboard_snapshot._scope_context_cache.clear()

    out = build_issue_rows(
        settings, query=query, offset=0, limit=1, sort_by="updated", sort_dir="desc"
    )

    assert out["total"] == 2
    assert [row["key"] for row in out["rows"]] == ["MEX-2"]
