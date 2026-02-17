"""Unified insight engine for adaptive, filter-aware executive narratives."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd

from bug_resolution_radar.ui.common import normalize_text_col, priority_rank


@dataclass(frozen=True)
class InsightMetric:
    label: str
    value: str


@dataclass(frozen=True)
class ActionInsight:
    title: str
    body: str
    score: float = 0.0
    status_filters: List[str] | None = None
    priority_filters: List[str] | None = None
    assignee_filters: List[str] | None = None


@dataclass(frozen=True)
class TrendInsightPack:
    metrics: List[InsightMetric]
    cards: List[ActionInsight]
    executive_tip: str | None = None


THEME_RULES: List[Tuple[str, List[str]]] = [
    ("Softoken", ["softoken", "token", "firma", "otp"]),
    ("Crédito", ["credito", "crédito", "cvv", "tarjeta", "tdc"]),
    ("Monetarias", ["monetarias", "saldo", "nomina", "nómina"]),
    ("Tareas", ["tareas", "task", "acciones", "dashboard"]),
    ("Pagos", ["pago", "pagos", "tpv", "cobranza"]),
    ("Transferencias", ["transferencia", "spei", "swift", "divisas"]),
    ("Login y acceso", ["login", "acceso", "face id", "biometr", "password", "tokenbnc"]),
    ("Notificaciones", ["notificacion", "notificación", "push", "mensaje"]),
]


CRITICAL_PRIORITY_FILTERS = ["Supone un impedimento", "Highest", "High"]
TRIAGE_STATUS_FILTERS = ["New", "Analysing", "Analyzing"]
ACTIVE_STATUS_FILTERS = [
    "En progreso",
    "In Progress",
    "Analysing",
    "Analyzing",
    "Ready To Verify",
    "To Rework",
    "Test",
]


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _to_dt_naive(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(series, errors="coerce")
    try:
        if hasattr(out.dt, "tz") and out.dt.tz is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        try:
            out = out.dt.tz_localize(None)
        except Exception:
            pass
    return out


def _fmt_days(value: float | int | None, default: str = "—") -> str:
    if value is None or pd.isna(value):
        return default
    v = max(0.0, float(value))
    if v < 10:
        return f"{v:.1f} d"
    return f"{v:.0f} d"


def _fmt_pct(value: float | int | None, default: str = "—") -> str:
    if value is None or pd.isna(value):
        return default
    return f"{float(value) * 100.0:.1f}%"


def _fmt_ratio(value: float | int | None, default: str = "—") -> str:
    if value is None or pd.isna(value):
        return default
    if value == float("inf"):
        return "inf"
    return f"{float(value):.2f}"


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return float("inf") if numerator > 0 else 0.0
    return float(numerator) / float(denominator)


def _norm_text(value: object) -> str:
    txt = str(value or "").strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return txt


def classify_theme(summary: object, *, theme_rules: Sequence[Tuple[str, Sequence[str]]] | None = None) -> str:
    rules = list(theme_rules or THEME_RULES)
    text = _norm_text(summary)
    if not text:
        return "Otros"
    for theme_name, keys in rules:
        for kw in keys:
            if re.search(rf"\b{re.escape(_norm_text(kw))}\b", text):
                return str(theme_name)
    return "Otros"


def theme_counts(open_df: pd.DataFrame) -> pd.Series:
    df = _safe_df(open_df)
    if df.empty or "summary" not in df.columns:
        return pd.Series(dtype="int64")
    summaries = df["summary"].fillna("").astype(str).str.strip()
    summaries = summaries[summaries != ""]
    if summaries.empty:
        return pd.Series(dtype="int64")
    return summaries.map(classify_theme).value_counts()


def top_non_other_theme(open_df: pd.DataFrame) -> Tuple[str, int]:
    vc = theme_counts(open_df)
    if vc.empty:
        return "-", 0
    non_other = vc[vc.index.astype(str) != "Otros"]
    if non_other.empty:
        return "—", 0
    return str(non_other.index[0]), int(non_other.iloc[0])


def _daily_flow(dff: pd.DataFrame, *, lookback_days: int = 90) -> pd.DataFrame:
    if dff.empty:
        return pd.DataFrame(columns=["date", "created", "closed", "net", "backlog_proxy"])
    created = _to_dt_naive(dff["created"]) if "created" in dff.columns else pd.Series(pd.NaT, index=dff.index)
    closed = _to_dt_naive(dff["resolved"]) if "resolved" in dff.columns else pd.Series(pd.NaT, index=dff.index)

    valid_created = created.dropna()
    valid_closed = closed.dropna()
    if valid_created.empty and valid_closed.empty:
        return pd.DataFrame(columns=["date", "created", "closed", "net", "backlog_proxy"])

    end_candidates: List[pd.Timestamp] = []
    if not valid_created.empty:
        end_candidates.append(pd.Timestamp(valid_created.max()).normalize())
    if not valid_closed.empty:
        end_candidates.append(pd.Timestamp(valid_closed.max()).normalize())
    end_ts = max(end_candidates) if end_candidates else pd.Timestamp.utcnow().normalize()
    start_ts = end_ts - pd.Timedelta(days=max(lookback_days - 1, 1))

    created_daily = (
        valid_created[valid_created >= start_ts].dt.floor("D").value_counts(sort=False)
        if not valid_created.empty
        else pd.Series(dtype="int64")
    )
    closed_daily = (
        valid_closed[valid_closed >= start_ts].dt.floor("D").value_counts(sort=False)
        if not valid_closed.empty
        else pd.Series(dtype="int64")
    )

    days = pd.date_range(start=start_ts, end=end_ts, freq="D")
    daily = pd.DataFrame({"date": days})
    daily["created"] = [int(created_daily.get(d, 0)) for d in days]
    daily["closed"] = [int(closed_daily.get(d, 0)) for d in days]
    daily["net"] = daily["created"] - daily["closed"]
    daily["backlog_proxy"] = daily["net"].cumsum().clip(lower=0)
    return daily


def _age_days(open_df: pd.DataFrame) -> pd.Series:
    if open_df.empty or "created" not in open_df.columns:
        return pd.Series([], dtype=float)
    created = _to_dt_naive(open_df["created"])
    valid = created.notna()
    if not valid.any():
        return pd.Series([], dtype=float)
    now = pd.Timestamp.utcnow().tz_localize(None)
    ages = (now - created[valid]).dt.total_seconds() / 86400.0
    return ages.clip(lower=0.0)


def _age_days_aligned(df: pd.DataFrame) -> pd.Series:
    out = pd.Series(np.nan, index=df.index, dtype=float)
    if df.empty or "created" not in df.columns:
        return out
    created = _to_dt_naive(df["created"])
    valid = created.notna()
    if not valid.any():
        return out
    now = pd.Timestamp.utcnow().tz_localize(None)
    out.loc[valid] = ((now - created.loc[valid]).dt.total_seconds() / 86400.0).clip(lower=0.0)
    return out


def _stale_days_from_updated(df: pd.DataFrame) -> pd.Series:
    out = pd.Series(np.nan, index=df.index, dtype=float)
    if df.empty or "updated" not in df.columns:
        return out
    updated = _to_dt_naive(df["updated"])
    valid = updated.notna()
    if not valid.any():
        return out
    now = pd.Timestamp.utcnow().tz_localize(None)
    out.loc[valid] = ((now - updated.loc[valid]).dt.total_seconds() / 86400.0).clip(lower=0.0)
    return out


def _resolution_days(dff: pd.DataFrame) -> Tuple[pd.Series, pd.DataFrame]:
    if dff.empty or "created" not in dff.columns or "resolved" not in dff.columns:
        return pd.Series([], dtype=float), pd.DataFrame()
    created = _to_dt_naive(dff["created"])
    resolved = _to_dt_naive(dff["resolved"])
    closed = dff.copy(deep=False)
    closed["__created"] = created
    closed["__resolved"] = resolved
    closed = closed[closed["__created"].notna() & closed["__resolved"].notna()].copy(deep=False)
    if closed.empty:
        return pd.Series([], dtype=float), closed
    closed["resolution_days"] = (
        (closed["__resolved"] - closed["__created"]).dt.total_seconds() / 86400.0
    ).clip(lower=0.0)
    return closed["resolution_days"].astype(float), closed


def _sorted_cards(cards: Iterable[ActionInsight], *, limit: int = 5) -> List[ActionInsight]:
    valid = [c for c in cards if str(c.title or "").strip() and str(c.body or "").strip()]
    return sorted(valid, key=lambda c: float(c.score), reverse=True)[:limit]


def build_trend_insight_pack(chart_id: str, *, dff: pd.DataFrame, open_df: pd.DataFrame) -> TrendInsightPack:
    cid = str(chart_id or "").strip()
    safe_dff = _safe_df(dff)
    safe_open = _safe_df(open_df)

    if cid == "timeseries":
        return _timeseries_pack(safe_dff, safe_open)
    if cid == "age_buckets":
        return _age_pack(safe_open)
    if cid == "resolution_hist":
        return _resolution_pack(safe_dff)
    if cid == "open_priority_pie":
        return _priority_pack(safe_open)
    if cid == "open_status_bar":
        return _status_pack(safe_open)
    return TrendInsightPack(
        metrics=[],
        cards=[ActionInsight(title="Sin insights", body="No hay reglas de insight para este grafico.")],
        executive_tip=None,
    )


def _timeseries_pack(dff: pd.DataFrame, open_df: pd.DataFrame) -> TrendInsightPack:
    daily = _daily_flow(dff, lookback_days=90)
    if daily.empty:
        return TrendInsightPack(
            metrics=[
                InsightMetric("Creacion (ult. 14d)", "—"),
                InsightMetric("Cierre (ult. 14d)", "—"),
                InsightMetric("Ratio cierre/entrada", "—"),
            ],
            cards=[
                ActionInsight(
                    title="Datos insuficientes",
                    body=(
                        "No hay fechas de creacion/cierre suficientes con el filtro actual para evaluar el flujo."
                    ),
                    score=1.0,
                )
            ],
            executive_tip=None,
        )

    created_14 = int(daily["created"].tail(14).sum())
    closed_14 = int(daily["closed"].tail(14).sum())
    ratio_close_entry = _ratio(closed_14, created_14)
    net_14 = int(created_14 - closed_14)
    weekly_net = float(daily["net"].tail(28).mean()) * 7.0 if len(daily) >= 7 else float(daily["net"].mean()) * 7.0
    open_now = int(len(open_df))
    created_tail = daily["created"].tail(30)
    closed_tail = daily["closed"].tail(30)
    created_cv = (
        float(created_tail.std(ddof=0)) / float(created_tail.mean())
        if float(created_tail.mean()) > 0
        else 0.0
    )
    closed_cv = (
        float(closed_tail.std(ddof=0)) / float(closed_tail.mean())
        if float(closed_tail.mean()) > 0
        else 0.0
    )

    closed_30 = float(daily["closed"].tail(30).sum())
    run_rate = (closed_30 / 30.0) if closed_30 > 0 else 0.0
    runway_days = (open_now / run_rate) if run_rate > 0 else float("inf")

    backlog = daily["backlog_proxy"]
    last14 = backlog.tail(14)
    prev14 = backlog.tail(28).head(14) if len(backlog) >= 28 else pd.Series(dtype=float)
    slope_last = float(last14.iloc[-1] - last14.iloc[0]) if len(last14) >= 2 else 0.0
    slope_prev = float(prev14.iloc[-1] - prev14.iloc[0]) if len(prev14) >= 2 else 0.0

    cards: List[ActionInsight] = []
    if net_14 > 0:
        cards.append(
            ActionInsight(
                title="Entrada por encima de salida",
                body=(
                    f"En 14 dias entraron {created_14} y cerraron {closed_14} (saldo +{net_14}). "
                    "Sin correccion de capacidad o de calidad de entrada, la cartera seguira creciendo."
                ),
                score=20.0 + float(net_14),
            )
        )
    elif net_14 < 0:
        cards.append(
            ActionInsight(
                title="Ventana real de reduccion",
                body=(
                    f"En 14 dias cerrasteis {closed_14} frente a {created_14} entradas "
                    f"(saldo -{abs(net_14)}). Es momento de cerrar cola envejecida."
                ),
                score=10.0 + float(abs(net_14)),
            )
        )
    else:
        cards.append(
            ActionInsight(
                title="Flujo equilibrado",
                body=(
                    "La entrada y la salida estan equilibradas en los ultimos 14 dias. "
                    "El siguiente salto vendra de eliminar cuellos de botella concretos."
                ),
                score=6.0,
            )
        )

    if run_rate > 0:
        cards.append(
            ActionInsight(
                title="Run-rate de vaciado",
                body=(
                    f"Con un ritmo de cierre de {run_rate:.2f} issues/dia, el backlog abierto actual "
                    f"({open_now}) requeriria ~{_fmt_days(runway_days)} si no entra demanda nueva."
                ),
                score=14.0 if runway_days > 120 else 7.0,
            )
        )
    else:
        cards.append(
            ActionInsight(
                title="Sin capacidad de salida visible",
                body=(
                    "No hay cierres suficientes en 30 dias para estimar vaciado. "
                    "La prioridad ejecutiva es desbloquear el tramo final del flujo."
                ),
                score=28.0,
            )
        )

    if slope_last > 0 and slope_last > (slope_prev + 2.0):
        cards.append(
            ActionInsight(
                title="Aceleracion de backlog",
                body=(
                    f"La pendiente reciente del backlog proxy es +{slope_last:.0f} (vs {slope_prev:.0f} en el bloque previo). "
                    "Hay riesgo de saturacion operativa."
                ),
                score=16.0 + slope_last,
            )
        )
    elif slope_last < 0 and abs(slope_last) > abs(slope_prev):
        cards.append(
            ActionInsight(
                title="Mejora de tendencia",
                body=(
                    f"La pendiente reciente del backlog proxy mejora ({slope_last:.0f} vs {slope_prev:.0f}). "
                    "Conviene consolidar con foco en duplicados y bloqueadas antiguas."
                ),
                score=8.0 + abs(slope_last),
            )
        )

    if weekly_net > 2.0:
        cards.append(
            ActionInsight(
                title="Tendencia semanal neta positiva",
                body=(
                    f"El saldo medio reciente es +{weekly_net:.1f} incidencias/semana. "
                    "Si persiste, el backlog seguira aumentando."
                ),
                score=12.0 + weekly_net,
            )
        )
    elif weekly_net < -2.0:
        cards.append(
            ActionInsight(
                title="Reduccion semanal sostenida",
                body=(
                    f"El saldo medio reciente es {weekly_net:.1f} incidencias/semana. "
                    "Hay traccion suficiente para limpiar cola envejecida."
                ),
                score=7.0 + abs(weekly_net),
            )
        )

    if "priority" in open_df.columns and "status" in open_df.columns and not open_df.empty:
        crit_mask = normalize_text_col(open_df["priority"], "(sin priority)").astype(str).map(priority_rank) <= 2
        triage_mask = normalize_text_col(open_df["status"], "(sin estado)").astype(str).isin(TRIAGE_STATUS_FILTERS)
        crit_early = int((crit_mask & triage_mask).sum())
        if crit_early > 0:
            cards.append(
                ActionInsight(
                    title="Criticas sin primer diagnostico",
                    body=(
                        f"Hay {crit_early} incidencias High/Highest en estados iniciales. "
                        "Resolver esta bolsa reduce riesgo cliente de forma inmediata."
                    ),
                    priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                    status_filters=list(TRIAGE_STATUS_FILTERS),
                    score=18.0 + float(crit_early),
                )
            )

    if created_cv >= 1.05 and created_14 >= 8:
        cards.append(
            ActionInsight(
                title="Entrada inestable",
                body=(
                    f"La variabilidad de entrada (CV={created_cv:.2f}) es alta en 30 dias. "
                    "Conviene reforzar prevencion en semanas de release para evitar picos de backlog."
                ),
                score=11.0 + (created_cv * 6.0),
            )
        )

    if closed_cv >= 1.00 and closed_14 > 0:
        cards.append(
            ActionInsight(
                title="Cierre irregular",
                body=(
                    f"El cierre muestra alta oscilacion (CV={closed_cv:.2f}). "
                    "Estandarizar la capacidad de salida mejora la predictibilidad operativa."
                ),
                score=9.0 + (closed_cv * 5.0),
            )
        )

    if "summary" in open_df.columns and open_now > 0:
        summaries = open_df["summary"].fillna("").astype(str).str.strip()
        summaries = summaries[summaries != ""]
        if not summaries.empty:
            dup_vc = summaries.value_counts()
            dup_groups = int((dup_vc > 1).sum())
            dup_issues = int(dup_vc[dup_vc > 1].sum())
            dup_share = (dup_issues / open_now) if open_now else 0.0
            if dup_share >= 0.12:
                cards.append(
                    ActionInsight(
                        title="Reincidencia funcional",
                        body=(
                            f"{dup_issues} incidencias abiertas pertenecen a {dup_groups} grupos repetidos "
                            f"({_fmt_pct(dup_share)} del backlog). Atacar esta bolsa acelera cierres netos."
                        ),
                        score=12.0 + (dup_share * 100.0),
                    )
                )

    if "assignee" in open_df.columns and open_now >= 6:
        assignee = normalize_text_col(open_df["assignee"], "(sin asignar)")
        own_vc = assignee.value_counts()
        if not own_vc.empty:
            top_owner = str(own_vc.index[0])
            top_owner_share = float(own_vc.iloc[0]) / float(max(int(own_vc.sum()), 1))
            if top_owner_share >= 0.35:
                cards.append(
                    ActionInsight(
                        title="Concentracion de ownership",
                        body=(
                            f"{top_owner} concentra {_fmt_pct(top_owner_share)} del backlog abierto. "
                            "Repartir carga reduce riesgo de cuello por persona."
                        ),
                        assignee_filters=[top_owner],
                        score=10.0 + (top_owner_share * 100.0),
                    )
                )

    tip: str | None
    if ratio_close_entry < 1.0:
        tip = (
            "Palanca ejecutiva: alinear compromiso semanal de cierres con entrada real para evitar crecimiento estructural."
        )
    elif ratio_close_entry > 1.1:
        tip = (
            "Momento favorable: usar el superavit de cierre para recortar deuda de mas de 30 dias."
        )
    else:
        tip = (
            "Flujo estable: priorizar precision en triage y reducir reincidencias para sostener el equilibrio."
        )

    return TrendInsightPack(
        metrics=[
            InsightMetric("Creacion (ult. 14d)", f"{created_14}"),
            InsightMetric("Cierre (ult. 14d)", f"{closed_14}"),
            InsightMetric("Ratio cierre/entrada", _fmt_ratio(ratio_close_entry)),
        ],
        cards=_sorted_cards(cards),
        executive_tip=tip,
    )


def _age_pack(open_df: pd.DataFrame) -> TrendInsightPack:
    ages = _age_days(open_df)
    if ages.empty:
        return TrendInsightPack(
            metrics=[
                InsightMetric("Antiguedad tipica", "—"),
                InsightMetric("Casos mas atascados", "—"),
                InsightMetric(">30 dias", "—"),
            ],
            cards=[
                ActionInsight(
                    title="Datos insuficientes",
                    body="No hay fechas de creacion validas para medir envejecimiento con este filtro.",
                    score=1.0,
                )
            ],
            executive_tip=None,
        )

    p50 = float(np.nanpercentile(ages, 50))
    p90 = float(np.nanpercentile(ages, 90))
    over30 = float((ages > 30).mean())
    over60 = float((ages > 60).mean())
    total = int(len(ages))

    cards: List[ActionInsight] = []
    cards.append(
        ActionInsight(
            title="Coste de cola larga",
            body=(
                f"La mediana operativa es {_fmt_days(p50)} pero el 10% mas lento llega a {_fmt_days(p90)}. "
                "Ese tramo final es donde mas se degrada la experiencia de cliente."
            ),
            score=8.0 + (p90 / 8.0),
        )
    )

    if over30 >= 0.25:
        cards.append(
            ActionInsight(
                title="Backlog envejecido",
                body=(
                    f"{_fmt_pct(over30)} de abiertas superan 30 dias ({int(round(over30 * total))} casos). "
                    "Se recomienda clinica semanal para cerrar, dividir o cancelar casos sin traccion."
                ),
                score=20.0 + float(over30 * 100.0),
            )
        )
    if over60 >= 0.12:
        cards.append(
            ActionInsight(
                title="Deuda cronica",
                body=(
                    f"El {_fmt_pct(over60)} del backlog supera 60 dias. "
                    "A partir de este umbral, el coste de contexto suele multiplicarse."
                ),
                score=16.0 + float(over60 * 100.0),
            )
        )

    if "priority" in open_df.columns:
        pr = normalize_text_col(open_df["priority"], "(sin priority)")
        older_mask = ages > 30
        if older_mask.any():
            pr_old = pr.loc[older_mask.index[older_mask]].value_counts()
            if not pr_old.empty:
                top = str(pr_old.index[0])
                cards.append(
                    ActionInsight(
                        title="Prioridad dominante en cola antigua",
                        body=(
                            f"En >30 dias domina {top} ({int(pr_old.iloc[0])} casos). "
                            "Conviene atacar en lotes por prioridad para recuperar velocidad."
                        ),
                        priority_filters=[top],
                        score=10.0 + float(pr_old.iloc[0]),
                    )
                )

        critical_old_mask = pr.map(priority_rank) <= 2
        crit_old_count = int((critical_old_mask & (ages.reindex(pr.index, fill_value=np.nan) > 14)).sum())
        if crit_old_count > 0:
            cards.append(
                ActionInsight(
                    title="Criticas envejecidas",
                    body=(
                        f"{crit_old_count} incidencias High/Highest llevan mas de 14 dias abiertas. "
                        "Escalado selectivo y cierre de bloqueos deberia ser la accion del dia."
                    ),
                    priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                    score=22.0 + float(crit_old_count),
                )
            )

        if "status" in open_df.columns:
            stx = normalize_text_col(open_df["status"], "(sin estado)").astype(str)
            early_old = int(
                (
                    (pr.map(priority_rank) <= 2)
                    & stx.isin(TRIAGE_STATUS_FILTERS)
                    & (ages.reindex(pr.index, fill_value=np.nan) > 7)
                ).sum()
            )
            if early_old > 0:
                cards.append(
                    ActionInsight(
                        title="Criticas bloqueadas en entrada",
                        body=(
                            f"{early_old} High/Highest llevan mas de 7 dias en estados iniciales. "
                            "Alinear diagnostico y decision ejecutiva evitara envejecimiento adicional."
                        ),
                        priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                        status_filters=list(TRIAGE_STATUS_FILTERS),
                        score=18.0 + float(early_old),
                    )
                )

    if "assignee" in open_df.columns and len(open_df) >= 5:
        assignee = normalize_text_col(open_df["assignee"], "(sin asignar)")
        old_assignee = assignee.loc[ages.index[ages > 30]]
        vc = old_assignee.value_counts()
        if not vc.empty:
            top_assignee = str(vc.index[0])
            share = float(vc.iloc[0]) / float(max(int(vc.sum()), 1))
            if share >= 0.35:
                cards.append(
                    ActionInsight(
                        title="Concentracion de casos antiguos",
                        body=(
                            f"{top_assignee} concentra {_fmt_pct(share)} de la cola >30d. "
                            "Redistribuir ownership ayuda a acelerar resolucion."
                        ),
                        assignee_filters=[top_assignee],
                        score=12.0 + float(share * 100.0),
                    )
                )

    stale_days = _stale_days_from_updated(open_df)
    if stale_days.notna().any():
        stale_14 = float((stale_days > 14).mean())
        stale_21 = float((stale_days > 21).mean())
        if stale_14 >= 0.20:
            cards.append(
                ActionInsight(
                    title="Backlog sin movimiento reciente",
                    body=(
                        f"{_fmt_pct(stale_14)} no se actualiza en >14 dias "
                        f"(y {_fmt_pct(stale_21)} en >21 dias)."
                    ),
                    score=12.0 + (stale_14 * 100.0),
                )
            )

    return TrendInsightPack(
        metrics=[
            InsightMetric("Antiguedad tipica", _fmt_days(p50)),
            InsightMetric("Casos mas atascados", _fmt_days(p90)),
            InsightMetric(">30 dias", _fmt_pct(over30)),
        ],
        cards=_sorted_cards(cards),
        executive_tip=(
            "Regla de control: cada semana debe bajar el numero absoluto de casos >30 dias."
        ),
    )


def _resolution_pack(dff: pd.DataFrame) -> TrendInsightPack:
    days, closed = _resolution_days(dff)
    if days.empty:
        return TrendInsightPack(
            metrics=[
                InsightMetric("Resolucion habitual", "—"),
                InsightMetric("Resolucion lenta", "—"),
                InsightMetric("Casos muy lentos", "—"),
            ],
            cards=[
                ActionInsight(
                    title="Datos insuficientes",
                    body=(
                        "No hay incidencias cerradas con fechas completas para medir tiempos de resolucion."
                    ),
                    score=1.0,
                )
            ],
            executive_tip=None,
        )

    med = float(days.median())
    p90 = float(days.quantile(0.90))
    p95 = float(days.quantile(0.95))
    tail_share = float((days >= p90).mean()) if len(days) > 0 else 0.0

    cards: List[ActionInsight] = []
    cards.append(
        ActionInsight(
            title="Impacto real en experiencia",
            body=(
                f"La mediana de cierre es {_fmt_days(med)} pero el tramo lento sube a {_fmt_days(p90)}. "
                "Atacar ese percentil alto suele tener mas retorno que cerrar casos faciles."
            ),
            score=8.0 + (p90 / 10.0),
        )
    )

    if p95 > (med * 2.8):
        cards.append(
            ActionInsight(
                title="Cola extrema de resolucion",
                body=(
                    f"El percentil 95 ({_fmt_days(p95)}) multiplica por {p95 / max(med, 1.0):.1f} la mediana. "
                    "Hay friccion estructural en un subconjunto de casos."
                ),
                score=16.0 + (p95 / max(med, 1.0)),
            )
        )

    if "priority" in closed.columns and not closed.empty:
        pr = normalize_text_col(closed["priority"], "(sin priority)")
        grouped = closed.assign(priority=pr).groupby("priority")["resolution_days"].median().sort_values(ascending=False)
        if len(grouped) >= 2:
            slowest = str(grouped.index[0])
            fastest = str(grouped.index[-1])
            cards.append(
                ActionInsight(
                    title="Brecha por prioridad",
                    body=(
                        f"Prioridad mas lenta: {slowest} ({_fmt_days(grouped.iloc[0])}) "
                        f"vs mas rapida: {fastest} ({_fmt_days(grouped.iloc[-1])}). "
                        "La dispersion indica oportunidades de estandarizar flujo."
                    ),
                    priority_filters=[slowest],
                    score=10.0 + float(grouped.iloc[0]),
                )
            )

    if "__resolved" in closed.columns and not closed.empty:
        now = pd.Timestamp.utcnow().tz_localize(None)
        resolved_30 = int((closed["__resolved"] >= (now - pd.Timedelta(days=30))).sum())
        if resolved_30 <= 5:
            cards.append(
                ActionInsight(
                    title="Baja traccion de cierre reciente",
                    body=(
                        f"Solo {resolved_30} cierres en 30 dias con el filtro actual. "
                        "Sin mejorar throughput, el backlog tardara en bajar de forma perceptible."
                    ),
                    score=18.0 - float(resolved_30),
                )
            )

        recent = closed[closed["__resolved"] >= (now - pd.Timedelta(days=30))]
        prev = closed[
            (closed["__resolved"] >= (now - pd.Timedelta(days=60)))
            & (closed["__resolved"] < (now - pd.Timedelta(days=30)))
        ]
        if len(recent) >= 5 and len(prev) >= 5:
            med_recent = float(recent["resolution_days"].median())
            med_prev = float(prev["resolution_days"].median())
            if med_prev > 0 and med_recent > (med_prev * 1.25):
                cards.append(
                    ActionInsight(
                        title="Degradacion reciente del ciclo",
                        body=(
                            f"La mediana de cierre sube de {_fmt_days(med_prev)} a {_fmt_days(med_recent)} "
                            "en los ultimos 30 dias."
                        ),
                        score=14.0 + ((med_recent / max(med_prev, 1.0)) * 4.0),
                    )
                )
            elif med_prev > 0 and med_recent < (med_prev * 0.80):
                cards.append(
                    ActionInsight(
                        title="Mejora reciente del ciclo",
                        body=(
                            f"La mediana de cierre baja de {_fmt_days(med_prev)} a {_fmt_days(med_recent)} "
                            "en los ultimos 30 dias."
                        ),
                        score=9.0 + ((med_prev / max(med_recent, 1.0)) * 2.0),
                    )
                )

    if "priority" in closed.columns and not closed.empty:
        pr = normalize_text_col(closed["priority"], "(sin priority)")
        hi = closed.loc[pr.map(priority_rank) <= 2, "resolution_days"]
        lo = closed.loc[pr.map(priority_rank) >= 3, "resolution_days"]
        if len(hi) >= 4 and len(lo) >= 4:
            med_hi = float(hi.median())
            med_lo = float(lo.median())
            if med_hi > (med_lo * 1.30):
                cards.append(
                    ActionInsight(
                        title="Criticas cierran mas lento que el resto",
                        body=(
                            f"High/Highest cierran en {_fmt_days(med_hi)} de mediana vs {_fmt_days(med_lo)} en prioridades menores."
                        ),
                        priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                        score=15.0 + (med_hi - med_lo),
                    )
                )

    return TrendInsightPack(
        metrics=[
            InsightMetric("Resolucion habitual", _fmt_days(med)),
            InsightMetric("Resolucion lenta", _fmt_days(p90)),
            InsightMetric("Casos muy lentos", _fmt_days(p95)),
        ],
        cards=_sorted_cards(cards),
        executive_tip=(
            f"El {tail_share * 100.0:.1f}% de cierres vive en el tramo lento: objetivo directo de mejora."
        ),
    )


def _priority_pack(open_df: pd.DataFrame) -> TrendInsightPack:
    if open_df.empty or "priority" not in open_df.columns:
        return TrendInsightPack(
            metrics=[
                InsightMetric("Total abiertas", "0"),
                InsightMetric("Prioridad dominante", "—"),
                InsightMetric("Riesgo ponderado", "—"),
            ],
            cards=[
                ActionInsight(
                    title="Datos insuficientes",
                    body="No hay prioridades en las incidencias abiertas para este filtro.",
                    score=1.0,
                )
            ],
            executive_tip=None,
        )

    df = open_df.copy(deep=False)
    df["priority"] = normalize_text_col(df["priority"], "(sin priority)")
    counts = df["priority"].value_counts()
    total = int(len(df))
    dominant = str(counts.index[0]) if not counts.empty else "—"
    dominant_count = int(counts.iloc[0]) if not counts.empty else 0
    dominant_share = (dominant_count / total) if total else 0.0

    df["_prio_rank"] = df["priority"].map(priority_rank).fillna(99).astype(int)
    df["_weight"] = (6 - df["_prio_rank"]).clip(lower=1, upper=6)
    risk_score = int(df["_weight"].sum())
    high_share = float((df["_prio_rank"] <= 2).mean()) if total else 0.0
    missing_share = float((df["priority"] == "(sin priority)").mean()) if total else 0.0

    cards: List[ActionInsight] = []
    if dominant != "—":
        cards.append(
            ActionInsight(
                title="Concentracion de prioridad",
                body=(
                    f"{dominant} concentra {_fmt_pct(dominant_share)} del backlog abierto "
                    f"({dominant_count} de {total})."
                ),
                priority_filters=[dominant],
                score=8.0 + (dominant_share * 100.0),
            )
        )

    cards.append(
        ActionInsight(
            title="Riesgo ponderado",
            body=(
                f"Score ponderado = {risk_score}. "
                "Permite priorizar capacidad segun impacto y no solo por volumen bruto."
            ),
            score=float(risk_score) / float(max(total, 1)),
        )
    )

    if high_share >= 0.35:
        cards.append(
            ActionInsight(
                title="Inflacion de prioridades altas",
                body=(
                    f"Las prioridades High/Highest suponen {_fmt_pct(high_share)} del backlog. "
                    "Si se mantiene, la matriz de prioridad pierde poder de decision."
                ),
                priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                score=18.0 + (high_share * 100.0),
            )
        )

    if missing_share >= 0.18:
        cards.append(
            ActionInsight(
                title="Backlog sin prioridad clara",
                body=(
                    f"{_fmt_pct(missing_share)} de abiertas no tiene prioridad definida. "
                    "Riesgo de ejecucion erratica y sobrecarga en triage."
                ),
                priority_filters=["(sin priority)"],
                score=10.0 + (missing_share * 100.0),
            )
        )

    if "status" in df.columns:
        stx = normalize_text_col(df["status"], "(sin estado)").astype(str)
        crit_early = int(((df["_prio_rank"] <= 2) & stx.isin(TRIAGE_STATUS_FILTERS)).sum())
        if crit_early > 0:
            cards.append(
                ActionInsight(
                    title="Criticas sin arrancar",
                    body=(
                        f"{crit_early} incidencias High/Highest siguen en New/Analysing. "
                        "Asignar owner y primer diagnostico hoy reduce impacto cliente."
                    ),
                    priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                    status_filters=list(TRIAGE_STATUS_FILTERS),
                    score=22.0 + float(crit_early),
                )
            )

    if "assignee" in df.columns:
        assignee = normalize_text_col(df["assignee"], "(sin asignar)")
        crit_unassigned = int(((df["_prio_rank"] <= 2) & assignee.eq("(sin asignar)")).sum())
        if crit_unassigned > 0:
            cards.append(
                ActionInsight(
                    title="Criticas sin owner",
                    body=(
                        f"{crit_unassigned} High/Highest no tienen asignacion explicita. "
                        "Asignar ownership es la decision con mayor retorno inmediato."
                    ),
                    priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                    assignee_filters=["(sin asignar)"],
                    score=20.0 + float(crit_unassigned),
                )
            )

    if "created" in df.columns:
        ages = _age_days_aligned(df)
        if ages.notna().any():
            crit_old = int(((df["_prio_rank"] <= 2) & (ages > 14)).sum())
            if crit_old > 0:
                cards.append(
                    ActionInsight(
                        title="Criticas con antiguedad elevada",
                        body=(
                            f"{crit_old} High/Highest superan 14 dias de antiguedad. "
                            "Conviene forzar decision ejecutiva de desbloqueo o cierre."
                        ),
                        priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                        score=20.0 + float(crit_old),
                    )
                )

    stale_days = _stale_days_from_updated(df)
    if stale_days.notna().any():
        crit_stale = int(((df["_prio_rank"] <= 2) & (stale_days > 7)).sum())
        if crit_stale > 0:
            cards.append(
                ActionInsight(
                    title="Criticas sin movimiento reciente",
                    body=(
                        f"{crit_stale} High/Highest no tienen actualizacion en mas de 7 dias."
                    ),
                    priority_filters=list(CRITICAL_PRIORITY_FILTERS),
                    score=14.0 + float(crit_stale),
                )
            )

    return TrendInsightPack(
        metrics=[
            InsightMetric("Total abiertas", f"{total}"),
            InsightMetric("Prioridad dominante", dominant),
            InsightMetric("Riesgo ponderado", f"{risk_score}"),
        ],
        cards=_sorted_cards(cards),
        executive_tip=(
            "La prioridad debe ordenar decisiones, no absorber toda la demanda como urgente."
        ),
    )


def _status_pack(open_df: pd.DataFrame) -> TrendInsightPack:
    if open_df.empty or "status" not in open_df.columns:
        return TrendInsightPack(
            metrics=[
                InsightMetric("Total abiertas", "0"),
                InsightMetric("Estado dominante", "—"),
                InsightMetric("Concentracion top", "—"),
            ],
            cards=[
                ActionInsight(
                    title="Datos insuficientes",
                    body="No hay estados disponibles para evaluar flujo operativo.",
                    score=1.0,
                )
            ],
            executive_tip=None,
        )

    df = open_df.copy(deep=False)
    df["status"] = normalize_text_col(df["status"], "(sin estado)")
    counts = df["status"].value_counts()
    total = int(len(df))
    top_status = str(counts.index[0]) if not counts.empty else "—"
    top_count = int(counts.iloc[0]) if not counts.empty else 0
    top_share = (top_count / total) if total else 0.0

    cards: List[ActionInsight] = []
    if top_status != "—":
        cards.append(
            ActionInsight(
                title="Cuello de botella probable",
                body=(
                    f"{_fmt_pct(top_share)} del backlog esta en {top_status} "
                    f"({top_count} de {total})."
                ),
                status_filters=[top_status],
                score=12.0 + (top_share * 100.0),
            )
        )

    active_mask = df["status"].astype(str).isin(ACTIVE_STATUS_FILTERS)
    active_share = float(active_mask.mean()) if total else 0.0
    cards.append(
        ActionInsight(
            title="Carga activa del equipo",
            body=(
                f"{_fmt_pct(active_share)} del backlog esta en estados activos. "
                "Por encima de 60% suele subir el cambio de contexto."
            ),
            status_filters=[s for s in ACTIVE_STATUS_FILTERS if s in df["status"].astype(str).unique().tolist()],
            score=8.0 + (active_share * 100.0),
        )
    )

    triage_mask = df["status"].astype(str).isin(TRIAGE_STATUS_FILTERS)
    triage_share = float(triage_mask.mean()) if total else 0.0
    if triage_share >= 0.35:
        cards.append(
            ActionInsight(
                title="Deuda de triage",
                body=(
                    f"{_fmt_pct(triage_share)} de abiertas estan en New/Analysing. "
                    "Una rutina diaria de triage suele reducir esta bolsa rapidamente."
                ),
                status_filters=list(TRIAGE_STATUS_FILTERS),
                score=16.0 + (triage_share * 100.0),
            )
        )

    blocked_count = int(df["status"].astype(str).str.lower().str.contains("blocked|bloque", regex=True).sum())
    blocked_share = (blocked_count / total) if total else 0.0
    if blocked_count > 0:
        cards.append(
            ActionInsight(
                title="Bloqueos con impacto operativo",
                body=(
                    f"Hay {blocked_count} bloqueadas ({_fmt_pct(blocked_share)}). "
                    "Un circuito de desbloqueo de 24h suele liberar capacidad sin ampliar equipo."
                ),
                status_filters=["Blocked", "Bloqueado"],
                score=15.0 + float(blocked_count),
            )
        )

    stale_days = _stale_days_from_updated(df)
    if stale_days.notna().any() and top_status != "—":
        dom_mask = df["status"].astype(str).eq(top_status)
        dom_stale = stale_days.loc[dom_mask]
        if dom_stale.notna().any():
            dom_stale_med = float(dom_stale.median())
            if dom_stale_med >= 10.0:
                cards.append(
                    ActionInsight(
                        title="Estado dominante sin avance",
                        body=(
                            f"Las incidencias en {top_status} llevan {_fmt_days(dom_stale_med)} "
                            "sin actualizacion mediana."
                        ),
                        status_filters=[top_status],
                        score=11.0 + (dom_stale_med / 2.0),
                    )
                )

    if "assignee" in df.columns and total >= 8:
        assignee = normalize_text_col(df["assignee"], "(sin asignar)")
        active_df = df.loc[active_mask].copy(deep=False)
        if not active_df.empty:
            active_assignee = assignee.loc[active_df.index]
            vc = active_assignee.value_counts()
            if not vc.empty:
                top_owner = str(vc.index[0])
                top_owner_share = float(vc.iloc[0]) / float(max(int(vc.sum()), 1))
                if top_owner_share >= 0.40 and int(vc.iloc[0]) >= 4:
                    cards.append(
                        ActionInsight(
                            title="Sobrecarga de trabajo activo",
                            body=(
                                f"{top_owner} concentra {_fmt_pct(top_owner_share)} de las incidencias en curso."
                            ),
                            assignee_filters=[top_owner],
                            score=10.0 + (top_owner_share * 100.0),
                        )
                    )

    accepted = int((df["status"].astype(str) == "Accepted").sum())
    ready = int((df["status"].astype(str) == "Ready to deploy").sum())
    deployed = int((df["status"].astype(str) == "Deployed").sum())
    if accepted > 0:
        conv = (ready / accepted) if accepted else 0.0
        if conv < 0.35:
            cards.append(
                ActionInsight(
                    title="Friccion Accepted -> Ready",
                    body=(
                        f"Accepted={accepted} y Ready to deploy={ready} "
                        f"(conversion {_fmt_pct(conv)})."
                    ),
                    status_filters=["Accepted", "Ready to deploy"],
                    score=13.0 + float(accepted - ready),
                )
            )
    if ready > 0:
        conv_release = (deployed / ready) if ready else 0.0
        if conv_release < 0.70:
            cards.append(
                ActionInsight(
                    title="Embudo de release",
                    body=(
                        f"Ready to deploy={ready} y Deployed={deployed} "
                        f"(conversion {_fmt_pct(conv_release)})."
                    ),
                    status_filters=["Ready to deploy", "Deployed"],
                    score=12.0 + float(ready - deployed),
                )
            )

    tip = "Control de flujo recomendado: medir SLA por estado y revisar desvio diariamente."
    if top_share > 0.45:
        tip = (
            f"Prioridad de gestion: descargar {top_status} hasta bajar por debajo de 35% del backlog."
        )

    return TrendInsightPack(
        metrics=[
            InsightMetric("Total abiertas", f"{total}"),
            InsightMetric("Estado dominante", top_status),
            InsightMetric("Concentracion top", _fmt_pct(top_share)),
        ],
        cards=_sorted_cards(cards),
        executive_tip=tip,
    )


def build_people_plan_recommendations(
    *,
    assignee: str,
    open_count: int,
    flow_risk_pct: float,
    critical_risk_pct: float,
    blocked_count: int,
    in_progress_count: int,
    exit_count: int,
    aging_p90_days: float | None = None,
) -> List[str]:
    recs: List[str] = []

    if blocked_count > 0:
        recs.append(
            f"Desbloquear primero: {blocked_count} incidencias bloqueadas en cartera de {assignee}."
        )
    if critical_risk_pct >= 55.0:
        recs.append(
            "Criticidad atrapada en entrada/bloqueado: fijar owners y fecha compromiso en las de mayor impacto."
        )
    if flow_risk_pct >= 60.0:
        recs.append(
            "Entrada saturada: recortar WIP nuevo y ejecutar triage duro de duplicados o fuera de alcance."
        )
    if in_progress_count > 0 and exit_count == 0:
        recs.append(
            "Sin empuje a salida: acordar objetivo semanal explicito de paso a Verify/Deploy."
        )
    if aging_p90_days is not None and aging_p90_days >= 30.0:
        recs.append(
            f"Cola lenta elevada (p90={aging_p90_days:.0f}d): abrir mini plan de limpieza quincenal."
        )
    if open_count >= 12 and not recs:
        recs.append(
            "Volumen relevante pero estable: mantener limite de WIP y revision semanal de aging."
        )
    if not recs:
        recs.append("Riesgo controlado: sostener disciplina de flujo y evitar acumulacion en entrada.")

    return recs[:4]


def build_ops_health_brief(*, dff: pd.DataFrame, open_df: pd.DataFrame) -> List[str]:
    safe_dff = _safe_df(dff)
    safe_open = _safe_df(open_df)
    if safe_open.empty:
        return ["No hay backlog abierto con los filtros activos."]

    open_total = int(len(safe_open))
    aged_30 = int((_age_days(safe_open) > 30).sum()) if "created" in safe_open.columns else 0
    aged_30_pct = (aged_30 / open_total) if open_total else 0.0
    blocked = 0
    if "status" in safe_open.columns:
        status_norm = normalize_text_col(safe_open["status"], "(sin estado)").astype(str).str.lower()
        blocked = int(status_norm.str.contains("blocked|bloque", regex=True).sum())
    blocked_pct = (blocked / open_total) if open_total else 0.0

    lines: List[str] = []
    lines.append(
        f"Backlog abierto: {open_total} incidencias; cola >30d: {_fmt_pct(aged_30_pct)} ({aged_30})."
    )
    if blocked > 0:
        lines.append(
            f"Bloqueadas activas: {blocked} ({_fmt_pct(blocked_pct)}). Requiere circuito de desbloqueo diario."
        )

    if "priority" in safe_open.columns:
        pr = normalize_text_col(safe_open["priority"], "(sin priority)")
        critical_share = float((pr.map(priority_rank) <= 2).mean()) if open_total else 0.0
        if critical_share >= 0.30:
            lines.append(
                f"Criticidad elevada: {_fmt_pct(critical_share)} del backlog abierto esta en High/Highest."
            )

    if "updated" in safe_open.columns:
        stale_days = _stale_days_from_updated(safe_open)
        if stale_days.notna().any():
            stale14 = float((stale_days > 14).mean())
            if stale14 >= 0.20:
                lines.append(
                    f"Estancamiento: {_fmt_pct(stale14)} de abiertas sin actualizacion en >14 dias."
                )

    if not safe_dff.empty and "created" in safe_dff.columns:
        created = _to_dt_naive(safe_dff["created"])
        resolved = _to_dt_naive(safe_dff["resolved"]) if "resolved" in safe_dff.columns else pd.Series(pd.NaT, index=safe_dff.index)
        now = pd.Timestamp.utcnow().tz_localize(None)
        from_14 = now - pd.Timedelta(days=14)
        created_14 = int((created >= from_14).sum())
        resolved_14 = int((resolved >= from_14).sum())
        if created_14 > 0 or resolved_14 > 0:
            delta = created_14 - resolved_14
            if delta > 0:
                lines.append(
                    f"Presion de flujo 14d: +{delta} netas (entradas {created_14} vs cierres {resolved_14})."
                )
            else:
                lines.append(
                    f"Flujo 14d favorable: {resolved_14 - created_14} netas reducidas (cierres {resolved_14})."
                )

    return lines[:3]


def build_duplicates_brief(
    *,
    total_open: int,
    duplicate_groups: int,
    duplicate_issues: int,
    heuristic_clusters: int,
) -> str:
    if total_open <= 0:
        return "Sin backlog abierto para evaluar duplicados."
    if duplicate_issues <= 0 and heuristic_clusters <= 0:
        return "No hay señal fuerte de duplicidad con los filtros actuales."

    dup_share = (duplicate_issues / total_open) if total_open else 0.0
    if dup_share >= 0.18:
        return (
            f"Presion por duplicidad: {duplicate_issues} issues en {duplicate_groups} grupos "
            f"({_fmt_pct(dup_share)} del backlog abierto)."
        )
    return (
        f"Duplicidad controlable: {duplicate_issues} issues en {duplicate_groups} grupos exactos "
        f"y {heuristic_clusters} clusters heuristicos."
    )


def build_topic_brief(*, topic: str, sub_df: pd.DataFrame, total_open: int) -> str:
    sub = _safe_df(sub_df)
    if sub.empty:
        return f"{topic}: sin incidencias activas con el filtro actual."

    count = int(len(sub))
    share = (count / total_open) if total_open else 0.0
    status_txt = "sin datos de estado"
    if "status" in sub.columns:
        stx = normalize_text_col(sub["status"], "(sin estado)").astype(str)
        top_status = stx.value_counts().head(1)
        if not top_status.empty:
            status_txt = f"estado dominante {top_status.index[0]} ({int(top_status.iloc[0])})"

    age_txt = ""
    if "created" in sub.columns:
        ages = _age_days(sub)
        if not ages.empty:
            old_share = float((ages > 30).mean())
            age_txt = f"; cola >30d {_fmt_pct(old_share)}"

    return f"{topic}: {_fmt_pct(share)} del backlog abierto, {status_txt}{age_txt}."
