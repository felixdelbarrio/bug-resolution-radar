"""Centralized issue dataframe enrichment from source-specific stores."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from bug_resolution_radar.analytics.issue_functionality import HELIX_EXECUTIVE_DESCRIPTION_COL
from bug_resolution_radar.config import Settings
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo

_HELIX_EXECUTIVE_RAW_KEYS: tuple[str, ...] = (
    "BBVA_ExecutiveDescription",
    "bbva_executivedescription",
    "ExecutiveDescription",
    "Executive Description",
)
_HELIX_EXECUTIVE_RAW_TOKENS: frozenset[str] = frozenset(
    {"bbva executive description", "bbva executivedescription", "executive description"}
)


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _text(value: object) -> str:
    return str(value or "").strip()


def _extract_text(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("value", "displayName", "name", "label", "fullName", "id"):
            txt = _text(value.get(key))
            if txt:
                return txt
        return ""
    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    return _text(value)


def _normalize_raw_key(value: object) -> str:
    token = _text(value).lower()
    token = re.sub(r"[^a-z0-9]+", " ", token)
    return re.sub(r"\s+", " ", token).strip()


def _raw_executive_description(raw_fields: Mapping[str, Any] | None) -> str:
    raw = raw_fields if isinstance(raw_fields, Mapping) else {}
    for key in _HELIX_EXECUTIVE_RAW_KEYS:
        txt = _extract_text(raw.get(key))
        if txt:
            return txt
    for key, value in raw.items():
        if _normalize_raw_key(key) not in _HELIX_EXECUTIVE_RAW_TOKENS:
            continue
        txt = _extract_text(value)
        if txt:
            return txt
    return ""


def _item_executive_description(item: HelixWorkItem) -> str:
    return _text(item.executive_description) or _raw_executive_description(item.raw_fields)


def _helix_revision_key(settings: Settings) -> tuple[str, int, int]:
    path = Path(str(getattr(settings, "HELIX_DATA_PATH", "") or "")).expanduser()
    try:
        stats = path.stat()
        return str(path.resolve()), int(stats.st_mtime_ns), int(stats.st_size)
    except Exception:
        return str(path.resolve()), -1, -1


def _raw_parquet_revision(path: str) -> tuple[str, int, int]:
    raw_path = Path(path).with_suffix(".raw.parquet")
    try:
        stats = raw_path.stat()
        return str(raw_path.resolve()), int(stats.st_mtime_ns), int(stats.st_size)
    except Exception:
        return str(raw_path.resolve()), -1, -1


def _description_map_from_raw_parquet(path: str) -> dict[str, str] | None:
    resolved = Path(path)
    if not resolved.exists():
        return None
    try:
        frame = pd.read_parquet(
            resolved,
            columns=["id", "source_id", "BBVA_ExecutiveDescription"],
        )
    except Exception:
        return None
    if frame.empty:
        return {}

    ids = frame["id"].fillna("").astype(str).str.strip().str.upper()
    source_ids = frame["source_id"].fillna("").astype(str).str.strip().str.lower()
    descriptions = frame["BBVA_ExecutiveDescription"].fillna("").astype(str).str.strip()
    valid = ids.ne("") & descriptions.ne("")
    out: dict[str, str] = {}
    for item_id, source_id, description in zip(
        ids.loc[valid],
        source_ids.loc[valid],
        descriptions.loc[valid],
    ):
        out.setdefault(item_id, description)
        if source_id:
            out.setdefault(f"{source_id}::{item_id}", description)
    return out


@lru_cache(maxsize=8)
def _helix_executive_description_map_cached(
    path: str,
    mtime_ns: int,
    size: int,
    raw_parquet_path: str,
    raw_parquet_mtime_ns: int,
    raw_parquet_size: int,
) -> dict[str, str]:
    del mtime_ns, size, raw_parquet_mtime_ns, raw_parquet_size
    parquet_map = _description_map_from_raw_parquet(raw_parquet_path)
    if parquet_map is not None:
        return parquet_map
    resolved = Path(path)
    if not resolved.exists():
        return {}
    try:
        doc = HelixRepo(resolved).load() or HelixDocument.empty()
    except Exception:
        return {}

    out: dict[str, str] = {}
    for item in doc.items:
        item_id = _text(item.id).upper()
        if not item_id:
            continue
        description = _item_executive_description(item)
        if not description:
            continue
        source_id = _text(item.source_id).lower()
        out.setdefault(item_id, description)
        if source_id:
            out[f"{source_id}::{item_id}"] = description
    return out


def helix_executive_description_map(settings: Settings) -> dict[str, str]:
    path, mtime_ns, size = _helix_revision_key(settings)
    raw_path, raw_mtime_ns, raw_size = _raw_parquet_revision(path)
    return _helix_executive_description_map_cached(
        path,
        mtime_ns,
        size,
        raw_path,
        raw_mtime_ns,
        raw_size,
    )


def enrich_issue_dataframe_with_helix(
    df: pd.DataFrame | None,
    *,
    settings: Settings,
) -> pd.DataFrame:
    """Fill Helix executive descriptions from the Helix store when issues lack them."""
    safe = _safe_df(df)
    if safe.empty:
        return safe.copy(deep=False)
    if "key" not in safe.columns:
        return safe.copy(deep=False)

    description_map = helix_executive_description_map(settings)
    work = safe.copy(deep=False)
    if HELIX_EXECUTIVE_DESCRIPTION_COL not in work.columns:
        work[HELIX_EXECUTIVE_DESCRIPTION_COL] = ""
    if not description_map:
        return work

    keys = work["key"].fillna("").astype(str).str.strip().str.upper()
    source_ids = (
        work["source_id"].fillna("").astype(str).str.strip().str.lower()
        if "source_id" in work.columns
        else pd.Series("", index=work.index, dtype=str)
    )
    merge_keys = source_ids + "::" + keys
    merge_keys = merge_keys.where(source_ids.ne(""), keys)
    mapped = merge_keys.map(description_map).fillna(keys.map(description_map)).fillna("")
    current = work[HELIX_EXECUTIVE_DESCRIPTION_COL].fillna("").astype(str).str.strip()
    if not mapped.astype(str).str.len().gt(0).any():
        return work
    work[HELIX_EXECUTIVE_DESCRIPTION_COL] = current.where(current.ne(""), mapped).to_numpy(
        copy=False
    )
    return work


def helix_revision_token(settings: Settings) -> tuple[str, int, int]:
    """Expose the Helix store revision for caches depending on enriched issue data."""
    return _helix_revision_key(settings)
