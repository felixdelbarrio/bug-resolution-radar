from __future__ import annotations

import json
from pathlib import Path

from bug_resolution_radar.config import Settings
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.services.source_maintenance import (
    cache_inventory,
    purge_source_cache,
    reset_cache_store,
    remove_helix_source_from_settings,
    remove_jira_source_from_settings,
    source_cache_impact,
)
from bug_resolution_radar.ui.common import save_issues_doc
from bug_resolution_radar.ui.insights.learning_store import InsightsLearningStore


def test_remove_jira_source_from_settings_clears_legacy_fallback() -> None:
    settings = Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"Core MX","jql":"status = Open"},'
            '{"country":"España","alias":"Retail ES","jql":"project = RETAIL"}]'
        ),
        JIRA_JQL="project = LEGACY",
    )

    updated, removed = remove_jira_source_from_settings(settings, "jira:mexico:core-mx")
    assert removed is True
    rows = json.loads(updated.JIRA_SOURCES_JSON)
    assert len(rows) == 1
    assert rows[0]["alias"] == "Retail ES"
    assert updated.JIRA_JQL == ""


def test_remove_helix_source_from_settings_clears_legacy_fallback() -> None:
    settings = Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        HELIX_SOURCES_JSON=(
            '[{"country":"México","alias":"MX SmartIT","organization":"ORG1"},'
            '{"country":"España","alias":"ES SmartIT","organization":"ORG2"}]'
        ),
        HELIX_BASE_URL="https://helix.example.com",
    )

    updated, removed = remove_helix_source_from_settings(settings, "helix:mexico:mx-smartit")
    assert removed is True
    rows = json.loads(updated.HELIX_SOURCES_JSON)
    assert len(rows) == 1
    assert rows[0]["alias"] == "ES SmartIT"
    assert "base_url" not in rows[0]
    assert "browser" not in rows[0]
    assert "proxy" not in rows[0]
    assert "ssl_verify" not in rows[0]
    assert updated.HELIX_BASE_URL == "https://helix.example.com"


def test_purge_source_cache_removes_issues_helix_and_learning(tmp_path: Path) -> None:
    issues_path = tmp_path / "issues.json"
    helix_path = tmp_path / "helix_dump.json"
    learning_path = tmp_path / "insights_learning.json"

    issues_doc = IssuesDocument(
        schema_version="1.0",
        ingested_at="2026-01-01T00:00:00+00:00",
        jira_base_url="https://jira.example.com",
        query="multi-source",
        issues=[
            NormalizedIssue(
                key="J-1",
                summary="Jira MX",
                status="Open",
                type="Bug",
                priority="High",
                source_type="jira",
                source_alias="Core MX",
                source_id="jira:mexico:core-mx",
            ),
            NormalizedIssue(
                key="H-1",
                summary="Helix ES",
                status="Open",
                type="Helix",
                priority="Medium",
                source_type="helix",
                source_alias="ES SmartIT",
                source_id="helix:espana:es-smartit",
            ),
        ],
    )
    save_issues_doc(str(issues_path), issues_doc)

    helix_repo = HelixRepo(helix_path)
    helix_repo.save(
        HelixDocument(
            schema_version="1.0",
            ingested_at="2026-01-01T00:00:00+00:00",
            helix_base_url="https://helix.example.com",
            query="multi-source",
            items=[
                HelixWorkItem(
                    id="H-1",
                    summary="Item ES",
                    source_alias="ES SmartIT",
                    source_id="helix:espana:es-smartit",
                ),
                HelixWorkItem(
                    id="H-2",
                    summary="Item MX",
                    source_alias="MX SmartIT",
                    source_id="helix:mexico:mx-smartit",
                ),
            ],
        )
    )

    learning_store = InsightsLearningStore(learning_path)
    learning_store.load()
    learning_store.set_scope(
        "España::helix:espana:es-smartit",
        state={"seen": {"a": 1}},
        interactions=3,
        country="España",
        source_id="helix:espana:es-smartit",
    )
    learning_store.set_scope(
        "México::jira:mexico:core-mx",
        state={"seen": {"b": 2}},
        interactions=5,
        country="México",
        source_id="jira:mexico:core-mx",
    )
    learning_store.save()

    settings = Settings(
        DATA_PATH=str(issues_path),
        HELIX_DATA_PATH=str(helix_path),
        INSIGHTS_LEARNING_PATH=str(learning_path),
    )

    stats = purge_source_cache(settings, "helix:espana:es-smartit")
    assert stats["issues_removed"] == 1
    assert stats["helix_items_removed"] == 1
    assert stats["learning_scopes_removed"] == 1

    reloaded_issues = json.loads(issues_path.read_text(encoding="utf-8"))
    reloaded_issue_sids = [str(x.get("source_id") or "") for x in reloaded_issues.get("issues", [])]
    assert "helix:espana:es-smartit" not in reloaded_issue_sids

    reloaded_helix = helix_repo.load()
    assert reloaded_helix is not None
    reloaded_helix_sids = [str(x.source_id or "") for x in reloaded_helix.items]
    assert "helix:espana:es-smartit" not in reloaded_helix_sids

    learning_raw = json.loads(learning_path.read_text(encoding="utf-8"))
    scopes = learning_raw.get("scopes", {})
    assert "España::helix:espana:es-smartit" not in scopes
    assert "México::jira:mexico:core-mx" in scopes


