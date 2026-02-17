from __future__ import annotations

from pathlib import Path
from typing import Final, List

import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.notes import NotesStore
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.components.filters import render_filters, render_status_priority_matrix

# ✅ Modules live in bug_resolution_radar.ui.dashboard.*
from bug_resolution_radar.ui.dashboard.data_context import build_dashboard_data_context
from bug_resolution_radar.ui.dashboard.issues import render_issues_tab
from bug_resolution_radar.ui.dashboard.kanban import render_kanban_tab
from bug_resolution_radar.ui.dashboard.layout import apply_dashboard_layout
from bug_resolution_radar.ui.dashboard.notes import render_notes_tab
from bug_resolution_radar.ui.dashboard.overview import render_overview_tab
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
    return list(DASHBOARD_SECTIONS)


def normalize_dashboard_section(section: str | None) -> str:
    s = (section or "").strip().lower()
    return s if s in DASHBOARD_SECTIONS else "overview"


def render(settings: Settings, *, active_section: str = "overview") -> str:
    section = normalize_dashboard_section(active_section)

    # Layout / styles
    apply_dashboard_layout()

    # Load dataframe (cached by file mtime to minimize rerun cost)
    df = load_issues_df(settings.DATA_PATH)

    if df.empty:
        st.warning("No hay datos todavía. Usa la opción Ingesta de la barra superior.")
        return section

    # Notes (local)
    notes = NotesStore(Path(settings.NOTES_PATH))
    notes.load()

    # Filters only in Issues/Kanban/Trends (single canonical state for all sections).
    if section in {"issues", "kanban", "trends"}:
        render_filters(df, key_prefix="dashboard")

    ctx = build_dashboard_data_context(df_all=df, settings=settings)

    if section == "overview":
        # Summary + matrix (matrix remains synchronized with canonical filters).
        render_overview_tab(settings=settings, kpis=ctx.kpis, dff=ctx.dff, open_df=ctx.open_df)
        st.markdown("---")
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
        render_notes_tab(dff=ctx.dff, notes=notes)

    return section
