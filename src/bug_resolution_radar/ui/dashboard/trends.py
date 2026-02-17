# bug_resolution_radar/ui/dashboard/trends.py
from __future__ import annotations

from typing import Dict, List, Tuple

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
from bug_resolution_radar.ui.style import apply_plotly_bbva


# -------------------------
# Helpers: fechas robustas (evita date vs datetime / tz-aware vs tz-naive)
# -------------------------
def _to_dt_naive(s: pd.Series) -> pd.Series:
    """Coerce a datetime64[ns] y quita timezone si la hay (para comparaciones seguras)."""
    if s is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(s, errors="coerce")
    try:
        if hasattr(out.dt, "tz") and out.dt.tz is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        # best-effort en tipos mixtos
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
    """
    Buckets canon:
      0-2, 3-7, 8-14, 15-30, >30
    """
    bins = [-np.inf, 2, 7, 14, 30, np.inf]
    labels = ["0-2", "3-7", "8-14", "15-30", ">30"]
    cat = pd.cut(age_days, bins=bins, labels=labels, right=True, include_lowest=True, ordered=True)
    # For plotly ordering stability
    return cat


# -------------------------
# Charts catalog
# -------------------------
def available_trend_charts() -> List[Tuple[str, str]]:
    return [
        ("timeseries", "Evolución del backlog (últimos 90 días)"),
        ("age_buckets", "Antigüedad de abiertas (distribución)"),
        ("resolution_hist", "Tiempos de resolución (cerradas)"),
        ("open_priority_pie", "Abiertas por Priority"),
        ("open_status_bar", "Abiertas por Estado"),
    ]


# -------------------------
# Public entrypoint
# -------------------------
def render_trends_tab(*, dff: pd.DataFrame, open_df: pd.DataFrame, kpis: dict) -> None:
    dff = _safe_df(dff)
    open_df = _safe_df(open_df)
    kpis = kpis if isinstance(kpis, dict) else {}

    chart_options = available_trend_charts()
    id_to_label: Dict[str, str] = {cid: label for cid, label in chart_options}
    all_ids = [cid for cid, _ in chart_options]

    if not all_ids:
        st.info("No hay gráficos configurados.")
        return

    # 1) Selector único ARRIBA
    if "trend_chart_single" not in st.session_state:
        st.session_state["trend_chart_single"] = (
            "timeseries" if "timeseries" in all_ids else all_ids[0]
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
        help="Selecciona un único gráfico. Se mostrará 1 por pantalla.",
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
        fig = kpis.get("timeseries_chart")
        if fig is None:
            st.info("No hay datos suficientes para la serie temporal con los filtros actuales.")
            return
        fig.update_layout(title=None)
        st.plotly_chart(apply_plotly_bbva(fig), use_container_width=True)
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
            color="status",
            barmode="stack",
            category_orders={"bucket": bucket_order, "status": status_order},
            color_discrete_map=status_color_map(status_order),
        )
        fig.update_layout(title=None, xaxis_title="bucket", yaxis_title="count")
        st.plotly_chart(apply_plotly_bbva(fig), use_container_width=True)
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

        fig = px.histogram(
            closed,
            x="resolution_days",
            nbins=30,
        )
        fig.update_layout(title=None)
        st.plotly_chart(apply_plotly_bbva(fig), use_container_width=True)
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
        fig.update_layout(title=None)
        fig.update_traces(sort=False)
        st.plotly_chart(apply_plotly_bbva(fig), use_container_width=True)
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
            color="priority",
            barmode="stack",
            category_orders={"status": status_order, "priority": priority_order},
            color_discrete_map=priority_color_map(),
        )
        fig.update_layout(title=None)
        st.plotly_chart(apply_plotly_bbva(fig), use_container_width=True)
        return

    st.info("Gráfico no reconocido.")


