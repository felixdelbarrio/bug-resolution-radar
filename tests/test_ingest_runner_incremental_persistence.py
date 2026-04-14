from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from bug_resolution_radar.config import Settings
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem

ingest_runner = importlib.import_module("bug_resolution_radar.services.ingest_runner")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        DATA_PATH=str((tmp_path / "issues.json").resolve()),
        HELIX_DATA_PATH=str((tmp_path / "helix.json").resolve()),
    )


def test_run_jira_ingest_persists_checkpoint_after_each_source(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    issue_snapshots: list[IssuesDocument] = []

    def _fake_load_issues_doc(path: str) -> IssuesDocument:
        del path
        return IssuesDocument.empty()

    def _fake_save_issues_doc(path: str, doc: IssuesDocument) -> None:
        del path
        issue_snapshots.append(doc.model_copy(deep=True))

    def _fake_ingest_jira(*, source: dict[str, str], existing_doc: IssuesDocument, **_: Any):
        doc = existing_doc.model_copy(deep=True)
        source_id = str(source.get("source_id") or "").strip()
        doc.issues.append(
            NormalizedIssue(
                key=f"J-{len(doc.issues) + 1}",
                summary=f"Issue {source_id}",
                status="Open",
                type="Bug",
                priority="High",
                country=str(source.get("country") or "").strip(),
                source_alias=str(source.get("alias") or "").strip(),
                source_id=source_id,
                source_type="jira",
            )
        )
        return True, f"{source_id}: ok", doc

    monkeypatch.setattr(ingest_runner, "load_issues_doc", _fake_load_issues_doc)
    monkeypatch.setattr(ingest_runner, "save_issues_doc", _fake_save_issues_doc)
    monkeypatch.setattr(ingest_runner, "ingest_jira", _fake_ingest_jira)

    result = ingest_runner.run_jira_ingest(
        settings,
        selected_sources=[
            {"source_id": "jira:mx:a", "country": "México", "alias": "A"},
            {"source_id": "jira:mx:b", "country": "México", "alias": "B"},
        ],
    )

    assert result["state"] == "success"
    assert result["success_count"] == 2
    assert len(issue_snapshots) == 2
    assert [len(snapshot.issues) for snapshot in issue_snapshots] == [1, 2]


def test_run_helix_ingest_persists_partial_and_success_checkpoints_per_source(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    issue_snapshots: list[IssuesDocument] = []
    helix_snapshots: list[HelixDocument] = []

    class _FakeHelixRepo:
        def __init__(self, _: Path) -> None:
            pass

        def load(self) -> HelixDocument:
            return HelixDocument.empty()

        def save(self, doc: HelixDocument) -> None:
            helix_snapshots.append(doc.model_copy(deep=True))

    def _fake_load_issues_doc(path: str) -> IssuesDocument:
        del path
        return IssuesDocument.empty()

    def _fake_save_issues_doc(path: str, doc: IssuesDocument) -> None:
        del path
        issue_snapshots.append(doc.model_copy(deep=True))

    def _fake_ingest_helix(**kwargs: Any):
        source_id = str(kwargs.get("source_id") or "").strip()
        country = str(kwargs.get("country") or "").strip()
        alias = str(kwargs.get("source_alias") or "").strip()
        item = HelixWorkItem(
            id=f"{source_id}-1",
            summary=f"Helix {source_id}",
            status="Open",
            country=country,
            source_alias=alias,
            source_id=source_id,
        )
        doc = HelixDocument.empty()
        doc.helix_base_url = "https://helix.example.com"
        doc.query = source_id
        doc.items = [item]
        if source_id.endswith(":a"):
            return False, f"{source_id}: parcial", doc
        return True, f"{source_id}: ok", doc

    monkeypatch.setattr(ingest_runner, "HelixRepo", _FakeHelixRepo)
    monkeypatch.setattr(ingest_runner, "load_issues_doc", _fake_load_issues_doc)
    monkeypatch.setattr(ingest_runner, "save_issues_doc", _fake_save_issues_doc)
    monkeypatch.setattr(ingest_runner, "ingest_helix", _fake_ingest_helix)

    result = ingest_runner.run_helix_ingest(
        settings,
        selected_sources=[
            {"source_id": "helix:mx:a", "country": "México", "alias": "A"},
            {"source_id": "helix:mx:b", "country": "México", "alias": "B"},
        ],
    )

    assert result["state"] == "partial"
    assert result["success_count"] == 1
    assert len(helix_snapshots) == 2
    assert [len(snapshot.items) for snapshot in helix_snapshots] == [1, 2]
    assert len(issue_snapshots) == 2
    assert [len(snapshot.issues) for snapshot in issue_snapshots] == [1, 2]
