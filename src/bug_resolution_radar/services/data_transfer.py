"""Portable, validated backup and incremental restore for business data."""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from bug_resolution_radar.config import Settings
from bug_resolution_radar.models.schema import IssuesDocument
from bug_resolution_radar.models.schema_helix import HelixDocument
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.issues_store import save_issues_doc
from bug_resolution_radar.services.downloads import (
    ensure_download_dir,
    save_download_content,
)
from bug_resolution_radar.services.ingest_merge import helix_merge_key, issue_merge_key

TRANSFER_FORMAT = "bug-resolution-radar-transfer"
TRANSFER_VERSION = 1
TRANSFER_EXTENSION = ".brr"
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024

_DATASET_FILES = {
    "issues": "data/issues.json",
    "helix": "data/helix.json",
    "notes": "data/notes.json",
    "learning": "data/insights_learning.json",
}
_DATASET_LABELS = {
    "issues": "Incidencias del radar",
    "helix": "Histórico Helix",
    "notes": "Anotaciones de seguimiento",
    "learning": "Aprendizaje de insights",
}
_TRANSFER_LOCK = RLock()


class TransferValidationError(ValueError):
    """Raised when a selected transfer package is not safe to import."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat(timespec="seconds")


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_json_path(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TransferValidationError(
            f"No se puede leer {path.name}; revisa el fichero de datos de origen."
        ) from exc


def _load_issues_for_export(settings: Settings) -> IssuesDocument:
    path = Path(settings.DATA_PATH).expanduser()
    if not path.exists():
        return IssuesDocument.empty()
    try:
        return IssuesDocument.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TransferValidationError(
            "Las incidencias actuales presentan inconsistencias y no se ha creado el respaldo."
        ) from exc


def _load_helix_for_export(settings: Settings) -> HelixDocument:
    path = Path(settings.HELIX_DATA_PATH).expanduser()
    if not path.exists():
        return HelixDocument.empty()
    try:
        return HelixDocument.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TransferValidationError(
            "El histórico Helix actual presenta inconsistencias y no se ha creado el respaldo."
        ) from exc


def _legacy_note_id(issue_key: str, created_at: str, note: str, index: int) -> str:
    digest = _sha256(f"{issue_key}|{created_at}|{note}|{index}".encode("utf-8"))[:16]
    return f"imported-{digest}"


def _normalize_notes_payload(raw: Any) -> dict[str, dict[str, list[dict[str, str]]]]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise TransferValidationError("Las anotaciones no tienen el formato esperado.")

    normalized: dict[str, dict[str, list[dict[str, str]]]] = {}
    for raw_key, raw_value in raw.items():
        issue_key = str(raw_key or "").strip().upper()
        if not issue_key:
            raise TransferValidationError("Se ha encontrado una anotación sin incidencia asociada.")
        if isinstance(raw_value, dict) and isinstance(raw_value.get("entries"), list):
            candidates = raw_value["entries"]
        elif isinstance(raw_value, dict) and "note" in raw_value:
            candidates = [raw_value]
        elif isinstance(raw_value, list):
            candidates = raw_value
        else:
            candidates = [raw_value]

        entries: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for index, candidate in enumerate(candidates):
            if isinstance(candidate, dict):
                note = str(candidate.get("note") or "").strip()
                created_at = str(
                    candidate.get("createdAt") or candidate.get("created_at") or ""
                ).strip()
                entry_id = str(candidate.get("id") or "").strip()
            else:
                note = str(candidate or "").strip()
                created_at = ""
                entry_id = ""
            if not note:
                continue
            if not entry_id:
                entry_id = _legacy_note_id(issue_key, created_at, note, index)
            if entry_id in seen_ids:
                raise TransferValidationError(
                    "Las anotaciones contienen identificadores duplicados."
                )
            seen_ids.add(entry_id)
            entries.append({"id": entry_id, "createdAt": created_at, "note": note})
        if entries:
            normalized[issue_key] = {"entries": entries}
    return normalized


def _normalize_learning_payload(raw: Any) -> dict[str, Any]:
    if raw in (None, {}):
        return {"version": 1, "scopes": {}}
    if not isinstance(raw, dict):
        raise TransferValidationError("El aprendizaje de insights no tiene el formato esperado.")
    scopes = raw.get("scopes", {})
    if not isinstance(scopes, dict):
        raise TransferValidationError("Los ámbitos de aprendizaje no tienen el formato esperado.")
    clean_scopes: dict[str, dict[str, Any]] = {}
    for raw_key, raw_scope in scopes.items():
        scope_key = str(raw_key or "").strip()
        if not scope_key or not isinstance(raw_scope, dict):
            raise TransferValidationError("Se ha encontrado un ámbito de aprendizaje no válido.")
        clean_scopes[scope_key] = dict(raw_scope)
    return {"version": int(raw.get("version", 1) or 1), "scopes": clean_scopes}


def _note_count(payload: dict[str, Any]) -> int:
    return sum(
        len(record.get("entries", []))
        for record in payload.values()
        if isinstance(record, dict) and isinstance(record.get("entries"), list)
    )


def _dataset_counts(
    issues: IssuesDocument,
    helix: HelixDocument,
    notes: dict[str, Any],
    learning: dict[str, Any],
) -> dict[str, int]:
    return {
        "issues": len(issues.issues),
        "helix": len(helix.items),
        "notes": _note_count(notes),
        "learning": len(learning.get("scopes", {})),
    }


def _manifest(
    *,
    created_at: str,
    files: dict[str, bytes],
    counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "format": TRANSFER_FORMAT,
        "version": TRANSFER_VERSION,
        "createdAt": created_at,
        "datasets": {
            key: {
                "path": _DATASET_FILES[key],
                "records": int(counts[key]),
                "sha256": _sha256(files[key]),
            }
            for key in _DATASET_FILES
        },
    }


def _build_archive(files: dict[str, bytes], manifest: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", _json_bytes(manifest))
        for key, member_name in _DATASET_FILES.items():
            archive.writestr(member_name, files[key])
    return buffer.getvalue()


def _history_path(settings: Settings) -> Path:
    return Path(settings.DATA_PATH).expanduser().with_name("data_transfer_history.json")


def _append_history(settings: Settings, record: dict[str, Any]) -> None:
    path = _history_path(settings)
    try:
        raw = _read_json_path(path, default={"version": 1, "operations": []})
        operations = raw.get("operations", []) if isinstance(raw, dict) else []
        if not isinstance(operations, list):
            operations = []
        operations.append(record)
        payload = {"version": 1, "operations": operations[-50:]}
        _atomic_write(path, _json_bytes(payload))
    except Exception:
        # Operational history must never turn a successful transfer into a failure.
        return


def transfer_history(settings: Settings) -> dict[str, Any]:
    raw = _read_json_path(
        _history_path(settings),
        default={"version": 1, "operations": []},
    )
    operations = raw.get("operations", []) if isinstance(raw, dict) else []
    return {"operations": list(reversed(operations[-20:])) if isinstance(operations, list) else []}


def export_business_data(settings: Settings) -> dict[str, Any]:
    """Create one validated, portable package in the configured downloads directory."""
    with _TRANSFER_LOCK:
        issues = _load_issues_for_export(settings)
        helix = _load_helix_for_export(settings)
        notes = _normalize_notes_payload(
            _read_json_path(Path(settings.NOTES_PATH).expanduser(), default={})
        )
        learning = _normalize_learning_payload(
            _read_json_path(Path(settings.INSIGHTS_LEARNING_PATH).expanduser(), default={})
        )
        counts = _dataset_counts(issues, helix, notes, learning)
        files = {
            "issues": issues.model_dump_json(ensure_ascii=False).encode("utf-8"),
            "helix": helix.model_dump_json(ensure_ascii=False).encode("utf-8"),
            "notes": _json_bytes(notes),
            "learning": _json_bytes(learning),
        }
        created_at = _iso_now()
        archive_content = _build_archive(
            files,
            _manifest(created_at=created_at, files=files, counts=counts),
        )
        file_name = f"respaldo_radar_{_utc_now().strftime('%Y%m%d_%H%M%S')}{TRANSFER_EXTENSION}"
        saved_path = save_download_content(
            settings,
            file_name=file_name,
            content=archive_content,
        )
        stats = [
            {"key": key, "label": _DATASET_LABELS[key], "count": int(counts[key])}
            for key in _DATASET_FILES
        ]
        payload = {
            "operation": "export",
            "summary": "Respaldo completo creado y preparado para trasladar.",
            "completedAt": created_at,
            "fileName": saved_path.name,
            "savedPath": str(saved_path),
            "savedDir": str(saved_path.parent),
            "fileSize": len(archive_content),
            "totalRecords": sum(counts.values()),
            "stats": stats,
        }
        _append_history(
            settings,
            {
                "id": uuid4().hex,
                "operation": "export",
                "completedAt": created_at,
                "fileName": saved_path.name,
                "totalRecords": sum(counts.values()),
                "headline": "Respaldo completo creado",
                "stats": stats,
            },
        )
        return payload


def _safe_archive_path(settings: Settings, file_name: str) -> Path:
    clean_name = Path(str(file_name or "").strip()).name
    if not clean_name or clean_name != str(file_name or "").strip():
        raise TransferValidationError("Selecciona un respaldo disponible en Descargas de Informes.")
    if not clean_name.lower().endswith(TRANSFER_EXTENSION):
        raise TransferValidationError("El fichero seleccionado no es un respaldo del radar.")
    download_dir = ensure_download_dir(settings).resolve()
    candidate = (download_dir / clean_name).resolve()
    if candidate.parent != download_dir or not candidate.is_file():
        raise TransferValidationError("El respaldo seleccionado ya no está disponible.")
    if candidate.stat().st_size > MAX_ARCHIVE_BYTES:
        raise TransferValidationError("El respaldo supera el tamaño máximo admitido.")
    return candidate


def list_transfer_packages(settings: Settings) -> dict[str, Any]:
    directory = ensure_download_dir(settings)
    rows: list[dict[str, Any]] = []
    for path in directory.glob(f"*{TRANSFER_EXTENSION}"):
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append(
            {
                "fileName": path.name,
                "fileSize": int(stat.st_size),
                "modifiedAt": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(
                    timespec="seconds"
                ),
            }
        )
    rows.sort(key=lambda row: (row["modifiedAt"], row["fileName"]), reverse=True)
    return {"directory": str(directory), "packages": rows}


def _decode_archive(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        with zipfile.ZipFile(path, mode="r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            required = {"manifest.json", *_DATASET_FILES.values()}
            if len(names) != len(set(names)):
                raise TransferValidationError("El respaldo contiene elementos duplicados.")
            if set(names) != required:
                raise TransferValidationError(
                    "El respaldo está incompleto o contiene datos ajenos."
                )
            if any(
                info.is_dir()
                or info.filename.startswith(("/", "\\"))
                or ".." in Path(info.filename).parts
                for info in infos
            ):
                raise TransferValidationError("El respaldo contiene rutas no permitidas.")
            expanded_size = sum(max(0, int(info.file_size)) for info in infos)
            if expanded_size > MAX_EXPANDED_BYTES:
                raise TransferValidationError("El respaldo expandido supera el tamaño admitido.")
            raw_manifest = archive.read("manifest.json")
            try:
                manifest = json.loads(raw_manifest.decode("utf-8"))
            except Exception as exc:
                raise TransferValidationError(
                    "No se puede leer el inventario del respaldo."
                ) from exc
            if not isinstance(manifest, dict):
                raise TransferValidationError("El inventario del respaldo no es válido.")
            if manifest.get("format") != TRANSFER_FORMAT:
                raise TransferValidationError("El fichero no pertenece a Bug Resolution Radar.")
            if int(manifest.get("version", 0) or 0) != TRANSFER_VERSION:
                raise TransferValidationError(
                    "La versión del respaldo no es compatible con esta aplicación."
                )
            datasets = manifest.get("datasets")
            if not isinstance(datasets, dict) or set(datasets) != set(_DATASET_FILES):
                raise TransferValidationError(
                    "El inventario de datos del respaldo está incompleto."
                )

            raw_files: dict[str, bytes] = {}
            for key, member_name in _DATASET_FILES.items():
                descriptor = datasets.get(key)
                if not isinstance(descriptor, dict) or descriptor.get("path") != member_name:
                    raise TransferValidationError(
                        f"El bloque «{_DATASET_LABELS[key]}» no coincide con el inventario."
                    )
                content = archive.read(member_name)
                if _sha256(content) != str(descriptor.get("sha256") or ""):
                    raise TransferValidationError(
                        f"El bloque «{_DATASET_LABELS[key]}» está incompleto o ha cambiado."
                    )
                raw_files[key] = content
    except TransferValidationError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise TransferValidationError("No se puede abrir el respaldo seleccionado.") from exc

    try:
        issues = IssuesDocument.model_validate_json(raw_files["issues"])
        helix = HelixDocument.model_validate_json(raw_files["helix"])
        notes = _normalize_notes_payload(json.loads(raw_files["notes"].decode("utf-8")))
        learning = _normalize_learning_payload(json.loads(raw_files["learning"].decode("utf-8")))
    except TransferValidationError:
        raise
    except Exception as exc:
        raise TransferValidationError(
            "El respaldo contiene datos que no superan las comprobaciones de calidad."
        ) from exc

    payloads = {
        "issues": issues,
        "helix": helix,
        "notes": notes,
        "learning": learning,
    }
    _validate_business_payloads(payloads)
    actual_counts = _dataset_counts(issues, helix, notes, learning)
    for key, actual_count in actual_counts.items():
        expected_count = int(manifest["datasets"][key].get("records", -1))
        if expected_count != actual_count:
            raise TransferValidationError(
                f"El recuento de «{_DATASET_LABELS[key]}» no coincide con el inventario."
            )
    return manifest, payloads


def _validate_unique_business_keys(
    items: list[Any],
    *,
    key_fn: Callable[[Any], str],
    label: str,
) -> None:
    seen: set[str] = set()
    for item in items:
        key = str(key_fn(item) or "").strip()
        if not key:
            raise TransferValidationError(f"«{label}» contiene un registro sin identificador.")
        if key in seen:
            raise TransferValidationError(f"«{label}» contiene identificadores duplicados.")
        seen.add(key)


def _validate_business_payloads(payloads: dict[str, Any]) -> None:
    _validate_unique_business_keys(
        payloads["issues"].issues,
        key_fn=issue_merge_key,
        label=_DATASET_LABELS["issues"],
    )
    _validate_unique_business_keys(
        payloads["helix"].items,
        key_fn=helix_merge_key,
        label=_DATASET_LABELS["helix"],
    )
    for issue_key, record in payloads["notes"].items():
        entry_ids = [str(item.get("id") or "").strip() for item in record.get("entries", [])]
        if not issue_key or any(not entry_id for entry_id in entry_ids):
            raise TransferValidationError(
                "«Anotaciones de seguimiento» contiene una anotación sin identificador."
            )
        if len(entry_ids) != len(set(entry_ids)):
            raise TransferValidationError(
                "«Anotaciones de seguimiento» contiene identificadores duplicados."
            )


def _load_destination(settings: Settings) -> dict[str, Any]:
    issues_path = Path(settings.DATA_PATH).expanduser()
    helix_path = Path(settings.HELIX_DATA_PATH).expanduser()
    try:
        issues = (
            IssuesDocument.model_validate_json(issues_path.read_text(encoding="utf-8"))
            if issues_path.exists()
            else IssuesDocument.empty()
        )
        helix = (
            HelixDocument.model_validate_json(helix_path.read_text(encoding="utf-8"))
            if helix_path.exists()
            else HelixDocument.empty()
        )
    except Exception as exc:
        raise TransferValidationError(
            "Los datos actuales del sistema destino necesitan revisión antes de importar."
        ) from exc
    return {
        "issues": issues,
        "helix": helix,
        "notes": _normalize_notes_payload(
            _read_json_path(Path(settings.NOTES_PATH).expanduser(), default={})
        ),
        "learning": _normalize_learning_payload(
            _read_json_path(Path(settings.INSIGHTS_LEARNING_PATH).expanduser(), default={})
        ),
    }


def _model_merge_stats(
    existing: list[Any],
    incoming: list[Any],
    *,
    key_fn: Callable[[Any], str],
) -> tuple[list[Any], dict[str, int]]:
    merged = {key_fn(item): item for item in existing}
    new_count = 0
    updated_count = 0
    unchanged_count = 0
    for item in incoming:
        key = key_fn(item)
        current = merged.get(key)
        if current is None:
            new_count += 1
        elif current.model_dump() == item.model_dump():
            unchanged_count += 1
        else:
            updated_count += 1
        merged[key] = item
    return list(merged.values()), {
        "sourceCount": len(incoming),
        "destinationCount": len(existing),
        "newCount": new_count,
        "updatedCount": updated_count,
        "unchangedCount": unchanged_count,
        "finalCount": len(merged),
    }


def _merge_notes(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, int]]:
    merged: dict[str, dict[str, list[dict[str, str]]]] = {
        issue_key: {"entries": [dict(entry) for entry in record.get("entries", [])]}
        for issue_key, record in existing.items()
    }
    existing_count = _note_count(existing)
    new_count = 0
    updated_count = 0
    unchanged_count = 0
    for issue_key, record in incoming.items():
        destination_entries = merged.setdefault(issue_key, {"entries": []})["entries"]
        by_id = {
            str(entry.get("id") or ""): index for index, entry in enumerate(destination_entries)
        }
        for entry in record.get("entries", []):
            entry_id = str(entry.get("id") or "")
            index = by_id.get(entry_id)
            if index is None:
                by_id[entry_id] = len(destination_entries)
                destination_entries.append(dict(entry))
                new_count += 1
            elif destination_entries[index] == entry:
                unchanged_count += 1
            else:
                destination_entries[index] = dict(entry)
                updated_count += 1
    return merged, {
        "sourceCount": _note_count(incoming),
        "destinationCount": existing_count,
        "newCount": new_count,
        "updatedCount": updated_count,
        "unchangedCount": unchanged_count,
        "finalCount": _note_count(merged),
    }


def _scope_is_newer(incoming: dict[str, Any], existing: dict[str, Any]) -> bool:
    incoming_at = str(incoming.get("updated_at") or incoming.get("updatedAt") or "")
    existing_at = str(existing.get("updated_at") or existing.get("updatedAt") or "")
    if incoming_at and existing_at:
        return incoming_at >= existing_at
    return bool(incoming_at) or not bool(existing_at)


def _merge_learning(
    existing: dict[str, Any], incoming: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, int]]:
    existing_scopes = existing.get("scopes", {})
    incoming_scopes = incoming.get("scopes", {})
    merged_scopes = {key: dict(value) for key, value in existing_scopes.items()}
    new_count = 0
    updated_count = 0
    unchanged_count = 0
    for key, scope in incoming_scopes.items():
        current = merged_scopes.get(key)
        if current is None:
            merged_scopes[key] = dict(scope)
            new_count += 1
        elif current == scope:
            unchanged_count += 1
        elif _scope_is_newer(scope, current):
            merged_scopes[key] = dict(scope)
            updated_count += 1
        else:
            unchanged_count += 1
    return {
        "version": max(int(existing.get("version", 1)), int(incoming.get("version", 1))),
        "scopes": merged_scopes,
    }, {
        "sourceCount": len(incoming_scopes),
        "destinationCount": len(existing_scopes),
        "newCount": new_count,
        "updatedCount": updated_count,
        "unchangedCount": unchanged_count,
        "finalCount": len(merged_scopes),
    }


def _merge_payloads(
    destination: dict[str, Any],
    incoming: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    merged_issues, issue_stats = _model_merge_stats(
        destination["issues"].issues,
        incoming["issues"].issues,
        key_fn=issue_merge_key,
    )
    merged_helix, helix_stats = _model_merge_stats(
        destination["helix"].items,
        incoming["helix"].items,
        key_fn=helix_merge_key,
    )
    merged_notes, note_stats = _merge_notes(destination["notes"], incoming["notes"])
    merged_learning, learning_stats = _merge_learning(destination["learning"], incoming["learning"])

    destination_issues: IssuesDocument = destination["issues"]
    incoming_issues: IssuesDocument = incoming["issues"]
    destination_helix: HelixDocument = destination["helix"]
    incoming_helix: HelixDocument = incoming["helix"]
    issues_doc = destination_issues.model_copy(deep=True)
    issues_doc.issues = merged_issues
    if (
        not destination_issues.issues
        or incoming_issues.ingested_at >= destination_issues.ingested_at
    ):
        issues_doc.ingested_at = incoming_issues.ingested_at
        issues_doc.jira_base_url = incoming_issues.jira_base_url or destination_issues.jira_base_url
        issues_doc.query = incoming_issues.query or destination_issues.query
    helix_doc = destination_helix.model_copy(deep=True)
    helix_doc.items = merged_helix
    if not destination_helix.items or incoming_helix.ingested_at >= destination_helix.ingested_at:
        helix_doc.ingested_at = incoming_helix.ingested_at
        helix_doc.helix_base_url = incoming_helix.helix_base_url or destination_helix.helix_base_url
        helix_doc.query = incoming_helix.query or destination_helix.query

    stats_by_key = {
        "issues": issue_stats,
        "helix": helix_stats,
        "notes": note_stats,
        "learning": learning_stats,
    }
    stats = [
        {"key": key, "label": _DATASET_LABELS[key], **stats_by_key[key]} for key in _DATASET_FILES
    ]
    return {
        "issues": issues_doc,
        "helix": helix_doc,
        "notes": merged_notes,
        "learning": merged_learning,
    }, stats


def validate_transfer_package(settings: Settings, file_name: str) -> dict[str, Any]:
    """Fully inspect a package and preview its incremental effect without writing."""
    with _TRANSFER_LOCK:
        path = _safe_archive_path(settings, file_name)
        manifest, incoming = _decode_archive(path)
        destination = _load_destination(settings)
        _, stats = _merge_payloads(destination, incoming)
        total_source = sum(item["sourceCount"] for item in stats)
        total_new = sum(item["newCount"] for item in stats)
        total_updated = sum(item["updatedCount"] for item in stats)
        total_unchanged = sum(item["unchangedCount"] for item in stats)
        return {
            "valid": True,
            "summary": "Respaldo verificado: está completo y es apto para importar.",
            "fileName": path.name,
            "fileSize": int(path.stat().st_size),
            "createdAt": str(manifest.get("createdAt") or ""),
            "checkedAt": _iso_now(),
            "mode": "incremental",
            "totalSourceRecords": total_source,
            "totalNewRecords": total_new,
            "totalUpdatedRecords": total_updated,
            "totalUnchangedRecords": total_unchanged,
            "stats": stats,
            "warnings": [],
        }


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _main_data_paths(settings: Settings) -> dict[str, Path]:
    return {
        "issues": Path(settings.DATA_PATH).expanduser(),
        "helix": Path(settings.HELIX_DATA_PATH).expanduser(),
        "notes": Path(settings.NOTES_PATH).expanduser(),
        "learning": Path(settings.INSIGHTS_LEARNING_PATH).expanduser(),
    }


def _serialize_merged(merged: dict[str, Any]) -> dict[str, bytes]:
    return {
        "issues": merged["issues"].model_dump_json(ensure_ascii=False).encode("utf-8"),
        "helix": merged["helix"].model_dump_json(ensure_ascii=False).encode("utf-8"),
        "notes": _json_bytes(merged["notes"]),
        "learning": _json_bytes(merged["learning"]),
    }


def _refresh_read_models(settings: Settings, merged: dict[str, Any]) -> None:
    save_issues_doc(settings.DATA_PATH, merged["issues"])
    HelixRepo(Path(settings.HELIX_DATA_PATH).expanduser()).save(merged["helix"])


def _remove_read_sidecars(settings: Settings, key: str) -> None:
    if key == "issues":
        base = Path(settings.DATA_PATH).expanduser()
        candidates = [base.with_suffix(".parquet"), base.with_suffix(".workspace.json")]
    elif key == "helix":
        base = Path(settings.HELIX_DATA_PATH).expanduser()
        candidates = [base.with_suffix(".raw.parquet"), base.with_suffix(".meta.json")]
    else:
        candidates = []
    for candidate in candidates:
        try:
            candidate.unlink(missing_ok=True)
        except Exception:
            pass


def import_transfer_package(settings: Settings, file_name: str) -> dict[str, Any]:
    """Validate again and incrementally merge a package into the current system."""
    with _TRANSFER_LOCK:
        path = _safe_archive_path(settings, file_name)
        _, incoming = _decode_archive(path)
        destination = _load_destination(settings)
        merged, stats = _merge_payloads(destination, incoming)
        paths = _main_data_paths(settings)
        contents = _serialize_merged(merged)
        previous: dict[str, tuple[bool, bytes]] = {}
        for key, target in paths.items():
            previous[key] = (target.exists(), target.read_bytes() if target.exists() else b"")

        try:
            for key, target in paths.items():
                _atomic_write(target, contents[key])
            _refresh_read_models(settings, merged)
        except Exception as exc:
            for key, target in paths.items():
                existed, content = previous[key]
                try:
                    if existed:
                        _atomic_write(target, content)
                    else:
                        target.unlink(missing_ok=True)
                except Exception:
                    pass
            try:
                if previous["issues"][0]:
                    restored_issues = IssuesDocument.model_validate_json(previous["issues"][1])
                    save_issues_doc(settings.DATA_PATH, restored_issues)
                else:
                    _remove_read_sidecars(settings, "issues")
                if previous["helix"][0]:
                    restored_helix = HelixDocument.model_validate_json(previous["helix"][1])
                    HelixRepo(Path(settings.HELIX_DATA_PATH)).save(restored_helix)
                else:
                    _remove_read_sidecars(settings, "helix")
            except Exception:
                pass
            raise RuntimeError(
                "La importación no se ha completado y se han conservado los datos anteriores."
            ) from exc

        completed_at = _iso_now()
        total_new = sum(item["newCount"] for item in stats)
        total_updated = sum(item["updatedCount"] for item in stats)
        total_unchanged = sum(item["unchangedCount"] for item in stats)
        total_final = sum(item["finalCount"] for item in stats)
        payload = {
            "operation": "import",
            "summary": (
                f"Importación incremental completada: {total_new} altas, "
                f"{total_updated} actualizaciones y {total_unchanged} coincidencias sin cambios."
            ),
            "completedAt": completed_at,
            "fileName": path.name,
            "mode": "incremental",
            "totalNewRecords": total_new,
            "totalUpdatedRecords": total_updated,
            "totalUnchangedRecords": total_unchanged,
            "totalFinalRecords": total_final,
            "stats": stats,
        }
        _append_history(
            settings,
            {
                "id": uuid4().hex,
                "operation": "import",
                "completedAt": completed_at,
                "fileName": path.name,
                "totalRecords": total_new + total_updated,
                "headline": "Importación incremental completada",
                "stats": stats,
            },
        )
        return payload
