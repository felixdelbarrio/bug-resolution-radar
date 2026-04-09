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
from bug_resolution_radar.ui.insights.state import (
    INSIGHTS_FUNCTIONALITY_KEY as _INSIGHTS_FUNCTIONALITY_KEY,
    INSIGHTS_FUNCTIONALITY_WIDGET_KEY as _INSIGHTS_FUNCTIONALITY_WIDGET_KEY,
    INSIGHTS_PRIORITY_KEY as _INSIGHTS_PRIORITY_KEY,
    INSIGHTS_PRIORITY_WIDGET_KEY as _INSIGHTS_PRIORITY_WIDGET_KEY,
    INSIGHTS_STATUS_KEY as _INSIGHTS_STATUS_KEY,
    INSIGHTS_STATUS_WIDGET_KEY as _INSIGHTS_STATUS_WIDGET_KEY,
    INSIGHTS_VIEW_MODE_KEY as _INSIGHTS_VIEW_MODE_KEY,
    INSIGHTS_VIEW_MODE_WIDGET_KEY as _INSIGHTS_VIEW_MODE_WIDGET_KEY,
)
from bug_resolution_radar.ui.insights.top_topics import render_top_topics_tab


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
            border-radius: 18px !important;
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 52%, transparent) !important;
            background:
              radial-gradient(110% 150% at 0% 0%, color-mix(in srgb, var(--bbva-primary) 18%, transparent), transparent 58%),
              radial-gradient(120% 150% at 100% 0%, color-mix(in srgb, var(--bbva-link) 18%, transparent), transparent 60%),
              color-mix(in srgb, var(--bbva-surface) 92%, var(--bbva-surface-2));
            box-shadow:
              0 14px 34px color-mix(in srgb, var(--bbva-primary) 14%, transparent),
              inset 0 1px 0 color-mix(in srgb, #ffffff 26%, transparent);
            padding: 0.68rem 0.72rem 0.56rem 0.72rem !important;
            margin-bottom: 0.5rem !important;
          }
          .st-key-insights_combo_panel [data-testid="stMarkdownContainer"] p {
            margin-bottom: 0.2rem !important;
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
            margin-bottom: 0.3rem;
          }
          .st-key-insights_combo_panel .insights-combo-row {
            margin-top: 0.08rem;
          }
          .st-key-insights_combo_panel [data-baseweb="select"] > div {
            min-height: 2.34rem !important;
            border-radius: 12px !important;
            border: 1px solid color-mix(in srgb, var(--bbva-border) 84%, transparent) !important;
            background: color-mix(in srgb, var(--bbva-surface) 90%, var(--bbva-surface-2)) !important;
            box-shadow:
              inset 0 1px 0 color-mix(in srgb, #ffffff 10%, transparent),
              0 2px 8px color-mix(in srgb, var(--bbva-primary) 6%, transparent) !important;
          }
          .st-key-insights_combo_panel [data-baseweb="select"] > div:hover {
            border-color: color-mix(in srgb, var(--bbva-primary) 58%, transparent) !important;
            background: color-mix(in srgb, var(--bbva-surface) 84%, var(--bbva-surface-2)) !important;
          }
          .st-key-insights_combo_panel [data-baseweb="select"] > div:focus-within {
            border-color: color-mix(in srgb, var(--bbva-primary) 78%, transparent) !important;
            box-shadow:
              0 0 0 2px color-mix(in srgb, var(--bbva-primary) 24%, transparent),
              inset 0 1px 0 color-mix(in srgb, #ffffff 12%, transparent) !important;
          }
          .st-key-insights_combo_panel [data-baseweb="tag"] {
            border-radius: 999px !important;
            border: 1px solid color-mix(in srgb, var(--bbva-primary) 54%, transparent) !important;
            background: color-mix(in srgb, var(--bbva-primary) 18%, transparent) !important;
            color: var(--bbva-text) !important;
            font-weight: 700 !important;
          }
          .st-key-insights_combo_panel [data-baseweb="select"] input::placeholder {
            color: color-mix(in srgb, var(--bbva-text-muted) 90%, transparent) !important;
            opacity: 0.95 !important;
          }
          .st-key-insights_combo_panel [data-testid="stMultiSelect"] label p,
          .st-key-insights_combo_panel [data-testid="stSelectbox"] label p {
            font-size: 0.79rem !important;
            font-weight: 780 !important;
            letter-spacing: 0.04em !important;
            text-transform: uppercase !important;
            color: color-mix(in srgb, var(--bbva-text) 84%, var(--bbva-primary)) !important;
          }
          @media (max-width: 980px) {
            .st-key-insights_combo_panel {
              border-radius: 14px !important;
              padding: 0.52rem 0.52rem 0.42rem 0.52rem !important;
            }
            .st-key-insights_combo_panel [data-baseweb="select"] > div {
              min-height: 2.26rem !important;
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
    status_key_missing = _INSIGHTS_STATUS_KEY not in st.session_state
    status_widget_missing = _INSIGHTS_STATUS_WIDGET_KEY not in st.session_state
    st.session_state.setdefault(_INSIGHTS_VIEW_MODE_KEY, INSIGHTS_VIEW_MODE_QUINCENAL)
    st.session_state.setdefault(_INSIGHTS_STATUS_KEY, [])
    st.session_state.setdefault(_INSIGHTS_PRIORITY_KEY, [])
    st.session_state.setdefault(_INSIGHTS_FUNCTIONALITY_KEY, [])
    st.session_state.setdefault(
        _INSIGHTS_VIEW_MODE_WIDGET_KEY,
        st.session_state.get(_INSIGHTS_VIEW_MODE_KEY, INSIGHTS_VIEW_MODE_QUINCENAL),
    )
    st.session_state.setdefault(
        _INSIGHTS_STATUS_WIDGET_KEY,
        list(st.session_state.get(_INSIGHTS_STATUS_KEY) or []),
    )
    st.session_state.setdefault(
        _INSIGHTS_PRIORITY_WIDGET_KEY,
        list(st.session_state.get(_INSIGHTS_PRIORITY_KEY) or []),
    )
    st.session_state.setdefault(
        _INSIGHTS_FUNCTIONALITY_WIDGET_KEY,
        list(st.session_state.get(_INSIGHTS_FUNCTIONALITY_KEY) or []),
    )

    initial_ctx = build_insights_combo_context(
        accumulated_df=accumulated_df,
        quincenal_df=quincenal_df,
        view_mode=st.session_state.get(
            _INSIGHTS_VIEW_MODE_WIDGET_KEY, INSIGHTS_VIEW_MODE_QUINCENAL
        ),
        selected_statuses=list(st.session_state.get(_INSIGHTS_STATUS_WIDGET_KEY) or []),
        selected_priorities=list(st.session_state.get(_INSIGHTS_PRIORITY_WIDGET_KEY) or []),
        selected_functionalities=list(
            st.session_state.get(_INSIGHTS_FUNCTIONALITY_WIDGET_KEY) or []
        ),
        apply_default_status_when_empty=(status_key_missing and status_widget_missing),
    )
    st.session_state[_INSIGHTS_VIEW_MODE_KEY] = initial_ctx.view_mode
    st.session_state[_INSIGHTS_STATUS_KEY] = list(initial_ctx.selected_statuses)
    st.session_state[_INSIGHTS_PRIORITY_KEY] = list(initial_ctx.selected_priorities)
    st.session_state[_INSIGHTS_FUNCTIONALITY_KEY] = list(initial_ctx.selected_functionalities)
    # Keep widget values sanitized to available options without overriding user changes.
    st.session_state[_INSIGHTS_VIEW_MODE_WIDGET_KEY] = initial_ctx.view_mode
    st.session_state[_INSIGHTS_STATUS_WIDGET_KEY] = list(initial_ctx.selected_statuses)
    st.session_state[_INSIGHTS_PRIORITY_WIDGET_KEY] = list(initial_ctx.selected_priorities)
    st.session_state[_INSIGHTS_FUNCTIONALITY_WIDGET_KEY] = list(
        initial_ctx.selected_functionalities
    )

    _inject_insights_combo_panel_css()
    with st.container(key="insights_combo_panel"):
        st.markdown(
            '<div class="insights-combo-kicker">Filtros</div>',
            unsafe_allow_html=True,
        )

        r1_view, r1_status = st.columns([1.12, 1.88], gap="small")
        r2_priority, r2_theme = st.columns([1.0, 2.0], gap="small")

        with r1_view:
            st.selectbox(
                "Vista",
                options=list(INSIGHTS_VIEW_MODE_OPTIONS),
                format_func=lambda mode: INSIGHTS_VIEW_MODE_LABELS.get(mode, str(mode)),
                key=_INSIGHTS_VIEW_MODE_WIDGET_KEY,
                help=(
                    "Valores quincena actual (por defecto) o vista acumulada para analizar "
                    "la tendencia histórica."
                ),
            )
        with r1_status:
            st.multiselect(
                "Estado",
                options=list(initial_ctx.status_options),
                key=_INSIGHTS_STATUS_WIDGET_KEY,
                placeholder="Sin valor (todos)",
            )
        with r2_priority:
            st.multiselect(
                "Prioridad",
                options=list(initial_ctx.priority_options),
                key=_INSIGHTS_PRIORITY_WIDGET_KEY,
                placeholder="Sin valor (todas)",
            )
        with r2_theme:
            st.multiselect(
                "Funcionalidades",
                options=list(initial_ctx.functionality_options),
                key=_INSIGHTS_FUNCTIONALITY_WIDGET_KEY,
                placeholder="Sin valor (todas)",
                help=("Listado dinámico según la vista elegida y los filtros de prioridad/estado."),
            )
        final_ctx = build_insights_combo_context(
            accumulated_df=accumulated_df,
            quincenal_df=quincenal_df,
            view_mode=st.session_state.get(
                _INSIGHTS_VIEW_MODE_WIDGET_KEY, INSIGHTS_VIEW_MODE_QUINCENAL
            ),
            selected_statuses=list(st.session_state.get(_INSIGHTS_STATUS_WIDGET_KEY) or []),
            selected_priorities=list(st.session_state.get(_INSIGHTS_PRIORITY_WIDGET_KEY) or []),
            selected_functionalities=list(
                st.session_state.get(_INSIGHTS_FUNCTIONALITY_WIDGET_KEY) or []
            ),
            apply_default_status_when_empty=False,
        )
        st.session_state[_INSIGHTS_STATUS_KEY] = list(final_ctx.selected_statuses)
        st.session_state[_INSIGHTS_PRIORITY_KEY] = list(final_ctx.selected_priorities)
        st.session_state[_INSIGHTS_FUNCTIONALITY_KEY] = list(final_ctx.selected_functionalities)
        st.session_state[_INSIGHTS_VIEW_MODE_KEY] = final_ctx.view_mode

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
            combo_ctx = _render_insights_combo_panel(
                accumulated_df=dff,
                quincenal_df=dff_quincenal,
            )
            scoped = _safe_df(combo_ctx.filtered_df)
            use_accumulated_scope = combo_ctx.view_mode == INSIGHTS_VIEW_MODE_ACCUMULATED
            history_ctx = build_insights_combo_context(
                accumulated_df=dff,
                quincenal_df=dff_quincenal,
                view_mode=INSIGHTS_VIEW_MODE_ACCUMULATED,
                selected_statuses=list(combo_ctx.selected_statuses),
                selected_priorities=list(combo_ctx.selected_priorities),
                selected_functionalities=list(combo_ctx.selected_functionalities),
                apply_default_status_when_empty=False,
            )
            render_top_topics_tab(
                settings=settings,
                dff_filtered=scoped,
                dff_history=_safe_df(history_ctx.filtered_df),
                kpis=kpis,
                use_accumulated_scope=use_accumulated_scope,
                header_left_render=None,
            )
        with t2:
            render_duplicates_tab(
                settings=settings,
                dff_filtered=dff_quincenal,
                header_left_render=None,
            )
        with t3:
            render_backlog_people_tab(
                settings=settings,
                dff_filtered=dff_quincenal,
                header_left_render=None,
            )
        with t4:
            render_ops_health_tab(
                settings=settings,
                dff_filtered=dff_quincenal,
                header_left_render=None,
            )
