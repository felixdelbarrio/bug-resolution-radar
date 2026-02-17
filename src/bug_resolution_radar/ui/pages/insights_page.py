"""Insights page router for top topics, duplicates, people and operational health."""

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
    st.session_state.pop("__jump_to_insights_tab", None)

    st.markdown(
        """
        <style>
          .st-key-insights_shell div[data-baseweb="tab-list"] {
            margin-bottom: 0.34rem !important;
          }
          .st-key-insights_shell div[data-testid="stTabs"] div[data-baseweb="tab-panel"] {
            padding-top: 0.56rem !important;
          }
          .st-key-insights_shell div[data-testid="stTabs"] div[data-baseweb="tab-panel"] > div[data-testid="stVerticalBlock"] {
            row-gap: 0.44rem !important;
          }
          @media (max-width: 860px) {
            .st-key-insights_shell div[data-testid="stTabs"] div[data-baseweb="tab-panel"] {
              padding-top: 0.42rem !important;
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="insights_shell"):
        t1, t2, t3, t4 = st.tabs(["Top tópicos", "Duplicados", "Personas", "Salud operativa"])

        with t1:
            render_top_topics_tab(settings=settings, dff_filtered=dff, kpis=kpis)
        with t2:
            render_duplicates_tab(settings=settings, dff_filtered=dff)
        with t3:
            render_backlog_people_tab(settings=settings, dff_filtered=dff)
        with t4:
            render_ops_health_tab(settings=settings, dff_filtered=dff)
