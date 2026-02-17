# src/bug_resolution_radar/ui/pages/insights_page.py
from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.insights.backlog_people import render_backlog_people_tab
from bug_resolution_radar.ui.insights.duplicates import render_duplicates_tab
from bug_resolution_radar.ui.insights.ops_health import render_ops_health_tab
from bug_resolution_radar.ui.insights.top_topics import render_top_topics_tab


def _safe_df(x: Any) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


def render(
    settings: Settings,
    *,
    dff_filtered: pd.DataFrame,
    kpis: Dict[str, Any],
) -> None:
    """
    Insights page (tab):
      - Tabs para modularizar:
          1) Top tópicos (Top 10 problemas/funcionalidades)
          2) Duplicados (clusters similares)
          3) Personas (concentración + modo acción)
          4) Salud operativa (KPIs + top antiguas)
    """
    dff = _safe_df(dff_filtered)
    if dff.empty:
        st.warning("No hay datos con los filtros actuales.")
        return

    st.markdown(
        """
        <style>
          div[data-testid="stTabs"] div[data-baseweb="tab-panel"] {
            padding-top: 0.20rem !important;
          }
          div[data-testid="stTabs"] div[data-baseweb="tab-border"] {
            margin-bottom: 0.20rem !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    views = {
        "top_topics": "Top tópicos",
        "duplicates": "Duplicados",
        "people": "Personas",
        "ops_health": "Salud operativa",
    }
    default_view = "top_topics"
    jump_view = str(st.session_state.pop("__jump_to_insights_tab", "") or "").strip()
    if jump_view in views:
        st.session_state["insights_inner_tab"] = jump_view
    if str(st.session_state.get("insights_inner_tab") or "") not in views:
        st.session_state["insights_inner_tab"] = default_view

    picked = st.segmented_control(
        "Vista Insights",
        options=list(views.keys()),
        format_func=lambda k: views.get(str(k), str(k)),
        key="insights_inner_tab",
        selection_mode="single",
        label_visibility="collapsed",
    )
    view = str(picked or st.session_state.get("insights_inner_tab") or default_view)

    if view == "top_topics":
        render_top_topics_tab(settings=settings, dff_filtered=dff, kpis=kpis)
    elif view == "duplicates":
        render_duplicates_tab(settings=settings, dff_filtered=dff)
    elif view == "people":
        render_backlog_people_tab(settings=settings, dff_filtered=dff)
    else:
        render_ops_health_tab(settings=settings, dff_filtered=dff)