# -------------------------
# “WoW” insights
# -------------------------
def _render_trend_insights(*, chart_id: str, dff: pd.DataFrame, open_df: pd.DataFrame) -> None:
    """
    Insights pensados para gestión (backlog, riesgo, foco, flujo).
    Evita obviedades y devuelve acciones sugeridas.
    """
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

    bullets: List[str] = []

    if slope_last > 0 and (prev14 is None or slope_last > slope_prev):
        bullets.append(
            f"📈 **Aceleración de backlog**: en los últimos 14 días el backlog proxy sube **+{int(slope_last)}** "
            f"(vs **+{int(slope_prev)}** en los 14 días anteriores). Señal de saturación del flujo."
        )
    elif slope_last > 0:
        bullets.append(
            f"📈 **Backlog creciendo**: el backlog proxy sube **+{int(slope_last)}** en 14 días. "
            "Prioriza cerrar antes de seguir abriendo."
        )
    elif slope_last < 0:
        bullets.append(
            f"✅ **Backlog bajando**: el backlog proxy cae **{int(abs(slope_last))}** en 14 días. "
            "Buen momento para atacar deuda técnica/causas raíz."
        )
    else:
        bullets.append("⚖️ **Backlog estable** en los últimos 14 días (señal de equilibrio).")

    if flow_ratio == np.inf:
        bullets.append(
            "🚨 **Cierre a cero** en 14 días: revisa bloqueos (QA, releases) o colas de validación."
        )
    elif flow_ratio >= 1.2:
        bullets.append(
            "🧯 **Capacidad insuficiente**: estás abriendo bastante más de lo que cierras. "
            "Acción: fija un objetivo semanal de cierre y limita WIP (por estado/equipo)."
        )
    elif flow_ratio <= 0.9:
        bullets.append(
            "🧹 **Ventana de limpieza**: cierras más de lo que abres. "
            "Acción: usa el margen para eliminar reincidencias (top componentes/causas) y automatizar pruebas."
        )

    if risk_flag:
        bullets.append(
            f"⏳ **Tendencia semanal neta positiva** (~{weekly_net:.1f} issues/semana): "
            "si se mantiene, el backlog seguirá creciendo aunque hoy parezca controlado."
        )

    for b in bullets[:5]:
        st.write("• " + b)

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
        st.metric("Mediana antigüedad", f"{p50:.0f} días")
    with c2:
        st.metric("P90 antigüedad", f"{p90:.0f} días")
    with c3:
        st.metric(">30 días", f"{pct_over30:.1f}%")

    bullets: List[str] = []
    bullets.append(
        "🧠 **Cola larga = coste oculto**: un P90 alto suele indicar issues “difíciles” o bloqueadas. "
        "Separarlas del flujo normal evita que contaminen la velocidad del equipo."
    )

    if pct_over30 >= 25:
        bullets.append(
            f"⚠️ **Backlog envejecido**: {pct_over30:.1f}% supera 30 días. "
            "Acción: crea una “clínica de envejecidos” semanal (60–90 min) para decidir: cerrar, re-priorizar o descomponer."
        )

    if "priority" in df.columns:
        tail = df[df["age_days"] > 30].copy()
        if not tail.empty:
            pr = tail["priority"].astype(str).value_counts().head(3)
            top_prios = ", ".join([f"{k} ({int(v)})" for k, v in pr.items()])
            bullets.append(
                f"🎯 **Dónde duele la cola**: en >30 días dominan: **{top_prios}**. "
                "Acción: si High/Highest aparecen, hay riesgo de SLA/impacto cliente: forzar plan de cierre con dueño y fecha."
            )

    bullets.append(
        "📌 **Política útil**: para evitar envejecimiento, limita WIP por estado (Accepted/En progreso) "
        "y exige criterio de salida (Definition of Done + verificación)."
    )

    for b in bullets[:5]:
        st.write("• " + b)


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
        st.metric("Mediana resolución", f"{med:.1f} d")
    with c2:
        st.metric("P90 resolución", f"{p90:.1f} d")
    with c3:
        st.metric("P95 resolución", f"{p95:.1f} d")

    bullets: List[str] = []
    bullets.append(
        "🧠 **P90/P95 mandan**: la experiencia de negocio la determinan los casos lentos, no la mediana. "
        "Si mejoras el P90, el sistema se siente “mucho más rápido”."
    )

    if p95 > med * 3:
        bullets.append(
            "🧯 **Cola pesada** detectada: el P95 es >3x la mediana. "
            "Acción: clasifica cierres lentos por causa (dependencias, QA, release, acceso, datos) y pon owners."
        )

    if "priority" in closed.columns:
        grp = (
            closed.groupby(closed["priority"].astype(str))["resolution_days"]
            .median()
            .sort_values(ascending=False)
        )
        if not grp.empty:
            worst = str(grp.index[0])
            bullets.append(
                f"🎯 **Dónde se atasca**: la mediana peor está en **{worst}** ({grp.iloc[0]:.1f} d). "
                "Acción: revisa si esa prioridad tiene ‘hand-offs’ extra (validación, comités) que alargan el ciclo."
            )

    bullets.append(
        "📌 Palanca práctica: crea una vía rápida para incidentes con plantilla + checklist de evidencias "
        "(logs, pasos, device, build). Reduce rebotes y acelera diagnóstico."
    )

    for b in bullets[:5]:
        st.write("• " + b)


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

    bullets: List[str] = []
    if top:
        pct = (int(counts.iloc[0]) / total * 100.0) if total else 0.0
        bullets.append(
            f"📌 **Concentración**: **{top}** representa **{pct:.1f}%** del backlog. "
            "Acción: si es Medium/Low y crece, puede ocultar deuda que se convertirá en incidentes."
        )

    bullets.append(
        "🧠 **Riesgo ponderado**: no basta contar issues; una sola High puede equivaler a muchas Low en impacto. "
        "Usa este score para decidir si necesitas ‘modo incidente’ (swarming) esta semana."
    )

    if "status" in df.columns:
        early = {"New", "Accepted", "Analysing", "Analyzing"}
        crit = df[df["_prio_rank"] <= 2]
        if not crit.empty:
            crit_early = crit[crit["status"].astype(str).isin(early)]
            if len(crit_early) > 0:
                bullets.append(
                    f"🚨 **Críticas sin arrancar**: {len(crit_early)} issues High/Highest siguen en estados iniciales. "
                    "Acción: asigna owner hoy y fuerza primer diagnóstico (no más de 24–48h)."
                )

    bullets.append(
        "📌 Consejo: limita el número de prioridades ‘altas’ activas. Si todo es High, nada es High. "
        "Mantén un cupo y exige justificación."
    )

    for b in bullets[:5]:
        st.write("• " + b)


