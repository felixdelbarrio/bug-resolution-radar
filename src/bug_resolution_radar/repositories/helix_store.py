"""Read-optimized helpers for Helix persistence sidecars."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from bug_resolution_radar.models.schema_helix import HelixDocument
from bug_resolution_radar.repositories.helix_repo import HelixRepo


def _export_parquet_path(path: Path) -> Path:
    return path.with_suffix(".raw.parquet")


def _meta_path(path: Path) -> Path:
    return path.with_suffix(".meta.json")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def _atomic_write_parquet(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)


def _jsonable_text(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _coerce_export_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return ""
        return value.tz_convert("UTC").isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc).isoformat()
            if value.tzinfo is not None
            else value.isoformat()
        )
    return _jsonable_text(value)


def _build_export_df(doc: HelixDocument) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in list(doc.items or []):
        source_id = str(item.source_id or "").strip().lower()
        item_id = str(item.id or "").strip().upper()
        if not item_id:
            continue
        merge_key = f"{source_id}::{item_id}" if source_id else item_id
        row: dict[str, Any] = {
            "merge_key": merge_key,
            "source_id": source_id,
            "ID de la Incidencia": item_id,
            "__item_url__": str(item.url or "").strip(),
        }
        raw_fields = item.raw_fields or {}
        for key, value in raw_fields.items():
            row[str(key)] = _coerce_export_scalar(value)
        rows.append(row)

    if not rows:
        return pd.DataFrame(
            columns=["merge_key", "source_id", "ID de la Incidencia", "__item_url__"]
        )

    df = pd.DataFrame(rows)
    front = [
        col
        for col in ("merge_key", "source_id", "ID de la Incidencia", "__item_url__")
        if col in df.columns
    ]
    rest = [col for col in df.columns if col not in front]
    return df[front + rest].copy()


def _build_meta(doc: HelixDocument) -> dict[str, Any]:
    helix_source_ids = {
        str(item.source_id or "").strip()
        for item in list(doc.items or [])
        if str(item.source_id or "").strip()
    }
    return {
        "schema_version": str(doc.schema_version or "1.0"),
        "ingested_at": str(doc.ingested_at or ""),
        "helix_base_url": str(doc.helix_base_url or ""),
        "query": str(doc.query or ""),
        "helix_source_count": len(helix_source_ids),
        "items_count": len(list(doc.items or [])),
    }


def sync_helix_sidecars(path: Path, doc: HelixDocument) -> None:
    export_df = _build_export_df(doc)
    meta = _build_meta(doc)
    try:
        _atomic_write_text(
            _meta_path(path),
            json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
        )
    except Exception:
        pass

    if export_df.empty:
        try:
            _export_parquet_path(path).unlink(missing_ok=True)
        except Exception:
            pass
        return

    try:
        _atomic_write_parquet(_export_parquet_path(path), export_df)
    except Exception:
        try:
            _export_parquet_path(path).unlink(missing_ok=True)
        except Exception:
            pass


@lru_cache(maxsize=8)
def _load_export_df_cached(path: str, json_mtime_ns: int, parquet_mtime_ns: int) -> pd.DataFrame:
    resolved = Path(path)
    parquet_path = _export_parquet_path(resolved)
    if parquet_mtime_ns >= json_mtime_ns and parquet_path.exists():
        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            pass

    doc = HelixRepo(resolved).load() or HelixDocument.empty()
    export_df = _build_export_df(doc)
    try:
        sync_helix_sidecars(resolved, doc)
    except Exception:
        pass
    return export_df


def load_helix_export_df(path: str) -> pd.DataFrame:
    resolved = Path(path).expanduser()
    json_mtime_ns = resolved.stat().st_mtime_ns if resolved.exists() else -1
    parquet_path = _export_parquet_path(resolved)
    parquet_mtime_ns = parquet_path.stat().st_mtime_ns if parquet_path.exists() else -1
    return _load_export_df_cached(
        str(resolved.resolve()),
        json_mtime_ns,
        parquet_mtime_ns,
    ).copy(deep=False)


@lru_cache(maxsize=8)
def _load_meta_cached(path: str, json_mtime_ns: int, meta_mtime_ns: int) -> dict[str, Any]:
    resolved = Path(path)
    meta_path = _meta_path(resolved)
    if meta_mtime_ns >= json_mtime_ns and meta_path.exists():
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    doc = HelixRepo(resolved).load() or HelixDocument.empty()
    meta = _build_meta(doc)
    try:
        sync_helix_sidecars(resolved, doc)
    except Exception:
        pass
    return meta


def load_helix_meta(path: str) -> dict[str, Any]:
    resolved = Path(path).expanduser()
    json_mtime_ns = resolved.stat().st_mtime_ns if resolved.exists() else -1
    meta_path = _meta_path(resolved)
    meta_mtime_ns = meta_path.stat().st_mtime_ns if meta_path.exists() else -1
    return dict(
        _load_meta_cached(
            str(resolved.resolve()),
            json_mtime_ns,
            meta_mtime_ns,
        )
    )
