"""Trend charts and adaptive management insights for the dashboard."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.cache import cached_by_signature, dataframe_signature
from bug_resolution_radar.ui.common import (
    normalize_text_col,
    priority_color_map,
    priority_rank,
    status_color_map,
)
from bug_resolution_radar.ui.dashboard.constants import canonical_status_order
from bug_resolution_radar.ui.dashboard.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
)
from bug_resolution_radar.ui.insights.engine import ActionInsight, build_trend_insight_pack
from bug_resolution_radar.ui.insights.copilot import (
    CopilotAnswer,
    NextBestAction,
    answer_copilot_question,
    build_operational_snapshot,
    build_session_delta_lines,
    choose_next_best_action,
    simulate_backlog_what_if,
)
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


def _to_dt_naive(s: pd.Series) -> pd.Series:
    """Convert to naive datetime64 for safe arithmetic/comparisons."""
    if s is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(s, errors="coerce")
    try:
        if hasattr(out.dt, "tz") and out.dt.tz is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        try:
            out = out.dt.tz_localize(None)
        except Exception:
            pass
    return out


def _safe_df(df: pd.DataFrame) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


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
    status = ",".join(sorted([str(x).strip().lower() for x in list(insight.status_filters or []) if str(x).strip()]))
    priority = ",".join(
        sorted([str(x).strip().lower() for x in list(insight.priority_filters or []) if str(x).strip()])
    )
    assignee = ",".join(
        sorted([str(x).strip().lower() for x in list(insight.assignee_filters or []) if str(x).strip()])
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
            score=float(card.score) + novelty_bonus + affinity_bonus + active_alignment + last_alignment,
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


def _register_shown_insights(cards: List[ActionInsight], *, chart_id: str, render_token: str) -> None:
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


def _age_bucket_from_days(age_days: pd.Series) -> pd.Categorical:
    """Build canonical age buckets: 0-2, 3-7, 8-14, 15-30, >30 days."""
    bins = [-np.inf, 2, 7, 14, 30, np.inf]
    labels = ["0-2", "3-7", "8-14", "15-30", ">30"]
    cat = pd.cut(age_days, bins=bins, labels=labels, right=True, include_lowest=True, ordered=True)
    return cat


def _resolution_band(days: pd.Series) -> pd.Categorical:
    """Build resolution speed bands for semantic coloring."""
    bins = [-np.inf, 7, 30, np.inf]
    labels = ["Rapida (0-7d)", "Media (8-30d)", "Lenta (>30d)"]
    return pd.cut(days, bins=bins, labels=labels, right=True, include_lowest=True, ordered=True)


def _resolution_bucket(days: pd.Series) -> pd.Categorical:
    """Build categorical buckets to avoid confusion in continuous histograms."""
    bins = [-0.1, 0.0, 2.0, 7.0, 14.0, 30.0, 60.0, 90.0, np.inf]
    labels = [
        "Mismo dia (0d)",
        "1-2d",
        "3-7d",
        "8-14d",
        "15-30d",
        "31-60d",
        "61-90d",
        ">90d",
    ]
    return pd.cut(days, bins=bins, labels=labels, right=True, include_lowest=True, ordered=True)


def _add_bar_totals(
    fig: Any, *, x_values: list[str], y_totals: list[float], font_size: int = 12
) -> None:
    """Add a total label above each bar column (stack/group safe)."""
    if not x_values or not y_totals:
        return
    ymax = max(float(v) for v in y_totals) if y_totals else 0.0
    offset = max(1.0, ymax * 0.035)
    text_color = (
        "#EAF0FF" if bool(st.session_state.get("workspace_dark_mode", False)) else "#11192D"
    )
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
    """Build daily aggregates for timeseries chart from the filtered dataframe."""
    if dff.empty:
        return pd.DataFrame()

    created = (
        _to_dt_naive(dff["created"])
        if "created" in dff.columns
        else pd.Series(pd.NaT, index=dff.index)
    )
    resolved = (
        _to_dt_naive(dff["resolved"])
        if "resolved" in dff.columns
        else pd.Series(pd.NaT, index=dff.index)
    )

    created_notna = created.notna()
    resolved_notna = resolved.notna()
    if not created_notna.any() and not resolved_notna.any():
        return pd.DataFrame()

    end_candidates = []
    if created_notna.any():
        end_candidates.append(created.loc[created_notna].max())
    if resolved_notna.any():
        end_candidates.append(resolved.loc[resolved_notna].max())
    end_ts = (
        pd.Timestamp(max(end_candidates)).normalize()
        if end_candidates
        else pd.Timestamp.utcnow().normalize()
    )
    start_ts = end_ts - pd.Timedelta(days=90)

    created_daily = (
        created.loc[created_notna & (created >= start_ts)].dt.floor("D").value_counts(sort=False)
    )
    closed_daily = (
        resolved.loc[resolved_notna & (resolved >= start_ts)].dt.floor("D").value_counts(sort=False)
    )

    all_dates = created_daily.index.union(closed_daily.index).sort_values()
    if all_dates.empty:
        return pd.DataFrame()

    daily = pd.DataFrame({"date": all_dates})
    daily["created"] = created_daily.reindex(all_dates, fill_value=0).to_numpy()
    daily["closed"] = closed_daily.reindex(all_dates, fill_value=0).to_numpy()
    # Avoid negative baseline in windowed view; keeps interpretation stable under filters.
    daily["open_backlog_proxy"] = (daily["created"] - daily["closed"]).cumsum().clip(lower=0)
    return daily


def _age_bucket_grouped(open_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate open issues by age bucket and status."""
    if open_df.empty or "created" not in open_df.columns:
        return pd.DataFrame()

    df = open_df.copy(deep=False)
    df["__created_dt"] = _to_dt_naive(df["created"])
    df = df[df["__created_dt"].notna()].copy(deep=False)
    if df.empty:
        return pd.DataFrame()

    now = pd.Timestamp.utcnow().tz_localize(None)
    df["__age_days"] = (now - df["__created_dt"]).dt.total_seconds() / 86400.0
    df["__age_days"] = df["__age_days"].clip(lower=0.0)

    if "status" not in df.columns:
        df["status"] = "(sin estado)"
    else:
        df["status"] = df["status"].astype(str)

    df["bucket"] = _age_bucket_from_days(df["__age_days"])
    return (
        df.groupby(["bucket", "status"], dropna=False, observed=False)
        .size()
        .reset_index(name="count")
        .sort_values(["bucket", "count"], ascending=[True, False])
    )


