"""Trend charts and adaptive management insights for the dashboard."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from time import perf_counter
from typing import Any, Dict, List, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

from bug_resolution_radar.analytics.kpis import (
    OPEN_AGE_BUCKET_LABELS,
    build_open_age_priority_payload,
    build_timeseries_daily,
)
from bug_resolution_radar.config import Settings
from bug_resolution_radar.theme.design_tokens import BBVA_DARK, BBVA_LIGHT
from bug_resolution_radar.ui.cache import cached_by_signature, dataframe_signature
from bug_resolution_radar.ui.common import (
    normalize_text_col,
    priority_color_map,
    priority_rank,
)
from bug_resolution_radar.ui.dashboard.age_buckets_chart import (
    AGE_BUCKET_ORDER,
    build_age_bucket_points,
    build_age_bucket_priority_distribution,
    build_age_buckets_issue_distribution,
    build_age_buckets_open_priority_stacked,
)
from bug_resolution_radar.ui.dashboard.constants import (
    Y_AXIS_LABEL_OPEN_ISSUES,
    canonical_status_order,
)
from bug_resolution_radar.ui.dashboard.exports.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.dashboard.performance import (
    elapsed_ms,
    render_perf_footer,
    resolve_budget,
)
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
)
from bug_resolution_radar.ui.insights.copilot import (
    build_operational_snapshot,
    build_session_delta_lines,
)
from bug_resolution_radar.ui.insights.engine import ActionInsight, build_trend_insight_pack
from bug_resolution_radar.ui.insights.learning_store import (
    LEARNING_BASELINE_SNAPSHOT_KEY,
    LEARNING_INTERACTIONS_KEY,
    LEARNING_STATE_KEY,
    ensure_learning_session_loaded,
    increment_learning_interactions,
    persist_learning_session,
    set_learning_snapshot,
)
from bug_resolution_radar.ui.style import apply_plotly_bbva

TERMINAL_STATUS_TOKENS: Tuple[str, ...] = (
    "closed",
    "resolved",
    "done",
    "deployed",
    "accepted",
    "cancelled",
    "canceled",
)
_TRENDS_PERF_BUDGETS_MS: dict[str, dict[str, float]] = {
    "default": {
        "selector_scope": 85.0,
        "chart": 315.0,
        "exports": 65.0,
        "insights": 265.0,
        "total": 735.0,
    },
    "timeseries": {
        "selector_scope": 85.0,
        "chart": 275.0,
        "exports": 65.0,
        "insights": 265.0,
        "total": 695.0,
    },
    "age_buckets": {
        "selector_scope": 85.0,
        "chart": 330.0,
        "exports": 65.0,
        "insights": 265.0,
        "total": 770.0,
    },
    "resolution_hist": {
        "selector_scope": 85.0,
        "chart": 350.0,
        "exports": 65.0,
        "insights": 265.0,
        "total": 790.0,
    },
    "open_priority_pie": {
        "selector_scope": 85.0,
        "chart": 245.0,
        "exports": 65.0,
        "insights": 265.0,
        "total": 660.0,
    },
    "open_status_bar": {
        "selector_scope": 85.0,
        "chart": 295.0,
        "exports": 65.0,
        "insights": 265.0,
        "total": 710.0,
    },
}
_TRENDS_PERF_ORDER: list[str] = ["selector_scope", "chart", "exports", "insights", "total"]


def _trends_perf_budget(view: str) -> dict[str, float]:
    return resolve_budget(
        view=view,
        budgets_by_view=_TRENDS_PERF_BUDGETS_MS,
        default_view="default",
    )


def _safe_df(df: pd.DataFrame) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _norm_status_token(value: object) -> str:
    txt = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", txt).strip()


def _status_filter_has_terminal(status_filters: List[str]) -> bool:
    return any(
        any(tok in _norm_status_token(st_name) for tok in TERMINAL_STATUS_TOKENS)
        for st_name in list(status_filters or [])
    )


def _effective_trends_open_scope(
    *,
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
    active_status_filters: List[str],
) -> tuple[pd.DataFrame, bool]:
    """
    Return the dataframe scope for open-like trend charts.

    Normally charts use open_df (abiertas). If active status filters include
    terminal states (e.g. Deployed), open_df can be empty by definition, so we
    switch to the filtered status subset from dff to keep chart behavior coherent.
    """
    safe_open = _safe_df(open_df)
    safe_dff = _safe_df(dff)
    chosen = [str(x).strip() for x in list(active_status_filters or []) if str(x).strip()]
    if not chosen:
        return safe_open, False
    if safe_dff.empty or "status" not in safe_dff.columns:
        return safe_open, False

    status_norm = normalize_text_col(safe_dff["status"], "(sin estado)")
    scoped = safe_dff.loc[status_norm.isin(chosen)].copy(deep=False)
    if scoped.empty:
        return safe_open, False
    if _status_filter_has_terminal(chosen):
        return scoped, True
    return safe_open, False


def _exclude_terminal_status_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude terminal/finalist statuses from an open-like dataframe view."""
    safe = _safe_df(df)
    if safe.empty or "status" not in safe.columns:
        return safe.copy(deep=False)
    status_norm = normalize_text_col(safe["status"], "(sin estado)").map(_norm_status_token)
    terminal_mask = status_norm.map(
        lambda st_name: any(tok in str(st_name or "") for tok in TERMINAL_STATUS_TOKENS)
    )
    return safe.loc[~terminal_mask].copy(deep=False)


