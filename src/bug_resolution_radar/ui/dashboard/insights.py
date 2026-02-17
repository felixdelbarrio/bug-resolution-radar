# bug_resolution_radar/ui/dashboard/insights.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import normalize_text_col, priority_rank


# ---------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class Insight:
    level: str  # "ok" | "info" | "warn"
    title: str
    body: str


# ---------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------
def _now_utc() -> pd.Timestamp:
    # Use UTC to avoid timezone surprises; timestamps in data are typically tz-naive.
    return pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))


def _fmt_int(x: Any, default: str = "—") -> str:
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return default
        return f"{int(round(float(x)))}"
    except Exception:
        return default


def _fmt_days(x: Any, default: str = "—") -> str:
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return default
        v = float(x)
        if v < 0:
            v = 0.0
        if v < 10:
            return f"{v:.1f} días"
        return f"{v:.0f} días"
    except Exception:
        return default


def _fmt_pct(x: Any, default: str = "—") -> str:
    try:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return default
        return f"{100.0 * float(x):.1f}%"
    except Exception:
        return default


def _safe_dt(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(s, errors="coerce")
    return out


def _has_cols(df: pd.DataFrame, cols: Iterable[str]) -> bool:
    return all(c in df.columns for c in cols)


def _age_days(open_df: pd.DataFrame) -> pd.Series:
    if open_df is None or open_df.empty or "created" not in open_df.columns:
        return pd.Series([], dtype=float)
    created = _safe_dt(open_df["created"])
    return ((_now_utc() - created).dt.total_seconds() / 86400.0).clip(lower=0.0)


# ---------------------------------------------------------------------
# Core computations used by multiple charts
# ---------------------------------------------------------------------
def _daily_flow(df: pd.DataFrame, days: int = 90) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Returns:
      ts: DataFrame with columns [date, created, resolved, net, open]
      stats: dict with helpful aggregates
    """
    if df is None or df.empty or not _has_cols(df, ["created"]):
        return pd.DataFrame(), {}

    d = df.copy()
    d["created"] = _safe_dt(d.get("created"))
    d["resolved"] = _safe_dt(d.get("resolved")) if "resolved" in d.columns else pd.NaT

    end = _now_utc().normalize()
    start = end - pd.Timedelta(days=days - 1)

    created = (
        d.loc[d["created"].notna(), ["created"]]
        .assign(date=lambda x: x["created"].dt.normalize())
        .groupby("date")
        .size()
        .rename("created")
    )

    resolved = (
        d.loc[d["resolved"].notna(), ["resolved"]]
        .assign(date=lambda x: x["resolved"].dt.normalize())
        .groupby("date")
        .size()
        .rename("resolved")
    )

    idx = pd.date_range(start=start, end=end, freq="D")
    ts = pd.DataFrame(index=idx)
    ts["created"] = created.reindex(idx, fill_value=0).astype(int)
    ts["resolved"] = resolved.reindex(idx, fill_value=0).astype(int)
    ts["net"] = ts["created"] - ts["resolved"]

    # Approximate "open" series as cumulative net relative to first day open count
    # (We can compute exact open today, then back-calc.)
    open_today = int((d["resolved"].isna()).sum()) if "resolved" in d.columns else int(len(d))
    ts["open"] = open_today - ts["net"][::-1].cumsum()[::-1]  # back-propagate from today

    stats = {
        "open_today": float(open_today),
        "created_14d": float(ts["created"].tail(14).sum()),
        "resolved_14d": float(ts["resolved"].tail(14).sum()),
        "created_30d": float(ts["created"].tail(30).sum()),
        "resolved_30d": float(ts["resolved"].tail(30).sum()),
        "net_14d": float(ts["net"].tail(14).sum()),
        "net_30d": float(ts["net"].tail(30).sum()),
    }
    return ts.reset_index(names="date"), stats


def _resolution_days(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty or not _has_cols(df, ["created", "resolved"]):
        return pd.Series([], dtype=float)
    created = _safe_dt(df["created"])
    resolved = _safe_dt(df["resolved"])
    mask = created.notna() & resolved.notna()
    if not mask.any():
        return pd.Series([], dtype=float)
    days = ((resolved[mask] - created[mask]).dt.total_seconds() / 86400.0).clip(lower=0.0)
    return days.astype(float)


def _hhi(shares: pd.Series) -> float:
    """Herfindahl–Hirschman Index on shares (0..1). Higher => more concentrated."""
    s = shares.dropna().astype(float)
    if s.empty:
        return float("nan")
    s = s / s.sum()
    return float((s * s).sum())


# ---------------------------------------------------------------------
# Insight generators per chart
# ---------------------------------------------------------------------
def build_chart_insights(
    chart_id: str, *, dff: pd.DataFrame, open_df: pd.DataFrame
) -> List[Insight]:
    """
    Build "non-obvious but actionable" insights for a given chart.
    All computations are derived from filtered dataframes.
    """
    chart_id = (chart_id or "").strip()
    out: List[Insight] = []

    if chart_id == "timeseries":
        ts, stats = _daily_flow(dff, days=90)
        if ts.empty:
            return [
                Insight(
                    "info",
                    "Sin serie temporal suficiente",
                    "Faltan fechas de creación/resolución para este análisis.",
                )
            ]

        created_14 = stats.get("created_14d", 0.0)
        resolved_14 = stats.get("resolved_14d", 0.0)
        net_14 = stats.get("net_14d", 0.0)
        resolved_30 = stats.get("resolved_30d", 0.0)

        # 1) Inflow vs outflow
        if created_14 + resolved_14 > 0:
            ratio = (resolved_14 / created_14) if created_14 > 0 else float("inf")
            level = "ok" if ratio >= 1.0 else "warn"
            msg = (
                f"En los últimos 14 días se han creado {_fmt_int(created_14)} y cerrado {_fmt_int(resolved_14)} "
                f"(balance {('+' if net_14 > 0 else '')}{_fmt_int(net_14)}). "
            )
            if ratio >= 1.0:
                msg += "Estáis quemando backlog (salís por encima de la entrada)."
            else:
                msg += "La entrada supera a la salida: si esto se mantiene, el backlog crecerá."
            out.append(Insight(level, "Balance entrada/salida (14d)", msg))

        # 2) Tiempo estimado para vaciar abiertas al ritmo actual (30d)
        open_now = int(len(open_df)) if open_df is not None else 0
        daily_close = (resolved_30 / 30.0) if resolved_30 > 0 else 0.0
        if daily_close > 0:
            runway = open_now / daily_close
            level = "info" if runway <= 120 else "warn"
            out.append(
                Insight(
                    level,
                    "Tiempo estimado para vaciar abiertas",
                    f"Al ritmo de cierre de los últimos 30 días (~{daily_close:.2f}/día), "
                    f"el backlog abierto actual ({open_now}) tardaría ~{_fmt_days(runway)} en vaciarse si no entrara nada nuevo. "
                    "Útil para planificar capacidad y expectativas con negocio.",
                )
            )
        else:
            out.append(
                Insight(
                    "warn",
                    "Ritmo de cierre insuficiente",
                    "No hay cierres suficientes en 30 días para estimar el tiempo de vaciado. "
                    "Esto suele indicar poco ritmo de cierre o que el filtro actual deja muy pocas cerradas.",
                )
            )

        # 3) Anomaly / spike signal
        med_new = float(ts["created"].median())
        max_new = float(ts["created"].max())
        if med_new > 0 and max_new >= 3.0 * med_new:
            spike_day = ts.loc[ts["created"].idxmax(), "date"]
            out.append(
                Insight(
                    "info",
                    "Señal de pico de entrada",
                    f"Se observa un pico de creación (máximo {_fmt_int(max_new)} en un día) vs mediana {_fmt_int(med_new)}. "
                    f"Fecha aproximada: {pd.to_datetime(spike_day).date()}. "
                    "Sugerencia: correlaciona con releases/incidentes y revisa si faltó triage preventivo.",
                )
            )

        # 4) Weekday pattern (ops)
        try:
            tmp = ts.copy()
            tmp["dow"] = pd.to_datetime(tmp["date"]).dt.day_name()
            by_dow = (
                tmp.groupby("dow")[["created", "resolved"]]
                .mean()
                .sort_values("created", ascending=False)
            )
            if not by_dow.empty:
                top_dow = by_dow.index[0]
                out.append(
                    Insight(
                        "info",
                        "Patrón operativo semanal",
                        f"El día con mayor entrada media es **{top_dow}**. "
                        "Si coincide con despliegues, puedes mover ventanas de release o reforzar guardia/triage ese día.",
                    )
                )
        except Exception:
            pass

        return out[:4]

    if chart_id == "age_buckets":
        ages = _age_days(open_df)
        if ages.empty:
            return [
                Insight(
                    "info",
                    "Sin datos de antigüedad",
                    "Faltan fechas de creación en issues abiertas para calcular antigüedad.",
                )
            ]

        p50 = float(np.nanpercentile(ages, 50))
        p75 = float(np.nanpercentile(ages, 75))
        p90 = float(np.nanpercentile(ages, 90))
        tail30 = float((ages > 30).mean())
        tail60 = float((ages > 60).mean())

        out.append(
            Insight(
                "info",
                "Antigüedad normal vs antigüedad atascada",
                f"La mitad de los casos tarda alrededor de {_fmt_days(p50)} en moverse, "
                f"pero los más atascados llegan a {_fmt_days(p90)}. "
                "Este tramo final suele concentrar bloqueos reales.",
            )
        )
        out.append(
            Insight(
                "warn" if tail30 >= 0.25 else "info",
                "Riesgo por acumulación antigua",
                f"Issues abiertas >30d: {_fmt_pct(tail30)} · >60d: {_fmt_pct(tail60)}. "
                "Cuando la cola larga supera ~25%, suele aparecer deuda de contexto (nadie recuerda el origen) y el coste de cierre sube.",
            )
        )

        # Tail by priority (if available)
        if "priority" in open_df.columns:
            pr = normalize_text_col(open_df["priority"], "(sin priority)")
            old_mask = ages > 30
            if old_mask.any():
                byp = pr[old_mask].value_counts()
                top = byp.index[0] if not byp.empty else None
                if top:
                    out.append(
                        Insight(
                            "warn" if priority_rank(top) <= 2 else "info",
                            "Qué prioridad se está enquistando",
                            f"La prioridad más frecuente en >30d es **{top}** ({_fmt_int(byp.iloc[0])} items). "
                            "Acción: crea una campaña de cierre por lotes (batch) de esa prioridad para recuperar velocidad.",
                        )
                    )
        return out[:4]

    if chart_id == "resolution_hist":
        res = _resolution_days(dff)
        if res.empty:
            return [
                Insight(
                    "info",
                    "Sin cierres con fechas suficientes",
                    "Faltan created/resolved en cerradas para estimar tiempos de resolución.",
                )
            ]

        median = float(np.nanmedian(res))
        p75 = float(np.nanpercentile(res, 75))
        p90 = float(np.nanpercentile(res, 90))

        out.append(
            Insight(
                "info",
                "Tiempo real de resolución",
                f"Resolución habitual: {_fmt_days(median)} · casos lentos: {_fmt_days(p90)}. "
                "Si bajas el tiempo de los casos lentos, la experiencia del cliente mejora más rápido.",
            )
        )

        # Outlier pressure
        very_slow = float((res > p90).mean())
        out.append(
            Insight(
                "info",
                "Casos de cierre lento",
                f"El {_fmt_pct(very_slow)} de los cierres está en el tramo más lento; ahí suelen vivir dependencias externas, falta de ownership o tickets mal definidos. "
                "Acción: etiqueta esos casos y crea una categoría de causa raíz (blocked/dependency/spec).",
            )
        )

        # Priority comparison if present
        if "priority" in dff.columns:
            closed = dff.copy()
            closed["created"] = _safe_dt(closed.get("created"))
            closed["resolved"] = _safe_dt(closed.get("resolved"))
            mask = closed["created"].notna() & closed["resolved"].notna()
            closed = closed[mask].copy()
            if not closed.empty:
                closed["resolution_days"] = (
                    (closed["resolved"] - closed["created"]).dt.total_seconds() / 86400.0
                ).clip(lower=0.0)
                closed["priority"] = normalize_text_col(closed["priority"], "(sin priority)")
                g = closed.groupby("priority")["resolution_days"].median().sort_values()
                if len(g) >= 2:
                    fastest = g.index[0]
                    slowest = g.index[-1]
                    out.append(
                        Insight(
                            "warn" if priority_rank(slowest) <= priority_rank(fastest) else "info",
                            "Diferencial por prioridad",
                            f"La prioridad más rápida es **{fastest}** ({_fmt_days(g.iloc[0])}) y la más lenta **{slowest}** ({_fmt_days(g.iloc[-1])}). "
                            "Si una prioridad alta está entre las más lentas, indica fricción (dependencias, falta de definición o demasiados casos en curso).",
                        )
                    )
        return out[:4]

    if chart_id == "open_priority_pie":
        if open_df is None or open_df.empty or "priority" not in open_df.columns:
            return [
                Insight(
                    "info",
                    "Sin datos de prioridad",
                    "No hay columna priority o no hay abiertas con los filtros actuales.",
                )
            ]

        pr = normalize_text_col(open_df["priority"], "(sin priority)")
        vc = pr.value_counts()
        shares = vc / float(vc.sum()) if vc.sum() else vc
        hhi = _hhi(shares)

        # Concentration
        if not np.isnan(hhi):
            level = "warn" if hhi >= 0.35 else "info"
            out.append(
                Insight(
                    level,
                    "Concentración del backlog",
                    f"Índice HHI: {hhi:.2f} (cuanto más alto, más concentrado). "
                    "Concentración alta suele significar: o bien un problema estructural (mismo tipo de fallo) o un sesgo de priorización.",
                )
            )

        # High-priority share
        hi = [p for p in vc.index.tolist() if priority_rank(p) <= 2]  # P0/P1/P2-ish
        hi_share = float(shares.loc[hi].sum()) if hi else 0.0
        out.append(
            Insight(
                "warn" if hi_share >= 0.35 else "info",
                "Peso de prioridades altas",
                f"Prioridades altas (≈P0–P2): {_fmt_pct(hi_share)} del backlog filtrado. "
                "Si supera ~35%, suele indicar que la priorización se usa como 'urgente por defecto' y pierde señal.",
            )
        )

        # Old high priority
        ages = _age_days(open_df)
        if not ages.empty:
            old = ages > 30
            if old.any():
                old_pr = pr[old].value_counts()
                if not old_pr.empty:
                    top_old = old_pr.index[0]
                    out.append(
                        Insight(
                            "warn" if priority_rank(top_old) <= 2 else "info",
                            "Alerta: prioridad antigua",
                            f"En >30d, la prioridad dominante es **{top_old}** ({_fmt_int(old_pr.iloc[0])} items). "
                            "Acción: define una política: 'si P1 supera 30d, escalado obligatorio / decisión de cerrar o re-priorizar'.",
                        )
                    )

        return out[:4]

    if chart_id == "open_status_bar":
        if open_df is None or open_df.empty or "status" not in open_df.columns:
            return [
                Insight(
                    "info",
                    "Sin estados",
                    "No hay columna status o no hay abiertas con los filtros actuales.",
                )
            ]

        stc = normalize_text_col(open_df["status"], "(sin estado)")
        vc = stc.value_counts()
        top_status = vc.index[0] if not vc.empty else None

        # Bottleneck candidate: high count + high age
        ages = _age_days(open_df)
        if not ages.empty:
            tmp = pd.DataFrame({"status": stc, "age": ages})
            g = (
                tmp.groupby("status")
                .agg(count=("age", "size"), mean_age=("age", "mean"))
                .sort_values(["count", "mean_age"], ascending=[False, False])
            )
            if not g.empty:
                cand = g.index[0]
                out.append(
                    Insight(
                        "warn" if g.loc[cand, "mean_age"] >= 30 else "info",
                        "Posible cuello de botella",
                        f"**{cand}** concentra {_fmt_int(g.loc[cand, 'count'])} issues con antigüedad media {_fmt_days(g.loc[cand, 'mean_age'])}. "
                        "Acción: revisa si es un estado de espera ('blocked', 'waiting') y crea un carril explícito para dependencias.",
                    )
                )

        if top_status:
            share = float(vc.iloc[0] / vc.sum()) if vc.sum() else 0.0
            out.append(
                Insight(
                    "warn" if share >= 0.45 else "info",
                    "Carga concentrada en un estado",
                    f"El estado dominante es **{top_status}** con {_fmt_int(vc.iloc[0])} issues ({_fmt_pct(share)}). "
                    "Si un estado supera ~45%, suele ser síntoma de demasiados casos acumulados o de un paso del flujo que no escala.",
                )
            )

        # Flow health suggestion: too many states or too many empty states
        n_states = int(vc.shape[0])
        out.append(
            Insight(
                "info",
                "Higiene del flujo",
                f"Estados activos en el filtro: {_fmt_int(n_states)}. "
                "Si hay demasiados, el flujo se vuelve difuso; si hay pocos, quizá falta granularidad para diagnosticar. "
                "Buen equilibrio: 6–10 estados que representen decisiones, no micro-tareas.",
            )
        )

        accepted_cnt = int((stc == "Accepted").sum())
        rtd_cnt = int((stc == "Ready to deploy").sum())
        deployed_cnt = int((stc == "Deployed").sum())
        if accepted_cnt > 0:
            rtd_conv = float(rtd_cnt) / float(accepted_cnt)
            if rtd_conv < 0.35:
                out.append(
                    Insight(
                        "warn",
                        "Atasco de Accepted a Ready to deploy",
                        f"Hay {_fmt_int(accepted_cnt)} en **Accepted** y {_fmt_int(rtd_cnt)} en **Ready to deploy** "
                        f"(conversión {_fmt_pct(rtd_conv)}). Acción: define tiempo máximo de salida de Accepted y revisión diaria de bloqueos.",
                    )
                )
        if rtd_cnt > 0:
            dep_conv = float(deployed_cnt) / float(rtd_cnt)
            if dep_conv < 0.70:
                out.append(
                    Insight(
                        "warn",
                        "Embudo en despliegue",
                        f"Hay {_fmt_int(rtd_cnt)} en **Ready to deploy** y {_fmt_int(deployed_cnt)} en **Deployed** "
                        f"(conversión {_fmt_pct(dep_conv)}). Acción: revisar capacidad de release y ventanas de despliegue.",
                    )
                )
        return out[:4]

    # Fallback
    return [
        Insight("info", "Sin insights específicos", "No hay insights definidos para este gráfico.")
    ]


# ---------------------------------------------------------------------
# Rendering helpers (nice cards)
# ---------------------------------------------------------------------
def render_insights(insights: List[Insight], *, key_prefix: str = "ins") -> None:
    """Render insights in a polished, compact layout."""
    if not insights:
        return

    icon = {"ok": "✅", "info": "💡", "warn": "⚠️"}

    st.markdown('<div class="bbva-insights">', unsafe_allow_html=True)
    st.markdown("#### Insights")
    for i, it in enumerate(insights):
        ic = icon.get(it.level, "💡")
        with st.expander(f"{ic} {it.title}", expanded=(i == 0)):
            st.write(it.body)
    st.markdown("</div>", unsafe_allow_html=True)
