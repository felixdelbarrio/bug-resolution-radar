"""Strict one-way desktop-to-GPC handoff packages."""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from bug_resolution_radar.common.security import validate_navigation_url
from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.cloud_projection import (
    PROJECTION_SCHEMA,
    PROJECTION_SCHEMA_VERSION,
    REPORT_MIME_TYPE,
    SEMANTIC_CONTRACT,
    TREND_IDS,
    build_cloud_projection_artifact,
    canonical_json_bytes,
    sha256_bytes,
)
from bug_resolution_radar.services.downloads import ensure_download_dir, save_download_content

TRANSFER_FORMAT = "bug-resolution-radar-transfer"
TRANSFER_VERSION = 3
TRANSFER_EXTENSION = ".brr"
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_EXPANDED_BYTES = 120 * 1024 * 1024
MAX_PROJECTION_BYTES = 24 * 1024 * 1024
MAX_REPORT_BYTES = 20 * 1024 * 1024

_DATASET_FILES = {
    "projection": "data/projection.json",
    "report": "artifacts/period_followup.pptx",
}
_DATASET_LABELS = {
    "projection": "Proyección canónica",
    "report": "Presentación de seguimiento",
}
_PROJECTION_FIELDS = {
    "schema",
    "schemaVersion",
    "semanticContract",
    "generatedAt",
    "scope",
    "semantics",
    "administration",
    "views",
    "newsletterFacts",
    "report",
    "factsSha256",
}
_SCOPE_FIELDS = {
    "scopeKey",
    "scopeLabel",
    "country",
    "scopeMode",
    "sourceIds",
    "dataVersion",
    "referenceDate",
    "immutable",
}
_TRANSFER_LOCK = RLock()


class TransferValidationError(ValueError):
    """Raised when a handoff package violates the current strict contract."""


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _manifest(
    *,
    created_at: str,
    scope: dict[str, Any],
    files: dict[str, bytes],
) -> dict[str, Any]:
    if set(files) != set(_DATASET_FILES):
        raise TransferValidationError("Los artefactos del traslado v3 están incompletos.")
    return {
        "format": TRANSFER_FORMAT,
        "version": TRANSFER_VERSION,
        "createdAt": str(created_at),
        "scope": dict(scope),
        "semanticContract": SEMANTIC_CONTRACT,
        "datasets": {
            key: {
                "path": _DATASET_FILES[key],
                "sha256": sha256_bytes(files[key]),
                "bytes": len(files[key]),
                "records": 1,
            }
            for key in _DATASET_FILES
        },
    }


