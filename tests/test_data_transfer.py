from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.cloud_projection import (
    REPORT_MIME_TYPE,
    CloudProjectionArtifact,
    canonical_json_bytes,
)
from bug_resolution_radar.services.data_transfer import (
    TransferValidationError,
    _build_archive,
    _decode_archive,
    _manifest,
    export_business_data,
    validate_transfer_package,
)


def _settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for name in ("issues.json", "helix.json", "notes.json"):
        (data_dir / name).write_text("{}", encoding="utf-8")
    return Settings(
        DATA_PATH=str(data_dir / "issues.json"),
        HELIX_DATA_PATH=str(data_dir / "helix.json"),
        NOTES_PATH=str(data_dir / "notes.json"),
        REPORT_PPT_DOWNLOAD_DIR=str(tmp_path / "downloads"),
    )


def _pptx_bytes(marker: bytes = b"canonical-report") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("ppt/presentation.xml", b"<p:presentation/>")
        archive.writestr("ppt/media/marker.bin", marker)
    return output.getvalue()


def _artifact(report_content: bytes) -> CloudProjectionArtifact:
    newsletter = {
        "periodLabel": "España · Periodo 01/07 - 14/07/2026",
        "focusLabel": "Incidencias con criticidad alta",
        "metrics": {
            "createdCurrent": 2,
            "createdPrevious": 1,
            "closedCurrent": 1,
            "closedPrevious": 0,
            "currentOpen": 3,
            "focusOpen": 2,
            "otherOpen": 1,
            "agedOpen": 1,
            "resolutionCurrent": "3.0d",
        },
        "previousOpen": 2,
        "backlogDelta": 1,
        "criticalOpen": 2,
        "evolution": {
            "tone": "negative",
            "title": "Backlog incrementado en 1",
            "summary": "El backlog pasa de 2 a 3.",
            "focus": ["Reducir la cola envejecida."],
            "yearLabel": "Evolución 2026",
            "fortnightLabel": "01-14 JUL",
        },
        "responsibleRollups": [],
        "draft": {
            "subject": "Seguimiento quincenal",
            "greeting": "Buenos días,",
            "intro": "Adjunto el informe.",
            "reportLinkLabel": "Enlace a la presentación",
            "summary": "El backlog aumenta.",
            "responsibleIntro": "Datos por responsable:",
            "responsibleParagraphs": [],
            "closing": "Esperamos que esta información os sea de utilidad.",
        },
    }
    report_hash = hashlib.sha256(report_content).hexdigest()
    scope = {
        "scopeKey": "espana::jira:espana:core",
        "scopeLabel": "España · Core",
        "country": "España",
        "scopeMode": "source",
        "sourceIds": ["jira:espana:core"],
        "dataVersion": "a" * 24,
        "referenceDate": "2026-07-14",
        "immutable": True,
    }
    projection = {
        "schema": "bug-resolution-radar-cloud-projection",
        "schemaVersion": 3,
        "semanticContract": "desktop-authoritative-v3",
        "generatedAt": "2026-07-23T10:00:00+00:00",
        "scope": scope,
        "semantics": {"sourceOfTruth": "desktop"},
        "administration": {"jiraSources": []},
        "views": {
            "overview": {
                "stats": {"issues_total": 3},
                "charts": [
                    {"id": chart_id}
                    for chart_id in (
                        "timeseries",
                        "age_buckets",
                        "open_status_bar",
                        "open_priority_pie",
                        "resolution_hist",
                    )
                ],
            },
            "insights": {"catalog": [], "byId": {}},
            "trends": {
                "catalog": [
                    {"id": chart_id}
                    for chart_id in (
                        "timeseries",
                        "age_buckets",
                        "open_status_bar",
                        "open_priority_pie",
                        "resolution_hist",
                    )
                ],
                "byId": {
                    chart_id: {}
                    for chart_id in (
                        "timeseries",
                        "age_buckets",
                        "open_status_bar",
                        "open_priority_pie",
                        "resolution_hist",
                    )
                },
            },
            "issues": {
                "total": 1,
                "rows": [
                    {
                        "issue_uid": "jira:espana:core::RAD-1",
                        "key": "RAD-1",
                    }
                ],
            },
        },
        "newsletterFacts": newsletter,
        "report": {
            "fileName": "seguimiento-espana.pptx",
            "mimeType": REPORT_MIME_TYPE,
            "sha256": report_hash,
            "bytes": len(report_content),
            "slideCount": 8,
        },
        "factsSha256": hashlib.sha256(canonical_json_bytes(newsletter)).hexdigest(),
    }
    return CloudProjectionArtifact(
        projection=projection,
        projection_content=canonical_json_bytes(projection),
        report_content=report_content,
    )