def _ensure_learning_state() -> Dict[str, Any]:
    raw = st.session_state.get(LEARNING_STATE_KEY)
    if isinstance(raw, dict):
        state: Dict[str, Any] = raw
    else:
        state = {}
    if not isinstance(state.get("shown_counts"), dict):
        state["shown_counts"] = {}
    if not isinstance(state.get("clicked_counts"), dict):
        state["clicked_counts"] = {}
    if not isinstance(state.get("last_click_filters"), dict):
        state["last_click_filters"] = {"status": [], "priority": [], "assignee": []}
    if not isinstance(state.get("chart_seen_counts"), dict):
        state["chart_seen_counts"] = {}
    if not isinstance(state.get("last_render_token"), str):
        state["last_render_token"] = ""
    if not isinstance(state.get("last_context_token"), str):
        state["last_context_token"] = ""
    if not isinstance(state.get("copilot_intents"), dict):
        state["copilot_intents"] = {}
    st.session_state[LEARNING_STATE_KEY] = state
    return state


def _active_filter_snapshot() -> Dict[str, List[str]]:
    return {
        "status": list(st.session_state.get(FILTER_STATUS_KEY) or []),
        "priority": list(st.session_state.get(FILTER_PRIORITY_KEY) or []),
        "assignee": list(st.session_state.get(FILTER_ASSIGNEE_KEY) or []),
    }


