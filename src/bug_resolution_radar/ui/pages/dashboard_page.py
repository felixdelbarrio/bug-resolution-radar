"""Top-level dashboard page router and section orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Final, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.notes import NotesStore
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.components.filters import render_filters, render_status_priority_matrix
from bug_resolution_radar.ui.dashboard.data_context import build_dashboard_data_context
from bug_resolution_radar.ui.dashboard.issues import render_issues_tab
from bug_resolution_radar.ui.dashboard.kanban import render_kanban_tab
from bug_resolution_radar.ui.dashboard.layout import apply_dashboard_layout
from bug_resolution_radar.ui.dashboard.notes import render_notes_tab
from bug_resolution_radar.ui.dashboard.overview import render_overview_kpis, render_overview_tab
from bug_resolution_radar.ui.dashboard.trends import render_trends_tab
from bug_resolution_radar.ui.pages.insights_page import render as render_insights_page

DASHBOARD_SECTIONS: Final[List[str]] = [
    "overview",
    "issues",
    "kanban",
    "trends",
    "insights",
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
    return df.loc[mask].copy(deep=False)


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

    if section in {"issues", "kanban", "trends"}:
        render_filters(scoped_df, key_prefix="dashboard")

    ctx = build_dashboard_data_context(
        df_all=scoped_df,
        settings=settings,
        include_kpis=section in {"overview", "trends", "insights"},
    )

    if section == "overview":
        render_overview_kpis(kpis=ctx.kpis, dff=ctx.dff, open_df=ctx.open_df)
        render_overview_tab(settings=settings, kpis=ctx.kpis, dff=ctx.dff, open_df=ctx.open_df)
        render_status_priority_matrix(ctx.open_df, ctx.fs, key_prefix="mx_overview")
    elif section == "issues":
        render_issues_tab(dff=ctx.dff)
    elif section == "kanban":
        render_kanban_tab(open_df=ctx.open_df)
    elif section == "trends":
        render_trends_tab(dff=ctx.dff, open_df=ctx.open_df, kpis=ctx.kpis)
    elif section == "insights":
        render_insights_page(settings, dff_filtered=ctx.dff, kpis=ctx.kpis)
    elif section == "notes":
        if notes is None:
            notes = NotesStore(Path(settings.NOTES_PATH))
            notes.load()
        render_notes_tab(dff=ctx.dff, notes=notes)

    return section
