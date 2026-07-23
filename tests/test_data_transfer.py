from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bug_resolution_radar.config import Settings
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.issues_store import load_issues_doc, save_issues_doc
from bug_resolution_radar.services.data_transfer import (
    TransferValidationError,
    export_business_data,
    import_transfer_package,
    list_transfer_packages,
    validate_transfer_package,
)

api_app = importlib.import_module("bug_resolution_radar.api.app")


def _settings(root: Path, *, downloads: Path) -> Settings:
    return Settings(
        DATA_PATH=str(root / "issues.json"),
        HELIX_DATA_PATH=str(root / "helix.json"),
        NOTES_PATH=str(root / "notes.json"),
        INSIGHTS_LEARNING_PATH=str(root / "learning.json"),
        REPORT_PPT_DOWNLOAD_DIR=str(downloads),
    )


def _issue(key: str, *, summary: str = "Resumen") -> NormalizedIssue:
    return NormalizedIssue(
        key=key,
        summary=summary,
        status="Open",
        type="Bug",
        priority="High",
        country="España",
        source_type="jira",
        source_alias="Core",
        source_id="jira:espana:core",
    )


def _seed_source(settings: Settings) -> None:
    save_issues_doc(
        settings.DATA_PATH,
        IssuesDocument(ingested_at="2026-07-22T10:00:00+00:00", issues=[_issue("RAD-1")]),
    )
    HelixRepo(Path(settings.HELIX_DATA_PATH)).save(
        HelixDocument(
            ingested_at="2026-07-22T10:00:00+00:00",
            items=[
                HelixWorkItem(
                    id="INC0001",
                    summary="Incidencia Helix",
                    source_id="helix:espana:core",
                    country="España",
                )
            ],
        )
    )
    Path(settings.NOTES_PATH).write_text(
        json.dumps(
            {
                "RAD-1": {
                    "entries": [
                        {
                            "id": "note-1",
                            "createdAt": "2026-07-22T11:00:00+00:00",
                            "note": "Seguimiento activo",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    Path(settings.INSIGHTS_LEARNING_PATH).write_text(
        json.dumps(
            {
                "version": 1,
                "scopes": {
                    "España::jira:espana:core": {
                        "interactions": 3,
                        "updated_at": "2026-07-22T12:00:00+00:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_export_validate_and_incrementally_import_all_business_data(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    source = _settings(tmp_path / "source", downloads=downloads)
    Path(source.DATA_PATH).parent.mkdir(parents=True)
    _seed_source(source)

    exported = export_business_data(source)

    assert exported["totalRecords"] == 4
    assert Path(exported["savedPath"]).parent == downloads
    assert Path(exported["savedPath"]).suffix == ".brr"
    assert [row["count"] for row in exported["stats"]] == [1, 1, 1, 1]
    assert list_transfer_packages(source)["packages"][0]["fileName"] == exported["fileName"]

    destination = _settings(tmp_path / "destination", downloads=downloads)
    Path(destination.DATA_PATH).parent.mkdir(parents=True)
    save_issues_doc(
        destination.DATA_PATH,
        IssuesDocument(
            issues=[
                _issue("RAD-1", summary="Versión anterior"),
                _issue("RAD-LOCAL", summary="Solo en destino"),
            ]
        ),
    )

    preview = validate_transfer_package(destination, exported["fileName"])

    assert preview["valid"] is True
    assert preview["totalNewRecords"] == 3
    assert preview["totalUpdatedRecords"] == 1
    assert preview["totalUnchangedRecords"] == 0
    issue_preview = next(row for row in preview["stats"] if row["key"] == "issues")
    assert issue_preview == {
        "key": "issues",
        "label": "Incidencias del radar",
        "sourceCount": 1,
        "destinationCount": 2,
        "newCount": 0,
        "updatedCount": 1,
        "unchangedCount": 0,
        "finalCount": 2,
    }

    imported = import_transfer_package(destination, exported["fileName"])

    assert imported["totalNewRecords"] == 3
    assert imported["totalUpdatedRecords"] == 1
    final_issues = load_issues_doc(destination.DATA_PATH)
    assert {item.key for item in final_issues.issues} == {"RAD-1", "RAD-LOCAL"}
    assert next(item for item in final_issues.issues if item.key == "RAD-1").summary == "Resumen"
    assert (
        len((HelixRepo(Path(destination.HELIX_DATA_PATH)).load() or HelixDocument.empty()).items)
        == 1
    )
    assert (
        json.loads(Path(destination.NOTES_PATH).read_text(encoding="utf-8"))["RAD-1"]["entries"][0][
            "note"
        ]
        == "Seguimiento activo"
    )

    repeated = import_transfer_package(destination, exported["fileName"])
    assert repeated["totalNewRecords"] == 0
    assert repeated["totalUpdatedRecords"] == 0
    assert repeated["totalUnchangedRecords"] == 4


def test_validation_rejects_a_package_with_modified_business_data(tmp_path: Path) -> None:
    downloads = tmp_path / "downloads"
    settings = _settings(tmp_path / "source", downloads=downloads)
    Path(settings.DATA_PATH).parent.mkdir(parents=True)
    _seed_source(settings)
    exported = export_business_data(settings)
    archive_path = Path(exported["savedPath"])

    with zipfile.ZipFile(archive_path, mode="a") as archive:
        archive.writestr("data/issues.json", b'{"issues":[]}')

    with pytest.raises(TransferValidationError, match="duplicados"):
        validate_transfer_package(settings, exported["fileName"])


def test_validation_rejects_files_outside_the_configured_download_directory(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "source", downloads=tmp_path / "downloads")
    Path(settings.DATA_PATH).parent.mkdir(parents=True)

    with pytest.raises(TransferValidationError, match="Descargas de Informes"):
        validate_transfer_package(settings, "../otro-respaldo.brr")


def test_api_guides_export_validation_and_import_in_business_language(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path / "source", downloads=tmp_path / "downloads")
    Path(settings.DATA_PATH).parent.mkdir(parents=True)
    _seed_source(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)
    client = TestClient(api_app.create_app())

    exported = client.post("/api/data-transfer/export", json={})
    assert exported.status_code == 200
    assert exported.json()["summary"] == "Respaldo completo creado y preparado para trasladar."

    packages = client.get("/api/data-transfer/packages")
    assert packages.status_code == 200
    assert packages.json()["packages"][0]["fileName"] == exported.json()["fileName"]

    checked = client.post(
        "/api/data-transfer/validate",
        json={"fileName": exported.json()["fileName"]},
    )
    assert checked.status_code == 200
    assert checked.json()["valid"] is True
    assert checked.json()["totalUnchangedRecords"] == 4

    imported = client.post(
        "/api/data-transfer/import",
        json={"fileName": exported.json()["fileName"]},
    )
    assert imported.status_code == 200
    assert "Importación incremental completada" in imported.json()["summary"]

    history = client.get("/api/data-transfer/history")
    assert history.status_code == 200
    assert [item["operation"] for item in history.json()["operations"][:2]] == [
        "import",
        "export",
    ]