def _insights_status(open_df: pd.DataFrame) -> None:
    if open_df is None or open_df.empty or "status" not in open_df.columns:
        st.caption("Sin datos suficientes para insights por estado.")
        return

    df = open_df.copy()
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

    bullets: List[str] = []
    if top_status:
        bullets.append(
            f"🧠 **Cuello de botella probable**: {top_share:.1f}% del backlog está en **{top_status}**. "
            "Acción: revisa qué condición de salida está fallando (QA, aprobación, dependencias, releases)."
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

    bullets.append(
        f"📌 **WIP activo estimado**: {active_pct:.1f}% está en estados “activos”. "
        "Si es alto, suele indicar multitarea y cambios de contexto; limitar WIP sube throughput."
    )

    triage_states = {"New", "Accepted"}
    triage = df[df["status"].astype(str).isin(triage_states)]
    triage_pct = (len(triage) / total * 100.0) if total else 0.0
    if triage_pct >= 40:
        bullets.append(
            f"🧯 **Deuda de triage**: {triage_pct:.1f}% en New/Accepted. "
            "Acción: sesión diaria de 15 min para convertir New→(descartar/planificar/asignar) y evitar ‘pila infinita’."
        )

    bullets.append(
        "🎯 Recomendación: define SLAs internos por estado (p.ej. ‘Accepted max 3 días’). "
        "Los cuellos se vuelven visibles sin mirar cada issue."
    )

    for b in bullets[:5]:
        st.write("• " + b)
