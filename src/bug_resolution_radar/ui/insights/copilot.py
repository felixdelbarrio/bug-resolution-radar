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


@dataclass(frozen=True)
class CopilotRoute:
    cta: str
    section: str
    trend_chart: str | None = None
    insights_tab: str | None = None
    status_filters: List[str] | None = None
    priority_filters: List[str] | None = None
    assignee_filters: List[str] | None = None


KNOWN_INTENTS = (
    "risk",
    "priority",
    "bottleneck",
    "action",
    "change",
    "duplicates",
    "summary",
    "simulation",
    "other",
)

INTENT_LABELS = {
    "risk": "riesgo cliente",
    "priority": "priorizacion",
    "bottleneck": "cuello de botella",
    "action": "accion recomendada",
    "change": "evolucion entre sesiones",
    "duplicates": "duplicidades",
    "summary": "resumen general",
    "simulation": "escenarios what-if",
    "other": "consulta abierta",
}

TERMINAL_STATUS_TOKENS = (
    "closed",
    "resolved",
    "done",
    "deployed",
    "accepted",
    "ready to deploy",
    "cancelled",
    "canceled",
)


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


def _norm(txt: str) -> str:
    t = unicodedata.normalize("NFKD", str(txt or "").strip().lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t


def _is_terminal_status(value: object) -> bool:
    token = _norm(str(value or ""))
    if not token:
        return False
    return any(t in token for t in TERMINAL_STATUS_TOKENS)


def _push_unique(target: List[str], value: str, *, max_len: int) -> None:
    txt = str(value or "").strip()
    if not txt:
        return
    if txt in target:
        return
    if len(target) >= max_len:
        return
    target.append(txt)


def _push_unique_unbounded(target: List[str], value: str) -> None:
    txt = str(value or "").strip()
    if not txt:
        return
    if txt in target:
        return
    target.append(txt)


def _safe_series_count(mask: pd.Series) -> int:
    try:
        return int(mask.sum())
    except Exception:
        return 0


def normalize_intent_counts(raw: Any) -> Dict[str, int]:
    counts_raw = raw if isinstance(raw, dict) else {}
    counts: Dict[str, int] = {}
    for intent in KNOWN_INTENTS:
        val = counts_raw.get(intent, 0)
        try:
            parsed = int(val)
        except Exception:
            parsed = 0
        counts[intent] = max(parsed, 0)
    return counts


def classify_question_intent(question: str) -> str:
    q = _norm(question)
    if not q:
        return "other"
    if any(k in q for k in ["riesgo", "cliente", "impacto"]):
        return "risk"
    if any(k in q for k in ["prioridad", "priority"]):
        return "priority"
    if any(k in q for k in ["estado", "cuello", "atasco", "bloqueo"]):
        return "bottleneck"
    if any(k in q for k in ["que hago", "accion", "next", "prioridad hoy"]):
        return "action"
    if any(k in q for k in ["cambio", "ultima sesion", "ultima", "evolucion"]):
        return "change"
    if any(k in q for k in ["duplic", "reincid", "repet"]):
        return "duplicates"
    if any(k in q for k in ["resumen", "brief", "situacion", "situacion actual"]):
        return "summary"
    if re.search(r"\b(simula|what if|escenario|proyeccion)\b", q):
        return "simulation"
    return "other"


def top_learned_intents(intent_counts: Dict[str, int], *, limit: int = 2) -> List[str]:
    counts = normalize_intent_counts(intent_counts)
    pairs = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    out: List[str] = []
    for intent, weight in pairs:
        if weight <= 0:
            continue
        _push_unique(out, intent, max_len=max(limit, 1))
    return out[: max(limit, 1)]


def _open_unique_values(open_df: pd.DataFrame, *, column: str, empty_label: str) -> List[str]:
    if not isinstance(open_df, pd.DataFrame) or open_df.empty or column not in open_df.columns:
        return []
    vals = normalize_text_col(open_df[column], empty_label).astype(str).tolist()
    out: List[str] = []
    for v in vals:
        _push_unique_unbounded(out, v)
    return out


def _match_filters_to_available(
    requested: List[str] | None,
    *,
    available: List[str],
    kind: str,
) -> List[str]:
    req = [str(x).strip() for x in list(requested or []) if str(x).strip()]
    if not req:
        return []
    if not available:
        return []

    out: List[str] = []
    available_norm = [(_norm(v), v) for v in available]
    for raw in req:
        q = _norm(raw)
        exact = [orig for nrm, orig in available_norm if nrm == q]
        for v in exact:
            _push_unique_unbounded(out, v)
        if exact:
            continue

        if kind == "status" and q in {"blocked", "bloqueado"}:
            for nrm, orig in available_norm:
                if ("blocked" in nrm) or ("bloque" in nrm):
                    _push_unique_unbounded(out, orig)
            if out:
                continue

        if kind == "priority" and q in {
            "highest",
            "high",
            "supone un impedimento",
            "impedimento",
        }:
            for nrm, orig in available_norm:
                if nrm in {"highest", "high", "supone un impedimento", "impedimento"}:
                    _push_unique_unbounded(out, orig)
                elif "high" in nrm or "imped" in nrm:
                    _push_unique_unbounded(out, orig)
            if out:
                continue

        if kind == "assignee" and q in {"sin asignar", "(sin asignar)"}:
            for nrm, orig in available_norm:
                if nrm in {"sin asignar", "(sin asignar)"}:
                    _push_unique_unbounded(out, orig)
            if out:
                continue

        if len(q) >= 3:
            fuzzy = [orig for nrm, orig in available_norm if q in nrm or nrm in q]
            for v in fuzzy:
                _push_unique_unbounded(out, v)
    return out


def _open_match_count(
    *,
    open_df: pd.DataFrame,
    status_filters: List[str],
    priority_filters: List[str],
    assignee_filters: List[str],
) -> int:
    if not isinstance(open_df, pd.DataFrame) or open_df.empty:
        return 0
    mask = pd.Series(True, index=open_df.index)
    if status_filters and "status" in open_df.columns:
        stx = normalize_text_col(open_df["status"], "(sin estado)")
        mask &= stx.isin(status_filters)
    if priority_filters and "priority" in open_df.columns:
        pr = normalize_text_col(open_df["priority"], "(sin priority)")
        mask &= pr.isin(priority_filters)
    if assignee_filters and "assignee" in open_df.columns:
        ass = normalize_text_col(open_df["assignee"], "(sin asignar)")
        mask &= ass.isin(assignee_filters)
    return int(mask.sum())


def resolve_filters_against_open_df(
    *,
    open_df: pd.DataFrame,
    status_filters: List[str] | None = None,
    priority_filters: List[str] | None = None,
    assignee_filters: List[str] | None = None,
) -> tuple[List[str], List[str], List[str]]:
    status = _match_filters_to_available(
        status_filters,
        available=_open_unique_values(open_df, column="status", empty_label="(sin estado)"),
        kind="status",
    )
    priority = _match_filters_to_available(
        priority_filters,
        available=_open_unique_values(open_df, column="priority", empty_label="(sin priority)"),
        kind="priority",
    )
    assignee = _match_filters_to_available(
        assignee_filters,
        available=_open_unique_values(open_df, column="assignee", empty_label="(sin asignar)"),
        kind="assignee",
    )

    if not isinstance(open_df, pd.DataFrame) or open_df.empty:
        return status, priority, assignee

    # Guarantee useful navigation: if strict combination is empty, relax dimensions progressively.
    if (
        _open_match_count(
            open_df=open_df,
            status_filters=status,
            priority_filters=priority,
            assignee_filters=assignee,
        )
        > 0
    ):
        return status, priority, assignee

    if (
        assignee
        and _open_match_count(
            open_df=open_df,
            status_filters=status,
            priority_filters=priority,
            assignee_filters=[],
        )
        > 0
    ):
        return status, priority, []

    if (
        priority
        and _open_match_count(
            open_df=open_df,
            status_filters=status,
            priority_filters=[],
            assignee_filters=[],
        )
        > 0
    ):
        return status, [], []

    if (
        status
        and _open_match_count(
            open_df=open_df,
            status_filters=[],
            priority_filters=[],
            assignee_filters=[],
        )
        > 0
    ):
        return [], [], []

    return status, priority, assignee


def learned_intents_caption(intent_counts: Dict[str, int]) -> str | None:
    top = top_learned_intents(intent_counts, limit=2)
    if not top:
        return None
    labels = [INTENT_LABELS.get(x, x) for x in top]
    if len(labels) == 1:
        return f"Aprendiendo de tus preguntas: foco en {labels[0]}."
    return f"Aprendiendo de tus preguntas: foco en {labels[0]} y {labels[1]}."


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

    created_open = (
        _to_dt_naive(safe_open["created"])
        if "created" in safe_open.columns
        else pd.Series([], dtype="datetime64[ns]")
    )
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
    critical_mask = (
        (priority.map(priority_rank) <= 2) if not priority.empty else pd.Series([], dtype=bool)
    )
    critical_count = _safe_series_count(critical_mask) if not critical_mask.empty else 0
    unassigned_count = _safe_series_count(assignee.eq("(sin asignar)")) if not assignee.empty else 0
    critical_unassigned = (
        _safe_series_count(critical_mask & assignee.eq("(sin asignar)"))
        if (not critical_mask.empty and not assignee.empty)
        else 0
    )
    aged30_count = _safe_series_count(age_days > 30) if not age_days.empty else 0

    top_status = "—"
    top_status_share = 0.0
    top_active_status = "—"
    top_active_status_share = 0.0
    if not status.empty:
        vc = status.value_counts()
        if not vc.empty:
            top_status = str(vc.index[0])
            top_status_share = float(vc.iloc[0]) / float(max(int(vc.sum()), 1))
            active_vc = vc[[not _is_terminal_status(str(idx)) for idx in vc.index]]
            if not active_vc.empty:
                top_active_status = str(active_vc.index[0])
                top_active_status_share = float(active_vc.iloc[0]) / float(max(int(vc.sum()), 1))

    top_priority = "—"
    top_priority_share = 0.0
    if not priority.empty:
        pv = priority.value_counts()
        if not pv.empty:
            top_priority = str(pv.index[0])
            top_priority_share = float(pv.iloc[0]) / float(max(int(pv.sum()), 1))

    created_all = (
        _to_dt_naive(safe_dff["created"])
        if "created" in safe_dff.columns
        else pd.Series([], dtype="datetime64[ns]")
    )
    resolved_all = (
        _to_dt_naive(safe_dff["resolved"])
        if "resolved" in safe_dff.columns
        else pd.Series([], dtype="datetime64[ns]")
    )
    from_14 = now - pd.Timedelta(days=14)
    created_14 = _safe_series_count(created_all >= from_14) if not created_all.empty else 0
    resolved_14 = _safe_series_count(resolved_all >= from_14) if not resolved_all.empty else 0
    net_14 = int(created_14 - resolved_14)
    close_entry_ratio_14 = (
        (float(resolved_14) / float(created_14))
        if created_14 > 0
        else (float("inf") if resolved_14 > 0 else 0.0)
    )

    closed_subset = pd.DataFrame()
    if not safe_dff.empty and "created" in safe_dff.columns and "resolved" in safe_dff.columns:
        c = _to_dt_naive(safe_dff["created"])
        r = _to_dt_naive(safe_dff["resolved"])
        closed_subset = safe_dff.copy(deep=False)
        closed_subset["__c"] = c
        closed_subset["__r"] = r
        closed_subset = closed_subset[
            closed_subset["__c"].notna() & closed_subset["__r"].notna()
        ].copy(deep=False)
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

    updated_open = (
        _to_dt_naive(safe_open["updated"])
        if "updated" in safe_open.columns
        else pd.Series([], dtype="datetime64[ns]")
    )
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
        "top_status_is_final": _is_terminal_status(top_status),
        "top_status_share": top_status_share,
        "top_active_status": top_active_status,
        "top_active_status_share": top_active_status_share,
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
                    f"{label}: {_fmt_pct(b)} -> {_fmt_pct(c)} ({'+' if d > 0 else ''}{d * 100.0:.1f} pp).",
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
    actions = list_next_best_actions(snapshot=snapshot, cards=cards)
    if actions:
        return actions[0]
    return NextBestAction(
        title="Seguimiento operativo",
        body="Con el filtro actual no se observa una desviacion dominante.",
        expected_impact="Impacto esperado: mantener control de flujo y seguimiento periodico.",
    )


def list_next_best_actions(
    *,
    snapshot: Dict[str, Any],
    cards: Sequence[Any] | None = None,
) -> List[NextBestAction]:
    s = snapshot if isinstance(snapshot, dict) else {}
    crit_unassigned = int(s.get("critical_unassigned_count", 0) or 0)
    blocked = int(s.get("blocked_count", 0) or 0)
    net14 = int(s.get("net_14", 0) or 0)
    aged30_pct = float(s.get("aged30_pct", 0.0) or 0.0)
    dup_share = float(s.get("duplicate_share", 0.0) or 0.0)
    top_status = str(s.get("top_status", "—") or "—")
    top_active_status = str(s.get("top_active_status", "—") or "—")
    focus_status = (
        top_active_status
        if top_active_status != "—"
        else (top_status if (top_status != "—" and not _is_terminal_status(top_status)) else "—")
    )
    actions: List[NextBestAction] = []

    if crit_unassigned > 0:
        actions.append(
            NextBestAction(
                title="Asignacion de ownership critico",
                body=(
                    f"Con el filtro actual se observan {crit_unassigned} incidencias High/Highest "
                    "sin owner asignado."
                ),
                expected_impact=(
                    "Impacto esperado: trazabilidad de ownership sobre "
                    f"{crit_unassigned} incidencias criticas."
                ),
                priority_filters=["Supone un impedimento", "Highest", "High"],
                assignee_filters=["(sin asignar)"],
            )
        )
    if blocked > 0 and float(s.get("blocked_pct", 0.0) or 0.0) >= 0.08:
        actions.append(
            NextBestAction(
                title="Revision de bloqueos activos",
                body=(
                    f"Con el filtro actual se observan {blocked} incidencias en estado bloqueado."
                ),
                expected_impact=(
                    "Impacto esperado: priorizacion de desbloqueo sobre "
                    f"{blocked} incidencias activas."
                ),
                status_filters=["Blocked", "Bloqueado"],
            )
        )
    if net14 > 0:
        actions.append(
            NextBestAction(
                title="Ajuste de balance entrada-salida",
                body=(
                    f"En los ultimos 14 dias la entrada supera a la salida en +{net14} incidencias."
                ),
                expected_impact=(
                    "Impacto esperado: establecer un objetivo de cierres para absorber "
                    "el diferencial de entrada."
                ),
                status_filters=[focus_status] if focus_status != "—" else None,
            )
        )
    if aged30_pct >= 0.25:
        actions.append(
            NextBestAction(
                title="Tratamiento de cola envejecida",
                body=(f"El {_fmt_pct(aged30_pct)} del backlog abierto supera los 30 dias."),
                expected_impact=(
                    "Impacto esperado: reducir el riesgo de envejecimiento "
                    "al trabajar esta cola de forma dedicada."
                ),
            )
        )
    if dup_share >= 0.10:
        actions.append(
            NextBestAction(
                title="Consolidacion de duplicidades",
                body=(f"Las duplicidades representan {_fmt_pct(dup_share)} del backlog abierto."),
                expected_impact=(
                    "Impacto esperado: reducir carga operativa al consolidar incidencias repetidas."
                ),
            )
        )

    if cards and not actions:
        first = cards[0]
        title = str(getattr(first, "title", "") or "Sostener ritmo actual")
        body = str(getattr(first, "body", "") or "El flujo esta estable.")
        actions.append(
            NextBestAction(
                title=title,
                body=body,
                expected_impact="Impacto esperado: mantener tendencia y atacar deuda puntual.",
                status_filters=list(getattr(first, "status_filters", []) or []),
                priority_filters=list(getattr(first, "priority_filters", []) or []),
                assignee_filters=list(getattr(first, "assignee_filters", []) or []),
            )
        )

    if not actions:
        actions.append(
            NextBestAction(
                title="Seguimiento operativo",
                body="Con el filtro actual no se observa una desviacion dominante.",
                expected_impact="Impacto esperado: mantener control de flujo y seguimiento periodico.",
            )
        )
    return actions


def build_copilot_suggestions(
    *,
    snapshot: Dict[str, Any],
    baseline_snapshot: Dict[str, Any] | None = None,
    next_action: NextBestAction | None = None,
    intent_counts: Dict[str, int] | None = None,
    limit: int = 4,
) -> List[str]:
    s = snapshot if isinstance(snapshot, dict) else {}
    base = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}
    learned = normalize_intent_counts(intent_counts)
    out: List[str] = []

    focus_status = str(s.get("top_active_status", "—") or "—").strip()

    # Prioritize learned intent patterns so suggestions feel personalized over time.
    for intent in top_learned_intents(learned, limit=2):
        if intent == "risk":
            _push_unique(out, "Cual es el mayor riesgo cliente hoy?", max_len=limit)
        elif intent == "priority":
            _push_unique(out, "Que prioridad debo atacar para reducir riesgo real?", max_len=limit)
        elif intent == "bottleneck":
            _push_unique(
                out,
                (
                    f"Que esta frenando el avance en {focus_status}?"
                    if focus_status and focus_status != "—"
                    else "Que cuello de botella penaliza mas el flujo?"
                ),
                max_len=limit,
            )
        elif intent == "action":
            _push_unique(out, "Que accion concreta priorizo esta semana?", max_len=limit)
        elif intent == "change":
            _push_unique(out, "Como cambio la situacion desde mi ultima sesion?", max_len=limit)
        elif intent == "duplicates":
            _push_unique(out, "Cuanto backlog estamos perdiendo en duplicidades?", max_len=limit)
        elif intent == "summary":
            _push_unique(out, "Dame un resumen general de la situacion actual.", max_len=limit)
        elif intent == "simulation":
            _push_unique(
                out, "Que pasaria si reducimos entrada un 20% y subimos cierres?", max_len=limit
            )

    if next_action is not None:
        _push_unique(
            out,
            f"Como ejecuto ya la accion '{next_action.title}' y que impacto espero?",
            max_len=limit,
        )
    if (
        float(s.get("critical_pct", 0.0) or 0.0) >= 0.12
        or int(s.get("critical_unassigned_count", 0) or 0) > 0
    ):
        _push_unique(
            out,
            "Donde esta la bolsa critica sin owner y como la cierro primero?",
            max_len=limit,
        )
    if float(s.get("blocked_pct", 0.0) or 0.0) >= 0.08:
        _push_unique(
            out,
            "Que desbloqueo priorizo para recuperar throughput en 48h?",
            max_len=limit,
        )
    if int(s.get("net_14", 0) or 0) > 0:
        _push_unique(
            out,
            "Que ajuste de capacidad necesito para revertir el balance neto positivo?",
            max_len=limit,
        )
    if float(s.get("duplicate_share", 0.0) or 0.0) >= 0.10:
        _push_unique(
            out,
            "Que impacto tendria eliminar duplicados esta semana?",
            max_len=limit,
        )
    if base:
        _push_unique(
            out,
            "Como ha cambiado la situacion respecto a mi ultima sesion?",
            max_len=limit,
        )
    _push_unique(out, "Que accion concreta priorizo esta semana?", max_len=limit)
    _push_unique(out, "Cual es el mayor riesgo cliente hoy?", max_len=limit)
    _push_unique(
        out,
        (
            f"Que esta frenando el avance en {focus_status}?"
            if focus_status and focus_status != "—"
            else "Que cuello de botella penaliza mas el flujo?"
        ),
        max_len=limit,
    )
    _push_unique(out, "Dame un resumen general de la situacion actual.", max_len=limit)

    return out[: max(limit, 1)]


