"""Chart registry for trends and summary visualizations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from bug_resolution_radar.analytics.age_buckets_chart import (
    AGE_BUCKET_ORDER,
    build_age_bucket_points,
    build_age_buckets_issue_distribution,
)
from bug_resolution_radar.analytics.issues import normalize_text_col, priority_rank
from bug_resolution_radar.analytics.kpis import (
    OPEN_AGE_BUCKET_LABELS,
    build_open_age_priority_payload,
)
from bug_resolution_radar.analytics.trend_constants import (
    Y_AXIS_LABEL_OPEN_ISSUES,
    canonical_status_order,
)
from bug_resolution_radar.theme.plotly_style import apply_plotly_bbva
from bug_resolution_radar.theme.semantic_colors import (
    flow_signal_color_map,
    priority_color_map,
)

TERMINAL_STATUS_TOKENS = (
    "closed",
    "resolved",
    "done",
    "deployed",
    "accepted",
    "cancelled",
    "canceled",
)


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
    dark_mode: bool = False


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
    return f"{x * 100:.1f}%"


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


def _open_age_days_series(dff: pd.DataFrame) -> pd.Series:
    payload = build_open_age_priority_payload(dff)
    opened = payload.get("open") if isinstance(payload, dict) else None
    if not isinstance(opened, pd.DataFrame) or opened.empty or "open_days" not in opened.columns:
        return pd.Series([], dtype=float)
    return pd.to_numeric(opened["open_days"], errors="coerce").dropna().clip(lower=0.0)


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
    out = apply_plotly_bbva(fig, showlegend=True, dark_mode=ctx.dark_mode)
    color_map = flow_signal_color_map()
    name_map = {
        "created": "Creadas",
        "closed": "Cerradas",
        "open_backlog_proxy": "Backlog abierto",
    }
    for trace in list(getattr(out, "data", []) or []):
        name_raw = str(getattr(trace, "name", "") or "").strip()
        token = name_raw.lower()
        display_name = name_map.get(token)
        if display_name:
            trace.name = display_name
        color = color_map.get(token)
        if color and hasattr(trace, "line"):
            line_obj = getattr(trace, "line", None)
            line_width = float(getattr(line_obj, "width", 2.5) or 2.5)
            trace.line = dict(color=color, width=max(2.5, line_width))
        if color and hasattr(trace, "marker"):
            marker_obj = getattr(trace, "marker", None)
            raw_marker_size = getattr(marker_obj, "size", 0) if marker_obj is not None else 0
            try:
                marker_size = float(raw_marker_size or 0)
            except Exception:
                marker_size = 0.0
            trace.marker = dict(color=color, size=marker_size if marker_size > 0 else 6)
    out.update_layout(legend_title_text="", yaxis_title=Y_AXIS_LABEL_OPEN_ISSUES)
    return out


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
    # Este gráfico debe incluir también estados finalistas; usa el scope filtrado completo.
    points = build_age_bucket_points(ctx.dff)
    if points.empty:
        return None

    statuses = points["status"].astype(str).unique().tolist()
    canon = canonical_status_order()
    canon_present = [s for s in canon if s in statuses]
    rest = [s for s in statuses if s not in set(canon_present)]
    status_order = canon_present + rest
    return build_age_buckets_issue_distribution(
        issues=points,
        status_order=status_order,
        bucket_order=AGE_BUCKET_ORDER,
        dark_mode=ctx.dark_mode,
    )


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
    payload = build_open_age_priority_payload(ctx.dff)
    grouped = payload.get("grouped") if isinstance(payload, dict) else None
    if not isinstance(grouped, pd.DataFrame) or grouped.empty:
        return None

    priority_order = sorted(
        grouped["priority"].astype(str).unique().tolist(),
        key=_priority_sort_key,
    )
    fig = px.bar(
        grouped,
        x="age_bucket",
        y="count",
        text="count",
        color="priority",
        barmode="stack",
        category_orders={
            "age_bucket": list(OPEN_AGE_BUCKET_LABELS),
            "priority": priority_order,
        },
        color_discrete_map=priority_color_map(),
        title="Días que llevan abiertas las incidencias por prioridad",
    )
    fig.update_layout(
        title_text="",
        xaxis_title="Rango en días",
        yaxis_title=Y_AXIS_LABEL_OPEN_ISSUES,
        bargap=0.10,
    )
    fig.update_traces(textposition="inside", textfont=dict(size=10))
    return apply_plotly_bbva(fig, showlegend=True, dark_mode=ctx.dark_mode)


def _insights_resolution_hist(ctx: ChartContext) -> List[str]:
    days = _open_age_days_series(ctx.dff)
    if days.empty:
        return [
            "No hay incidencias abiertas con fechas de creación suficientes para analizar antigüedad.",
            "Tip: revisa la calidad de `created` en la ingesta y ataca primero los casos de mayor prioridad con más días abiertos.",
        ]

    p50 = float(days.quantile(0.5))
    p90 = float(days.quantile(0.9))
    over30 = float((days > 30).mean()) if len(days) > 0 else 0.0

    return [
        f"Antigüedad abierta: habitual **{p50:.0f}d** · tramo crítico **{p90:.0f}d**. "
        "El percentil alto muestra dónde se atasca de verdad el backlog.",
        f"Cola larga: **{_fmt_pct(over30)}** de abiertas supera 30 días. "
        "Acción: focalizar desbloqueos por prioridad en ese tramo mejora throughput y percepción de control.",
    ]


def _render_open_priority_pie(ctx: ChartContext) -> Optional[go.Figure]:
    open_df = ctx.open_df
    if open_df is None or open_df.empty or "priority" not in open_df.columns:
        return None

    dff = open_df.copy()
    if "status" in dff.columns:
        status_norm = (
            normalize_text_col(dff["status"], "(sin estado)").astype(str).str.lower().str.strip()
        )
        terminal_mask = status_norm.map(
            lambda st_name: any(tok in str(st_name or "") for tok in TERMINAL_STATUS_TOKENS)
        )
        dff = dff.loc[~terminal_mask].copy(deep=False)
    if dff.empty:
        return None
    dff["priority"] = normalize_text_col(dff["priority"], "(sin priority)")

    fig = px.pie(
        dff,
        names="priority",
        hole=0.55,
        color="priority",
        color_discrete_map=priority_color_map(),
        title="Issues abiertos por prioridad",
    )
    fig.update_traces(sort=False)
    return apply_plotly_bbva(fig, showlegend=True, dark_mode=ctx.dark_mode)


def _insights_open_priority_pie(ctx: ChartContext) -> List[str]:
    open_df = ctx.open_df
    if open_df is None or open_df.empty or "priority" not in open_df.columns:
        return ["No hay datos de prioridad para generar insights con los filtros actuales."]

    dff = open_df.copy()
    if "status" in dff.columns:
        status_norm = (
            normalize_text_col(dff["status"], "(sin estado)").astype(str).str.lower().str.strip()
        )
        terminal_mask = status_norm.map(
            lambda st_name: any(tok in str(st_name or "") for tok in TERMINAL_STATUS_TOKENS)
        )
        dff = dff.loc[~terminal_mask].copy(deep=False)
    if dff.empty:
        return ["No hay incidencias abiertas por prioridad con los filtros actuales."]

    counts = dff["priority"].astype(str).value_counts()
    total = int(counts.sum())
    if total == 0:
        return ["No hay issues para este análisis."]

    top = int(counts.iloc[0])
    top_prio = str(counts.index[0])
    share = float(top) / float(total)

    return [
        f"Concentración: **{top_prio}** representa **{_fmt_pct(share)}** del conjunto analizado (sobre {total} issues). "
        "Alta concentración sugiere que tu sistema de priorización está ‘aplanado’ o que hay una fuente dominante de problemas.",
        "Acción: si la prioridad más alta domina, crea un ‘fast lane’ con definición de listo (DoR) estricta; "
        "si domina una prioridad baja, revisa higiene: duplicados, issues sin owner o sin impacto claro.",
    ]


def _render_open_status_bar(ctx: ChartContext) -> Optional[go.Figure]:
    status_df = ctx.dff
    if status_df is None or status_df.empty or "status" not in status_df.columns:
        return None

    dff = status_df.copy()
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
        text="count",
        color="priority",
        title="Issues por Estado",
        category_orders={"status": ordered_statuses, "priority": priority_order},
        color_discrete_map=priority_color_map(),
    )
    fig.update_traces(textposition="inside", textfont=dict(size=12))
    return apply_plotly_bbva(fig, showlegend=True, dark_mode=ctx.dark_mode)


def _insights_open_status_bar(ctx: ChartContext) -> List[str]:
    status_df = ctx.dff
    if status_df is None or status_df.empty or "status" not in status_df.columns:
        return ["No hay datos de estado para generar insights con los filtros actuales."]

    stc = normalize_text_col(status_df["status"], "(sin estado)").astype(str)
    counts = stc.value_counts()
    total = int(counts.sum())
    if total == 0:
        return ["No hay issues para este análisis."]

    non_terminal_counts = counts[
        [
            not any(tok in str(status_name or "").strip().lower() for tok in TERMINAL_STATUS_TOKENS)
            for status_name in counts.index
        ]
    ]
    if non_terminal_counts.empty:
        return [
            "No hay concentración relevante en estados operativos con este filtro.",
            "Acción ‘WOW’: abre foco en estados activos (New, Analysing, En progreso, Blocked) para detectar dónde se frena el flujo.",
        ]

    top_status = str(non_terminal_counts.index[0])
    top_cnt = int(non_terminal_counts.iloc[0])
    share = float(top_cnt) / float(total)
    insights = [
        f"Cuello de botella: el estado **{top_status}** concentra **{_fmt_pct(share)}** del conjunto analizado "
        f"({top_cnt}/{total}). Cuando un estado domina, suele ser un ‘waiting room’ (bloqueos, validación, dependencias).",
        "Acción ‘WOW’: define un límite de casos para ese estado (con revisión diaria de bloqueos). "
        "Reducir casos acumulados en el cuello suele acelerar el flujo sin aumentar capacidad.",
    ]
    return insights[:3]


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
            title="Días abiertas por prioridad",
            subtitle="Antigüedad de incidencias abiertas y cola de riesgo",
            group="Calidad",
            render=_render_resolution_hist,
            insights=_insights_resolution_hist,
        ),
        ChartSpec(
            chart_id="open_priority_pie",
            title="Issues abiertos por prioridad",
            subtitle="Concentración y salud del sistema de priorización",
            group="Backlog",
            render=_render_open_priority_pie,
            insights=_insights_open_priority_pie,
        ),
        ChartSpec(
            chart_id="open_status_bar",
            title="Backlog por estado",
            subtitle="Concentración por fase y ritmo de salida del flujo",
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
