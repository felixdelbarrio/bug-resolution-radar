from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bug_resolution_radar.config import Settings, build_source_id
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.repositories.issues_store import save_issues_doc
from bug_resolution_radar.services.settings_contracts import (
    _rollup_eligible_sources_by_country,
    save_settings_payload,
)


def _seed_issue(path: Path, *, country: str, alias: str, source_type: str) -> str:
    source_id = build_source_id(source_type, country, alias)
    now = datetime.now(timezone.utc).isoformat()
    save_issues_doc(
        str(path),
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
                    country=country,
                    source_alias=alias,
                    source_id=source_id,
                    source_type=source_type,
                    url="https://jira.example.com/browse/RAD-1",
                )
            ]
        ),
    )
    return source_id


def test_rollup_eligible_sources_include_configured_sources_without_results(tmp_path: Path) -> None:
    settings = Settings(
        DATA_PATH=str((tmp_path / "issues.json").resolve()),
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
        HELIX_SOURCES_JSON="[]",
    )

    out = _rollup_eligible_sources_by_country(settings)

    assert out == {
        "México": [
            {
                "source_id": "jira:mexico:core",
                "source_type": "jira",
                "country": "México",
                "alias": "Core",
                "jql": "project = CORE",
            }
        ]
    }


def test_rollup_eligible_sources_fall_back_to_inferred_dataset_sources(tmp_path: Path) -> None:
    data_path = (tmp_path / "issues.json").resolve()
    source_id = _seed_issue(data_path, country="México", alias="Retail", source_type="jira")
    settings = Settings(
        DATA_PATH=str(data_path),
        JIRA_SOURCES_JSON="[]",
        HELIX_SOURCES_JSON="[]",
    )

    out = _rollup_eligible_sources_by_country(settings)

    assert out["México"] == [
        {
            "source_id": source_id,
            "country": "México",
            "alias": "Retail",
            "source_type": "jira",
        }
    ]


def test_period_functionality_detail_setting_defaults_off() -> None:
    settings = Settings()

    assert str(settings.PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED).strip().lower() == "false"
    assert str(settings.PERIOD_REPORT_FINALIST_DISCREPANCIES_ENABLED).strip().lower() == "false"
    assert str(settings.FINALIST_STATUS_ANALYSIS_MODE).strip() == "selected_sources"


def test_save_settings_payload_persists_period_report_preferences(
    monkeypatch, tmp_path: Path
) -> None:
    import bug_resolution_radar.config as cfg

    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(cfg, "ENV_PATH", env_path)
    monkeypatch.setattr(cfg, "ENV_EXAMPLE_PATH", tmp_path / ".env.example")

    payload = {
        "values": {
            **Settings().model_dump(),
            "PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED": "true",
            "PERIOD_REPORT_FINALIST_DISCREPANCIES_ENABLED": "true",
            "OPEN_ISSUES_FOCUS_MODE": "maestras",
            "FINALIST_STATUS_ANALYSIS_MODE": "country_finalist_status",
        },
        "supportedCountries": ["México"],
        "jiraSources": [],
        "helixSources": [],
        "countryRollupSources": {},
        "jiraDisabledSourceIds": [],
        "helixDisabledSourceIds": [],
    }

    saved = save_settings_payload(payload)

    values = saved["values"]
    assert values["PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED"] == "true"
    assert values["PERIOD_REPORT_FINALIST_DISCREPANCIES_ENABLED"] == "true"
    assert values["OPEN_ISSUES_FOCUS_MODE"] == "maestras"
    assert values["FINALIST_STATUS_ANALYSIS_MODE"] == "country_finalist_status"
    persisted = env_path.read_text(encoding="utf-8")
    assert "PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED=true" in persisted
    assert "PERIOD_REPORT_FINALIST_DISCREPANCIES_ENABLED=true" in persisted
    assert "OPEN_ISSUES_FOCUS_MODE=maestras" in persisted
    assert "FINALIST_STATUS_ANALYSIS_MODE=country_finalist_status" in persisted
