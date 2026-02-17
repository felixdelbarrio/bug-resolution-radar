"""Copilot-style analytics helpers over the filtered operational backlog context."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import pandas as pd

from bug_resolution_radar.ui.common import normalize_text_col, priority_rank


@dataclass(frozen=True)
class NextBestAction:
    title: str
    body: str
    expected_impact: str
    status_filters: List[str] | None = None
    priority_filters: List[str] | None = None
    assignee_filters: List[str] | None = None


@dataclass(frozen=True)
class CopilotAnswer:
    answer: str
    confidence: float
    evidence: List[str]
    followups: List[str]


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


def _fmt_pct(x: float) -> str:
    return f"{x * 100.0:.1f}%"


def _fmt_days(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "—"
    v = max(0.0, float(x))
    if v < 10:
        return f"{v:.1f} d"
    return f"{v:.0f} d"


def _norm(txt: str) -> str:
    t = unicodedata.normalize("NFKD", str(txt or "").strip().lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t


def _safe_series_count(mask: pd.Series) -> int:
    try:
        return int(mask.sum())
    except Exception:
        return 0


def build_operational_snapshot(*, dff: pd.DataFrame, open_df: pd.DataFrame) -> Dict[str, Any]:
    safe_dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    safe_open = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    open_total = int(len(safe_open))

    status = (
        normalize_text_col(safe_open["status"], "(sin estado)").astype(str)
        if (not safe_open.empty and "status" in safe_open.columns)
        else pd.Series([], dtype=str)
    )
    priority = (
        normalize_text_col(safe_open["priority"], "(sin priority)").astype(str)
        if (not safe_open.empty and "priority" in safe_open.columns)
        else pd.Series([], dtype=str)
    )
    assignee = (
        normalize_text_col(safe_open["assignee"], "(sin asignar)").astype(str)
        if (not safe_open.empty and "assignee" in safe_open.columns)
        else pd.Series([], dtype=str)
    )

    created_open = _to_dt_naive(safe_open["created"]) if "created" in safe_open.columns else pd.Series([], dtype="datetime64[ns]")
    now = pd.Timestamp.utcnow().tz_localize(None)
    age_days = (
        ((now - created_open).dt.total_seconds() / 86400.0).clip(lower=0.0)
        if not created_open.empty
        else pd.Series([], dtype=float)
    )

    blocked_count = (
        _safe_series_count(status.str.lower().str.contains("blocked|bloque", regex=True))
        if not status.empty
        else 0
    )
    critical_mask = (priority.map(priority_rank) <= 2) if not priority.empty else pd.Series([], dtype=bool)
    critical_count = _safe_series_count(critical_mask) if not critical_mask.empty else 0
    unassigned_count = (
        _safe_series_count(assignee.eq("(sin asignar)")) if not assignee.empty else 0
    )
    critical_unassigned = (
        _safe_series_count(critical_mask & assignee.eq("(sin asignar)"))
        if (not critical_mask.empty and not assignee.empty)
        else 0
    )
    aged30_count = _safe_series_count(age_days > 30) if not age_days.empty else 0

    top_status = "—"
    top_status_share = 0.0
    if not status.empty:
        vc = status.value_counts()
        if not vc.empty:
            top_status = str(vc.index[0])
            top_status_share = float(vc.iloc[0]) / float(max(int(vc.sum()), 1))

    top_priority = "—"
    top_priority_share = 0.0
    if not priority.empty:
        pv = priority.value_counts()
        if not pv.empty:
            top_priority = str(pv.index[0])
            top_priority_share = float(pv.iloc[0]) / float(max(int(pv.sum()), 1))

    created_all = (
        _to_dt_naive(safe_dff["created"]) if "created" in safe_dff.columns else pd.Series([], dtype="datetime64[ns]")
    )
    resolved_all = (
        _to_dt_naive(safe_dff["resolved"]) if "resolved" in safe_dff.columns else pd.Series([], dtype="datetime64[ns]")
    )
    from_14 = now - pd.Timedelta(days=14)
    created_14 = _safe_series_count(created_all >= from_14) if not created_all.empty else 0
    resolved_14 = _safe_series_count(resolved_all >= from_14) if not resolved_all.empty else 0
    net_14 = int(created_14 - resolved_14)
    close_entry_ratio_14 = (float(resolved_14) / float(created_14)) if created_14 > 0 else (float("inf") if resolved_14 > 0 else 0.0)

    closed_subset = pd.DataFrame()
    if not safe_dff.empty and "created" in safe_dff.columns and "resolved" in safe_dff.columns:
        c = _to_dt_naive(safe_dff["created"])
        r = _to_dt_naive(safe_dff["resolved"])
        closed_subset = safe_dff.copy(deep=False)
        closed_subset["__c"] = c
        closed_subset["__r"] = r
        closed_subset = closed_subset[closed_subset["__c"].notna() & closed_subset["__r"].notna()].copy(
            deep=False
        )
        if not closed_subset.empty:
            closed_subset["__res_days"] = (
                (closed_subset["__r"] - closed_subset["__c"]).dt.total_seconds() / 86400.0
            ).clip(lower=0.0)
    median_resolution_days = (
        float(closed_subset["__res_days"].median()) if (not closed_subset.empty) else None
    )

    duplicate_groups = 0
    duplicate_issues = 0
    if not safe_open.empty and "summary" in safe_open.columns:
        summaries = safe_open["summary"].fillna("").astype(str).str.strip()
        summaries = summaries[summaries != ""]
        if not summaries.empty:
            dvc = summaries.value_counts()
            rep = dvc[dvc > 1]
            duplicate_groups = int(len(rep))
            duplicate_issues = int(rep.sum())

    updated_open = _to_dt_naive(safe_open["updated"]) if "updated" in safe_open.columns else pd.Series([], dtype="datetime64[ns]")
    stale_days = (
        ((now - updated_open).dt.total_seconds() / 86400.0).clip(lower=0.0)
        if not updated_open.empty
        else pd.Series([], dtype=float)
    )
    stale_14_count = _safe_series_count(stale_days > 14) if not stale_days.empty else 0

    return {
        "open_total": open_total,
        "blocked_count": blocked_count,
        "blocked_pct": (blocked_count / open_total) if open_total else 0.0,
        "critical_count": critical_count,
        "critical_pct": (critical_count / open_total) if open_total else 0.0,
        "unassigned_count": unassigned_count,
        "critical_unassigned_count": critical_unassigned,
        "aged30_count": aged30_count,
        "aged30_pct": (aged30_count / open_total) if open_total else 0.0,
        "top_status": top_status,
        "top_status_share": top_status_share,
        "top_priority": top_priority,
        "top_priority_share": top_priority_share,
        "created_14": int(created_14),
        "resolved_14": int(resolved_14),
        "net_14": net_14,
        "close_entry_ratio_14": close_entry_ratio_14,
        "median_resolution_days": median_resolution_days,
        "duplicate_groups": duplicate_groups,
        "duplicate_issues": duplicate_issues,
        "duplicate_share": (duplicate_issues / open_total) if open_total else 0.0,
        "stale_14_count": stale_14_count,
        "stale_14_pct": (stale_14_count / open_total) if open_total else 0.0,
    }


def build_session_delta_lines(
    current_snapshot: Dict[str, Any], baseline_snapshot: Dict[str, Any] | None
) -> List[str]:
    cur = current_snapshot if isinstance(current_snapshot, dict) else {}
    base = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}
    if not base:
        return [
            "No hay referencia previa guardada para este cliente. Esta sesion crea la primera linea base."
        ]

    candidates: List[tuple[float, str]] = []

    def add_abs(key: str, label: str, *, pct: bool = False) -> None:
        c = float(cur.get(key, 0.0) or 0.0)
        b = float(base.get(key, 0.0) or 0.0)
        d = c - b
        magnitude = abs(d) * (100.0 if pct else 1.0)
        if magnitude < (2.0 if pct else 1.0):
            return
        if pct:
            candidates.append(
                (
                    magnitude,
                    f"{label}: {_fmt_pct(b)} -> {_fmt_pct(c)} ({'+' if d > 0 else ''}{d*100.0:.1f} pp).",
                )
            )
        else:
            candidates.append(
                (
                    magnitude,
                    f"{label}: {int(b)} -> {int(c)} ({'+' if d > 0 else ''}{int(d)}).",
                )
            )

    add_abs("open_total", "Backlog abierto")
    add_abs("aged30_pct", "Cola >30 dias", pct=True)
    add_abs("blocked_count", "Bloqueadas activas")
    add_abs("critical_count", "Criticas abiertas")
    add_abs("stale_14_pct", "Sin movimiento >14 dias", pct=True)
    add_abs("net_14", "Balance neto 14d")

    if not candidates:
        return ["Sin cambios materiales frente a la ultima sesion en este cliente."]
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [txt for _, txt in candidates[:3]]


def choose_next_best_action(
    snapshot: Dict[str, Any], cards: Sequence[Any] | None = None
) -> NextBestAction:
    s = snapshot if isinstance(snapshot, dict) else {}
    crit_unassigned = int(s.get("critical_unassigned_count", 0) or 0)
    blocked = int(s.get("blocked_count", 0) or 0)
    net14 = int(s.get("net_14", 0) or 0)
    aged30_pct = float(s.get("aged30_pct", 0.0) or 0.0)
    dup_share = float(s.get("duplicate_share", 0.0) or 0.0)
    top_status = str(s.get("top_status", "—") or "—")

    if crit_unassigned > 0:
        return NextBestAction(
            title="Asignar ownership critico hoy",
            body=(
                f"Hay {crit_unassigned} incidencias High/Highest sin owner. "
                "Esta decision reduce riesgo cliente de forma inmediata."
            ),
            expected_impact=f"Impacto esperado: -{min(crit_unassigned, 8)} riesgos criticos en 24h.",
            priority_filters=["Supone un impedimento", "Highest", "High"],
            assignee_filters=["(sin asignar)"],
        )
    if blocked > 0 and float(s.get("blocked_pct", 0.0) or 0.0) >= 0.08:
        return NextBestAction(
            title="Desbloquear el cuello principal",
            body=(
                f"Hay {blocked} bloqueadas activas. "
                "Crear un circuito diario de desbloqueo libera capacidad sin ampliar equipo."
            ),
            expected_impact=f"Impacto esperado: mover 20-35% de bloqueadas a flujo activo esta semana.",
            status_filters=["Blocked", "Bloqueado"],
        )
    if net14 > 0:
        return NextBestAction(
            title="Corregir balance entrada-salida",
            body=(
                f"El balance 14d es +{net14}. "
                "Sin ajuste operativo, el backlog seguira creciendo."
            ),
            expected_impact=f"Impacto esperado: cerrar +{max(2, net14 // 3)} extra/semana para estabilizar.",
            status_filters=[top_status] if top_status != "—" else None,
        )
    if aged30_pct >= 0.25:
        return NextBestAction(
            title="Ataque quirurgico a cola envejecida",
            body=(
                f"El {_fmt_pct(aged30_pct)} del backlog supera 30 dias. "
                "Conviene una clinica semanal de cierre o descomposicion."
            ),
            expected_impact="Impacto esperado: reducir 10-15% de cola >30d en 2 semanas.",
        )
    if dup_share >= 0.10:
        return NextBestAction(
            title="Eliminar reincidencia visible",
            body=(
                f"Los duplicados suponen {_fmt_pct(dup_share)} del backlog. "
                "Consolidar grupos repetidos acelera reduccion neta."
            ),
            expected_impact="Impacto esperado: recorte directo de ruido operativo en 1 sprint.",
        )

    if cards:
        first = cards[0]
        title = str(getattr(first, "title", "") or "Sostener ritmo actual")
        body = str(getattr(first, "body", "") or "El flujo esta estable.")
        return NextBestAction(
            title=title,
            body=body,
            expected_impact="Impacto esperado: mantener tendencia y atacar deuda puntual.",
            status_filters=list(getattr(first, "status_filters", []) or []),
            priority_filters=list(getattr(first, "priority_filters", []) or []),
            assignee_filters=list(getattr(first, "assignee_filters", []) or []),
        )

    return NextBestAction(
        title="Sostener control operativo",
        body="No se detecta un desvio critico dominante en este filtro.",
        expected_impact="Impacto esperado: estabilidad si se mantiene disciplina de flujo.",
    )


def simulate_backlog_what_if(
    snapshot: Dict[str, Any],
    *,
    entry_reduction_pct: float,
    closure_boost_pct: float,
    unblock_pct: float,
) -> Dict[str, Any]:
    s = snapshot if isinstance(snapshot, dict) else {}
    open_total = float(s.get("open_total", 0.0) or 0.0)
    created_14 = float(s.get("created_14", 0.0) or 0.0)
    resolved_14 = float(s.get("resolved_14", 0.0) or 0.0)
    blocked = float(s.get("blocked_count", 0.0) or 0.0)

    in_week = created_14 / 2.0
    out_week = resolved_14 / 2.0
    sim_in = in_week * (1.0 - max(min(entry_reduction_pct, 95.0), 0.0) / 100.0)
    sim_out = out_week * (1.0 + max(min(closure_boost_pct, 300.0), 0.0) / 100.0)
    sim_out += blocked * (max(min(unblock_pct, 100.0), 0.0) / 100.0) * 0.35

    net_week = sim_in - sim_out
    backlog_8w = max(open_total + (net_week * 8.0), 0.0)

    weeks_to_zero: float | None
    if sim_out > sim_in and open_total > 0:
        weeks_to_zero = open_total / max(sim_out - sim_in, 1e-6)
    else:
        weeks_to_zero = None

    return {
        "weekly_in": sim_in,
        "weekly_out": sim_out,
        "weekly_net": net_week,
        "backlog_8w": backlog_8w,
        "delta_8w": backlog_8w - open_total,
        "weeks_to_zero": weeks_to_zero,
    }


def answer_copilot_question(
    *,
    question: str,
    snapshot: Dict[str, Any],
    baseline_snapshot: Dict[str, Any] | None = None,
    next_action: NextBestAction | None = None,
) -> CopilotAnswer:
    q = _norm(question)
    s = snapshot if isinstance(snapshot, dict) else {}
    base = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}
    followups = [
        "Que accion concreta haria hoy para bajar cartera?",
        "Que pasaria si reducimos entrada un 20%?",
        "Que cuello de botella esta penalizando mas al cliente?",
    ]

    evidence = [
        f"Backlog abierto: {int(s.get('open_total', 0) or 0)}",
        f"Balance 14d: {int(s.get('net_14', 0) or 0):+d}",
        f"Criticas: {int(s.get('critical_count', 0) or 0)}",
    ]

    if any(k in q for k in ["riesgo", "cliente", "impacto"]):
        ans = (
            f"El riesgo cliente hoy viene de criticas ({int(s.get('critical_count', 0) or 0)}), "
            f"bloqueadas ({int(s.get('blocked_count', 0) or 0)}) y cola >30d ({_fmt_pct(float(s.get('aged30_pct', 0.0) or 0.0))})."
        )
        return CopilotAnswer(answer=ans, confidence=0.84, evidence=evidence, followups=followups)

    if any(k in q for k in ["prioridad", "priority"]):
        ans = (
            f"La prioridad dominante es {s.get('top_priority', '—')} "
            f"({_fmt_pct(float(s.get('top_priority_share', 0.0) or 0.0))}). "
            f"Hay {int(s.get('critical_unassigned_count', 0) or 0)} criticas sin owner."
        )
        return CopilotAnswer(answer=ans, confidence=0.87, evidence=evidence, followups=followups)

    if any(k in q for k in ["estado", "cuello", "atasco", "bloqueo"]):
        ans = (
            f"El estado dominante es {s.get('top_status', '—')} "
            f"({_fmt_pct(float(s.get('top_status_share', 0.0) or 0.0))}) y hay "
            f"{int(s.get('blocked_count', 0) or 0)} bloqueadas."
        )
        return CopilotAnswer(answer=ans, confidence=0.85, evidence=evidence, followups=followups)

    if any(k in q for k in ["que hago", "accion", "next", "prioridad hoy"]):
        if next_action is not None:
            ans = f"{next_action.title}: {next_action.body} {next_action.expected_impact}"
            return CopilotAnswer(answer=ans, confidence=0.89, evidence=evidence, followups=followups)
        return CopilotAnswer(
            answer="La accion prioritaria depende del cuello dominante en el filtro actual.",
            confidence=0.62,
            evidence=evidence,
            followups=followups,
        )

    if any(k in q for k in ["cambio", "ultima sesion", "ultima", "evolucion"]):
        if base:
            delta_open = int((s.get("open_total", 0) or 0) - (base.get("open_total", 0) or 0))
            delta_blocked = int((s.get("blocked_count", 0) or 0) - (base.get("blocked_count", 0) or 0))
            ans = (
                f"Vs ultima sesion: backlog {'+' if delta_open > 0 else ''}{delta_open}, "
                f"bloqueadas {'+' if delta_blocked > 0 else ''}{delta_blocked}."
            )
            return CopilotAnswer(answer=ans, confidence=0.81, evidence=evidence, followups=followups)
        return CopilotAnswer(
            answer="Aun no hay baseline historico para comparar en este cliente.",
            confidence=0.55,
            evidence=evidence,
            followups=followups,
        )

    if any(k in q for k in ["duplic", "reincid", "repet"]):
        ans = (
            f"Hay {int(s.get('duplicate_issues', 0) or 0)} incidencias en grupos repetidos "
            f"({_fmt_pct(float(s.get('duplicate_share', 0.0) or 0.0))} del backlog)."
        )
        return CopilotAnswer(answer=ans, confidence=0.82, evidence=evidence, followups=followups)

    if any(k in q for k in ["resumen", "brief", "situacion", "situacion actual"]):
        ans = (
            f"Backlog {int(s.get('open_total', 0) or 0)}; balance 14d {int(s.get('net_14', 0) or 0):+d}; "
            f"cola >30d {_fmt_pct(float(s.get('aged30_pct', 0.0) or 0.0))}; "
            f"criticas {int(s.get('critical_count', 0) or 0)}."
        )
        return CopilotAnswer(answer=ans, confidence=0.88, evidence=evidence, followups=followups)

    if re.search(r"\b(simula|what if|escenario|proyeccion)\b", q):
        ans = (
            "Usa el simulador de impacto para estimar backlog a 8 semanas con reduccion de entrada, "
            "mejora de cierre y desbloqueo."
        )
        return CopilotAnswer(answer=ans, confidence=0.73, evidence=evidence, followups=followups)

    return CopilotAnswer(
        answer=(
            "Puedo ayudarte con riesgo cliente, cuello de botella, prioridades, cambios vs ultima sesion y simulaciones what-if."
        ),
        confidence=0.60,
        evidence=evidence,
        followups=followups,
    )
