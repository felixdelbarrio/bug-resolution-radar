from __future__ import annotations

from pathlib import Path
from typing import List

import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.kpis import compute_kpis
from bug_resolution_radar.notes import NotesStore
from bug_resolution_radar.ui.common import df_from_issues_doc, load_issues_doc
from bug_resolution_radar.ui.components.filters import apply_filters, render_status_priority_matrix

# ✅ Modules live in bug_resolution_radar.ui.dashboard.*
from bug_resolution_radar.ui.dashboard.layout import apply_dashboard_layout
from bug_resolution_radar.ui.dashboard.state import get_filter_state, open_only
from bug_resolution_radar.ui.dashboard.overview import render_overview_tab
from bug_resolution_radar.ui.dashboard.issues import render_issues_tab
from bug_resolution_radar.ui.dashboard.kanban import render_kanban_tab
from bug_resolution_radar.ui.dashboard.trends import render_trends_tab
from bug_resolution_radar.ui.pages.insights_page import render as render_insights_page
from bug_resolution_radar.ui.dashboard.notes import render_notes_tab


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

    # Load doc + dataframe
    doc = load_issues_doc(settings.DATA_PATH)
    df = df_from_issues_doc(doc)

    if df.empty:
        st.warning("No hay datos todavía. Ve a la pestaña de Ingesta y ejecuta una ingesta.")
        return

    # Notes (local)
    notes = NotesStore(Path(settings.NOTES_PATH))
    notes.load()

    # Read current filters from session_state (no widgets are created here)
    fs = get_filter_state()
    dff = apply_filters(df, fs)
    open_df = open_only(dff)

    # Compute KPIs once per rerun for the currently filtered dataframe
    kpis = compute_kpis(dff, settings=settings)

    # Tabs (support jump-to-tab)
    default_idx = _consume_jump_tab()
    tabs = st.tabs(["📌 Resumen", "🧾 Issues", "📋 Kanban", "📈 Tendencias", "🧠 Insights", "🗒️ Notas"])

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
                render_overview_tab(settings=settings, kpis=kpis, dff=dff, open_df=open_df)

                st.markdown("---")

                # 2) Justo debajo: Matriz Estado x Priority (abiertas)
                # ⚠️ key_prefix distinto para evitar IDs duplicados si en el futuro se vuelve a renderizar en otro tab
                render_status_priority_matrix(open_df, fs, key_prefix="mx_overview")

            elif name == "issues":
                # ✅ En Issues ya NO mostramos la matriz.
                # ✅ Filtros deben renderizarse sobre el dataset completo para no “encoger” opciones.
                # ✅ Pasamos también dff para compatibilidad y para que, si quieres, la tabla se base en la vista filtrada.
                render_issues_tab(df_all=df, dff=dff)

            elif name == "kanban":
                render_kanban_tab(open_df=open_only(dff))

            elif name == "trends":
                # Filtros SOLO aquí + 1 gráfico (modo slide) + contenedor en trends.py
                render_trends_tab(settings=settings, df_all=df)

            elif name == "insights":
                render_insights_page(settings, dff_filtered=dff, kpis=kpis)

            elif name == "notes":
                render_notes_tab(dff=dff, notes=notes)