def test_export_v3_contains_only_projection_and_exact_local_pptx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path)
    report_content = _pptx_bytes()
    artifact = _artifact(report_content)
    monkeypatch.setattr(
        "bug_resolution_radar.services.data_transfer.build_cloud_projection_artifact",
        lambda *_args, **_kwargs: artifact,
    )

    result = export_business_data(
        settings,
        country="España",
        source_ids=["jira:espana:core"],
        scope_mode="source",
    )

    assert result["totalRecords"] == 2
    with zipfile.ZipFile(result["savedPath"]) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "data/projection.json",
            "artifacts/period_followup.pptx",
        }
        manifest = json.loads(archive.read("manifest.json"))
        projection_bytes = archive.read("data/projection.json")
        packaged_report = archive.read("artifacts/period_followup.pptx")

    assert manifest["version"] == 3
    assert manifest["semanticContract"] == "desktop-authoritative-v3"
    assert set(manifest["datasets"]) == {"projection", "report"}
    for descriptor in manifest["datasets"].values():
        assert set(descriptor) == {"path", "sha256", "bytes", "records"}
        assert descriptor["records"] == 1
    assert packaged_report == report_content
    assert manifest["datasets"]["report"]["sha256"] == hashlib.sha256(report_content).hexdigest()
    assert (
        manifest["datasets"]["projection"]["sha256"] == hashlib.sha256(projection_bytes).hexdigest()
    )

    preview = validate_transfer_package(settings, result["fileName"])
    assert preview["valid"] is True
    assert preview["mode"] == "inspect-only"
    assert preview["scope"] == artifact.projection["scope"]


def test_archive_is_byte_deterministic_for_identical_inputs() -> None:
    artifact = _artifact(_pptx_bytes())
    files = {
        "projection": artifact.projection_content,
        "report": artifact.report_content,
    }
    manifest = _manifest(
        created_at=artifact.projection["generatedAt"],
        scope=artifact.projection["scope"],
        files=files,
    )
    assert _build_archive(files, manifest) == _build_archive(files, manifest)


def test_validation_rejects_report_whose_bytes_do_not_match_manifest(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    artifact = _artifact(_pptx_bytes())
    files = {
        "projection": artifact.projection_content,
        "report": artifact.report_content,
    }
    manifest = _manifest(
        created_at=artifact.projection["generatedAt"],
        scope=artifact.projection["scope"],
        files=files,
    )
    path = Path(settings.REPORT_PPT_DOWNLOAD_DIR) / "tampered.brr"
    path.parent.mkdir()
    path.write_bytes(
        _build_archive(
            {"projection": files["projection"], "report": _pptx_bytes(b"changed")},
            manifest,
        )
    )

    with pytest.raises(TransferValidationError, match="manifest"):
        _decode_archive(path)


def test_legacy_and_fake_desktop_import_contracts_are_not_exposed() -> None:
    import bug_resolution_radar.services.data_transfer as transfer

    assert transfer.TRANSFER_VERSION == 3
    assert not hasattr(transfer, "import_transfer_package")
    assert not hasattr(transfer, "list_transfer_packages")
    assert not hasattr(transfer, "optimize_transfer_archive")
