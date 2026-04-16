"""Persistence helpers for the normalized issues document."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from bug_resolution_radar.models.schema import IssuesDocument

_DATETIME_COLUMNS = ("created", "updated", "resolved")


def _parquet_path(path: Path) -> Path:
    return path.with_suffix(".parquet")


def _workspace_index_path(path: Path) -> Path:
    return path.with_suffix(".workspace.json")


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


@lru_cache(maxsize=8)
def _load_issues_doc_cached(path: str, mtime_ns: int) -> IssuesDocument:
    del mtime_ns  # cache invalidation key only
    resolved = Path(path)
    if not resolved.exists():
        return IssuesDocument.empty()
    try:
        return IssuesDocument.model_validate_json(resolved.read_text(encoding="utf-8"))
    except Exception:
        return IssuesDocument.empty()


def load_issues_doc(path: str) -> IssuesDocument:
    """Load `IssuesDocument` from JSON file or return an empty document."""
    resolved = Path(path)
    mtime_ns = resolved.stat().st_mtime_ns if resolved.exists() else -1
    return _load_issues_doc_cached(str(resolved.resolve()), mtime_ns).model_copy(deep=True)


def _parse_datetime_utc_mixed(series: pd.Series) -> pd.Series:
    """Parse mixed Jira/Helix datetime strings into UTC timestamps."""
    try:
        return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")
    except TypeError:
        return pd.to_datetime(series, utc=True, errors="coerce")


def _normalize_issue_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    safe = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if safe.empty:
        return safe
    out = safe.copy(deep=False)
    for column in _DATETIME_COLUMNS:
        if column not in out.columns:
            continue
        if not pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = _parse_datetime_utc_mixed(out[column])
    return out


def _issues_to_dataframe(doc: IssuesDocument) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = [issue.model_dump() for issue in doc.issues]
    if not rows:
        return pd.DataFrame()
    return _normalize_issue_dataframe(pd.DataFrame(rows))


def _build_workspace_index(df: pd.DataFrame) -> dict[str, Any]:
    safe = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if safe.empty or "country" not in safe.columns or "source_id" not in safe.columns:
        return {
            "schema_version": "1.0",
            "rowCount": 0,
            "hasData": False,
            "countries": [],
            "sourcesByCountry": {},
        }

    cols = [
        col
        for col in ("country", "source_id", "source_alias", "source_type")
        if col in safe.columns
    ]
    sources = safe.loc[:, cols].copy(deep=False)
    sources["country"] = sources["country"].fillna("").astype(str).str.strip()
    sources["source_id"] = sources["source_id"].fillna("").astype(str).str.strip()
    sources["source_alias"] = (
        sources["source_alias"].fillna("").astype(str).str.strip()
        if "source_alias" in sources.columns
        else sources["source_id"]
    )
    sources["source_type"] = (
        sources["source_type"].fillna("").astype(str).str.strip().str.lower()
        if "source_type" in sources.columns
        else sources["source_id"].str.split(":", n=1).str[0].str.strip().str.lower()
    )
    sources = sources.loc[sources["country"].ne("") & sources["source_id"].ne("")].drop_duplicates(
        subset=["country", "source_id"], keep="first"
    )

    countries: list[dict[str, Any]] = []
    sources_by_country: dict[str, list[dict[str, str]]] = {}
    for country, bucket in sources.groupby("country", sort=False):
        rows = bucket.sort_values(
            by=["source_alias", "source_id"],
            kind="mergesort",
        )
        source_rows = [
            {
                "source_id": str(row["source_id"]),
                "country": str(country),
                "alias": str(row["source_alias"] or row["source_id"]),
                "source_type": str(row["source_type"] or "").strip().lower() or "jira",
            }
            for _, row in rows.iterrows()
        ]
        countries.append({"country": str(country), "sourceCount": len(source_rows)})
        sources_by_country[str(country)] = source_rows

    return {
        "schema_version": "1.0",
        "rowCount": int(len(safe)),
        "hasData": bool(len(safe)),
        "countries": countries,
        "sourcesByCountry": sources_by_country,
    }


def _sync_read_models(path: Path, df: pd.DataFrame) -> None:
    index_payload = _build_workspace_index(df)
    try:
        _atomic_write_text(
            _workspace_index_path(path),
            json.dumps(index_payload, ensure_ascii=False, separators=(",", ":")),
        )
    except Exception:
        pass

    parquet_target = _parquet_path(path)
    if df.empty:
        try:
            parquet_target.unlink(missing_ok=True)
        except Exception:
            pass
        return

    try:
        _atomic_write_parquet(parquet_target, df)
    except Exception:
        try:
            parquet_target.unlink(missing_ok=True)
        except Exception:
            pass


def save_issues_doc(path: str, doc: IssuesDocument) -> None:
    """Save `IssuesDocument` to JSON and refresh read-optimized sidecars."""
    resolved = Path(path)
    payload = doc.model_dump_json(ensure_ascii=False)
    _atomic_write_text(resolved, payload)
    try:
        _sync_read_models(resolved, _issues_to_dataframe(doc))
    except Exception:
        # JSON is the source of truth; sidecars are best-effort accelerators.
        pass


@lru_cache(maxsize=8)
def _load_issues_df_cached(path: str, json_mtime_ns: int, parquet_mtime_ns: int) -> pd.DataFrame:
    resolved = Path(path)
    parquet_path = _parquet_path(resolved)
    if parquet_mtime_ns >= json_mtime_ns and parquet_path.exists():
        try:
            return _normalize_issue_dataframe(pd.read_parquet(parquet_path))
        except Exception:
            pass

    doc = _load_issues_doc_cached(path, json_mtime_ns)
    df = _issues_to_dataframe(doc)
    try:
        _sync_read_models(resolved, df)
    except Exception:
        pass
    return df


def load_issues_df(path: str) -> pd.DataFrame:
    """Load issues as DataFrame using Parquet sidecar when available."""
    resolved = Path(path)
    json_mtime_ns = resolved.stat().st_mtime_ns if resolved.exists() else -1
    parquet_path = _parquet_path(resolved)
    parquet_mtime_ns = parquet_path.stat().st_mtime_ns if parquet_path.exists() else -1
    return _load_issues_df_cached(
        str(resolved.resolve()),
        json_mtime_ns,
        parquet_mtime_ns,
    ).copy(deep=False)


@lru_cache(maxsize=8)
def _load_workspace_index_cached(
    path: str,
    json_mtime_ns: int,
    index_mtime_ns: int,
) -> dict[str, Any]:
    resolved = Path(path)
    index_path = _workspace_index_path(resolved)
    if index_mtime_ns >= json_mtime_ns and index_path.exists():
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    df = load_issues_df(path)
    index_payload = _build_workspace_index(df)
    try:
        _atomic_write_text(
            index_path,
            json.dumps(index_payload, ensure_ascii=False, separators=(",", ":")),
        )
    except Exception:
        pass
    return index_payload


def load_issues_workspace_index(path: str) -> dict[str, Any]:
    """Load a lightweight workspace index for country/source navigation."""
    resolved = Path(path)
    json_mtime_ns = resolved.stat().st_mtime_ns if resolved.exists() else -1
    index_path = _workspace_index_path(resolved)
    index_mtime_ns = index_path.stat().st_mtime_ns if index_path.exists() else -1
    return dict(
        _load_workspace_index_cached(
            str(resolved.resolve()),
            json_mtime_ns,
            index_mtime_ns,
        )
    )


def df_from_issues_doc(doc: IssuesDocument) -> pd.DataFrame:
    """Convert `IssuesDocument` into a pandas DataFrame."""
    return _issues_to_dataframe(doc)
