# bug_resolution_radar/ui/dashboard/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from bug_resolution_radar.ui.common import (
    normalize_text_col,
    priority_color_map,
    priority_rank,
)
from bug_resolution_radar.ui.dashboard.constants import canonical_status_order
from bug_resolution_radar.ui.style import apply_plotly_bbva


# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class ChartContext:
    """Inputs that chart renderers / insight generators may need.

    - dff: filtered dataframe (all issues)
    - open_df: filtered dataframe (only open issues)
    - kpis: computed KPIs dict (compute_kpis output)
    """

    dff: pd.DataFrame
    open_df: pd.DataFrame
    kpis: dict


@dataclass(frozen=True)
class ChartSpec:
    """Declarative chart registry entry."""

    chart_id: str
    title: str
    subtitle: str
    group: str  # e.g. "Evolución", "Backlog", "Calidad"
    render: Callable[[ChartContext], Optional[go.Figure]]
    insights: Callable[[ChartContext], List[str]]


# ---------------------------------------------------------------------
# Helpers (safe datetime + insights)
# ---------------------------------------------------------------------
def _fmt_pct(x: float) -> str:
    return f"{x*100:.1f}%"


def _safe_series(df: pd.DataFrame, col: str) -> pd.Series:
    if df is None or df.empty or col not in df.columns:
        return pd.Series([], dtype=float)
    return df[col]


