"""Shared UI performance helpers for dashboard tabs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from time import perf_counter

import streamlit as st


def elapsed_ms(start_ts: float) -> float:
    """Return elapsed milliseconds from a monotonic start timestamp."""
    return max(0.0, (perf_counter() - float(start_ts)) * 1000.0)


def resolve_budget(
    *,
    view: str,
    budgets_by_view: Mapping[str, Mapping[str, float]],
    default_view: str,
) -> dict[str, float]:
    """Return a normalized budget map for the requested view."""
    picked = budgets_by_view.get(str(view or "").strip()) or budgets_by_view.get(default_view) or {}
    return {str(k): float(v or 0.0) for k, v in picked.items()}


def detect_budget_overruns(
    *,
    ordered_blocks: Sequence[str],
    metrics_ms: Mapping[str, float],
    budgets_ms: Mapping[str, float],
) -> list[str]:
    """Return budget-exceeded blocks in a deterministic order."""
    out: list[str] = []
    for block in ordered_blocks:
        budget = float(budgets_ms.get(block, 0.0) or 0.0)
        value = float(metrics_ms.get(block, 0.0) or 0.0)
        if budget > 0.0 and value > budget:
            out.append(block)
    return out


def render_perf_footer(
    *,
    snapshot_key: str,
    view: str,
    ordered_blocks: Sequence[str],
    metrics_ms: Mapping[str, float],
    budgets_ms: Mapping[str, float],
    caption_prefix: str = "Perf",
) -> list[str]:
    """Render compact perf footer and persist normalized snapshot in session state."""
    parts: list[str] = []
    normalized_metrics = {str(k): float(v or 0.0) for k, v in metrics_ms.items()}
    normalized_budgets = {str(k): float(v or 0.0) for k, v in budgets_ms.items()}

    for block in ordered_blocks:
        if block not in normalized_metrics:
            continue
        value = normalized_metrics.get(block, 0.0)
        budget = normalized_budgets.get(block, 0.0)
        if budget > 0.0:
            parts.append(f"{block} {value:.0f}/{budget:.0f}ms")
        else:
            parts.append(f"{block} {value:.0f}ms")

    overruns = detect_budget_overruns(
        ordered_blocks=ordered_blocks,
        metrics_ms=normalized_metrics,
        budgets_ms=normalized_budgets,
    )
    st.session_state[str(snapshot_key)] = {
        "view": str(view),
        "metrics_ms": normalized_metrics,
        "budget_ms": normalized_budgets,
        "overruns": list(overruns),
    }
    if parts:
        st.caption(f"{caption_prefix} {view}: {' · '.join(parts)}")
    if overruns:
        st.caption(f"Budget excedido en: {', '.join(overruns)}")
    return overruns
