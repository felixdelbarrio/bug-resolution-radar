"""Workspace scope helpers shared by desktop/API frontends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from bug_resolution_radar.config import Settings, all_configured_sources, rollup_source_ids


@dataclass(frozen=True)
class WorkspaceSelection:
    country: str = ""
    source_id: str = ""
    scope_mode: str = "source"


def normalize_workspace_mode(value: object) -> str:
    token = str(value or "source").strip().lower()
    return token if token in {"country", "source"} else "source"


def _infer_source_type_from_source_id(source_id: str) -> str:
    token = str(source_id or "").strip().split(":", 1)[0].strip().lower()
    return token or "jira"


def inferred_sources_by_country(df_all: pd.DataFrame) -> Dict[str, List[Dict[str, str]]]:
    """Infer source metadata directly from ingested data preserving first-seen order."""
    if not isinstance(df_all, pd.DataFrame) or df_all.empty or "source_id" not in df_all.columns:
        return {}

    grouped: Dict[str, List[Dict[str, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for row in df_all.to_dict(orient="records"):
        source_id = str(row.get("source_id") or "").strip()
        country = str(row.get("country") or "").strip()
        if not source_id or not country:
            continue
        key = (country, source_id)
        if key in seen:
            continue
        seen.add(key)
        alias = (
            str(row.get("source_alias") or "").strip()
            or str(row.get("alias") or "").strip()
            or source_id
        )
        grouped.setdefault(country, []).append(
            {
                "source_id": source_id,
                "country": country,
                "alias": alias,
                "source_type": (
                    str(row.get("source_type") or "").strip().lower()
                    or _infer_source_type_from_source_id(source_id)
                ),
            }
        )
    return grouped


def merge_sources_by_country(
    primary: Dict[str, List[Dict[str, str]]],
    secondary: Dict[str, List[Dict[str, str]]],
) -> Dict[str, List[Dict[str, str]]]:
    """Merge grouped sources preserving primary order and appending unseen entries."""
    merged: Dict[str, List[Dict[str, str]]] = {
        country: [dict(row) for row in rows] for country, rows in dict(primary or {}).items()
    }
    seen = {
        (country, str(row.get("source_id") or "").strip())
        for country, rows in merged.items()
        for row in rows
        if str(row.get("source_id") or "").strip()
    }
    for country, rows in dict(secondary or {}).items():
        bucket = merged.setdefault(country, [])
        for row in rows:
            source_id = str(row.get("source_id") or "").strip()
            key = (country, source_id)
            if not source_id or key in seen:
                continue
            seen.add(key)
            bucket.append(dict(row))
    return merged


def sources_with_results(
    settings: Settings,
    *,
    configured_sources: List[Dict[str, str]] | None = None,
    df_all: pd.DataFrame | None = None,
) -> List[Dict[str, str]]:
    source_rows = (
        configured_sources if configured_sources is not None else all_configured_sources(settings)
    )
    if not source_rows:
        return []
    if not isinstance(df_all, pd.DataFrame) or df_all.empty or "source_id" not in df_all.columns:
        return []

    source_ids = df_all["source_id"].dropna().astype(str).str.strip()
    source_ids_with_results = {sid for sid in source_ids.unique().tolist() if sid}
    filtered_sources: List[Dict[str, str]] = []
    for src in source_rows:
        sid = str(src.get("source_id") or "").strip()
        if sid and sid in source_ids_with_results:
            filtered_sources.append(src)
    return filtered_sources


def sources_with_results_by_country(
    settings: Settings,
    *,
    df_all: pd.DataFrame,
) -> Dict[str, List[Dict[str, str]]]:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    configured_sources = all_configured_sources(settings)
    for src in sources_with_results(settings, configured_sources=configured_sources, df_all=df_all):
        country = str(src.get("country") or "").strip()
        if not country:
            continue
        grouped.setdefault(country, []).append(src)
    return grouped


def available_sources_by_country(
    settings: Settings,
    *,
    df_all: pd.DataFrame | None = None,
) -> Dict[str, List[Dict[str, str]]]:
    """Return source metadata backed by data, falling back to inferred dataset metadata."""
    configured = (
        sources_with_results_by_country(settings, df_all=df_all)
        if isinstance(df_all, pd.DataFrame) and not df_all.empty
        else {}
    )
    inferred = inferred_sources_by_country(df_all) if isinstance(df_all, pd.DataFrame) else {}
    return merge_sources_by_country(configured, inferred)


def apply_workspace_source_scope(
    df: pd.DataFrame,
    *,
    settings: Settings,
    selection: WorkspaceSelection,
) -> pd.DataFrame:
    """Scope dataframe by current country/source when columns are available."""
    if df is None or df.empty:
        return pd.DataFrame()

    selected_country = str(selection.country or "").strip()
    selected_source_id = str(selection.source_id or "").strip()
    scope_mode = normalize_workspace_mode(selection.scope_mode)
    if not selected_country and not selected_source_id:
        return df.copy(deep=False)

    mask = pd.Series(True, index=df.index)
    country_values: pd.Series | None = None
    if selected_country and "country" in df.columns:
        country_values = df["country"].fillna("").astype(str)
        mask &= country_values.eq(selected_country)
    if "source_id" in df.columns:
        source_values = df["source_id"].fillna("").astype(str)
        if scope_mode == "source":
            if selected_source_id:
                mask &= source_values.eq(selected_source_id)
        else:
            source_scope = (
                source_values.loc[mask]
                if selected_country and country_values is not None
                else source_values
            )
            available_source_ids = sorted({sid for sid in source_scope.tolist() if sid})
            selected_rollup = rollup_source_ids(
                settings,
                country=selected_country,
                available_source_ids=available_source_ids,
            )
            if selected_rollup:
                mask &= source_values.isin(selected_rollup)
    if bool(mask.all()):
        return df.copy(deep=False)
    return df.loc[mask].copy(deep=False)