def _quantile_hint(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    s = pd.Series(values).dropna()
    if s.empty:
        return None
    return float(s.quantile(q))


def _to_dt_naive(s: pd.Series) -> pd.Series:
    """Coerce to datetime64[ns] and strip timezone (naive) to avoid tz/date comparison issues."""
    if s is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(s, errors="coerce")
    # If tz-aware -> make naive
    try:
        if hasattr(out.dt, "tz") and out.dt.tz is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        # Some pandas versions / mixed types may fail; best-effort
        try:
            out = out.dt.tz_localize(None)
        except Exception:
            pass
    return out


def _resolution_days_series(dff: pd.DataFrame) -> pd.Series:
    if dff is None or dff.empty:
        return pd.Series([], dtype=float)
    if "resolved" not in dff.columns or "created" not in dff.columns:
        return pd.Series([], dtype=float)

    created = _to_dt_naive(dff["created"])
    resolved = _to_dt_naive(dff["resolved"])

    closed = dff.copy()
    closed["__created"] = created
    closed["__resolved"] = resolved
    closed = closed[closed["__resolved"].notna() & closed["__created"].notna()]
    if closed.empty:
        return pd.Series([], dtype=float)

    days = (closed["__resolved"] - closed["__created"]).dt.total_seconds() / 86400.0
    return days.clip(lower=0.0)


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


# ---------------------------------------------------------------------
# Chart renderers
# ---------------------------------------------------------------------
def _render_timeseries(ctx: ChartContext) -> Optional[go.Figure]:
    fig = ctx.kpis.get("timeseries_chart")
    if fig is None:
        return None
    # Already a plotly Figure produced by compute_kpis
    return apply_plotly_bbva(fig)


def _insights_timeseries(ctx: ChartContext) -> List[str]:
    # Heuristics: compare last 7 vs previous 7 in nuevas incidencias (created)
    dff = ctx.dff
    if dff is None or dff.empty or "created" not in dff.columns:
        return [
            "Si ves picos de nuevas incidencias, suele correlacionar con releases o cambios de configuración: cruza esos días con despliegues para encontrar el driver real.",
            "Consejo de gestión: si el backlog no baja aunque cierres, el ritmo de cierre está por debajo de la entrada de nuevas incidencias. Revisa capacidad o criterios de entrada.",
        ]

    created = _to_dt_naive(dff["created"]).dropna()
    if created.empty:
        return [
            "Si el backlog no baja aunque cierres, el ritmo de cierre está por debajo de la entrada. Revisa capacidad o criterios de entrada.",
            "Tip: compara semanas con picos frente a releases/incidentes para identificar fuentes recurrentes de deuda.",
        ]

    max_dt = created.max()
    w7 = max_dt - pd.Timedelta(days=7)
    w14 = max_dt - pd.Timedelta(days=14)

    new_last7 = int((created >= w7).sum())
    new_prev7 = int(((created >= w14) & (created < w7)).sum())
    delta = new_last7 - new_prev7

    trend = "sube" if delta > 0 else "baja" if delta < 0 else "se mantiene"
    msg1 = (
        f"Nuevas incidencias última semana: **{new_last7}** vs semana anterior: **{new_prev7}** → {trend}. "
        "Úsalo como señal temprana para ajustar capacidad antes de que crezca el backlog."
    )

    msg2 = (
        "Acción recomendada: si esta curva sube 2–3 semanas seguidas, prioriza ‘quick wins’ (bugs repetibles/duplicados) "
        "y bloquea nuevas entradas sin criterio de severidad para evitar deuda crónica."
    )
    return [msg1, msg2]


def _render_age_buckets(ctx: ChartContext) -> Optional[go.Figure]:
    fig = ctx.kpis.get("age_buckets_chart")
    if fig is None:
        return None
    return apply_plotly_bbva(fig)


def _insights_age_buckets(ctx: ChartContext) -> List[str]:
    open_df = ctx.open_df
    if open_df is None or open_df.empty:
        return [
            "No hay issues abiertas con los filtros actuales: buen momento para endurecer calidad de entrada y evitar re-aperturas."
        ]

    if "created" not in open_df.columns:
        return [
            "La cola de antigüedad es el ‘interés’ de la deuda técnica: una cola larga suele indicar bloqueos de producto o falta de ownership.",
            "Acción: define un tiempo objetivo por prioridad y revisa semanalmente los casos más antiguos (son los que más impacto tienen).",
        ]

    created = _to_dt_naive(open_df["created"]).dropna()
    if created.empty:
        return [
            "Si no hay fechas de creación fiables, normaliza el campo ‘created’ en la ingesta para poder medir envejecimiento y deuda.",
        ]

    now = pd.Timestamp.utcnow().tz_localize(None)
    age_days = (now - created).dt.total_seconds() / 86400.0
    if age_days.empty:
        return [
            "Si no hay fechas de creación fiables, normaliza el campo ‘created’ en la ingesta para poder medir envejecimiento y deuda.",
        ]

    p50 = _quantile_hint(age_days.tolist(), 0.5)
    p90 = _quantile_hint(age_days.tolist(), 0.9)
    p95 = _quantile_hint(age_days.tolist(), 0.95)

    msgs: List[str] = []
    if p90 is not None and p50 is not None and p95 is not None:
        msgs.append(
            f"Antigüedad habitual: **{p50:.0f}d** · casos más atascados: **{p90:.0f}d** (extremos: {p95:.0f}d). "
            "En los casos atascados es donde se concentra el riesgo reputacional."
        )
    msgs.append(
        "Acción ‘WOW’: crea un ‘war room’ de 45 min/semana solo para el **top 10% más antiguo**. "
        "Objetivo: o se desbloquea con owner/plan, o se cierra/recategoriza con decisión explícita."
    )
    return msgs


def _render_resolution_hist(ctx: ChartContext) -> Optional[go.Figure]:
    days = _resolution_days_series(ctx.dff)
    if days.empty:
        return None

    fig = px.histogram(
        pd.DataFrame({"resolution_days": days}),
        x="resolution_days",
        nbins=30,
        title="Histograma: días hasta resolución (cerradas)",
    )
    return apply_plotly_bbva(fig)


def _insights_resolution_hist(ctx: ChartContext) -> List[str]:
    days = _resolution_days_series(ctx.dff)
    if days.empty:
        return [
            "No hay suficientes cierres con fechas para analizar tiempos de resolución.",
            "Tip: asegura ‘created’ y ‘resolved’ en la ingesta y mide tiempo habitual vs casos lentos (mejor que mirar solo la media).",
        ]

    p50 = float(days.quantile(0.5))
    p90 = float(days.quantile(0.9))
    mean = float(days.mean())

    return [
        f"Tiempo de resolución: media **{mean:.1f}d** · habitual **{p50:.0f}d** · lento **{p90:.0f}d**. "
        "Si la media queda muy por encima del tiempo habitual, hay pocos casos muy lentos que distorsionan el resultado.",
        "Acción: clasifica el 10% más lento por causa raíz (bloqueo externo, falta de reproducibilidad, dependencias) "
        "y ataca la causa, no el síntoma. Reducir los casos lentos suele mejorar satisfacción más que cerrar más casos fáciles.",
    ]


def _render_open_priority_pie(ctx: ChartContext) -> Optional[go.Figure]:
    open_df = ctx.open_df
    if open_df is None or open_df.empty or "priority" not in open_df.columns:
        return None

    dff = open_df.copy()
    dff["priority"] = normalize_text_col(dff["priority"], "(sin priority)")

    fig = px.pie(
        dff,
        names="priority",
        hole=0.55,
        color="priority",
        color_discrete_map=priority_color_map(),
        title="Abiertas por Priority",
    )
    fig.update_traces(sort=False)
    return apply_plotly_bbva(fig)


def _insights_open_priority_pie(ctx: ChartContext) -> List[str]:
    open_df = ctx.open_df
    if open_df is None or open_df.empty or "priority" not in open_df.columns:
        return ["No hay datos de prioridad para generar insights con los filtros actuales."]

    counts = open_df["priority"].astype(str).value_counts()
    total = int(counts.sum())
    if total == 0:
        return ["No hay issues abiertas para este análisis."]

    top = int(counts.iloc[0])
    top_prio = str(counts.index[0])
    share = float(top) / float(total)

    return [
        f"Concentración: **{top_prio}** representa **{_fmt_pct(share)}** del backlog abierto (sobre {total} issues). "
        "Alta concentración sugiere que tu sistema de priorización está ‘aplanado’ o que hay una fuente dominante de problemas.",
        "Acción: si la prioridad más alta domina, crea un ‘fast lane’ con definición de listo (DoR) estricta; "
        "si domina una prioridad baja, revisa higiene: duplicados, issues sin owner o sin impacto claro.",
    ]


def _render_open_status_bar(ctx: ChartContext) -> Optional[go.Figure]:
    open_df = ctx.open_df
    if open_df is None or open_df.empty or "status" not in open_df.columns:
        return None

    dff = open_df.copy()
    dff["status"] = normalize_text_col(dff["status"], "(sin estado)")
    if "priority" in dff.columns:
        dff["priority"] = normalize_text_col(dff["priority"], "(sin priority)")
    else:
        dff["priority"] = "(sin priority)"

    # Status order: canonical, then by volume.
    stc_total = dff["status"].astype(str).value_counts().reset_index()
    stc_total.columns = ["status", "count"]

    status_order = canonical_status_order()
    stc_total["__rank"] = _rank_by_canon(stc_total["status"], status_order)
    stc_total = stc_total.sort_values(["__rank", "count"], ascending=[True, False]).drop(
        columns="__rank"
    )
    ordered_statuses = stc_total["status"].astype(str).tolist()

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
        color="priority",
        barmode="stack",
        title="Abiertas por Estado",
        category_orders={"status": ordered_statuses, "priority": priority_order},
        color_discrete_map=priority_color_map(),
    )
    return apply_plotly_bbva(fig)


