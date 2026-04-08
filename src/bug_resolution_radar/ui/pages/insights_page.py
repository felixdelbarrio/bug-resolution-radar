"""Insights page router for top topics, duplicates, people and operational health."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.insights_scope import (
    INSIGHTS_VIEW_MODE_ACCUMULATED,
    INSIGHTS_VIEW_MODE_LABELS,
    INSIGHTS_VIEW_MODE_OPTIONS,
    INSIGHTS_VIEW_MODE_QUINCENAL,
    InsightsComboContext,
    build_insights_combo_context,
)
from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.dashboard.quincenal_scope import (
    QUINCENAL_SCOPE_CLOSED_CURRENT,
    QUINCENAL_SCOPE_CREATED_CURRENT,
    apply_issue_key_scope,
    quincenal_scope_options,
)
from bug_resolution_radar.ui.insights.backlog_people import render_backlog_people_tab
from bug_resolution_radar.ui.insights.duplicates import render_duplicates_tab
from bug_resolution_radar.ui.insights.ops_health import render_ops_health_tab
from bug_resolution_radar.ui.insights.period_summary import render_period_summary_tab
from bug_resolution_radar.ui.insights.top_topics import render_top_topics_tab

_INSIGHTS_VIEW_MODE_KEY = "insights::combo::view_mode"
_INSIGHTS_STATUS_KEY = "insights::combo::status_values"
_INSIGHTS_PRIORITY_KEY = "insights::combo::priority_values"
_INSIGHTS_FUNCTIONALITY_KEY = "insights::combo::functionality_values"


def _safe_df(x: Any) -> pd.DataFrame:
    return x if isinstance(x, pd.DataFrame) else pd.DataFrame()


def _scope_reference_day(df: pd.DataFrame) -> pd.Timestamp | None:
    safe = _safe_df(df)
    if safe.empty:
        return None
    max_candidates: list[pd.Timestamp] = []
    for col in ("updated", "resolved", "created"):
        if col not in safe.columns:
            continue
        ts = pd.to_datetime(safe[col], errors="coerce", utc=True)
        if ts.notna().any():
            max_ts = ts.max()
            if pd.notna(max_ts):
                max_candidates.append(pd.Timestamp(max_ts))
    if not max_candidates:
        return None
    picked = max(max_candidates)
    try:
        picked = picked.tz_convert(None)
    except Exception:
        try:
            picked = picked.tz_localize(None)
        except Exception:
            pass
    return picked.normalize()


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

    options = quincenal_scope_options(
        safe,
        settings=settings,
        reference_day=_scope_reference_day(safe),
    )
    selected_keys: list[str] = []
    for label in (QUINCENAL_SCOPE_CREATED_CURRENT, QUINCENAL_SCOPE_CLOSED_CURRENT):
        selected_keys.extend(options.get(label, []))

    scoped = apply_issue_key_scope(safe, keys=selected_keys)
    if scoped.empty:
        return pd.DataFrame(columns=list(safe.columns))
    return scoped


def _inject_insights_combo_panel_css() -> None:
    st.markdown(
        """
        <style>
          .st-key-insights_combo_panel {
            border-radius: 16px !important;
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 52%, transparent) !important;
            background:
              radial-gradient(120% 160% at 0% 0%, color-mix(in srgb, var(--bbva-primary) 14%, transparent), transparent 60%),
              radial-gradient(140% 170% at 100% 0%, color-mix(in srgb, var(--bbva-primary) 14%, transparent), transparent 62%),
              color-mix(in srgb, var(--bbva-surface) 92%, var(--bbva-surface-2));
            box-shadow:
              0 10px 28px color-mix(in srgb, var(--bbva-primary) 12%, transparent),
              inset 0 1px 0 color-mix(in srgb, #ffffff 20%, transparent);
            padding: 0.58rem 0.62rem 0.46rem 0.62rem !important;
            margin-bottom: 0.36rem !important;
          }
          .st-key-insights_combo_panel [data-testid="stMarkdownContainer"] p {
            margin-bottom: 0.22rem !important;
          }
          .st-key-insights_combo_panel .insights-combo-kicker {
            display: inline-flex;
            align-items: center;
            gap: 0.38rem;
            border-radius: 999px;
            border: 1px solid color-mix(in srgb, var(--bbva-primary) 42%, transparent);
            background: color-mix(in srgb, var(--bbva-primary) 16%, transparent);
            color: var(--bbva-text);
            font-size: 0.73rem;
            font-weight: 790;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            padding: 0.16rem 0.62rem;
            margin-bottom: 0.34rem;
          }
          .st-key-insights_combo_panel [data-baseweb="select"] > div {
            min-height: 2.24rem !important;
            border-radius: 12px !important;
            border: 1px solid color-mix(in srgb, var(--bbva-border) 84%, transparent) !important;
            background: color-mix(in srgb, var(--bbva-surface) 90%, var(--bbva-surface-2)) !important;
            box-shadow: inset 0 1px 0 color-mix(in srgb, #ffffff 8%, transparent) !important;
          }
          .st-key-insights_combo_panel [data-baseweb="tag"] {
            border-radius: 999px !important;
            border: 1px solid color-mix(in srgb, var(--bbva-primary) 46%, transparent) !important;
            background: color-mix(in srgb, var(--bbva-primary) 16%, transparent) !important;
            color: var(--bbva-text) !important;
            font-weight: 700 !important;
          }
          .st-key-insights_combo_panel [data-testid="stMultiSelect"] label p,
          .st-key-insights_combo_panel [data-testid="stSelectbox"] label p {
            font-size: 0.83rem !important;
            font-weight: 720 !important;
            letter-spacing: 0.01em !important;
          }
          @media (max-width: 980px) {
            .st-key-insights_combo_panel {
              padding: 0.5rem 0.5rem 0.4rem 0.5rem !important;
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_insights_combo_panel(
    *,
    accumulated_df: pd.DataFrame,
    quincenal_df: pd.DataFrame,
) -> InsightsComboContext:
    st.session_state.setdefault(_INSIGHTS_VIEW_MODE_KEY, INSIGHTS_VIEW_MODE_QUINCENAL)
    status_key_missing = _INSIGHTS_STATUS_KEY not in st.session_state
    st.session_state.setdefault(_INSIGHTS_STATUS_KEY, [])
    st.session_state.setdefault(_INSIGHTS_PRIORITY_KEY, [])
    st.session_state.setdefault(_INSIGHTS_FUNCTIONALITY_KEY, [])

    initial_ctx = build_insights_combo_context(
        accumulated_df=accumulated_df,
        quincenal_df=quincenal_df,
        view_mode=st.session_state.get(_INSIGHTS_VIEW_MODE_KEY, INSIGHTS_VIEW_MODE_QUINCENAL),
        selected_statuses=list(st.session_state.get(_INSIGHTS_STATUS_KEY) or []),
        selected_priorities=list(st.session_state.get(_INSIGHTS_PRIORITY_KEY) or []),
        selected_functionalities=list(st.session_state.get(_INSIGHTS_FUNCTIONALITY_KEY) or []),
        apply_default_status_when_empty=status_key_missing,
    )
    st.session_state[_INSIGHTS_VIEW_MODE_KEY] = initial_ctx.view_mode
    st.session_state[_INSIGHTS_STATUS_KEY] = list(initial_ctx.selected_statuses)
    st.session_state[_INSIGHTS_PRIORITY_KEY] = list(initial_ctx.selected_priorities)
    st.session_state[_INSIGHTS_FUNCTIONALITY_KEY] = list(initial_ctx.selected_functionalities)

    _inject_insights_combo_panel_css()
    with st.container(key="insights_combo_panel"):
        st.markdown(
            '<div class="insights-combo-kicker">Control Tower · Insights</div>',
            unsafe_allow_html=True,
        )
        c_view, c_prio, c_status, c_theme = st.columns([1.26, 1.0, 1.22, 1.6], gap="small")

        with c_view:
            st.selectbox(
                "Vista",
                options=list(INSIGHTS_VIEW_MODE_OPTIONS),
                format_func=lambda mode: INSIGHTS_VIEW_MODE_LABELS.get(mode, str(mode)),
                key=_INSIGHTS_VIEW_MODE_KEY,
                help=(
                    "Valores quincena actual (por defecto) o vista acumulada para analizar "
                    "la tendencia histórica."
                ),
            )
        with c_prio:
            st.multiselect(
                "Prioridad",
                options=list(initial_ctx.priority_options),
                key=_INSIGHTS_PRIORITY_KEY,
                placeholder="Sin valor (todas)",
            )
        with c_status:
            st.multiselect(
                "Estado",
                options=list(initial_ctx.status_options),
                key=_INSIGHTS_STATUS_KEY,
                placeholder="Sin valor (todos)",
            )
        with c_theme:
            st.multiselect(
                "Funcionalidades",
                options=list(initial_ctx.functionality_options),
                key=_INSIGHTS_FUNCTIONALITY_KEY,
                placeholder="Sin valor (todas)",
                help=(
                    "Listado dinámico según la vista elegida y los filtros de prioridad/estado."
                ),
            )

    final_ctx = build_insights_combo_context(
        accumulated_df=accumulated_df,
        quincenal_df=quincenal_df,
        view_mode=st.session_state.get(_INSIGHTS_VIEW_MODE_KEY, INSIGHTS_VIEW_MODE_QUINCENAL),
        selected_statuses=list(st.session_state.get(_INSIGHTS_STATUS_KEY) or []),
        selected_priorities=list(st.session_state.get(_INSIGHTS_PRIORITY_KEY) or []),
        selected_functionalities=list(st.session_state.get(_INSIGHTS_FUNCTIONALITY_KEY) or []),
        apply_default_status_when_empty=False,
    )
    st.session_state[_INSIGHTS_STATUS_KEY] = list(final_ctx.selected_statuses)
    st.session_state[_INSIGHTS_PRIORITY_KEY] = list(final_ctx.selected_priorities)
    st.session_state[_INSIGHTS_FUNCTIONALITY_KEY] = list(final_ctx.selected_functionalities)
    return final_ctx


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
    st.session_state.pop("__jump_to_insights_tab", None)
    combo_ctx = _render_insights_combo_panel(
        accumulated_df=dff,
        quincenal_df=dff_quincenal,
    )
    scoped = _safe_df(combo_ctx.filtered_df)
    use_accumulated_scope = combo_ctx.view_mode == INSIGHTS_VIEW_MODE_ACCUMULATED

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
            render_period_summary_tab(settings=settings, dff_filtered=scoped)

        with t1:
            render_top_topics_tab(
                settings=settings,
                dff_filtered=scoped,
                dff_history=scoped,
                kpis=kpis,
                use_accumulated_scope=use_accumulated_scope,
                header_left_render=None,
            )
        with t2:
            render_duplicates_tab(
                settings=settings,
                dff_filtered=scoped,
                header_left_render=None,
            )
        with t3:
            render_backlog_people_tab(
                settings=settings,
                dff_filtered=scoped,
                header_left_render=None,
            )
        with t4:
            render_ops_health_tab(
                settings=settings,
                dff_filtered=scoped,
                header_left_render=None,
            )
