"""Centralized Issues workbook export service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4

import pandas as pd

from bug_resolution_radar.analytics.finalist_discrepancy_lists import (
    build_finalist_discrepancy_issue_list,
)
from bug_resolution_radar.config import Settings, all_configured_sources
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.services.dashboard_snapshot import DashboardQuery, load_scope_context
from bug_resolution_radar.services.helix_raw_export import build_helix_raw_export_frame
from bug_resolution_radar.services.tabular_export import dataframes_to_xlsx_bytes

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssueWorkbookExport:
    content: bytes
    sheet_names: tuple[str, ...]
    row_count: int


@dataclass(frozen=True)
class _SourceExportMeta:
    source_id: str
    source_type: str
    alias: str


def _sorted_export_frame(df: pd.DataFrame, *, query: DashboardQuery) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy(deep=False)
    work = df.copy(deep=False)
    sort_column = (
        str(query.issue_sort_col or "").strip()
        if str(query.issue_sort_col or "").strip() in work.columns
        else ("updated" if "updated" in work.columns else ("key" if "key" in work.columns else ""))
    )
    if sort_column:
        work = work.sort_values(sort_column, ascending=False, kind="mergesort")
    return work


def build_issue_export_frame(settings: Settings, *, query: DashboardQuery) -> pd.DataFrame:
    """Return the filtered persisted dataframe used by tabular exports."""
    context = load_scope_context(settings, query=query)
    return _sorted_export_frame(context.dff, query=query)


def build_finalist_discrepancies_export_frame(
    settings: Settings,
    *,
    query: DashboardQuery,
) -> pd.DataFrame:
    """Return the business dataset shared by Insights Excel and PPT."""
    context = load_scope_context(settings, query=query)
    rows = build_finalist_discrepancy_issue_list(context.finalist_discrepancies)
    return pd.DataFrame(
        [
            {
                "Helix ID": row.helix_id,
                "Título Helix": row.helix_summary,
                "Descripción Helix": row.helix_text,
                "Estado Helix": row.helix_status,
                "URL Helix": row.helix_url,
                "JIRA key": row.jira_key,
                "Resumen JIRA": row.jira_summary,
                "Estado JIRA": row.jira_status,
                "Prioridad JIRA": row.jira_priority,
                "Responsable JIRA": row.jira_assignee,
                "PO / Team Leader JIRA": row.po_team_leader,
                "Días abierta JIRA": row.jira_open_days,
                "Origen": row.source_alias,
                "URL JIRA": row.jira_url,
            }
            for row in rows
        ],
        columns=[
            "Helix ID",
            "Título Helix",
            "Descripción Helix",
            "Estado Helix",
            "URL Helix",
            "JIRA key",
            "Resumen JIRA",
            "Estado JIRA",
            "Prioridad JIRA",
            "Responsable JIRA",
            "PO / Team Leader JIRA",
            "Días abierta JIRA",
            "Origen",
            "URL JIRA",
        ],
    )


def build_finalist_discrepancies_workbook_export(
    settings: Settings,
    *,
    query: DashboardQuery,
) -> IssueWorkbookExport:
    frame = build_finalist_discrepancies_export_frame(settings, query=query)
    sheet_name = "Discrepancias finalistas"
    LOGGER.info(
        "finalist_discrepancies_export",
        extra={
            "run_id": uuid4().hex[:12],
            "slide_name": sheet_name,
            "rows_generated": int(len(frame)),
        },
    )
    return IssueWorkbookExport(
        content=dataframes_to_xlsx_bytes(
            [(sheet_name, frame)],
            include_index=False,
            hyperlink_columns_by_sheet={
                sheet_name: [("Helix ID", "URL Helix"), ("JIRA key", "URL JIRA")]
            },
        ),
        sheet_names=(sheet_name,),
        row_count=int(len(frame)),
    )


def _source_type_from_frame(df: pd.DataFrame) -> str:
    if df is None or df.empty or "source_type" not in df.columns:
        return ""
    values = [
        str(value or "").strip().lower()
        for value in df["source_type"].dropna().astype(str).tolist()
        if str(value or "").strip()
    ]
    return values[0] if values else ""


def _source_alias_from_frame(df: pd.DataFrame, *, fallback: str) -> str:
    if df is None or df.empty or "source_alias" not in df.columns:
        return fallback
    values = [
        str(value or "").strip()
        for value in df["source_alias"].dropna().astype(str).tolist()
        if str(value or "").strip()
    ]
    return values[0] if values else fallback


def _source_meta_by_id(
    settings: Settings,
    *,
    source_ids: Sequence[str],
    dff: pd.DataFrame,
) -> dict[str, _SourceExportMeta]:
    wanted = [str(source_id or "").strip() for source_id in list(source_ids or [])]
    wanted = [source_id for source_id in wanted if source_id]
    configured: dict[str, _SourceExportMeta] = {}
    for source in all_configured_sources(settings):
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            continue
        configured[source_id] = _SourceExportMeta(
            source_id=source_id,
            source_type=str(source.get("source_type") or "").strip().lower(),
            alias=str(source.get("alias") or "").strip() or source_id,
        )

    out: dict[str, _SourceExportMeta] = {}
    for source_id in wanted:
        frame = (
            dff.loc[dff["source_id"].fillna("").astype(str).eq(source_id)].copy(deep=False)
            if isinstance(dff, pd.DataFrame) and "source_id" in dff.columns
            else pd.DataFrame()
        )
        configured_meta = configured.get(source_id)
        source_type = (
            _source_type_from_frame(frame)
            or (configured_meta.source_type if configured_meta is not None else "")
            or "jira"
        )
        alias = _source_alias_from_frame(
            frame,
            fallback=(configured_meta.alias if configured_meta is not None else source_id),
        )
        out[source_id] = _SourceExportMeta(
            source_id=source_id,
            source_type=source_type,
            alias=alias,
        )
    return out


def _ordered_source_ids(dff: pd.DataFrame, *, query: DashboardQuery) -> list[str]:
    if not isinstance(dff, pd.DataFrame) or dff.empty or "source_id" not in dff.columns:
        return []
    present_source_ids = set(dff["source_id"].fillna("").astype(str).tolist())
    seen: set[str] = set()
    ordered: list[str] = []
    preferred = [str(query.workspace.source_id or "").strip()]
    preferred.extend(str(value or "").strip() for value in dff["source_id"].astype(str).tolist())
    for source_id in preferred:
        if not source_id or source_id in seen:
            continue
        if source_id not in present_source_ids:
            continue
        seen.add(source_id)
        ordered.append(source_id)
    return ordered


def _helix_data_path(settings: Settings) -> Path | None:
    raw_path = str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip() or "data/helix_dump.json"
    resolved = Path(raw_path).expanduser()
    if not resolved.exists():
        return None
    return resolved


def _load_helix_items_by_merge_key(settings: Settings) -> Mapping[str, HelixWorkItem]:
    helix_path = _helix_data_path(settings)
    if helix_path is None:
        return {}
    try:
        helix_doc = HelixRepo(helix_path).load() or HelixDocument.empty()
    except Exception:
        helix_doc = HelixDocument.empty()

    items: dict[str, HelixWorkItem] = {}
    for item in helix_doc.items:
        source_id = str(item.source_id or "").strip().lower()
        issue_key = str(item.id or "").strip().upper()
        if not issue_key:
            continue
        merge_key = f"{source_id}::{issue_key}" if source_id else issue_key
        items[merge_key] = item
        items.setdefault(issue_key, item)
    return items


def _sheet_name_for_source(
    meta: _SourceExportMeta,
    *,
    total_sources: int,
    helix_sources_count: int,
    jira_sources_count: int,
) -> str:
    alias = str(meta.alias or meta.source_id or "").strip() or "Origen"
    if meta.source_type == "helix":
        if total_sources == 1 or (helix_sources_count == 1 and jira_sources_count == 1):
            return "Helix Raw"
        return f"Helix Raw - {alias}"
    if meta.source_type == "jira":
        if total_sources == 1:
            return "Issues"
        if jira_sources_count == 1:
            return "JIRA"
        return f"JIRA - {alias}"
    return alias


def _standard_hyperlinks(df: pd.DataFrame) -> list[tuple[str, str]]:
    if isinstance(df, pd.DataFrame) and "key" in df.columns and "url" in df.columns:
        return [("key", "url")]
    return []


def build_issue_workbook_export(
    settings: Settings,
    *,
    query: DashboardQuery,
    helix_only: bool = False,
) -> IssueWorkbookExport:
    """Build the Issues workbook for the exact dashboard scope and filters."""
    context = load_scope_context(settings, query=query)
    dff = _sorted_export_frame(context.dff, query=query)
    if dff.empty:
        return IssueWorkbookExport(
            content=dataframes_to_xlsx_bytes([("Issues", dff)], include_index=False),
            sheet_names=("Issues",),
            row_count=0,
        )
    if "source_id" not in dff.columns:
        raise ValueError("El scope actual no contiene metadatos de origen.")

    source_ids = _ordered_source_ids(dff, query=query)
    meta_by_id = _source_meta_by_id(settings, source_ids=source_ids, dff=dff)
    source_items = [meta_by_id[source_id] for source_id in source_ids if source_id in meta_by_id]
    if helix_only:
        source_items = [meta for meta in source_items if meta.source_type == "helix"]
        if not source_items:
            raise ValueError("No hay incidencias Helix en el alcance actual para exportar.")

    total_sources = len(source_items)
    helix_sources_count = sum(1 for meta in source_items if meta.source_type == "helix")
    jira_sources_count = sum(1 for meta in source_items if meta.source_type == "jira")
    helix_items_by_merge_key: Mapping[str, HelixWorkItem] | None = None
    sheets: list[tuple[str, pd.DataFrame]] = []
    hyperlinks: dict[str, list[tuple[str, str]]] = {}

    for meta in source_items:
        source_df = dff.loc[dff["source_id"].fillna("").astype(str).eq(meta.source_id)].copy(
            deep=False
        )
        if source_df.empty:
            continue
        sheet_name = _sheet_name_for_source(
            meta,
            total_sources=total_sources,
            helix_sources_count=helix_sources_count,
            jira_sources_count=jira_sources_count,
        )
        if meta.source_type == "helix":
            if helix_items_by_merge_key is None:
                helix_items_by_merge_key = _load_helix_items_by_merge_key(settings)
            if not helix_items_by_merge_key:
                raise ValueError(
                    "No se ha podido cargar el dataset raw de Helix para la exportación."
                )
            raw_df = build_helix_raw_export_frame(
                source_df,
                helix_items_by_merge_key=helix_items_by_merge_key,
            )
            if raw_df is None or raw_df.empty:
                raise ValueError(
                    "No se han encontrado filas raw de Helix para las incidencias filtradas."
                )
            sheets.append((sheet_name, raw_df))
            hyperlinks[sheet_name] = [("ID de la Incidencia", "__item_url__")]
            continue

        sheets.append((sheet_name, source_df))
        link_specs = _standard_hyperlinks(source_df)
        if link_specs:
            hyperlinks[sheet_name] = link_specs

    if not sheets:
        raise ValueError("No hay incidencias para exportar.")

    return IssueWorkbookExport(
        content=dataframes_to_xlsx_bytes(
            sheets,
            include_index=False,
            hyperlink_columns_by_sheet=hyperlinks,
        ),
        sheet_names=tuple(sheet_name for sheet_name, _ in sheets),
        row_count=int(sum(len(sheet_df) for _, sheet_df in sheets)),
    )