def _insights_open_status_bar(ctx: ChartContext) -> List[str]:
    open_df = ctx.open_df
    if open_df is None or open_df.empty or "status" not in open_df.columns:
        return ["No hay datos de estado para generar insights con los filtros actuales."]

    stc = normalize_text_col(open_df["status"], "(sin estado)").astype(str)
    counts = stc.value_counts()
    total = int(counts.sum())
    if total == 0:
        return ["No hay issues abiertas para este análisis."]

    top_status = str(counts.index[0])
    top_cnt = int(counts.iloc[0])
    share = float(top_cnt) / float(total)

    insights = [
        f"Cuello de botella: el estado **{top_status}** concentra **{_fmt_pct(share)}** del backlog abierto "
        f"({top_cnt}/{total}). Cuando un estado domina, suele ser un ‘waiting room’ (bloqueos, validación, dependencias).",
        "Acción ‘WOW’: define un límite de casos para ese estado (con revisión diaria de bloqueos). "
        "Reducir casos acumulados en el cuello suele acelerar el flujo sin aumentar capacidad.",
    ]

    accepted_cnt = int((stc == "Accepted").sum())
    rtd_cnt = int((stc == "Ready to deploy").sum())
    deployed_cnt = int((stc == "Deployed").sum())

    if accepted_cnt > 0:
        rtd_conv = (rtd_cnt / accepted_cnt) * 100.0
        if rtd_conv < 35.0:
            insights.append(
                f"Flujo final con fricción: **Accepted={accepted_cnt}** vs **Ready to deploy={rtd_cnt}** "
                f"(conversión {rtd_conv:.1f}%). Revisa criterio de salida y fija un tiempo máximo para pasar a Ready to deploy."
            )
    if rtd_cnt > 0:
        dep_conv = (deployed_cnt / rtd_cnt) * 100.0
        if dep_conv < 70.0:
            insights.append(
                f"Embudo de despliegue: **Ready to deploy={rtd_cnt}** vs **Deployed={deployed_cnt}** "
                f"(conversión {dep_conv:.1f}%). Revisa capacidad/ventana de release."
            )

    return insights[:4]


