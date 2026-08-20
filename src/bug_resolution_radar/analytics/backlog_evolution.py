"""Operational backlog snapshots and material evolution signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from bug_resolution_radar.analytics.issues import critical_priority_mask, normalize_text_col


@dataclass(frozen=True)
class EvolutionInsight:
    title: str
    body: str
    score: float
    direction: str


def _to_dt_naive(values: object) -> pd.Series:
    series = values if isinstance(values, pd.Series) else pd.Series([], dtype=object)
    ts = pd.to_datetime(series, errors="coerce", utc=True)
    try:
        return ts.dt.tz_localize(None)
    except Exception:
        return pd.Series([], dtype="datetime64[ns]")


def _count(mask: pd.Series) -> int:
    if not isinstance(mask, pd.Series) or mask.empty:
        return 0
    return int(mask.fillna(False).sum())


def _reference_day(dff: pd.DataFrame, explicit: pd.Timestamp | str | None) -> pd.Timestamp:
    if explicit is not None:
        parsed = pd.to_datetime(explicit, errors="coerce", utc=True)
        if pd.notna(parsed):
            return pd.Timestamp(parsed).tz_convert(None).normalize()
    candidates: list[pd.Timestamp] = []
    for column in ("updated", "resolved", "created"):
        if column not in dff.columns:
            continue
        values = _to_dt_naive(dff[column])
        if values.notna().any():
            candidates.append(pd.Timestamp(values.max()).normalize())
    if candidates:
        return max(candidates)
    return pd.Timestamp.now("UTC").tz_localize(None).normalize()


def build_operational_snapshot(
    *,
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
    reference_day: pd.Timestamp | str | None = None,
) -> dict[str, Any]:
    """Build a compact, deterministic measurement for historical comparison."""
    safe_dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    safe_open = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    ref = _reference_day(safe_dff, reference_day)

    status = (
        normalize_text_col(safe_open["status"], "(sin estado)").astype(str)
        if "status" in safe_open.columns
        else pd.Series([], dtype=str)
    )
    priority = (
        normalize_text_col(safe_open["priority"], "(sin priority)").astype(str)
        if "priority" in safe_open.columns
        else pd.Series([], dtype=str)
    )
    created_open = (
        _to_dt_naive(safe_open["created"])
        if "created" in safe_open.columns
        else pd.Series([], dtype="datetime64[ns]")
    )
    updated_open = (
        _to_dt_naive(safe_open["updated"])
        if "updated" in safe_open.columns
        else pd.Series([], dtype="datetime64[ns]")
    )
    age_days = (
        ((ref - created_open).dt.total_seconds() / 86400.0).clip(lower=0.0)
        if not created_open.empty
        else pd.Series([], dtype=float)
    )
    stale_days = (
        ((ref - updated_open).dt.total_seconds() / 86400.0).clip(lower=0.0)
        if not updated_open.empty
        else pd.Series([], dtype=float)
    )

    open_total = int(len(safe_open))
    blocked_count = (
        _count(status.str.casefold().str.contains("blocked|bloque", regex=True))
        if not status.empty
        else 0
    )
    critical_count = _count(critical_priority_mask(priority)) if not priority.empty else 0
    aged30_count = _count(age_days > 30) if not age_days.empty else 0
    stale_14_count = _count(stale_days > 14) if not stale_days.empty else 0

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
    from_14 = ref - pd.Timedelta(days=14)
    created_14 = _count((created_all >= from_14) & (created_all <= ref))
    resolved_14 = _count((resolved_all >= from_14) & (resolved_all <= ref))

    return {
        "reference_date": ref.date().isoformat(),
        "open_total": open_total,
        "aged30_count": aged30_count,
        "aged30_pct": (aged30_count / open_total) if open_total else 0.0,
        "blocked_count": blocked_count,
        "blocked_pct": (blocked_count / open_total) if open_total else 0.0,
        "critical_count": critical_count,
        "critical_pct": (critical_count / open_total) if open_total else 0.0,
        "stale_14_count": stale_14_count,
        "stale_14_pct": (stale_14_count / open_total) if open_total else 0.0,
        "created_14": created_14,
        "resolved_14": resolved_14,
        "net_14": created_14 - resolved_14,
    }


def _measurement_label(current: dict[str, Any], baseline: dict[str, Any]) -> str:
    current_day = pd.to_datetime(current.get("reference_date"), errors="coerce")
    baseline_day = pd.to_datetime(baseline.get("reference_date"), errors="coerce")
    if pd.notna(current_day) and pd.notna(baseline_day):
        elapsed = abs(int((current_day - baseline_day).days))
        if 5 <= elapsed <= 9:
            return "WoW"
        if elapsed > 0:
            return f"vs última medición ({elapsed} días)"
    return "vs última medición"


def build_evolution_insight(
    current: dict[str, Any], baseline: dict[str, Any] | None
) -> EvolutionInsight | None:
    """Return only a material, evidence-backed evolution message."""
    cur = current if isinstance(current, dict) else {}
    base = baseline if isinstance(baseline, dict) else {}
    if not cur or not base:
        return None

    signals: list[tuple[float, int, str]] = []

    def add_count(key: str, label: str, weight: float, *, minimum: int = 1) -> None:
        before = int(base.get(key, 0) or 0)
        after = int(cur.get(key, 0) or 0)
        delta = after - before
        if abs(delta) < minimum:
            return
        direction = -1 if delta > 0 else 1
        verb = "baja" if delta < 0 else "sube"
        signals.append(
            (
                weight * abs(delta) / max(before, 1),
                direction,
                f"{label} {verb} de {before} a {after} ({delta:+d})",
            )
        )

    add_count("critical_count", "Prioridades críticas", 8.0)
    add_count("blocked_count", "Bloqueadas", 6.0)
    add_count("aged30_count", "Cola >30 días", 5.0)
    add_count("open_total", "Backlog abierto", 4.0)
    add_count("stale_14_count", "Sin movimiento >14 días", 3.0)
    add_count("net_14", "Balance neto 14d", 2.0, minimum=2)
    if not signals:
        return None

    signals.sort(key=lambda item: item[0], reverse=True)
    selected = signals[:3]
    balance = sum(importance * direction for importance, direction, _ in selected)
    direction = "improves" if balance > 0.2 else "worsens" if balance < -0.2 else "mixed"
    qualifier = _measurement_label(cur, base)
    title = {
        "improves": f"Evolución favorable {qualifier}",
        "worsens": f"Deterioro operativo {qualifier}",
        "mixed": f"Evolución mixta {qualifier}",
    }[direction]
    body = "; ".join(text for _, _, text in selected) + "."
    return EvolutionInsight(
        title=title,
        body=body,
        score=float(sum(importance for importance, _, _ in selected)),
        direction=direction,
    )


def build_evolution_lines(current: dict[str, Any], baseline: dict[str, Any] | None) -> list[str]:
    insight = build_evolution_insight(current, baseline)
    return [f"{insight.title}: {insight.body}"] if insight is not None else []