def _resolution_payload(dff: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build grouped resolution distribution plus export-ready closed subset."""
    empty_grouped = pd.DataFrame(columns=["resolution_bucket", "priority", "count"])
    empty_closed = pd.DataFrame(
        columns=[
            "key",
            "summary",
            "status",
            "priority",
            "created",
            "resolved",
            "resolution_days",
            "resolution_bucket",
        ]
    )
    if "resolved" not in dff.columns or "created" not in dff.columns:
        return {"grouped": empty_grouped, "closed": empty_closed}

    created = _to_dt_naive(dff["created"])
    resolved = _to_dt_naive(dff["resolved"])

    closed = dff.copy(deep=False)
    closed["__created"] = created
    closed["__resolved"] = resolved
    closed = closed[closed["__created"].notna() & closed["__resolved"].notna()].copy(deep=False)
    if closed.empty:
        return {"grouped": empty_grouped, "closed": empty_closed}

    closed["resolution_days"] = (
        (closed["__resolved"] - closed["__created"]).dt.total_seconds() / 86400.0
    ).clip(lower=0.0)
    if "priority" in closed.columns:
        closed["priority"] = normalize_text_col(closed["priority"], "(sin priority)")
    else:
        closed["priority"] = "(sin priority)"

    closed["resolution_bucket"] = _resolution_bucket(closed["resolution_days"])
    grouped_res = (
        closed.groupby(["resolution_bucket", "priority"], dropna=False, observed=False)
        .size()
        .reset_index(name="count")
    )
    export_cols = [
        "key",
        "summary",
        "status",
        "priority",
        "created",
        "resolved",
        "resolution_days",
        "resolution_bucket",
    ]
    export_df = closed[[c for c in export_cols if c in closed.columns]].copy(deep=False)
    return {"grouped": grouped_res, "closed": export_df}


def _open_status_payload(open_df: pd.DataFrame) -> dict[str, Any]:
    """Build grouped open-by-status data and canonical ordered categories."""
    if open_df.empty or "status" not in open_df.columns:
        return {"grouped": pd.DataFrame(), "status_order": []}

    dff = open_df.copy(deep=False)
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
        dff.groupby(["status", "priority"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["status", "count"], ascending=[True, False])
    )
    return {"grouped": grouped, "status_order": status_order}


def available_trend_charts() -> List[Tuple[str, str]]:
    """Return all available chart ids and visible labels for trends tab."""
    return [
        ("timeseries", "Evolución del backlog (últimos 90 días)"),
        ("age_buckets", "Antigüedad de abiertas (distribución)"),
        ("resolution_hist", "Tiempos de resolución (cerradas)"),
        ("open_priority_pie", "Abiertas por Priority"),
        ("open_status_bar", "Abiertas por Estado"),
    ]


def render_trends_tab(
    *, settings: Settings, dff: pd.DataFrame, open_df: pd.DataFrame, kpis: dict
) -> None:
    """Render trends tab with one selected chart and contextual insights."""
    dff = _safe_df(dff)
    open_df = _safe_df(open_df)
    kpis = kpis if isinstance(kpis, dict) else {}
    ensure_learning_session_loaded(settings=settings)

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
        _render_trend_chart(chart_id=selected_chart, kpis=kpis, dff=dff, open_df=open_df)
        _render_trend_insights(chart_id=selected_chart, dff=dff, open_df=open_df)


# -------------------------
# Chart renderers
# -------------------------
def _render_trend_chart(
    *, chart_id: str, kpis: dict, dff: pd.DataFrame, open_df: pd.DataFrame
) -> None:
    dff = _safe_df(dff)
    open_df = _safe_df(open_df)

    if chart_id == "timeseries":
        ts_sig = dataframe_signature(
            dff,
            columns=("created", "resolved"),
            salt="trends.timeseries.v1",
        )
        daily, _ = cached_by_signature(
            "trends.timeseries.daily",
            ts_sig,
            lambda: _timeseries_daily_from_filtered(dff),
            max_entries=10,
        )
        if not isinstance(daily, pd.DataFrame) or daily.empty:
            st.info("No hay datos suficientes para la serie temporal con los filtros actuales.")
            return
        fig = px.line(daily, x="date", y=["created", "closed", "open_backlog_proxy"])
        fig.update_layout(title_text="", xaxis_title="Fecha", yaxis_title="Incidencias")
        fig = apply_plotly_bbva(fig, showlegend=True)
        export_cols = ["key", "summary", "status", "priority", "assignee", "created", "resolved"]
        export_df = dff[[c for c in export_cols if c in dff.columns]].copy(deep=False)
        render_minimal_export_actions(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=export_df,
            figure=fig,
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    if chart_id == "age_buckets":
        # ✅ NUEVO: barras apiladas por Status dentro de cada bucket de antigüedad
        if open_df.empty or "created" not in open_df.columns:
            st.info("No hay datos suficientes (created) para antigüedad con los filtros actuales.")
            return

        age_sig = dataframe_signature(
            open_df,
            columns=("created", "status"),
            salt="trends.age_buckets.v1",
        )
        grp, _ = cached_by_signature(
            "trends.age_buckets.grouped",
            age_sig,
            lambda: _age_bucket_grouped(open_df),
            max_entries=10,
        )
        if not isinstance(grp, pd.DataFrame) or grp.empty:
            st.info("No hay datos suficientes para este gráfico con los filtros actuales.")
            return

        # Orden canónico de status (y los desconocidos al final)
        statuses = grp["status"].astype(str).unique().tolist()
        canon_status_order = canonical_status_order()
        # canon primero (si están), luego resto en orden estable
        canon_present = [s for s in canon_status_order if s in statuses]
        rest = [s for s in statuses if s not in set(canon_present)]
        status_order = canon_present + rest

        bucket_order = ["0-2", "3-7", "8-14", "15-30", ">30"]

        fig = px.bar(
            grp,
            x="bucket",
            y="count",
            text="count",
            color="status",
            barmode="stack",
            category_orders={"bucket": bucket_order, "status": status_order},
            color_discrete_map=status_color_map(status_order),
        )
        fig.update_layout(
            title_text="", xaxis_title="Rango de antiguedad", yaxis_title="Incidencias"
        )
        text_color = (
            "#EAF0FF" if bool(st.session_state.get("workspace_dark_mode", False)) else "#11192D"
        )
        fig.update_traces(textposition="inside", textfont=dict(size=10, color=text_color))
        age_totals = grp.groupby("bucket", dropna=False)["count"].sum()
        _add_bar_totals(
            fig,
            x_values=bucket_order,
            y_totals=[float(age_totals.get(b, 0)) for b in bucket_order],
            font_size=12,
        )
        fig = apply_plotly_bbva(fig, showlegend=True)
        render_minimal_export_actions(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=grp.copy(deep=False),
            figure=fig,
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    if chart_id == "resolution_hist":
        if "resolved" not in dff.columns or "created" not in dff.columns:
            st.info("No hay fechas suficientes (created/resolved) para calcular resolución.")
            return

        res_sig = dataframe_signature(
            dff,
            columns=("key", "summary", "status", "priority", "created", "resolved"),
            salt="trends.resolution_hist.v1",
        )
        res_payload, _ = cached_by_signature(
            "trends.resolution_hist.payload",
            res_sig,
            lambda: _resolution_payload(dff),
            max_entries=10,
        )
        grouped_res = res_payload.get("grouped") if isinstance(res_payload, dict) else None
        closed = res_payload.get("closed") if isinstance(res_payload, dict) else None

        if not isinstance(grouped_res, pd.DataFrame) or grouped_res.empty:
            st.info("No hay incidencias cerradas con fechas suficientes para este filtro.")
            return
        if not isinstance(closed, pd.DataFrame):
            closed = pd.DataFrame()

        priority_order = sorted(
            grouped_res["priority"].astype(str).unique().tolist(),
            key=_priority_sort_key,
        )
        fig = px.bar(
            grouped_res,
            x="resolution_bucket",
            y="count",
            text="count",
            color="priority",
            barmode="stack",
            category_orders={
                "resolution_bucket": [
                    "Mismo dia (0d)",
                    "1-2d",
                    "3-7d",
                    "8-14d",
                    "15-30d",
                    "31-60d",
                    "61-90d",
                    ">90d",
                ],
                "priority": priority_order,
            },
            color_discrete_map=priority_color_map(),
        )
        fig.update_layout(
            title_text="",
            xaxis_title="Tiempo de resolucion",
            yaxis_title="Incidencias",
            bargap=0.10,
        )
        fig.update_traces(textposition="inside", textfont=dict(size=10))
        res_order = [
            "Mismo dia (0d)",
            "1-2d",
            "3-7d",
            "8-14d",
            "15-30d",
            "31-60d",
            "61-90d",
            ">90d",
        ]
        res_totals = grouped_res.groupby("resolution_bucket", dropna=False)["count"].sum()
        _add_bar_totals(
            fig,
            x_values=res_order,
            y_totals=[float(res_totals.get(b, 0)) for b in res_order],
            font_size=12,
        )
        fig = apply_plotly_bbva(fig, showlegend=True)
        export_df = closed.copy(deep=False)
        render_minimal_export_actions(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=export_df,
            figure=fig,
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    if chart_id == "open_priority_pie":
        if open_df.empty or "priority" not in open_df.columns:
            st.info(
                "No hay datos suficientes para el gráfico de Priority con los filtros actuales."
            )
            return

        dff = open_df.copy()
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
        pie_export = dff.groupby("priority", dropna=False).size().reset_index(name="count")
        render_minimal_export_actions(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=pie_export,
            figure=fig,
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    if chart_id == "open_status_bar":
        if open_df.empty or "status" not in open_df.columns:
            st.info("No hay datos suficientes para el gráfico de Estado con los filtros actuales.")
            return

        status_sig = dataframe_signature(
            open_df,
            columns=("status", "priority"),
            salt="trends.open_status_bar.v1",
        )
        status_payload, _ = cached_by_signature(
            "trends.open_status_bar.payload",
            status_sig,
            lambda: _open_status_payload(open_df),
            max_entries=10,
        )
        grouped = status_payload.get("grouped") if isinstance(status_payload, dict) else None
        status_order_raw = (
            status_payload.get("status_order") if isinstance(status_payload, dict) else []
        )
        if not isinstance(grouped, pd.DataFrame) or grouped.empty:
            st.info("No hay datos suficientes para el gráfico de Estado con los filtros actuales.")
            return
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
            barmode="stack",
            category_orders={"status": status_order, "priority": priority_order},
            color_discrete_map=priority_color_map(),
        )
        fig.update_layout(title_text="", xaxis_title="Estado", yaxis_title="Incidencias")
        fig.update_traces(textposition="inside", textfont=dict(size=10))
        st_totals = grouped.groupby("status", dropna=False)["count"].sum()
        _add_bar_totals(
            fig,
            x_values=status_order,
            y_totals=[float(st_totals.get(s, 0)) for s in status_order],
            font_size=12,
        )
        fig = apply_plotly_bbva(fig, showlegend=True)
        render_minimal_export_actions(
            key_prefix=f"trends::{chart_id}",
            filename_prefix="tendencias",
            suffix=chart_id,
            csv_df=grouped.copy(deep=False),
            figure=fig,
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    st.info("Gráfico no reconocido.")


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
    next_action = choose_next_best_action(snapshot, cards=personalized_cards)

    with st.container(border=True, key=f"next_best_action_shell_{chart_id}"):
        st.markdown("#### Next Best Action")
        st.markdown(f"**{next_action.title}**")
        st.markdown(next_action.body)
        st.caption(next_action.expected_impact)
        has_action_filters = bool(
            next_action.status_filters or next_action.priority_filters or next_action.assignee_filters
        )
        if has_action_filters:
            st.button(
                "Aplicar accion en Issues ↗",
                key=f"nba_apply_btn_{chart_id}",
                width="stretch",
                on_click=_jump_to_issues,
                kwargs={
                    "status_filters": list(next_action.status_filters or []),
                    "priority_filters": list(next_action.priority_filters or []),
                    "assignee_filters": list(next_action.assignee_filters or []),
                    "insight_id": f"nextbest::{chart_id}",
                },
            )

    _render_insight_cards(personalized_cards, key_prefix=key_prefix, chart_id=str(chart_id))
    _register_shown_insights(
        personalized_cards,
        chart_id=str(chart_id),
        render_token=_render_token(
            chart_id=str(chart_id), dff=dff, open_df=open_df, active_filters=active_filters
        ),
    )

    with st.container(border=True, key=f"what_if_shell_{chart_id}"):
        st.markdown("#### Simulador de impacto (what-if)")
        s1, s2, s3 = st.columns(3)
        with s1:
            entry_reduction = st.slider(
                "Reducir entrada (%)",
                min_value=0,
                max_value=50,
                value=15,
                step=5,
                key=f"whatif_entry_{chart_id}",
            )
        with s2:
            closure_boost = st.slider(
                "Aumentar cierre (%)",
                min_value=0,
                max_value=60,
                value=20,
                step=5,
                key=f"whatif_close_{chart_id}",
            )
        with s3:
            unblock = st.slider(
                "Desbloquear bloqueadas (%)",
                min_value=0,
                max_value=100,
                value=30,
                step=10,
                key=f"whatif_unblock_{chart_id}",
            )
        sim = simulate_backlog_what_if(
            snapshot,
            entry_reduction_pct=float(entry_reduction),
            closure_boost_pct=float(closure_boost),
            unblock_pct=float(unblock),
        )
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Neto semanal simulado", f"{float(sim.get('weekly_net', 0.0)):+.1f}")
        with m2:
            st.metric("Backlog estimado en 8 semanas", f"{float(sim.get('backlog_8w', 0.0)):.0f}")
        with m3:
            weeks_to_zero = sim.get("weeks_to_zero")
            st.metric(
                "Semanas para vaciar",
                f"{float(weeks_to_zero):.1f}"
                if isinstance(weeks_to_zero, (int, float))
                else "No converge",
            )
        st.caption(
            "Estimacion orientativa basada en ritmo reciente y palancas de gestion sobre el filtro activo."
        )

    with st.container(border=True, key=f"copilot_shell_{chart_id}"):
        st.markdown("#### Copilot operativo")
        st.caption("Pregunta en lenguaje natural sobre lo que ves en pantalla.")
        suggestions = [
            "Cual es el mayor riesgo cliente hoy?",
            "Que accion concreta priorizo esta semana?",
            "Como ha cambiado la situacion desde mi ultima sesion?",
            "Que cuello de botella penaliza mas el flujo?",
        ]
        hist_key = f"copilot_history::{chart_id}"
        pick_col, action_col = st.columns([3, 1])
        with pick_col:
            pick = st.selectbox(
                "Preguntas sugeridas",
                options=["(elige)"] + suggestions,
                key=f"copilot_suggest_{chart_id}",
            )
        with action_col:
            if st.button("Usar sugerida", key=f"copilot_use_suggest_{chart_id}", width="stretch"):
                if pick and pick != "(elige)":
                    st.session_state[f"copilot_query_value_{chart_id}"] = pick

        with st.form(key=f"copilot_form_{chart_id}", clear_on_submit=False):
            q_default = str(st.session_state.get(f"copilot_query_value_{chart_id}") or "")
            query = st.text_input(
                "Pregunta",
                value=q_default,
                key=f"copilot_query_input_{chart_id}",
                placeholder="Ej: donde esta el mayor riesgo cliente hoy?",
            )
            asked = st.form_submit_button("Analizar")

        if asked and str(query or "").strip():
            ans: CopilotAnswer = answer_copilot_question(
                question=str(query),
                snapshot=snapshot,
                baseline_snapshot=baseline_snapshot,
                next_action=next_action,
            )
            history = st.session_state.get(hist_key)
            if not isinstance(history, list):
                history = []
            history.append(
                {
                    "q": str(query).strip(),
                    "a": ans.answer,
                    "confidence": float(ans.confidence),
                    "evidence": list(ans.evidence or []),
                    "followups": list(ans.followups or []),
                }
            )
            st.session_state[hist_key] = history[-5:]
            increment_learning_interactions(step=1, persist=True)

        history = st.session_state.get(hist_key)
        if isinstance(history, list) and history:
            latest = history[-1]
            st.markdown(f"**Respuesta** (confianza {float(latest.get('confidence', 0.0))*100.0:.0f}%)")
            st.markdown(str(latest.get("a", "")))
            ev = latest.get("evidence")
            if isinstance(ev, list) and ev:
                st.markdown("**Evidencia usada**")
                for line in ev[:4]:
                    st.markdown(f"- {line}")
            fups = latest.get("followups")
            if isinstance(fups, list) and fups:
                st.caption("Siguientes preguntas sugeridas:")
                for line in fups[:3]:
                    st.markdown(f"- {line}")

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
            color: var(--bbva-text) !important;
            font-size: 0.98rem !important;
            font-weight: 800 !important;
            border-radius: 8px !important;
            text-align: left !important;
            box-shadow: none !important;
          }
          [class*="st-key-trins_"] div[data-testid="stButton"] > button:hover {
            color: var(--bbva-primary) !important;
            transform: translateX(1px);
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