def route_copilot_action(
    *,
    question: str,
    snapshot: Dict[str, Any],
    next_action: NextBestAction | None = None,
) -> CopilotRoute:
    intent = classify_question_intent(question)
    s = snapshot if isinstance(snapshot, dict) else {}

    def _route_from_next_action() -> CopilotRoute | None:
        if next_action is None:
            return None
        has_filters = bool(
            next_action.status_filters
            or next_action.priority_filters
            or next_action.assignee_filters
        )
        if not has_filters:
            return None
        return CopilotRoute(
            cta=f"Aplicar: {next_action.title}",
            section="issues",
            status_filters=list(next_action.status_filters or []),
            priority_filters=list(next_action.priority_filters or []),
            assignee_filters=list(next_action.assignee_filters or []),
        )

    if intent in {"risk", "priority", "action"}:
        route = _route_from_next_action()
        if route is not None:
            return route

    if intent == "bottleneck":
        blocked = int(s.get("blocked_count", 0) or 0)
        if blocked > 0:
            return CopilotRoute(
                cta="Abrir bloqueadas en Issues",
                section="issues",
                status_filters=["Blocked", "Bloqueado"],
            )
        top_active_status = str(s.get("top_active_status", "—") or "—").strip()
        top_status = str(s.get("top_status", "—") or "—").strip()
        focus_status = (
            top_active_status
            if top_active_status and top_active_status != "—"
            else (
                top_status
                if top_status and top_status != "—" and not _is_terminal_status(top_status)
                else ""
            )
        )
        if focus_status:
            return CopilotRoute(
                cta=f"Abrir {focus_status} en Issues",
                section="issues",
                status_filters=[focus_status],
            )
        return CopilotRoute(
            cta="Revisar estados operativos en Issues",
            section="issues",
        )

    if intent == "duplicates":
        return CopilotRoute(
            cta="Ir a Insights de Duplicados",
            section="insights",
            insights_tab="duplicates",
        )

    if intent in {"change", "simulation", "summary"}:
        return CopilotRoute(
            cta="Abrir Tendencias",
            section="trends",
            trend_chart="timeseries",
        )

    route = _route_from_next_action()
    if route is not None:
        return route

    return CopilotRoute(
        cta="Ir a Issues",
        section="issues",
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
    intent = classify_question_intent(question)
    s = snapshot if isinstance(snapshot, dict) else {}
    base = baseline_snapshot if isinstance(baseline_snapshot, dict) else {}
    top_status = str(s.get("top_status", "—") or "—").strip()
    top_active_status = str(s.get("top_active_status", "—") or "—").strip()
    followups = [
        "Que accion concreta haria hoy para bajar cartera?",
        "Que pasaria si reducimos entrada un 20%?",
        (
            f"Que esta frenando el avance en {top_active_status}?"
            if top_active_status and top_active_status != "—"
            else "Que cuello de botella esta penalizando mas al cliente?"
        ),
    ]

    evidence = [
        f"Backlog abierto: {int(s.get('open_total', 0) or 0)}",
        f"Balance 14d: {int(s.get('net_14', 0) or 0):+d}",
        f"Criticas: {int(s.get('critical_count', 0) or 0)}",
    ]

    if intent == "risk":
        ans = (
            "Con los datos visibles, los principales factores de exposicion son "
            f"criticas ({int(s.get('critical_count', 0) or 0)}), "
            f"bloqueadas ({int(s.get('blocked_count', 0) or 0)}) y cola >30d "
            f"({_fmt_pct(float(s.get('aged30_pct', 0.0) or 0.0))})."
        )
        return CopilotAnswer(answer=ans, confidence=0.84, evidence=evidence, followups=followups)

    if intent == "priority":
        ans = (
            f"La prioridad dominante en el filtro es {s.get('top_priority', '—')} "
            f"({_fmt_pct(float(s.get('top_priority_share', 0.0) or 0.0))}) "
            f"y hay {int(s.get('critical_unassigned_count', 0) or 0)} criticas sin owner."
        )
        return CopilotAnswer(answer=ans, confidence=0.87, evidence=evidence, followups=followups)

    if intent == "bottleneck":
        if top_active_status and top_active_status != "—":
            ans = (
                f"El estado con mayor peso operativo en el filtro es {top_active_status} "
                f"({_fmt_pct(float(s.get('top_active_status_share', 0.0) or 0.0))}) y se observan "
                f"{int(s.get('blocked_count', 0) or 0)} bloqueadas."
            )
        elif top_status and top_status != "—" and not _is_terminal_status(top_status):
            ans = (
                f"El estado dominante en el filtro es {top_status} "
                f"({_fmt_pct(float(s.get('top_status_share', 0.0) or 0.0))}). "
                f"y se observan {int(s.get('blocked_count', 0) or 0)} bloqueadas."
            )
        else:
            ans = (
                "No se observa un estado operativo dominante con este filtro. "
                "Conviene ampliar foco a estados activos para identificar fricciones accionables."
            )
        return CopilotAnswer(answer=ans, confidence=0.85, evidence=evidence, followups=followups)

    if intent == "action":
        if next_action is not None:
            ans = f"{next_action.title}: {next_action.body} {next_action.expected_impact}"
            return CopilotAnswer(
                answer=ans, confidence=0.89, evidence=evidence, followups=followups
            )
        return CopilotAnswer(
            answer="La accion prioritaria depende de la principal friccion operativa del filtro actual.",
            confidence=0.62,
            evidence=evidence,
            followups=followups,
        )

    if intent == "change":
        if base:
            delta_open = int((s.get("open_total", 0) or 0) - (base.get("open_total", 0) or 0))
            delta_blocked = int(
                (s.get("blocked_count", 0) or 0) - (base.get("blocked_count", 0) or 0)
            )
            ans = (
                f"Comparado con la ultima sesion: backlog {'+' if delta_open > 0 else ''}{delta_open}, "
                f"bloqueadas {'+' if delta_blocked > 0 else ''}{delta_blocked}."
            )
            return CopilotAnswer(
                answer=ans, confidence=0.81, evidence=evidence, followups=followups
            )
        return CopilotAnswer(
            answer="Aun no hay baseline historico para comparar en este cliente.",
            confidence=0.55,
            evidence=evidence,
            followups=followups,
        )

    if intent == "duplicates":
        ans = (
            f"Hay {int(s.get('duplicate_issues', 0) or 0)} incidencias en grupos repetidos "
            f"({_fmt_pct(float(s.get('duplicate_share', 0.0) or 0.0))} del backlog)."
        )
        return CopilotAnswer(answer=ans, confidence=0.82, evidence=evidence, followups=followups)

    if intent == "summary":
        ans = (
            f"Backlog {int(s.get('open_total', 0) or 0)}; balance 14d {int(s.get('net_14', 0) or 0):+d}; "
            f"cola >30d {_fmt_pct(float(s.get('aged30_pct', 0.0) or 0.0))}; "
            f"criticas {int(s.get('critical_count', 0) or 0)}."
        )
        return CopilotAnswer(answer=ans, confidence=0.88, evidence=evidence, followups=followups)

    if intent == "simulation":
        ans = (
            "Usa el simulador de impacto para estimar backlog a 8 semanas con reduccion de entrada, "
            "mejora de cierre y desbloqueo."
        )
        return CopilotAnswer(answer=ans, confidence=0.73, evidence=evidence, followups=followups)

    return CopilotAnswer(
        answer=(
            "Puedo ayudarte con riesgo cliente, fricciones de flujo, prioridades, cambios vs ultima sesion y simulaciones what-if."
        ),
        confidence=0.60,
        evidence=evidence,
        followups=followups,
    )
