from __future__ import annotations

from pathlib import Path

from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem


def test_issues_document_empty_defaults() -> None:
    doc = IssuesDocument.empty()
    assert doc.schema_version == "1.0"
    assert doc.issues == []
    assert doc.ingested_at


def test_normalized_issue_ignores_extra_fields() -> None:
    issue = NormalizedIssue.model_validate(
        {
            "key": "ABC-1",
            "summary": "Bug de login",
            "status": "New",
            "type": "Bug",
            "priority": "High",
            "extra": "ignored",
        }
    )
    assert issue.key == "ABC-1"
    assert issue.priority == "High"


def test_helix_document_empty_defaults() -> None:
    doc = HelixDocument.empty()
    assert doc.items == []
    assert doc.ingested_at


def test_helix_repo_roundtrip(tmp_path: Path) -> None:
    repo_path = tmp_path / "helix" / "dump.json"
    repo = HelixRepo(repo_path)

    assert repo.load() is None

    doc = HelixDocument(
        schema_version="1.0",
        ingested_at="2025-01-01T00:00:00+00:00",
        helix_base_url="https://helix.example.com",
        query="status:open",
        items=[
            HelixWorkItem(
                id="H-1",
                summary="Incidente",
                status="New",
                priority="High",
                assignee="Alice",
                customer_name="BBVA",
                url="https://helix.example.com/workitem/H-1",
            )
        ],
    )
    repo.save(doc)

    loaded = repo.load()
    assert loaded is not None
    assert len(loaded.items) == 1
    assert loaded.items[0].id == "H-1"
    assert not (repo_path.with_suffix(".json.tmp")).exists()