def test_source_cache_impact_preview_counts_records(tmp_path: Path) -> None:
    issues_path = tmp_path / "issues.json"
    helix_path = tmp_path / "helix_dump.json"
    learning_path = tmp_path / "insights_learning.json"

    save_issues_doc(
        str(issues_path),
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="J-1",
                    summary="Jira MX",
                    status="Open",
                    type="Bug",
                    priority="High",
                    source_type="jira",
                    source_alias="Core MX",
                    source_id="jira:mexico:core-mx",
                ),
                NormalizedIssue(
                    key="J-2",
                    summary="Jira MX #2",
                    status="Open",
                    type="Bug",
                    priority="Medium",
                    source_type="jira",
                    source_alias="Core MX",
                    source_id="jira:mexico:core-mx",
                ),
            ]
        ),
    )

    HelixRepo(helix_path).save(
        HelixDocument(
            items=[
                HelixWorkItem(
                    id="H-1",
                    summary="Item ES",
                    source_alias="ES SmartIT",
                    source_id="helix:espana:es-smartit",
                )
            ]
        )
    )

    learning_store = InsightsLearningStore(learning_path)
    learning_store.load()
    learning_store.set_scope(
        "México::jira:mexico:core-mx",
        state={"seen": {"a": 1}},
        interactions=1,
        country="México",
        source_id="jira:mexico:core-mx",
    )
    learning_store.save()

    settings = Settings(
        DATA_PATH=str(issues_path),
        HELIX_DATA_PATH=str(helix_path),
        INSIGHTS_LEARNING_PATH=str(learning_path),
    )

    impact = source_cache_impact(settings, "jira:mexico:core-mx")
    assert impact["issues_records"] == 2
    assert impact["helix_items"] == 0
    assert impact["learning_scopes"] == 1


def test_cache_inventory_and_reset_store(tmp_path: Path) -> None:
    issues_path = tmp_path / "issues.json"
    helix_path = tmp_path / "helix_dump.json"
    learning_path = tmp_path / "insights_learning.json"

    save_issues_doc(
        str(issues_path),
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="J-1",
                    summary="Issue",
                    status="Open",
                    type="Bug",
                    priority="Low",
                    source_id="jira:mexico:core-mx",
                )
            ]
        ),
    )
    HelixRepo(helix_path).save(
        HelixDocument(
            items=[
                HelixWorkItem(
                    id="H-1",
                    summary="Helix issue",
                    source_id="helix:mexico:mx-smartit",
                )
            ]
        )
    )
    learning_store = InsightsLearningStore(learning_path)
    learning_store.load()
    learning_store.set_scope(
        "México::jira:mexico:core-mx",
        state={"seen": {"x": 1}},
        interactions=2,
        country="México",
        source_id="jira:mexico:core-mx",
    )
    learning_store.save()

    settings = Settings(
        DATA_PATH=str(issues_path),
        HELIX_DATA_PATH=str(helix_path),
        INSIGHTS_LEARNING_PATH=str(learning_path),
    )

    inv = {str(row["cache_id"]): row for row in cache_inventory(settings)}
    assert inv["issues"]["records"] == 1
    assert inv["helix"]["records"] == 1
    assert inv["learning"]["records"] == 1

    issue_reset = reset_cache_store(settings, "issues")
    helix_reset = reset_cache_store(settings, "helix")
    learning_reset = reset_cache_store(settings, "learning")

    assert issue_reset["before"] == 1
    assert issue_reset["after"] == 0
    assert helix_reset["before"] == 1
    assert helix_reset["after"] == 0
    assert learning_reset["before"] == 1
    assert learning_reset["after"] == 0

    inv_after = {str(row["cache_id"]): row for row in cache_inventory(settings)}
    assert inv_after["issues"]["records"] == 0
    assert inv_after["helix"]["records"] == 0
    assert inv_after["learning"]["records"] == 0
