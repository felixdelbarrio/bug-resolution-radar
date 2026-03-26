"""Insights page router for top topics, duplicates, people and operational health."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.dashboard.quincenal_scope import (
    apply_issue_key_scope,
    quincenal_scope_options,
)
from bug_resolution_radar.ui.insights.backlog_people import render_backlog_people_tab
from bug_resolution_radar.ui.insights.duplicates import render_duplicates_tab
from bug_resolution_radar.ui.insights.ops_health import render_ops_health_tab
from bug_resolution_radar.ui.insights.period_summary import render_period_summary_tab
from bug_resolution_radar.ui.insights.top_topics import render_top_topics_tab

_INSIGHTS_SCOPE_ACCUMULATED_KEY = "insights::scope::accumulated"


def _safe_df(x: Any) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


def _insights_quincenal_df(*, settings: Settings, dff: pd.DataFrame) -> pd.DataFrame:
    safe = _safe_df(dff)
    if safe.empty:
        return safe

    if (
        "created" not in safe.columns
        and "resolved" not in safe.columns
        and "updated" not in safe.columns
    ):
        return safe

    options = quincenal_scope_options(safe, settings=settings)
    selected_keys: list[str] = []
    for label in ("Nuevas (quincena actual)", "Cerradas (quincena actual)"):
        selected_keys.extend(options.get(label, []))

    scoped = apply_issue_key_scope(safe, keys=selected_keys)
    if scoped.empty:
        return pd.DataFrame(columns=list(safe.columns))
    return scoped


def _sync_scope_accumulated_from_widget(widget_key: str) -> None:
    st.session_state[_INSIGHTS_SCOPE_ACCUMULATED_KEY] = bool(
        st.session_state.get(widget_key, False)
    )


def _scope_toggle_synced(*, tab_key: str) -> None:
    canonical = bool(st.session_state.get(_INSIGHTS_SCOPE_ACCUMULATED_KEY, False))
    widget_key = f"{_INSIGHTS_SCOPE_ACCUMULATED_KEY}::{tab_key}"
    st.session_state[widget_key] = canonical
    st.checkbox(
        "Vista acumulada",
        key=widget_key,
        help=(
            "Desactivado (por defecto): muestra solo la última quincena. "
            "Activado: mantiene la vista acumulada en Insights."
        ),
        on_change=_sync_scope_accumulated_from_widget,
        args=(widget_key,),
    )


def render(
    settings: Settings,
    *,
    dff_filtered: pd.DataFrame,
    kpis: Dict[str, Any],
) -> None:
    """
    Insights page (tab):
      - Tabs para modularizar:
          1) Resumen quincenal
          2) Por funcionalidad (Top 10 problemas/funcionalidades)
          3) Duplicados (clusters similares)
          4) Personas (concentración + modo acción)
          5) Salud operativa (KPIs + top antiguas)
    """
    dff = _safe_df(dff_filtered)
    if dff.empty:
        st.warning("No hay datos con los filtros actuales.")
        return
    dff_quincenal = _insights_quincenal_df(settings=settings, dff=dff)
    st.session_state.setdefault(_INSIGHTS_SCOPE_ACCUMULATED_KEY, False)
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
        t0, t1, t2, t3, t4 = st.tabs(
            ["Resumen quincenal", "Por funcionalidad", "Duplicados", "Personas", "Salud operativa"]
        )

        with t0:
            render_period_summary_tab(settings=settings, dff_filtered=dff)

        with t1:
            use_accum = bool(st.session_state.get(_INSIGHTS_SCOPE_ACCUMULATED_KEY, False))
            scoped = dff if use_accum else dff_quincenal
            render_top_topics_tab(
                settings=settings,
                dff_filtered=scoped,
                kpis=kpis,
                header_left_render=lambda: _scope_toggle_synced(tab_key="top_topics"),
            )
        with t2:
            use_accum = bool(st.session_state.get(_INSIGHTS_SCOPE_ACCUMULATED_KEY, False))
            scoped = dff if use_accum else dff_quincenal
            render_duplicates_tab(
                settings=settings,
                dff_filtered=scoped,
                header_left_render=lambda: _scope_toggle_synced(tab_key="duplicates"),
            )
        with t3:
            use_accum = bool(st.session_state.get(_INSIGHTS_SCOPE_ACCUMULATED_KEY, False))
            scoped = dff if use_accum else dff_quincenal
            render_backlog_people_tab(
                settings=settings,
                dff_filtered=scoped,
                header_left_render=lambda: _scope_toggle_synced(tab_key="people"),
            )
        with t4:
            use_accum = bool(st.session_state.get(_INSIGHTS_SCOPE_ACCUMULATED_KEY, False))
            scoped = dff if use_accum else dff_quincenal
            render_ops_health_tab(
                settings=settings,
                dff_filtered=scoped,
                header_left_render=lambda: _scope_toggle_synced(tab_key="ops_health"),
            )
