"""Trend charts and adaptive management insights for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

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


def _build_timeseries_from_filtered(dff: pd.DataFrame) -> Any | None:
    """Build the evolution chart from the currently filtered dataframe."""
    if dff.empty:
        return None

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
        return None

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
        return None

    daily = pd.DataFrame({"date": all_dates})
    daily["created"] = created_daily.reindex(all_dates, fill_value=0).to_numpy()
    daily["closed"] = closed_daily.reindex(all_dates, fill_value=0).to_numpy()
    # Avoid negative baseline in windowed view; keeps interpretation stable under filters.
    daily["open_backlog_proxy"] = (daily["created"] - daily["closed"]).cumsum().clip(lower=0)

    return px.line(daily, x="date", y=["created", "closed", "open_backlog_proxy"])


def available_trend_charts() -> List[Tuple[str, str]]:
    """Return all available chart ids and visible labels for trends tab."""
    return [
        ("timeseries", "Evolución del backlog (últimos 90 días)"),
        ("age_buckets", "Antigüedad de abiertas (distribución)"),
        ("resolution_hist", "Tiempos de resolución (cerradas)"),
        ("open_priority_pie", "Abiertas por Priority"),
        ("open_status_bar", "Abiertas por Estado"),
    ]


def render_trends_tab(*, dff: pd.DataFrame, open_df: pd.DataFrame, kpis: dict) -> None:
    """Render trends tab with one selected chart and contextual insights."""
    dff = _safe_df(dff)
    open_df = _safe_df(open_df)
    kpis = kpis if isinstance(kpis, dict) else {}

    chart_options = available_trend_charts()
    id_to_label: Dict[str, str] = {cid: label for cid, label in chart_options}
    all_ids = [cid for cid, _ in chart_options]

    if not all_ids:
        st.info("No hay gráficos configurados.")
        return

    if "trend_chart_single" not in st.session_state:
        st.session_state["trend_chart_single"] = (
            "open_status_bar" if "open_status_bar" in all_ids else all_ids[0]
        )

    selected_chart = st.selectbox(
        "Gráfico",
        options=all_ids,
        index=(
            all_ids.index(st.session_state["trend_chart_single"])
            if st.session_state["trend_chart_single"] in all_ids
            else 0
        ),
        format_func=lambda x: id_to_label.get(x, x),
        key="trend_chart_single",
        label_visibility="collapsed",
    )

    # 2) Contenedor del gráfico seleccionado
    with st.container(border=True):
        _render_trend_chart(chart_id=selected_chart, kpis=kpis, dff=dff, open_df=open_df)

        st.markdown("---")
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
        fig = _build_timeseries_from_filtered(dff)
        if fig is None:
            st.info("No hay datos suficientes para la serie temporal con los filtros actuales.")
            return
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

        df = open_df.copy()
        df["__created_dt"] = _to_dt_naive(df["created"])
        df = df[df["__created_dt"].notna()].copy()
        if df.empty:
            st.info(
                "No hay fechas válidas (created) para calcular antigüedad con los filtros actuales."
            )
            return

        now = pd.Timestamp.utcnow().tz_localize(None)
        df["__age_days"] = (now - df["__created_dt"]).dt.total_seconds() / 86400.0
        df["__age_days"] = df["__age_days"].clip(lower=0.0)

        # status puede no existir; si no, ponemos un placeholder
        if "status" not in df.columns:
            df["status"] = "(sin estado)"
        else:
            df["status"] = df["status"].astype(str)

        df["bucket"] = _age_bucket_from_days(df["__age_days"])

        # Agregado: bucket x status
        grp = (
            df.groupby(["bucket", "status"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(["bucket", "count"], ascending=[True, False])
        )
        if grp.empty:
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

        created = _to_dt_naive(dff["created"])
        resolved = _to_dt_naive(dff["resolved"])

        closed = dff.copy()
        closed["__created"] = created
        closed["__resolved"] = resolved
        closed = closed[closed["__created"].notna() & closed["__resolved"].notna()].copy()

        if closed.empty:
            st.info("No hay incidencias cerradas con fechas suficientes para este filtro.")
            return

        closed["resolution_days"] = (
            (closed["__resolved"] - closed["__created"]).dt.total_seconds() / 86400.0
        ).clip(lower=0.0)
        if "priority" in closed.columns:
            closed["priority"] = normalize_text_col(closed["priority"], "(sin priority)")
        else:
            closed["priority"] = "(sin priority)"

        closed["resolution_bucket"] = _resolution_bucket(closed["resolution_days"])
        grouped_res = (
            closed.groupby(["resolution_bucket", "priority"], dropna=False)
            .size()
            .reset_index(name="count")
        )
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

        dff = open_df.copy()
        dff["status"] = normalize_text_col(dff["status"], "(sin estado)")
        if "priority" in dff.columns:
            dff["priority"] = normalize_text_col(dff["priority"], "(sin priority)")
        else:
            dff["priority"] = "(sin priority)"

        # Order statuses canonically by total volume.
        stc_total = dff["status"].astype(str).value_counts().reset_index()
        stc_total.columns = ["status", "count"]

        # ✅ Orden canónico (mismo que Issues/Matrix/Kanban)
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

    if chart_id == "timeseries":
        _insights_timeseries(dff)
        return
    if chart_id == "age_buckets":
        _insights_age(open_df)
        return
    if chart_id == "resolution_hist":
        _insights_resolution(dff)
        return
    if chart_id == "open_priority_pie":
        _insights_priority(open_df)
        return
    if chart_id == "open_status_bar":
        _insights_status(open_df)
        return


@dataclass(frozen=True)
class _TrendActionInsight:
    """Insight card model with optional filter actions and relevance score."""

    title: str
    body: str
    status_filters: List[str] | None = None
    priority_filters: List[str] | None = None
    assignee_filters: List[str] | None = None
    score: float = 0.0


def _jump_to_issues(
    *,
    status_filters: List[str] | None = None,
    priority_filters: List[str] | None = None,
    assignee_filters: List[str] | None = None,
) -> None:
    """Open Issues tab and sync filters derived from an actionable insight."""
    st.session_state["__jump_to_tab"] = "issues"
    st.session_state[FILTER_STATUS_KEY] = list(status_filters or [])
    st.session_state[FILTER_PRIORITY_KEY] = list(priority_filters or [])
    st.session_state[FILTER_ASSIGNEE_KEY] = list(assignee_filters or [])


def _render_insight_cards(cards: List[_TrendActionInsight], *, key_prefix: str) -> None:
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
        with cols[i % 2]:
            with st.container(border=True):
                if has_action:
                    with st.container(key=f"trins_{key_prefix}_{i}"):
                        st.button(
                            f"{item.title} ↗",
                            key=f"trins_btn_{key_prefix}_{i}",
                            use_container_width=True,
                            on_click=_jump_to_issues,
                            kwargs={
                                "status_filters": item.status_filters,
                                "priority_filters": item.priority_filters,
                                "assignee_filters": item.assignee_filters,
                            },
                        )
                else:
                    st.markdown(f"**{item.title}**")
                st.markdown(item.body)


def _insights_timeseries(dff: pd.DataFrame) -> None:
    if dff.empty or "created" not in dff.columns:
        st.caption("Sin datos suficientes para generar insights de evolución.")
        return

    df = dff.copy()

    df["__created_dt"] = _to_dt_naive(df["created"])
    if "resolved" in df.columns:
        df["__resolved_dt"] = _to_dt_naive(df["resolved"])
    else:
        df["__resolved_dt"] = pd.NaT

    created = df[df["__created_dt"].notna()].copy()
    if created.empty:
        st.caption("Sin created válidas para generar insights.")
        return

    max_dt = created["__created_dt"].max()
    end_ts = pd.Timestamp(max_dt).normalize()
    start_ts = end_ts - pd.Timedelta(days=90)

    created_day = created["__created_dt"].dt.normalize()
    created_counts = created_day[created_day >= start_ts].value_counts()

    closed = df[df["__resolved_dt"].notna()].copy()
    closed_day = (
        closed["__resolved_dt"].dt.normalize()
        if not closed.empty
        else pd.Series([], dtype="datetime64[ns]")
    )
    closed_counts = (
        closed_day[closed_day >= start_ts].value_counts()
        if not closed_day.empty
        else pd.Series([], dtype=int)
    )

    days = pd.date_range(start=start_ts, end=end_ts, freq="D")
    created_series = pd.Series({d: int(created_counts.get(d, 0)) for d in days})
    closed_series = pd.Series({d: int(closed_counts.get(d, 0)) for d in days})

    net = created_series - closed_series
    backlog_proxy = net.cumsum()

    last14 = backlog_proxy.tail(14)
    prev14 = backlog_proxy.tail(28).head(14) if len(backlog_proxy) >= 28 else None

    slope_last = float(last14.iloc[-1] - last14.iloc[0]) if len(last14) >= 2 else 0.0
    slope_prev = (
        float(prev14.iloc[-1] - prev14.iloc[0]) if prev14 is not None and len(prev14) >= 2 else 0.0
    )

    created_14 = int(created_series.tail(14).sum())
    closed_14 = int(closed_series.tail(14).sum())
    flow_ratio = (created_14 / closed_14) if closed_14 > 0 else np.inf

    weekly_net = float(net.tail(28).mean()) * 7.0 if len(net) >= 7 else float(net.mean()) * 7.0
    risk_flag = weekly_net > 0

    st.markdown("#### Insights accionables")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Creación (últ. 14d)", created_14)
    with c2:
        st.metric("Cierre (últ. 14d)", closed_14)
    with c3:
        st.metric("Ratio creación/cierre", "∞" if flow_ratio == np.inf else f"{flow_ratio:.2f}")

    cards: List[_TrendActionInsight] = []

    if slope_last > 0 and (prev14 is None or slope_last > slope_prev):
        cards.append(
            _TrendActionInsight(
                title="Aceleración de backlog",
                body=(
                    f"En los últimos 14 días el backlog proxy sube **+{int(slope_last)}** "
                    f"(vs **+{int(slope_prev)}** en los 14 días anteriores). Señal de saturación del flujo."
                ),
                score=max(20.0, float(slope_last)),
            )
        )
    elif slope_last > 0:
        cards.append(
            _TrendActionInsight(
                title="Backlog creciendo",
                body=(
                    f"El backlog proxy sube **+{int(slope_last)}** en 14 días. "
                    "Prioriza cerrar antes de seguir abriendo."
                ),
                score=max(10.0, float(slope_last)),
            )
        )
    elif slope_last < 0:
        cards.append(
            _TrendActionInsight(
                title="Backlog bajando",
                body=(
                    f"El backlog proxy cae **{int(abs(slope_last))}** en 14 días. "
                    "Buen momento para atacar deuda técnica/causas raíz."
                ),
                score=6.0,
            )
        )
    else:
        cards.append(
            _TrendActionInsight(
                title="Backlog estable",
                body="Se mantiene estable en los últimos 14 días (señal de equilibrio).",
                score=2.0,
            )
        )

    if flow_ratio == np.inf:
        cards.append(
            _TrendActionInsight(
                title="Cierre a cero",
                body="No hay cierres en 14 días: revisa bloqueos (QA, releases) o colas de validación.",
                score=30.0,
            )
        )
    elif flow_ratio >= 1.2:
        cards.append(
            _TrendActionInsight(
                title="Capacidad insuficiente",
                body=(
                    "Estás abriendo bastante más de lo que cierras. "
                    "Acción: fija un objetivo semanal de cierre y limita casos en curso."
                ),
                score=18.0 + float(flow_ratio),
            )
        )
    elif flow_ratio <= 0.9:
        cards.append(
            _TrendActionInsight(
                title="Ventana de limpieza",
                body=(
                    "Cierras más de lo que abres. Usa el margen para eliminar reincidencias "
                    "y automatizar pruebas."
                ),
                score=7.0,
            )
        )

    if risk_flag:
        cards.append(
            _TrendActionInsight(
                title="Tendencia semanal neta positiva",
                body=(
                    f"~**{weekly_net:.1f}** issues/semana. "
                    "Si se mantiene, el backlog seguirá creciendo."
                ),
                score=14.0 + float(weekly_net),
            )
        )

    _render_insight_cards(cards[:5], key_prefix="timeseries")

    st.caption(
        "Tip de gestión: si el ratio creación/cierre > 1 de forma sostenida, cualquier mejora visual será temporal. "
        "La palanca real está en reducir entrada (calidad/triage) o aumentar cierre (flujo/bloqueos)."
    )


def _insights_age(open_df: pd.DataFrame) -> None:
    if open_df is None or open_df.empty or "created" not in open_df.columns:
        st.caption("Sin datos suficientes para insights de antigüedad.")
        return

    df = open_df.copy()
    df["__created_dt"] = _to_dt_naive(df["created"])
    now = pd.Timestamp.utcnow().tz_localize(None)

    df = df[df["__created_dt"].notna()].copy()
    if df.empty:
        st.caption("No hay created válidas para calcular antigüedad.")
        return

    df["age_days"] = (now - df["__created_dt"]).dt.total_seconds() / 86400.0
    p50 = float(df["age_days"].median())
    p90 = float(df["age_days"].quantile(0.90))
    over30 = int((df["age_days"] > 30).sum())
    total = int(len(df))
    pct_over30 = (over30 / total * 100.0) if total else 0.0

    st.markdown("#### Insights accionables")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Antigüedad típica", f"{p50:.0f} días")
    with c2:
        st.metric("Casos más atascados", f"{p90:.0f} días")
    with c3:
        st.metric(">30 días", f"{pct_over30:.1f}%")

    cards: List[_TrendActionInsight] = []
    cards.append(
        _TrendActionInsight(
            title="Atasco en casos antiguos",
            body=(
                "Cuando los casos más lentos tardan mucho, el equipo pierde foco y velocidad. "
                "Separar esos casos en revisión específica mejora el ritmo general."
            ),
            score=max(8.0, p90 / 15.0),
        )
    )

    if pct_over30 >= 25:
        cards.append(
            _TrendActionInsight(
                title="Backlog envejecido",
                body=(
                    f"**{pct_over30:.1f}%** supera 30 días. "
                    "Acción: clínica semanal para cerrar, re-priorizar o descomponer."
                ),
                score=float(pct_over30),
            )
        )

    if "priority" in df.columns:
        tail = df[df["age_days"] > 30].copy()
        if not tail.empty:
            pr = tail["priority"].astype(str).value_counts().head(3)
            top_prios = ", ".join([f"{k} ({int(v)})" for k, v in pr.items()])
            cards.append(
                _TrendActionInsight(
                    title="Dónde duele la cola",
                    body=(
                        f"En >30 días dominan: **{top_prios}**. "
                        "Si High/Highest aparecen, hay riesgo de impacto cliente."
                    ),
                    priority_filters=[str(p) for p in pr.index.tolist()],
                    score=12.0 + float(len(pr)),
                )
            )

    cards.append(
        _TrendActionInsight(
            title="Política útil de flujo",
            body=(
                "Para evitar envejecimiento, limita cuántos casos caben por estado "
                "y exige criterio de salida."
            ),
            status_filters=["En progreso", "In Progress", "To Rework", "Test", "Ready To Verify"],
            score=5.0,
        )
    )

    _render_insight_cards(cards[:5], key_prefix="age")


def _insights_resolution(dff: pd.DataFrame) -> None:
    if dff is None or dff.empty or "resolved" not in dff.columns or "created" not in dff.columns:
        st.caption("Sin datos suficientes para insights de resolución.")
        return

    df = dff.copy()
    df["__created_dt"] = _to_dt_naive(df["created"])
    df["__resolved_dt"] = _to_dt_naive(df["resolved"])

    closed = df[df["__created_dt"].notna() & df["__resolved_dt"].notna()].copy()
    if closed.empty:
        st.caption("No hay cerradas con fechas suficientes para este filtro.")
        return

    closed["resolution_days"] = (
        (closed["__resolved_dt"] - closed["__created_dt"]).dt.total_seconds() / 86400.0
    ).clip(lower=0.0)

    med = float(closed["resolution_days"].median())
    p90 = float(closed["resolution_days"].quantile(0.90))
    p95 = float(closed["resolution_days"].quantile(0.95))

    st.markdown("#### Insights accionables")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Resolución habitual", f"{med:.1f} d")
    with c2:
        st.metric("Resolución lenta", f"{p90:.1f} d")
    with c3:
        st.metric("Casos muy lentos", f"{p95:.1f} d")

    cards: List[_TrendActionInsight] = []
    cards.append(
        _TrendActionInsight(
            title="Impacto de casos lentos",
            body=(
                "No basta con cerrar rápido los fáciles; si mejoras los más atascados, "
                "la percepción del cliente mejora de verdad."
            ),
            score=max(6.0, p90 / 10.0),
        )
    )

    if p95 > med * 3:
        cards.append(
            _TrendActionInsight(
                title="Cola de casos muy lentos",
                body=(
                    "Algunos casos tardan mucho más que el promedio. "
                    "Clasifica por causa y asigna responsable."
                ),
                score=max(10.0, p95 / max(med, 1.0)),
            )
        )

    if "priority" in closed.columns:
        grp = (
            closed.groupby(closed["priority"].astype(str))["resolution_days"]
            .median()
            .sort_values(ascending=False)
        )
        if not grp.empty:
            worst = str(grp.index[0])
            cards.append(
                _TrendActionInsight(
                    title="Dónde se atasca",
                    body=(
                        f"La mediana peor está en **{worst}** (**{grp.iloc[0]:.1f} d**). "
                        "Revisa pasos extra que alargan el ciclo."
                    ),
                    priority_filters=[worst],
                    score=float(grp.iloc[0]),
                )
            )

    cards.append(
        _TrendActionInsight(
            title="Vía rápida de incidentes",
            body=("Plantilla + checklist de evidencias reduce rebotes y acelera diagnóstico."),
            score=3.0,
        )
    )

    _render_insight_cards(cards[:5], key_prefix="resolution")


def _insights_priority(open_df: pd.DataFrame) -> None:
    if open_df is None or open_df.empty or "priority" not in open_df.columns:
        st.caption("Sin datos suficientes para insights por priority.")
        return

    df = open_df.copy()
    total = int(len(df))
    counts = df["priority"].astype(str).value_counts()
    top = str(counts.index[0]) if not counts.empty else None

    from bug_resolution_radar.ui.common import priority_rank  # local import to keep module clean

    df["_prio_rank"] = df["priority"].astype(str).map(priority_rank).fillna(99).astype(int)
    df["_weight"] = (6 - df["_prio_rank"]).clip(lower=1, upper=6)
    risk_score = int(df["_weight"].sum())

    st.markdown("#### Insights accionables")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total abiertas", total)
    with c2:
        st.metric("Priority dominante", top or "—")
    with c3:
        st.metric("Riesgo ponderado", risk_score)

    cards: List[_TrendActionInsight] = []
    if top:
        pct = (int(counts.iloc[0]) / total * 100.0) if total else 0.0
        cards.append(
            _TrendActionInsight(
                title="Concentración de prioridad",
                body=(
                    f"**{top}** representa **{pct:.1f}%** del backlog. "
                    "Si es Medium/Low y crece, puede ocultar deuda."
                ),
                priority_filters=[top],
                score=8.0 + pct,
            )
        )

    cards.append(
        _TrendActionInsight(
            title="Riesgo ponderado",
            body=(
                "No basta contar issues; una High puede equivaler a varias Low en impacto. "
                "Usa este score para decidir si activar modo incidente."
            ),
            score=float(risk_score / max(total, 1)),
        )
    )

    if "status" in df.columns:
        early = {"New", "Analysing", "Analyzing"}
        crit = df[df["_prio_rank"] <= 2]
        if not crit.empty:
            crit_early = crit[crit["status"].astype(str).isin(early)]
            if len(crit_early) > 0:
                cards.append(
                    _TrendActionInsight(
                        title="Críticas sin arrancar",
                        body=(
                            f"**{len(crit_early)}** issues High/Highest siguen en estados iniciales. "
                            "Asigna owner hoy y fuerza primer diagnóstico."
                        ),
                        priority_filters=["Supone un impedimento", "Highest", "High"],
                        status_filters=["New", "Analysing", "Analyzing"],
                        score=15.0 + float(len(crit_early)),
                    )
                )

    cards.append(
        _TrendActionInsight(
            title="Gobierno de prioridades",
            body=("Si todo es High, nada es High. Mantén cupo de prioridades altas activas."),
            priority_filters=["Supone un impedimento", "Highest", "High"],
            score=5.0,
        )
    )

    _render_insight_cards(cards[:5], key_prefix="priority")


def _insights_status(open_df: pd.DataFrame) -> None:
    if open_df is None or open_df.empty or "status" not in open_df.columns:
        st.caption("Sin datos suficientes para insights por estado.")
        return

    df = open_df.copy()
    df["status"] = normalize_text_col(df["status"], "(sin estado)")
    counts = df["status"].astype(str).value_counts()
    total = int(len(df))
    top_status = str(counts.index[0]) if not counts.empty else None
    top_share = (int(counts.iloc[0]) / total * 100.0) if (total and not counts.empty) else 0.0

    st.markdown("#### Insights accionables")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total abiertas", total)
    with c2:
        st.metric("Estado dominante", top_status or "—")
    with c3:
        st.metric("Concentración top estado", f"{top_share:.1f}%")

    cards: List[_TrendActionInsight] = []
    if top_status:
        cards.append(
            _TrendActionInsight(
                title="Cuello de botella probable",
                body=(
                    f"**{top_share:.1f}%** del backlog está en **{top_status}**. "
                    "Revisa la condición de salida que está fallando."
                ),
                status_filters=[top_status],
                score=top_share,
            )
        )

    active_states = {
        "En progreso",
        "In Progress",
        "Analysing",
        "Analyzing",
        "Ready To Verify",
        "To Rework",
        "Test",
    }
    active = df[df["status"].astype(str).isin(active_states)]
    active_pct = (len(active) / total * 100.0) if total else 0.0

    cards.append(
        _TrendActionInsight(
            title="Carga activa estimada",
            body=(
                f"**{active_pct:.1f}%** está en estados activos. "
                "Si es alto, suele indicar multitarea y cambios de contexto."
            ),
            status_filters=[
                s for s in active_states if s in df["status"].astype(str).unique().tolist()
            ],
            score=active_pct,
        )
    )

    triage_states = {"New", "Analysing", "Analyzing"}
    triage = df[df["status"].astype(str).isin(triage_states)]
    triage_pct = (len(triage) / total * 100.0) if total else 0.0
    if triage_pct >= 40:
        cards.append(
            _TrendActionInsight(
                title="Deuda de triage",
                body=(
                    f"**{triage_pct:.1f}%** en New/Analysing. "
                    "Haz sesión diaria breve para convertir entrada en decisiones."
                ),
                status_filters=["New", "Analysing", "Analyzing"],
                score=triage_pct + 5.0,
            )
        )

    # Flujo final: Accepted -> Ready to deploy -> Deployed
    accepted_cnt = int((df["status"].astype(str) == "Accepted").sum())
    rtd_cnt = int((df["status"].astype(str) == "Ready to deploy").sum())
    deployed_cnt = int((df["status"].astype(str) == "Deployed").sum())

    if accepted_cnt > 0:
        rtd_conv = (rtd_cnt / accepted_cnt) * 100.0
        if rtd_conv < 35.0:
            cards.append(
                _TrendActionInsight(
                    title="Atasco post-Accepted",
                    body=(
                        f"Hay **{accepted_cnt}** en Accepted y solo **{rtd_cnt}** en Ready to deploy "
                        f"(conversión **{rtd_conv:.1f}%**)."
                    ),
                    status_filters=["Accepted", "Ready to deploy"],
                    score=max(12.0, float(accepted_cnt - rtd_cnt)),
                )
            )

    if rtd_cnt > 0:
        dep_conv = (deployed_cnt / rtd_cnt) * 100.0
        if dep_conv < 70.0:
            cards.append(
                _TrendActionInsight(
                    title="Cuello en release",
                    body=(
                        f"Hay **{rtd_cnt}** en Ready to deploy y **{deployed_cnt}** en Deployed "
                        f"(conversión **{dep_conv:.1f}%**)."
                    ),
                    status_filters=["Ready to deploy", "Deployed"],
                    score=max(10.0, float(rtd_cnt - deployed_cnt)),
                )
            )
    elif accepted_cnt > 0 and deployed_cnt == 0:
        cards.append(
            _TrendActionInsight(
                title="Flujo detenido al final",
                body="Existen Accepted pero no llegan a Ready to deploy ni a Deployed.",
                status_filters=["Accepted", "Ready to deploy"],
                score=18.0 + float(accepted_cnt),
            )
        )

    cards.append(
        _TrendActionInsight(
            title="Política de tiempos por estado",
            body=(
                "Define tiempos máximos por estado para hacer visibles los cuellos "
                "sin revisar caso por caso."
            ),
            score=3.0,
        )
    )

    _render_insight_cards(cards[:5], key_prefix="status")