# ---------------------------------------------------------------------
# Public registry API
# ---------------------------------------------------------------------
def build_trends_registry() -> Dict[str, ChartSpec]:
    """Single source of truth for available trend charts."""
    specs = [
        ChartSpec(
            chart_id="timeseries",
            title="Evolución",
            subtitle="Últimos 90 días · señal temprana de deuda vs capacidad",
            group="Evolución",
            render=_render_timeseries,
            insights=_insights_timeseries,
        ),
        ChartSpec(
            chart_id="age_buckets",
            title="Antigüedad del backlog",
            subtitle="Dónde se acumula el riesgo operativo",
            group="Backlog",
            render=_render_age_buckets,
            insights=_insights_age_buckets,
        ),
        ChartSpec(
            chart_id="resolution_hist",
            title="Tiempos de resolución",
            subtitle="Más importante reducir los casos lentos que solo la media",
            group="Calidad",
            render=_render_resolution_hist,
            insights=_insights_resolution_hist,
        ),
        ChartSpec(
            chart_id="open_priority_pie",
            title="Backlog por prioridad",
            subtitle="Concentración y salud del sistema de priorización",
            group="Backlog",
            render=_render_open_priority_pie,
            insights=_insights_open_priority_pie,
        ),
        ChartSpec(
            chart_id="open_status_bar",
            title="Backlog por estado",
            subtitle="Detecta cuellos de botella y ‘waiting rooms’",
            group="Flujo",
            render=_render_open_status_bar,
            insights=_insights_open_status_bar,
        ),
    ]
    return {s.chart_id: s for s in specs}


def list_trend_chart_options(registry: Dict[str, ChartSpec]) -> List[tuple[str, str]]:
    """Return list of (id, label) for UI selectors."""
    order = ["timeseries", "age_buckets", "open_status_bar", "open_priority_pie", "resolution_hist"]
    out: List[tuple[str, str]] = []
    for cid in order:
        if cid in registry:
            spec = registry[cid]
            out.append((cid, f"{spec.title} — {spec.subtitle}"))
    for cid, spec in registry.items():
        if cid not in {x for x, _ in out}:
            out.append((cid, f"{spec.title} — {spec.subtitle}"))
    return out


def render_chart_with_insights(
    chart_id: str,
    *,
    ctx: ChartContext,
    registry: Dict[str, ChartSpec],
) -> None:
    """Render a chart + its insights (no layout container here; handled by layout.py)."""
    spec = registry.get(chart_id)
    if spec is None:
        st.info("Gráfico no disponible.")
        return

    fig = spec.render(ctx)
    if fig is None:
        st.info("No hay datos suficientes para este gráfico con los filtros actuales.")
        return

    st.plotly_chart(fig, use_container_width=True)

    bullets = spec.insights(ctx) or []
    if bullets:
        st.markdown("##### Insights")
        for b in bullets[:4]:
            st.markdown(f"- {b}")
