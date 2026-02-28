"""Top-level dashboard page router and section orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Final, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.notes import NotesStore
from bug_resolution_radar.ui.cache import cached_by_signature
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.components.filters import render_filters, render_status_priority_matrix
from bug_resolution_radar.ui.dashboard.data_context import build_dashboard_data_context
from bug_resolution_radar.ui.dashboard.layout import apply_dashboard_layout
from bug_resolution_radar.ui.dashboard.next_best_banner import render_next_best_banner
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
)
from bug_resolution_radar.ui.dashboard.tabs.issues_tab import render_issues_tab
from bug_resolution_radar.ui.dashboard.tabs.kanban_tab import render_kanban_tab
from bug_resolution_radar.ui.dashboard.tabs.notes_tab import render_notes_tab
from bug_resolution_radar.ui.dashboard.tabs.overview_tab import (
    render_overview_kpis,
    render_overview_tab,
)
from bug_resolution_radar.ui.dashboard.tabs.trends_tab import render_trends_tab
from bug_resolution_radar.ui.pages.insights_page import render as render_insights_page

DASHBOARD_SECTIONS: Final[List[str]] = [
    "overview",
    "insights",
    "trends",
    "issues",
    "kanban",
    "notes",
]


def dashboard_sections() -> List[str]:
    """Return ordered list of dashboard sections."""
    return list(DASHBOARD_SECTIONS)


def normalize_dashboard_section(section: str | None) -> str:
    """Normalize an arbitrary section value to a supported section id."""
    s = (section or "").strip().lower()
    return s if s in DASHBOARD_SECTIONS else "overview"


def _apply_workspace_source_scope(df: pd.DataFrame) -> pd.DataFrame:
    """Scope dataframe by currently selected country/source when columns are available."""
    if df is None or df.empty:
        return pd.DataFrame()

    selected_country = str(st.session_state.get("workspace_country") or "").strip()
    selected_source_id = str(st.session_state.get("workspace_source_id") or "").strip()
    if not selected_country and not selected_source_id:
        return df

    mask = pd.Series(True, index=df.index)
    if selected_country and "country" in df.columns:
        mask &= df["country"].fillna("").astype(str).eq(selected_country)
    if selected_source_id and "source_id" in df.columns:
        mask &= df["source_id"].fillna("").astype(str).eq(selected_source_id)
    if bool(mask.all()):
        return df.copy(deep=False)
    return df.loc[mask].copy(deep=False)


def _cache_filter_values(key: str) -> tuple[str, ...]:
    vals = [str(v).strip() for v in list(st.session_state.get(key) or []) if str(v).strip()]
    return tuple(sorted(set(vals)))


def _dashboard_data_cache_signature(
    *,
    settings: Settings,
    section: str,
    scoped_df: pd.DataFrame,
    include_kpis: bool,
    include_timeseries_chart: bool,
) -> str:
    data_path = Path(str(getattr(settings, "DATA_PATH", "") or "")).resolve()
    if data_path.exists():
        stat = data_path.stat()
        data_rev = f"{stat.st_mtime_ns}:{stat.st_size}"
    else:
        data_rev = "missing"

    selected_country = str(st.session_state.get("workspace_country") or "").strip()
    selected_source = str(st.session_state.get("workspace_source_id") or "").strip()
    filters_sig = (
        _cache_filter_values(FILTER_STATUS_KEY),
        _cache_filter_values(FILTER_PRIORITY_KEY),
        _cache_filter_values(FILTER_ASSIGNEE_KEY),
    )

    # Scoped dataframe is derived from source/country, but include a tiny shape signature
    # to stay safe when data is injected from tests or non-file sources.
    scoped_sig = f"{len(scoped_df)}:{len(scoped_df.columns)}"
    return "|".join(
        [
            str(data_path),
            data_rev,
            selected_country,
            selected_source,
            str(section),
            "kpis=1" if include_kpis else "kpis=0",
            "ts=1" if include_timeseries_chart else "ts=0",
            f"lookback_m={getattr(settings, 'ANALYSIS_LOOKBACK_MONTHS', 0)}",
            scoped_sig,
            str(filters_sig),
        ]
    )


def render(settings: Settings, *, active_section: str = "overview") -> str:
    """Render selected dashboard section and return normalized section id."""
    section = normalize_dashboard_section(active_section)

    apply_dashboard_layout()

    try:
        df = load_issues_df(settings.DATA_PATH)
    except Exception as exc:
        st.error(
            "No se pudieron cargar las incidencias. Revisa el archivo de datos o ejecuta Ingesta."
        )
        st.caption(f"Detalle técnico: {exc}")
        return section
    scoped_df = _apply_workspace_source_scope(df)
    if scoped_df.empty:
        st.warning("No hay datos todavía. Usa la opción Ingesta de la barra superior.")
        return section

    notes: NotesStore | None = None
    if section == "notes":
        notes = NotesStore(Path(settings.NOTES_PATH))
        notes.load()

    include_kpis = section in {"overview", "trends", "insights"}
    include_timeseries_chart = section in {"overview", "trends"}
    cache_signature = _dashboard_data_cache_signature(
        settings=settings,
        section=section,
        scoped_df=scoped_df,
        include_kpis=include_kpis,
        include_timeseries_chart=include_timeseries_chart,
    )
    ctx, _ = cached_by_signature(
        "dashboard:data_context",
        cache_signature,
        lambda: build_dashboard_data_context(
            df_all=scoped_df,
            settings=settings,
            include_kpis=include_kpis,
            include_timeseries_chart=include_timeseries_chart,
        ),
        max_entries=18,
    )
    if ctx.df_all.empty:
        st.warning(
            "No hay datos en la ventana de análisis configurada. "
            "Amplía los meses en Configuración → Preferencias → Favoritos."
        )
        return section

    if section in {"issues", "kanban"}:
        render_next_best_banner(df_all=ctx.df_all, section=section)
        render_filters(ctx.df_all, key_prefix="dashboard")

    if section == "overview":
        render_overview_kpis(kpis=ctx.kpis, dff=ctx.dff, open_df=ctx.open_df)
        render_overview_tab(settings=settings, kpis=ctx.kpis, dff=ctx.dff, open_df=ctx.open_df)
        render_status_priority_matrix(ctx.dff, ctx.fs, key_prefix="mx_overview")
    elif section == "issues":
        render_issues_tab(dff=ctx.dff, settings=settings)
    elif section == "kanban":
        render_kanban_tab(open_df=ctx.open_df)
    elif section == "trends":
        render_trends_tab(settings=settings, dff=ctx.dff, open_df=ctx.open_df, kpis=ctx.kpis)
    elif section == "insights":
        render_insights_page(settings, dff_filtered=ctx.dff, kpis=ctx.kpis)
    elif section == "notes":
        if notes is None:
            notes = NotesStore(Path(settings.NOTES_PATH))
            notes.load()
        render_notes_tab(dff=ctx.dff, notes=notes)

    return section
