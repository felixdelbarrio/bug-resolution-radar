from __future__ import annotations

from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.ui.pages.ingest_page import (
    _helix_last_ingest_payload,
    _jira_last_ingest_payload,
)


def test_jira_last_ingest_payload_uses_stored_values_when_not_reset() -> None:
    doc = IssuesDocument(
        schema_version="1.0",
        ingested_at="2026-02-20T10:00:00+00:00",
        jira_base_url="https://jira.example.com",
        query="project = APP",
        issues=[
            NormalizedIssue(
                key="APP-1",
                summary="Issue Jira",
                status="Open",
                type="Bug",
                priority="High",
                source_type="jira",
                source_id="jira:mx:core",
            ),
            NormalizedIssue(
                key="INC-1",
                summary="Issue Helix",
                status="Open",
                type="Helix",
                priority="Medium",
                source_type="helix",
                source_id="helix:mx:smartit",
            ),
        ],
    )

    payload = _jira_last_ingest_payload(doc, reset_display=False)

    assert payload["ingested_at"] == "2026-02-20T10:00:00+00:00"
    assert payload["jira_base_url"] == "https://jira.example.com"
    assert payload["query"] == "project = APP"
    assert payload["jira_source_count"] == 1
    assert payload["issues_count"] == 2


def test_jira_last_ingest_payload_resets_values_when_running() -> None:
    doc = IssuesDocument(
        schema_version="1.0",
        ingested_at="2026-02-20T10:00:00+00:00",
        jira_base_url="https://jira.example.com",
        query="project = APP",
    )

    payload = _jira_last_ingest_payload(doc, reset_display=True)

    assert payload["schema_version"] == "1.0"
    assert payload["ingested_at"] == ""
    assert payload["jira_base_url"] == ""
    assert payload["query"] == ""
    assert payload["jira_source_count"] == 0
    assert payload["issues_count"] == 0


def test_helix_last_ingest_payload_uses_stored_values_when_not_reset() -> None:
    doc = HelixDocument(
        schema_version="1.0",
        ingested_at="2026-02-21T11:00:00+00:00",
        helix_base_url="https://helix.example.com",
        query="country=mx",
        items=[
            HelixWorkItem(id="INC-1", source_id="helix:mx:smartit"),
            HelixWorkItem(id="INC-2", source_id=""),
        ],
    )

    payload = _helix_last_ingest_payload(
        doc,
        helix_path="data/helix_dump.json",
        reset_display=False,
    )

    assert payload["ingested_at"] == "2026-02-21T11:00:00+00:00"
    assert payload["helix_base_url"] == "https://helix.example.com"
    assert payload["query"] == "country=mx"
    assert payload["helix_source_count"] == 1
    assert payload["items_count"] == 2
    assert payload["data_path"] == "data/helix_dump.json"


def test_helix_last_ingest_payload_resets_values_when_running() -> None:
    doc = HelixDocument(schema_version="1.0")

    payload = _helix_last_ingest_payload(
        doc,
        helix_path="data/helix_dump.json",
        reset_display=True,
    )

    assert payload["schema_version"] == "1.0"
    assert payload["ingested_at"] == ""
    assert payload["helix_base_url"] == ""
    assert payload["query"] == ""
    assert payload["helix_source_count"] == 0
    assert payload["items_count"] == 0
    assert payload["data_path"] == "data/helix_dump.json"