def _dict_any(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _insight_identity(chart_id: str, insight: ActionInsight) -> str:
    base = f"{chart_id.strip().lower()}|{str(insight.title or '').strip().lower()}"
    status = ",".join(
        sorted(
            [str(x).strip().lower() for x in list(insight.status_filters or []) if str(x).strip()]
        )
    )
    priority = ",".join(
        sorted(
            [str(x).strip().lower() for x in list(insight.priority_filters or []) if str(x).strip()]
        )
    )
    assignee = ",".join(
        sorted(
            [str(x).strip().lower() for x in list(insight.assignee_filters or []) if str(x).strip()]
        )
    )
    digest = hashlib.sha1(f"{base}|{status}|{priority}|{assignee}".encode("utf-8")).hexdigest()[:12]
    return f"{chart_id}:{digest}"


def _overlap_ratio(active: List[str], candidate: List[str] | None) -> float:
    cand = [str(x).strip() for x in list(candidate or []) if str(x).strip()]
    if not active or not cand:
        return 0.0
    a = {x.lower() for x in active}
    c = {x.lower() for x in cand}
    if not c:
        return 0.0
    return float(len(a & c)) / float(len(c))


def _personalize_insights(
    cards: List[ActionInsight], *, chart_id: str, active_filters: Dict[str, List[str]]
) -> List[ActionInsight]:
    state = _ensure_learning_state()
    shown_counts = _dict_any(state.get("shown_counts"))
    clicked_counts = _dict_any(state.get("clicked_counts"))
    last_click = _dict_any(state.get("last_click_filters"))
    out: List[ActionInsight] = []

    for card in cards:
        iid = _insight_identity(chart_id, card)
        shown = int(shown_counts.get(iid, 0) or 0)
        clicked = int(clicked_counts.get(iid, 0) or 0)

        novelty_bonus = 0.0
        if shown == 0:
            novelty_bonus = 6.0
        elif shown == 1:
            novelty_bonus = 2.5
        else:
            novelty_bonus = -min(float(shown - 1), 4.0)

        affinity_bonus = min(float(clicked) * 2.0, 6.0)
        active_alignment = 0.0
        active_alignment += 4.0 * _overlap_ratio(
            active_filters.get("status", []), card.status_filters
        )
        active_alignment += 3.5 * _overlap_ratio(
            active_filters.get("priority", []), card.priority_filters
        )
        active_alignment += 3.0 * _overlap_ratio(
            active_filters.get("assignee", []), card.assignee_filters
        )

        last_alignment = 0.0
        last_alignment += 3.0 * _overlap_ratio(
            list(last_click.get("status", []) or []), card.status_filters
        )
        last_alignment += 2.5 * _overlap_ratio(
            list(last_click.get("priority", []) or []), card.priority_filters
        )
        last_alignment += 2.5 * _overlap_ratio(
            list(last_click.get("assignee", []) or []), card.assignee_filters
        )

        if not (card.status_filters or card.priority_filters or card.assignee_filters):
            active_alignment += 0.8

        personalized = ActionInsight(
            title=card.title,
            body=card.body,
            status_filters=list(card.status_filters or []),
            priority_filters=list(card.priority_filters or []),
            assignee_filters=list(card.assignee_filters or []),
            score=float(card.score)
            + novelty_bonus
            + affinity_bonus
            + active_alignment
            + last_alignment,
        )
        out.append(personalized)

    return sorted(out, key=lambda c: float(c.score), reverse=True)


def _render_token(
    *, chart_id: str, dff: pd.DataFrame, open_df: pd.DataFrame, active_filters: Dict[str, List[str]]
) -> str:
    status = ",".join(sorted([str(x) for x in active_filters.get("status", [])]))
    priority = ",".join(sorted([str(x) for x in active_filters.get("priority", [])]))
    assignee = ",".join(sorted([str(x) for x in active_filters.get("assignee", [])]))
    return f"{chart_id}|{len(dff)}|{len(open_df)}|{status}|{priority}|{assignee}"


def _register_shown_insights(
    cards: List[ActionInsight], *, chart_id: str, render_token: str
) -> None:
    state = _ensure_learning_state()
    last_token = str(state.get("last_render_token") or "")
    if last_token == render_token:
        return

    shown_counts = _dict_any(state.get("shown_counts"))
    for card in cards[:6]:
        iid = _insight_identity(chart_id, card)
        shown_counts[iid] = int(shown_counts.get(iid, 0) or 0) + 1
    state["shown_counts"] = shown_counts

    chart_seen = _dict_any(state.get("chart_seen_counts"))
    chart_seen[chart_id] = int(chart_seen.get(chart_id, 0) or 0) + 1
    state["chart_seen_counts"] = chart_seen
    state["last_render_token"] = render_token
    st.session_state[LEARNING_STATE_KEY] = state
    persist_learning_session()


def _track_context_interaction(*, chart_id: str, active_filters: Dict[str, List[str]]) -> None:
    state = _ensure_learning_state()
    status = ",".join(sorted([str(x) for x in active_filters.get("status", [])]))
    priority = ",".join(sorted([str(x) for x in active_filters.get("priority", [])]))
    assignee = ",".join(sorted([str(x) for x in active_filters.get("assignee", [])]))
    token = f"{chart_id}|{status}|{priority}|{assignee}"
    prev = str(state.get("last_context_token") or "")
    if token == prev:
        return
    state["last_context_token"] = token
    st.session_state[LEARNING_STATE_KEY] = state
    increment_learning_interactions(step=1, persist=True)


def _rank_by_canon(values: pd.Series, canon_order: List[str]) -> pd.Series:
    """
    Return an integer rank for each value using canon_order (case-insensitive).
    Unknown values are pushed to the end.
    """
    order_map = {s.lower(): i for i, s in enumerate(canon_order)}

    def _rank(x: object) -> int:
        v = str(x or "").strip().lower()
        return order_map.get(v, 10_000)

    return values.map(_rank)


def _priority_sort_key(priority: object) -> tuple[int, str]:
    p = str(priority or "").strip()
    pl = p.lower()
    if pl == "supone un impedimento":
        return (-1, pl)
    return (priority_rank(p), pl)


def _add_bar_totals(
    fig: Any, *, x_values: list[str], y_totals: list[float], font_size: int = 12
) -> None:
    """Add a total label above each bar column (stack/group safe)."""
    if not x_values or not y_totals:
        return
    ymax = max(float(v) for v in y_totals) if y_totals else 0.0
    offset = max(1.0, ymax * 0.035)
    dark_mode = bool(st.session_state.get("workspace_dark_mode", False))
    text_color = (BBVA_DARK if dark_mode else BBVA_LIGHT).ink
    fig.add_scatter(
        x=x_values,
        y=[float(v) + offset for v in y_totals],
        mode="text",
        text=[f"{int(v)}" for v in y_totals],
        textposition="top center",
        textfont=dict(size=font_size, color=text_color),
        hoverinfo="skip",
        showlegend=False,
        cliponaxis=False,
    )
    fig.update_yaxes(range=[0, ymax + (offset * 2.4)])


def _timeseries_daily_from_filtered(dff: pd.DataFrame) -> pd.DataFrame:
    """Build canonical daily aggregates for timeseries chart from the filtered dataframe."""
    return build_timeseries_daily(
        dff,
        lookback_days=90,
        include_deployed=True,
    )


def _resolution_payload(dff: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build grouped open-age distribution plus export-ready open subset."""
    return build_open_age_priority_payload(dff)


def _open_status_payload(status_df: pd.DataFrame) -> dict[str, Any]:
    """Build grouped issues-by-status data and canonical ordered categories."""
    if status_df.empty or "status" not in status_df.columns:
        return {"grouped": pd.DataFrame(), "status_order": []}

    dff = status_df.copy(deep=False)
    dff["status"] = normalize_text_col(dff["status"], "(sin estado)")
    if "priority" in dff.columns:
        dff["priority"] = normalize_text_col(dff["priority"], "(sin priority)")
    else:
        dff["priority"] = "(sin priority)"

    stc_total = dff["status"].astype(str).value_counts().reset_index()
    stc_total.columns = ["status", "count"]
    canon_status_order = canonical_status_order()
    stc_total["__rank"] = _rank_by_canon(stc_total["status"], canon_status_order)
    stc_total = stc_total.sort_values(["__rank", "count"], ascending=[True, False]).drop(
        columns="__rank"
    )
    status_order = stc_total["status"].astype(str).tolist()

    grouped = (
        dff.groupby(["status", "priority"], dropna=False, observed=False)
        .size()
        .reset_index(name="count")
        .sort_values(["status", "count"], ascending=[True, False])
    )
    return {"grouped": grouped, "status_order": status_order}


def available_trend_charts() -> List[Tuple[str, str]]:
    """Return all available chart ids and visible labels for trends tab."""
    return [
        ("timeseries", "Evolución del backlog (últimos 90 días)"),
        ("age_buckets", "Antigüedad por estado (distribución)"),
        ("resolution_hist", "Días abiertas por prioridad"),
        ("open_priority_pie", "Issues abiertos por prioridad"),
        ("open_status_bar", "Issues por Estado"),
    ]


def render_trends_tab(
    *, settings: Settings, dff: pd.DataFrame, open_df: pd.DataFrame, kpis: dict
) -> None:
    """Render trends tab with one selected chart and contextual insights."""
    section_start_ts = perf_counter()
    perf_ms: dict[str, float] = {}
    dff = _safe_df(dff)
    open_df = _safe_df(open_df)
    kpis = kpis if isinstance(kpis, dict) else {}
    ensure_learning_session_loaded(settings=settings)

    selector_start_ts = perf_counter()
    chart_options = available_trend_charts()
    id_to_label: Dict[str, str] = {cid: label for cid, label in chart_options}
    all_ids = [cid for cid, _ in chart_options]

    if not all_ids:
        st.info("No hay gráficos configurados.")
        return

    fallback_chart = "open_status_bar" if "open_status_bar" in all_ids else all_ids[0]
    current_chart = str(st.session_state.get("trend_chart_single") or "").strip()
    if current_chart not in all_ids:
        st.session_state["trend_chart_single"] = fallback_chart

    selected_chart = st.selectbox(
        "Gráfico",
        options=all_ids,
        format_func=lambda x: id_to_label.get(x, x),
        key="trend_chart_single",
        label_visibility="collapsed",
    )
    active_status_filters = list(st.session_state.get(FILTER_STATUS_KEY) or [])
    trends_open_df, adapted_for_terminal = _effective_trends_open_scope(
        dff=dff,
        open_df=open_df,
        active_status_filters=active_status_filters,
    )
    perf_ms["selector_scope"] = elapsed_ms(selector_start_ts)

    st.markdown(
        """
        <style>
          .st-key-trend_chart_shell [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--bbva-border-strong) !important;
            background: var(--bbva-surface-elevated) !important;
            box-shadow: 0 10px 24px color-mix(in srgb, var(--bbva-text) 10%, transparent) !important;
          }
          [class*="st-key-trins_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--bbva-border-strong) !important;
            background: var(--bbva-surface) !important;
            background: color-mix(in srgb, var(--bbva-surface) 92%, var(--bbva-surface-2)) !important;
          }
          [class*="st-key-trins_card_"] [data-testid="stMarkdownContainer"] p {
            color: var(--bbva-text) !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 2) Contenedor del gráfico seleccionado
    with st.container(border=True, key="trend_chart_shell"):
        if adapted_for_terminal and selected_chart not in {
            "open_priority_pie",
            "open_status_bar",
            "resolution_hist",
        }:
            st.caption(
                "Vista adaptada al estado finalista seleccionado (incluye incidencias finalizadas)."
            )
        chart_perf = _render_trend_chart(
            chart_id=selected_chart,
            kpis=kpis,
            dff=dff,
            open_df=trends_open_df,
        )
        perf_ms["chart"] = float(chart_perf.get("chart", 0.0) or 0.0)
        perf_ms["exports"] = float(chart_perf.get("exports", 0.0) or 0.0)
        if selected_chart == "open_priority_pie":
            insights_scope_df = _exclude_terminal_status_rows(trends_open_df)
        elif selected_chart == "open_status_bar":
            insights_scope_df = dff
        else:
            insights_scope_df = trends_open_df
        insights_start_ts = perf_counter()
        _render_trend_insights(chart_id=selected_chart, dff=dff, open_df=insights_scope_df)
        perf_ms["insights"] = elapsed_ms(insights_start_ts)
    perf_ms["total"] = elapsed_ms(section_start_ts)
    render_perf_footer(
        snapshot_key="trends::perf_snapshot",
        view=selected_chart,
        ordered_blocks=_TRENDS_PERF_ORDER,
        metrics_ms=perf_ms,
        budgets_ms=_trends_perf_budget(selected_chart),
    )


# -------------------------
# Chart renderers
# -------------------------
def _render_trend_chart(
    *, chart_id: str, kpis: dict, dff: pd.DataFrame, open_df: pd.DataFrame
) -> dict[str, float]:
    chart_start_ts = perf_counter()
    export_ms = 0.0

    def _measure_export(**kwargs: Any) -> None:
        nonlocal export_ms
        export_start_ts = perf_counter()
        render_minimal_export_actions(**kwargs)
        export_ms += elapsed_ms(export_start_ts)

    def _chart_perf_result() -> dict[str, float]:
        chart_total_ms = elapsed_ms(chart_start_ts)
        return {
            "chart": max(0.0, chart_total_ms - export_ms),
            "exports": float(export_ms),
        }

    dff = _safe_df(dff)
    open_df = _safe_df(open_df)

    if chart_id == "timeseries":
        ts_sig = dataframe_signature(
            dff,
            columns=("created", "resolved", "status", "updated"),
            salt="trends.timeseries.v2",
        )
        daily, _ = cached_by_signature(
            "trends.timeseries.daily",
            ts_sig,
            lambda: _timeseries_daily_from_filtered(dff),
            max_entries=10,
        )
        if not isinstance(daily, pd.DataFrame) or daily.empty:
            st.info("No hay datos suficientes para la serie temporal con los filtros actuales.")
            return _chart_perf_result()
        fig = px.line(daily, x="date", y=["created", "closed", "deployed", "open_backlog_proxy"])
        fig.update_layout(title_text="", xaxis_title="Fecha", yaxis_title=Y_AXIS_LABEL_OPEN_ISSUES)
        fig = apply_plotly_bbva(fig, showlegend=True)
        export_cols = ["key", "summary", "status", "priority", "assignee", "created", "resolved"]
        export_df = dff[[c for c in export_cols if c in dff.columns]].copy(deep=False)
        _measure_export(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=export_df,
            figure=fig,
        )
        st.plotly_chart(fig, width="stretch")
        return _chart_perf_result()

    if chart_id == "age_buckets":
        # Issue-level distribution by age bucket (one point per issue).
        if dff.empty or "created" not in dff.columns:
            st.info("No hay datos suficientes (created) para antigüedad con los filtros actuales.")
            return _chart_perf_result()

        age_sig = dataframe_signature(
            dff,
            columns=("created", "status", "key", "summary", "priority"),
            salt="trends.age_buckets.issues.v2",
        )
        points, _ = cached_by_signature(
            "trends.age_buckets.points",
            age_sig,
            lambda: build_age_bucket_points(dff),
            max_entries=10,
        )
        if not isinstance(points, pd.DataFrame) or points.empty:
            st.info("No hay datos suficientes para este gráfico con los filtros actuales.")
            return _chart_perf_result()

        # Orden canónico de status (y los desconocidos al final)
        statuses = points["status"].astype(str).unique().tolist()
        canon_status_order = canonical_status_order()
        # canon primero (si están), luego resto en orden estable
        canon_present = [s for s in canon_status_order if s in statuses]
        rest = [s for s in statuses if s not in set(canon_present)]
        status_order = canon_present + rest

        fig = build_age_buckets_issue_distribution(
            issues=points,
            status_order=status_order,
            bucket_order=AGE_BUCKET_ORDER,
        )
        _measure_export(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=points.copy(deep=False),
            figure=fig,
        )
        st.plotly_chart(fig, width="stretch")

        # Additional stacked view for open incidents by age bucket + priority.
        open_scope = _exclude_terminal_status_rows(open_df)
        if not open_scope.empty and "created" in open_scope.columns:
            open_age_sig = dataframe_signature(
                open_scope,
                columns=("created", "priority", "status", "key", "summary"),
                salt="trends.age_buckets.open_priority_stack.v1",
            )
            open_points, _ = cached_by_signature(
                "trends.age_buckets.open_points",
                open_age_sig,
                lambda: build_age_bucket_points(open_scope),
                max_entries=10,
            )
            grouped_open, _ = cached_by_signature(
                "trends.age_buckets.open_priority.grouped",
                open_age_sig,
                lambda: build_age_bucket_priority_distribution(
                    issues=open_points,
                    bucket_order=AGE_BUCKET_ORDER,
                ),
                max_entries=10,
            )
            if isinstance(grouped_open, pd.DataFrame) and not grouped_open.empty:
                stacked_fig = build_age_buckets_open_priority_stacked(
                    grouped=grouped_open,
                    bucket_order=AGE_BUCKET_ORDER,
                )
                _measure_export(
                    key_prefix=f"trends::{chart_id}::open_priority_stack",
                    filename_prefix="tendencias",
                    suffix=f"{chart_id}_open_priority_stack",
                    csv_df=grouped_open.copy(deep=False),
                    figure=stacked_fig,
                )
                st.plotly_chart(stacked_fig, width="stretch")
        return _chart_perf_result()

    if chart_id == "resolution_hist":
        if "created" not in dff.columns:
            st.info("No hay fechas suficientes (created) para calcular antigüedad de abiertas.")
            return _chart_perf_result()

        res_sig = dataframe_signature(
            dff,
            columns=("key", "summary", "status", "priority", "created", "updated", "resolved"),
            salt="trends.open_age_priority.v1",
        )
        res_payload, _ = cached_by_signature(
            "trends.open_age_priority.payload",
            res_sig,
            lambda: _resolution_payload(dff),
            max_entries=10,
        )
        grouped_res = res_payload.get("grouped") if isinstance(res_payload, dict) else None
        opened = res_payload.get("open") if isinstance(res_payload, dict) else None

        if not isinstance(grouped_res, pd.DataFrame) or grouped_res.empty:
            st.info("No hay incidencias abiertas con fechas suficientes para este filtro.")
            return _chart_perf_result()
        if not isinstance(opened, pd.DataFrame):
            opened = pd.DataFrame()

        priority_order = sorted(
            grouped_res["priority"].astype(str).unique().tolist(),
            key=_priority_sort_key,
        )
        fig = px.bar(
            grouped_res,
            x="age_bucket",
            y="count",
            text="count",
            color="priority",
            barmode="stack",
            category_orders={
                "age_bucket": [
                    *list(OPEN_AGE_BUCKET_LABELS),
                ],
                "priority": priority_order,
            },
            color_discrete_map=priority_color_map(),
        )
        fig.update_layout(
            title_text="",
            xaxis_title="Rango en días",
            yaxis_title=Y_AXIS_LABEL_OPEN_ISSUES,
            bargap=0.10,
        )
        fig.update_traces(textposition="inside", textfont=dict(size=10))
        res_order = list(OPEN_AGE_BUCKET_LABELS)
        res_totals = grouped_res.groupby("age_bucket", dropna=False, observed=False)["count"].sum()
        _add_bar_totals(
            fig,
            x_values=res_order,
            y_totals=[float(res_totals.get(b, 0)) for b in res_order],
            font_size=12,
        )
        fig = apply_plotly_bbva(fig, showlegend=True)
        export_df = opened.copy(deep=False)
        _measure_export(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=export_df,
            figure=fig,
        )
        st.plotly_chart(fig, width="stretch")
        return _chart_perf_result()

    if chart_id == "open_priority_pie":
        open_scope = _exclude_terminal_status_rows(open_df)
        if open_scope.empty or "priority" not in open_scope.columns:
            st.info(
                "No hay datos suficientes para el gráfico de Priority con los filtros actuales."
            )
            return _chart_perf_result()

        dff = open_scope.copy()
        dff["priority"] = normalize_text_col(dff["priority"], "(sin priority)")

        fig = px.pie(
            dff,
            names="priority",
            hole=0.55,
            color="priority",
            color_discrete_map=priority_color_map(),
        )
        fig.update_layout(title_text="")
        fig.update_traces(sort=False)
        fig = apply_plotly_bbva(fig, showlegend=True)
        pie_export = (
            dff.groupby("priority", dropna=False, observed=False).size().reset_index(name="count")
        )
        _measure_export(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=pie_export,
            figure=fig,
        )
        st.plotly_chart(fig, width="stretch")
        return _chart_perf_result()

    if chart_id == "open_status_bar":
        if dff.empty or "status" not in dff.columns:
            st.info("No hay datos suficientes para el gráfico de Estado con los filtros actuales.")
            return _chart_perf_result()

        status_sig = dataframe_signature(
            dff,
            columns=("status", "priority"),
            salt="trends.open_status_bar.v2",
        )
        status_payload, _ = cached_by_signature(
            "trends.open_status_bar.payload",
            status_sig,
            lambda: _open_status_payload(dff),
            max_entries=10,
        )
        grouped = status_payload.get("grouped") if isinstance(status_payload, dict) else None
        status_order_raw = (
            status_payload.get("status_order") if isinstance(status_payload, dict) else []
        )
        if not isinstance(grouped, pd.DataFrame) or grouped.empty:
            st.info("No hay datos suficientes para el gráfico de Estado con los filtros actuales.")
            return _chart_perf_result()
        status_order = status_order_raw if isinstance(status_order_raw, list) else []

        priority_order = sorted(
            grouped["priority"].astype(str).unique().tolist(),
            key=_priority_sort_key,
        )

        fig = px.bar(
            grouped,
            x="status",
            y="count",
            text="count",
            color="priority",
            category_orders={"status": status_order, "priority": priority_order},
            color_discrete_map=priority_color_map(),
        )
        fig.update_layout(title_text="", xaxis_title="Estado", yaxis_title="Incidencias")
        fig.update_traces(textposition="inside", textfont=dict(size=10))
        st_totals = grouped.groupby("status", dropna=False, observed=False)["count"].sum()
        _add_bar_totals(
            fig,
            x_values=status_order,
            y_totals=[float(st_totals.get(s, 0)) for s in status_order],
            font_size=12,
        )
        fig = apply_plotly_bbva(fig, showlegend=True)
        _measure_export(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=grouped.copy(deep=False),
            figure=fig,
        )
        st.plotly_chart(fig, width="stretch")
        return _chart_perf_result()

    st.info("Gráfico no reconocido.")
    return _chart_perf_result()


def _render_trend_insights(*, chart_id: str, dff: pd.DataFrame, open_df: pd.DataFrame) -> None:
    """Render management-oriented insights for the selected trend chart."""
    dff = _safe_df(dff)
    open_df = _safe_df(open_df)
    snapshot = build_operational_snapshot(dff=dff, open_df=open_df)
    set_learning_snapshot(snapshot, persist=True)
    baseline_snapshot = st.session_state.get(LEARNING_BASELINE_SNAPSHOT_KEY)
    if not isinstance(baseline_snapshot, dict):
        baseline_snapshot = {}

    with st.container(border=True, key=f"trend_delta_shell_{chart_id}"):
        st.markdown("#### Que cambio desde tu ultima sesion")
        for line in build_session_delta_lines(snapshot, baseline_snapshot):
            st.markdown(f"- {line}")

    pack = build_trend_insight_pack(chart_id, dff=dff, open_df=open_df)
    if not pack.metrics and not pack.cards:
        st.caption("Sin insights para este grafico con los filtros actuales.")
        return

    st.markdown("#### Insights accionables")
    if pack.metrics:
        cols = st.columns(len(pack.metrics))
        for col, metric in zip(cols, pack.metrics):
            with col:
                st.metric(metric.label, metric.value)

    active_filters = _active_filter_snapshot()
    _track_context_interaction(chart_id=str(chart_id), active_filters=active_filters)
    personalized_cards = _personalize_insights(
        pack.cards, chart_id=str(chart_id), active_filters=active_filters
    )
    key_prefix = str(chart_id or "chart").strip().replace("-", "_")

    _render_insight_cards(personalized_cards, key_prefix=key_prefix, chart_id=str(chart_id))
    _register_shown_insights(
        personalized_cards,
        chart_id=str(chart_id),
        render_token=_render_token(
            chart_id=str(chart_id), dff=dff, open_df=open_df, active_filters=active_filters
        ),
    )

    interactions = int(st.session_state.get(LEARNING_INTERACTIONS_KEY, 0) or 0)
    if interactions > 0:
        st.caption(
            f"Priorizacion adaptativa activa: {interactions} interacciones consideradas en esta sesion."
        )
    if pack.executive_tip:
        st.caption(pack.executive_tip)


def _jump_to_issues(
    *,
    status_filters: List[str] | None = None,
    priority_filters: List[str] | None = None,
    assignee_filters: List[str] | None = None,
    insight_id: str | None = None,
) -> None:
    """Open Issues tab and sync filters derived from an actionable insight."""
    st.session_state["__jump_to_tab"] = "issues"
    st.session_state[FILTER_STATUS_KEY] = list(status_filters or [])
    st.session_state[FILTER_PRIORITY_KEY] = list(priority_filters or [])
    st.session_state[FILTER_ASSIGNEE_KEY] = list(assignee_filters or [])
    if insight_id:
        state = _ensure_learning_state()
        clicked_counts = _dict_any(state.get("clicked_counts"))
        clicked_counts[insight_id] = int(clicked_counts.get(insight_id, 0) or 0) + 1
        state["clicked_counts"] = clicked_counts
        state["last_click_filters"] = {
            "status": list(status_filters or []),
            "priority": list(priority_filters or []),
            "assignee": list(assignee_filters or []),
        }
        st.session_state[LEARNING_STATE_KEY] = state
        increment_learning_interactions(step=1, persist=True)


def _render_insight_cards(cards: List[ActionInsight], *, key_prefix: str, chart_id: str) -> None:
    """Render insight cards; only cards with filters are shown as actionable links."""
    items = [c for c in cards if str(c.title or "").strip() and str(c.body or "").strip()]
    items = sorted(items, key=lambda c: float(c.score), reverse=True)
    if not items:
        return

    st.markdown(
        """
        <style>
          [class*="st-key-trins_"] div[data-testid="stButton"] > button {
            justify-content: flex-start !important;
            width: 100% !important;
            min-height: 1.65rem !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            color: var(--bbva-action-link) !important;
            font-family: var(--bbva-font-sans) !important;
            font-size: 0.98rem !important;
            font-weight: 760 !important;
            border-radius: 8px !important;
            text-align: left !important;
            box-shadow: none !important;
          }
          [class*="st-key-trins_"] div[data-testid="stButton"] > button *,
          [class*="st-key-trins_"] div[data-testid="stButton"] > button svg {
            color: inherit !important;
            fill: currentColor !important;
          }
          [class*="st-key-trins_"] div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] p,
          [class*="st-key-trins_"] div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] strong {
            color: var(--bbva-action-link) !important;
          }
          [class*="st-key-trins_"] div[data-testid="stButton"] > button:hover {
            color: var(--bbva-action-link-hover) !important;
            transform: translateX(1px);
          }
          [class*="st-key-trins_"] div[data-testid="stButton"] > button:hover div[data-testid="stMarkdownContainer"] p,
          [class*="st-key-trins_"] div[data-testid="stButton"] > button:hover div[data-testid="stMarkdownContainer"] strong {
            color: var(--bbva-action-link-hover) !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(2, gap="small")
    for i, item in enumerate(items[:6]):
        has_action = bool(item.status_filters or item.priority_filters or item.assignee_filters)
        insight_id = _insight_identity(chart_id, item)
        with cols[i % 2]:
            with st.container(border=True, key=f"trins_card_{key_prefix}_{i}"):
                if has_action:
                    with st.container(key=f"trins_{key_prefix}_{i}"):
                        st.button(
                            f"{item.title} ↗",
                            key=f"trins_btn_{key_prefix}_{i}",
                            width="stretch",
                            on_click=_jump_to_issues,
                            kwargs={
                                "status_filters": item.status_filters,
                                "priority_filters": item.priority_filters,
                                "assignee_filters": item.assignee_filters,
                                "insight_id": insight_id,
                            },
                        )
                else:
                    st.markdown(f"**{item.title}**")
                st.markdown(item.body)
