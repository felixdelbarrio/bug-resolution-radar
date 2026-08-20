"""Operational backlog snapshots and material evolution signals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from bug_resolution_radar.analytics.execution_evolution import build_execution_evolution


@dataclass(frozen=True)
class EvolutionInsight:
    title: str
    body: str
    score: float
    direction: str


def build_operational_snapshot(
    *,
    dff: pd.DataFrame,
    reference_day: pd.Timestamp | str | None = None,
) -> dict[str, Any]:
    """Build the canonical learning measurement used across views and reports."""
    safe_dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    evolution = build_execution_evolution(dff=safe_dff, reference_day=reference_day)
    return dict(evolution["learningMeasurement"])


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
    add_count("aged30_count", "Cola >30 días", 5.0)
    add_count("open_total", "Backlog abierto", 4.0)
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
