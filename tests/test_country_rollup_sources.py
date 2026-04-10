from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bug_resolution_radar.config import Settings, country_rollup_sources, rollup_source_ids
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.repositories.issues_store import save_issues_doc


def test_country_rollup_sources_keeps_only_configured_source_ids() -> None:
    settings = Settings(
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"Core","jql":"project = CORE"},'
            '{"country":"México","alias":"Retail","jql":"project = RET"}]'
        ),
        COUNTRY_ROLLUP_SOURCES_JSON=(
            '[{"country":"México","source_ids":["jira:mexico:core","jira:mexico:missing"]}]'
        ),
    )

    out = country_rollup_sources(settings)

    assert out == {"México": ["jira:mexico:core"]}


def test_rollup_source_ids_falls_back_to_available_when_not_configured() -> None:
    settings = Settings(
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
        COUNTRY_ROLLUP_SOURCES_JSON="[]",
    )

    out = rollup_source_ids(
        settings,
        country="México",
        available_source_ids=["jira:mexico:core", "jira:mexico:retail"],
    )

    assert out == ["jira:mexico:core", "jira:mexico:retail"]


def test_country_rollup_sources_keeps_dataset_backed_source_ids(tmp_path: Path) -> None:
    data_path = (tmp_path / "issues.json").resolve()
    now = datetime.now(timezone.utc).isoformat()
    save_issues_doc(
        str(data_path),
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="RAD-1",
                    summary="Error en pagos",
                    status="Open",
                    type="Bug",
                    priority="High",
                    created=now,
                    updated=now,
                    assignee="Alice",
                    country="México",
                    source_alias="S1.SENDA",
                    source_id="jira:mexico:s1-senda",
                    source_type="jira",
                    url="https://jira.example.com/browse/RAD-1",
                )
            ]
        ),
    )
    settings = Settings(
        DATA_PATH=str(data_path),
        COUNTRY_ROLLUP_SOURCES_JSON=(
            '[{"country":"México","source_ids":["jira:mexico:s1-senda","jira:mexico:missing"]}]'
        ),
    )

    out = country_rollup_sources(settings)

    assert out == {"México": ["jira:mexico:s1-senda"]}