def _zip_info(name: str, *, compression: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = compression
    info.create_system = 3
    info.external_attr = 0o600 << 16
    return info


def _build_archive(files: dict[str, bytes], manifest: dict[str, Any]) -> bytes:
    """Build byte-stable ZIP output for identical inputs."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", allowZip64=False) as archive:
        archive.writestr(
            _zip_info("manifest.json", compression=zipfile.ZIP_DEFLATED),
            canonical_json_bytes(manifest),
            compresslevel=9,
        )
        archive.writestr(
            _zip_info(_DATASET_FILES["projection"], compression=zipfile.ZIP_DEFLATED),
            files["projection"],
            compresslevel=9,
        )
        # PPTX is already a ZIP; storing it avoids costly, ineffective double compression.
        archive.writestr(
            _zip_info(_DATASET_FILES["report"], compression=zipfile.ZIP_STORED),
            files["report"],
        )
    content = buffer.getvalue()
    if len(content) > MAX_ARCHIVE_BYTES:
        raise TransferValidationError(
            "El traslado supera 40 MB; reduce el ámbito antes de publicarlo en GPC."
        )
    return content


def _history_path(settings: Settings) -> Path:
    return Path(settings.DATA_PATH).expanduser().with_name("data_transfer_history.json")


def _append_history(settings: Settings, record: dict[str, Any]) -> None:
    path = _history_path(settings)
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        operations = raw.get("operations", []) if isinstance(raw, dict) else []
        if not isinstance(operations, list):
            operations = []
        operations.append(record)
        _atomic_write(
            path,
            canonical_json_bytes({"version": 3, "operations": operations[-50:]}),
        )
    except Exception:
        # History is operational metadata and cannot invalidate a completed export.
        return


def transfer_history(settings: Settings) -> dict[str, Any]:
    path = _history_path(settings)
    if not path.exists():
        return {"operations": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TransferValidationError("No se puede leer el historial de traslados.") from exc
    operations = raw.get("operations", []) if isinstance(raw, dict) else []
    return {"operations": list(reversed(operations[-20:])) if isinstance(operations, list) else []}


def _source_revision(settings: Settings) -> tuple[tuple[str, int, int], ...]:
    revisions: list[tuple[str, int, int]] = []
    for raw_path in (
        settings.DATA_PATH,
        settings.HELIX_DATA_PATH,
        settings.NOTES_PATH,
    ):
        path = Path(str(raw_path or "")).expanduser()
        try:
            stat = path.stat()
            revisions.append((str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size)))
        except OSError:
            revisions.append((str(path.resolve()), -1, -1))
    return tuple(revisions)


def export_business_data(
    settings: Settings,
    *,
    country: str = "",
    source_ids: list[str] | None = None,
    scope_mode: str = "country",
) -> dict[str, Any]:
    """Export the immutable cloud projection and exact desktop PPTX."""
    with _TRANSFER_LOCK:
        artifact = None
        for attempt in range(2):
            before = _source_revision(settings)
            try:
                candidate = build_cloud_projection_artifact(
                    settings,
                    country=country,
                    source_ids=list(source_ids or []),
                    scope_mode=scope_mode,
                )
            except TransferValidationError:
                raise
            except ValueError as exc:
                raise TransferValidationError(str(exc)) from exc
            if before == _source_revision(settings):
                artifact = candidate
                break
            if attempt:
                raise TransferValidationError(
                    "Los datos cambiaron durante la exportación; vuelve a intentarlo al terminar "
                    "la ingesta."
                )
        if artifact is None:  # pragma: no cover - defensive guard
            raise TransferValidationError("No se ha podido estabilizar la vista para exportarla.")

        projection = artifact.projection
        files = {
            "projection": artifact.projection_content,
            "report": artifact.report_content,
        }
        created_at = str(projection["generatedAt"])
        manifest = _manifest(
            created_at=created_at,
            scope=dict(projection["scope"]),
            files=files,
        )
        archive_content = _build_archive(files, manifest)
        scope = projection["scope"]
        file_name = (
            f"traslado_radar_{scope['scopeKey'].replace(':', '-')}_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{TRANSFER_EXTENSION}"
        )
        saved_path = save_download_content(settings, file_name=file_name, content=archive_content)
        stats = [{"key": key, "label": _DATASET_LABELS[key], "count": 1} for key in _DATASET_FILES]
        payload = {
            "operation": "export",
            "summary": "Proyección GPC y presentación local exacta preparadas.",
            "completedAt": created_at,
            "fileName": saved_path.name,
            "savedPath": str(saved_path),
            "savedDir": str(saved_path.parent),
            "fileSize": len(archive_content),
            "totalRecords": 2,
            "stats": stats,
            "scope": scope,
            "semanticContract": SEMANTIC_CONTRACT,
            "projectionSha256": manifest["datasets"]["projection"]["sha256"],
            "reportSha256": manifest["datasets"]["report"]["sha256"],
            "reportSlideCount": int(projection["report"]["slideCount"]),
        }
        _append_history(
            settings,
            {
                "id": uuid4().hex,
                "operation": "export",
                "completedAt": created_at,
                "fileName": saved_path.name,
                "totalRecords": 2,
                "headline": f"Vista {scope['scopeLabel']} exportada a GPC",
                "stats": stats,
                "scope": scope,
            },
        )
        return payload


def _safe_archive_path(settings: Settings, file_name: str) -> Path:
    clean_name = Path(str(file_name or "").strip()).name
    if not clean_name or clean_name != str(file_name or "").strip():
        raise TransferValidationError("Selecciona un traslado disponible en Descargas de Informes.")
    if not clean_name.casefold().endswith(TRANSFER_EXTENSION):
        raise TransferValidationError("El fichero seleccionado no es un traslado .brr.")
    directory = ensure_download_dir(settings).resolve()
    candidate = (directory / clean_name).resolve()
    if candidate.parent != directory or not candidate.is_file():
        raise TransferValidationError("El traslado seleccionado ya no está disponible.")
    if candidate.stat().st_size > MAX_ARCHIVE_BYTES:
        raise TransferValidationError("El traslado supera el tamaño máximo admitido.")
    return candidate


def _require_exact_fields(value: Any, fields: set[str], *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise TransferValidationError(f"«{label}» no cumple el contrato v3.")
    return value


def _validate_scope(value: Any) -> dict[str, Any]:
    scope = _require_exact_fields(value, _SCOPE_FIELDS, label="scope")
    source_ids = scope.get("sourceIds")
    if (
        not str(scope.get("scopeKey") or "")
        or not str(scope.get("scopeLabel") or "")
        or not str(scope.get("country") or "")
        or scope.get("scopeMode") not in {"country", "source"}
        or not isinstance(source_ids, list)
        or not source_ids
        or source_ids != sorted(set(str(item) for item in source_ids))
        or scope.get("immutable") is not True
    ):
        raise TransferValidationError("El ámbito inmutable del traslado no es válido.")
    if scope["scopeMode"] == "source" and len(source_ids) != 1:
        raise TransferValidationError("El ámbito por origen debe declarar un único origen.")
    try:
        datetime.fromisoformat(str(scope.get("referenceDate")))
    except ValueError as exc:
        raise TransferValidationError("La fecha de referencia del ámbito no es válida.") from exc
    return scope


def _validate_pptx(content: bytes) -> None:
    if not content or len(content) > MAX_REPORT_BYTES or not content.startswith(b"PK"):
        raise TransferValidationError("La presentación adjunta no es un PPTX válido.")
    try:
        with zipfile.ZipFile(io.BytesIO(content), mode="r") as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "ppt/presentation.xml" not in names:
                raise TransferValidationError(
                    "La presentación adjunta no contiene una estructura Office válida."
                )
            if any(
                "vbaproject.bin" in name.casefold()
                or "/activex/" in name.casefold()
                or "/embeddings/" in name.casefold()
                for name in names
            ):
                raise TransferValidationError(
                    "La presentación contiene elementos ejecutables no permitidos."
                )
    except zipfile.BadZipFile as exc:
        raise TransferValidationError("La presentación adjunta está dañada.") from exc


def _validate_projection(
    projection: Any,
    *,
    manifest: dict[str, Any],
    report_content: bytes,
) -> dict[str, Any]:
    payload = _require_exact_fields(
        projection, _PROJECTION_FIELDS, label=_DATASET_LABELS["projection"]
    )
    if (
        payload.get("schema") != PROJECTION_SCHEMA
        or payload.get("schemaVersion") != PROJECTION_SCHEMA_VERSION
        or payload.get("semanticContract") != SEMANTIC_CONTRACT
    ):
        raise TransferValidationError("La proyección no pertenece al contrato GPC vigente.")
    scope = _validate_scope(payload.get("scope"))
    if scope != manifest.get("scope"):
        raise TransferValidationError("El ámbito del manifest no coincide con la proyección.")
    _require_exact_fields(
        payload.get("views"),
        {"overview", "insights", "trends", "issues"},
        label="projection.views",
    )
    views = payload["views"]
    overview_charts = views["overview"].get("charts")
    overview_chart_ids = (
        [str(chart.get("id") or "") for chart in overview_charts if isinstance(chart, dict)]
        if isinstance(overview_charts, list)
        else []
    )
    if overview_chart_ids != list(TREND_IDS):
        raise TransferValidationError("El catálogo de gráficos de Resumen está incompleto.")
    _require_exact_fields(views["trends"], {"catalog", "byId"}, label="views.trends")
    trend_catalog = views["trends"]["catalog"]
    trend_by_id = views["trends"]["byId"]
    trend_catalog_ids = (
        [str(item.get("id") or "") for item in trend_catalog if isinstance(item, dict)]
        if isinstance(trend_catalog, list)
        else []
    )
    if (
        trend_catalog_ids != list(TREND_IDS)
        or not isinstance(trend_by_id, dict)
        or set(trend_by_id) != set(TREND_IDS)
    ):
        raise TransferValidationError("El catálogo de Tendencias está incompleto.")
    _require_exact_fields(views["insights"], {"catalog", "byId"}, label="views.insights")
    issues = _require_exact_fields(views["issues"], {"total", "rows"}, label="views.issues")
    if not isinstance(issues["rows"], list) or int(issues["total"]) != len(issues["rows"]):
        raise TransferValidationError("La vista materializada de incidencias está incompleta.")
    administration = _require_exact_fields(
        payload.get("administration"), {"jiraSources"}, label="projection.administration"
    )
    if not isinstance(administration["jiraSources"], list):
        raise TransferValidationError("Las fuentes administrativas no son válidas.")
    administration_source_ids: set[str] = set()
    for row in administration["jiraSources"]:
        source = _require_exact_fields(
            row,
            {"sourceId", "alias", "poTeamLeader", "dashboardUrl"},
            label="projection.administration.jiraSources",
        )
        source_id = str(source["sourceId"] or "").strip()
        if (
            not source_id
            or source_id not in scope["sourceIds"]
            or source_id in administration_source_ids
            or not str(source["alias"] or "").strip()
        ):
            raise TransferValidationError("Una fuente administrativa no es válida.")
        administration_source_ids.add(source_id)
        try:
            validate_navigation_url(
                str(source["dashboardUrl"] or ""),
                field_name="Cuadro de mando Jira",
            )
        except ValueError as exc:
            raise TransferValidationError(str(exc)) from exc
    if not isinstance(payload.get("semantics"), dict):
        raise TransferValidationError(
            "La trazabilidad semántica del escritorio no está disponible."
        )
    newsletter = payload.get("newsletterFacts")
    if not isinstance(newsletter, dict):
        raise TransferValidationError("Los hechos de newsletter no son válidos.")
    if sha256_bytes(canonical_json_bytes(newsletter)) != str(payload.get("factsSha256") or ""):
        raise TransferValidationError("La huella de los hechos de newsletter no coincide.")
    report = _require_exact_fields(
        payload.get("report"),
        {"fileName", "mimeType", "sha256", "bytes", "slideCount"},
        label="projection.report",
    )
    descriptor = manifest["datasets"]["report"]
    if (
        report.get("mimeType") != REPORT_MIME_TYPE
        or not str(report.get("fileName") or "").casefold().endswith(".pptx")
        or report.get("sha256") != descriptor["sha256"]
        or report.get("bytes") != descriptor["bytes"]
        or report.get("bytes") != len(report_content)
        or not isinstance(report.get("slideCount"), int)
        or int(report["slideCount"]) <= 0
    ):
        raise TransferValidationError("Los metadatos de la presentación no son coherentes.")
    return payload


def _decode_archive(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            required = {"manifest.json", *_DATASET_FILES.values()}
            if len(names) != len(set(names)):
                raise TransferValidationError("El traslado contiene elementos duplicados.")
            if set(names) != required:
                raise TransferValidationError(
                    "El traslado v3 debe contener exclusivamente la proyección y el PPTX."
                )
            if any(
                info.is_dir()
                or info.filename.startswith(("/", "\\"))
                or ".." in Path(info.filename).parts
                or info.flag_bits & 0x1
                for info in infos
            ):
                raise TransferValidationError("El traslado contiene rutas no permitidas.")
            if sum(max(0, int(info.file_size)) for info in infos) > MAX_EXPANDED_BYTES:
                raise TransferValidationError("El traslado expandido supera el tamaño admitido.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            _require_exact_fields(
                manifest,
                {"format", "version", "createdAt", "scope", "semanticContract", "datasets"},
                label="manifest",
            )
            if (
                manifest.get("format") != TRANSFER_FORMAT
                or manifest.get("version") != TRANSFER_VERSION
                or manifest.get("semanticContract") != SEMANTIC_CONTRACT
            ):
                raise TransferValidationError("Solo se admite el traslado GPC v3 vigente.")
            _validate_scope(manifest.get("scope"))
            datasets = _require_exact_fields(
                manifest.get("datasets"), set(_DATASET_FILES), label="manifest.datasets"
            )
            files: dict[str, bytes] = {}
            for key, member_name in _DATASET_FILES.items():
                descriptor = _require_exact_fields(
                    datasets.get(key),
                    {"path", "sha256", "bytes", "records"},
                    label=f"datasets.{key}",
                )
                content = archive.read(member_name)
                if (
                    descriptor.get("path") != member_name
                    or descriptor.get("records") != 1
                    or descriptor.get("bytes") != len(content)
                    or descriptor.get("sha256") != sha256_bytes(content)
                ):
                    raise TransferValidationError(
                        f"«{_DATASET_LABELS[key]}» no coincide con el manifest."
                    )
                files[key] = content
    except TransferValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise TransferValidationError("No se puede abrir el traslado seleccionado.") from exc

    if len(files["projection"]) > MAX_PROJECTION_BYTES:
        raise TransferValidationError("La proyección supera el tamaño máximo admitido.")
    _validate_pptx(files["report"])
    try:
        projection = json.loads(files["projection"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TransferValidationError("No se puede leer la proyección canónica.") from exc
    projection = _validate_projection(
        projection,
        manifest=manifest,
        report_content=files["report"],
    )
    return manifest, {"projection": projection, "report": files["report"]}


def validate_transfer_package(settings: Settings, file_name: str) -> dict[str, Any]:
    """Inspect a handoff without offering a fake desktop import operation."""
    with _TRANSFER_LOCK:
        path = _safe_archive_path(settings, file_name)
        manifest, payloads = _decode_archive(path)
        projection = payloads["projection"]
        scope = projection["scope"]
        return {
            "valid": True,
            "summary": "Proyección GPC y PPTX verificados; el traslado está listo para publicar.",
            "fileName": path.name,
            "fileSize": int(path.stat().st_size),
            "createdAt": str(manifest.get("createdAt") or ""),
            "checkedAt": _iso_now(),
            "mode": "inspect-only",
            "scope": scope,
            "semanticContract": SEMANTIC_CONTRACT,
            "totalSourceRecords": 2,
            "stats": [
                {
                    "key": key,
                    "label": _DATASET_LABELS[key],
                    "sourceCount": 1,
                    "sha256": manifest["datasets"][key]["sha256"],
                    "bytes": manifest["datasets"][key]["bytes"],
                }
                for key in _DATASET_FILES
            ],
            "warnings": [],
        }
