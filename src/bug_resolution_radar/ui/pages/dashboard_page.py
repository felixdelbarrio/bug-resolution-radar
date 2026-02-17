from __future__ import annotations

from pathlib import Path
from typing import List

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


def _tab_names() -> List[str]:
    return ["overview", "issues", "kanban", "trends", "insights", "notes"]


def _tab_index_for(name: str) -> int:
    name = (name or "").strip().lower()
    names = _tab_names()
    return names.index(name) if name in names else 0


def _consume_jump_tab() -> int:
    """
    Allows other pages/components to request a tab jump on next rerun by setting:
      st.session_state["__jump_to_tab"] = "issues" | "trends" | ...
    We consume it once to avoid sticky behavior.
    """
    jump = st.session_state.get("__jump_to_tab")
    if jump:
        try:
            idx = _tab_index_for(str(jump))
        finally:
            # consume
            st.session_state.pop("__jump_to_tab", None)
        return idx
    return 0


def render(settings: Settings) -> None:
    st.subheader("Dashboard")

    # Layout / styles (wide, spacing, etc.)
    apply_dashboard_layout()

    # Load dataframe (cached by file mtime to minimize rerun cost)
    df = load_issues_df(settings.DATA_PATH)

    if df.empty:
        st.warning("No hay datos todavía. Ve a la pestaña de Ingesta y ejecuta una ingesta.")
        return

    # Notes (local)
    notes = NotesStore(Path(settings.NOTES_PATH))
    notes.load()

    # Single filters bar + single data context for every tab (no per-tab recompute divergence).
    render_filters(df, key_prefix="dashboard")
    ctx = build_dashboard_data_context(df_all=df, settings=settings)

    # Tabs (support jump-to-tab)
    default_idx = _consume_jump_tab()
    tabs = st.tabs(
        ["📌 Resumen", "🧾 Issues", "📋 Kanban", "📈 Tendencias", "🧠 Insights", "🗒️ Notas"]
    )

    # If we need a jump, we still render all blocks, but we put the requested tab first for Streamlit focus.
    # Streamlit doesn't officially support programmatic tab selection; reordering is the practical workaround.
    # We keep semantics stable by mapping blocks to the right tab object.
    if default_idx != 0:
        order = [default_idx] + [i for i in range(len(tabs)) if i != default_idx]
        tabs = [tabs[i] for i in order]

        # And map which logical tab each "slot" corresponds to
        logical = ["overview", "issues", "kanban", "trends", "insights", "notes"]
        logical = [logical[i] for i in order]
    else:
        logical = ["overview", "issues", "kanban", "trends", "insights", "notes"]

    # Render by logical name
    for tab, name in zip(tabs, logical):
        with tab:
            if name == "overview":
                # 1) Resumen (arriba): los 3 gráficos configurados (dentro de overview_tab)
                render_overview_tab(
                    settings=settings, kpis=ctx.kpis, dff=ctx.dff, open_df=ctx.open_df
                )

                st.markdown("---")

                # 2) Justo debajo: Matriz Estado x Priority (abiertas)
                # ⚠️ key_prefix distinto para evitar IDs duplicados si en el futuro se vuelve a renderizar en otro tab
                render_status_priority_matrix(ctx.open_df, ctx.fs, key_prefix="mx_overview")

            elif name == "issues":
                render_issues_tab(dff=ctx.dff)

            elif name == "kanban":
                render_kanban_tab(open_df=ctx.open_df)

            elif name == "trends":
                render_trends_tab(dff=ctx.dff, open_df=ctx.open_df, kpis=ctx.kpis)

            elif name == "insights":
                render_insights_page(settings, dff_filtered=ctx.dff, kpis=ctx.kpis)

            elif name == "notes":
                render_notes_tab(dff=ctx.dff, notes=notes)
