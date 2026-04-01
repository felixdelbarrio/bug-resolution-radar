"""Shared UI performance helpers for dashboard tabs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from time import perf_counter

import streamlit as st

_PERF_HISTORY_KEY = "__dashboard_perf_history"
_PERF_HISTORY_MAX_ROWS = 320


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


def _normalize_snapshot_payload(
    *,
    view: str,
    metrics_ms: Mapping[str, float],
    budgets_ms: Mapping[str, float],
    overruns: Sequence[str],
) -> dict[str, object]:
    return {
        "view": str(view),
        "metrics_ms": {str(k): float(v or 0.0) for k, v in metrics_ms.items()},
        "budget_ms": {str(k): float(v or 0.0) for k, v in budgets_ms.items()},
        "overruns": [str(x) for x in list(overruns or []) if str(x).strip()],
    }


def _append_perf_history(
    *,
    snapshot_key: str,
    payload: Mapping[str, object],
) -> None:
    raw_history = st.session_state.get(_PERF_HISTORY_KEY, [])
    history: list[dict[str, object]] = [
        dict(row) for row in raw_history if isinstance(row, Mapping)
    ]
    captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    metrics = payload.get("metrics_ms")
    budgets = payload.get("budget_ms")
    overruns = payload.get("overruns")
    metrics_map = metrics if isinstance(metrics, Mapping) else {}
    budgets_map = budgets if isinstance(budgets, Mapping) else {}
    overruns_seq = (
        overruns
        if isinstance(overruns, Sequence) and not isinstance(overruns, (str, bytes))
        else []
    )
    overruns_list = [str(x) for x in overruns_seq if str(x).strip()]
    row: dict[str, object] = {
        "captured_at_utc": captured_at,
        "snapshot_key": str(snapshot_key),
        "view": str(payload.get("view", "") or ""),
        "metrics_ms": dict(metrics_map),
        "budget_ms": dict(budgets_map),
        "overruns": list(overruns_list),
        "overrun_count": int(len(overruns_list)),
        "total_ms": float(metrics_map.get("total", 0.0) or 0.0),
        "total_budget_ms": float(budgets_map.get("total", 0.0) or 0.0),
    }

    if history:
        prev = history[-1]
        if (
            str(prev.get("snapshot_key", "") or "") == str(row["snapshot_key"])
            and prev.get("metrics_ms") == row.get("metrics_ms")
            and prev.get("budget_ms") == row.get("budget_ms")
            and prev.get("overruns") == row.get("overruns")
        ):
            prev["captured_at_utc"] = captured_at
            history[-1] = prev
        else:
            history.append(row)
    else:
        history.append(row)

    if len(history) > _PERF_HISTORY_MAX_ROWS:
        history = history[-_PERF_HISTORY_MAX_ROWS:]
    st.session_state[_PERF_HISTORY_KEY] = history


def perf_history_rows(*, limit: int | None = None) -> list[dict[str, object]]:
    raw_history = st.session_state.get(_PERF_HISTORY_KEY, [])
    history = [dict(row) for row in raw_history if isinstance(row, Mapping)]
    if limit is None:
        return history
    max_rows = max(0, int(limit))
    if max_rows == 0:
        return []
    return history[-max_rows:]


def clear_perf_history() -> int:
    removed = len(perf_history_rows())
    st.session_state[_PERF_HISTORY_KEY] = []
    return int(removed)


def list_perf_snapshots() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    latest_seen_by_key: dict[str, str] = {}
    for row in perf_history_rows(limit=_PERF_HISTORY_MAX_ROWS):
        snapshot_key = str(row.get("snapshot_key", "") or "")
        if not snapshot_key:
            continue
        latest_seen_by_key[snapshot_key] = str(row.get("captured_at_utc", "") or "")
    for raw_key, raw_value in st.session_state.items():
        key = str(raw_key)
        if not key.endswith("::perf_snapshot"):
            continue
        if not isinstance(raw_value, Mapping):
            continue
        view = str(raw_value.get("view", "") or "")
        metrics = raw_value.get("metrics_ms")
        budgets = raw_value.get("budget_ms")
        overruns = raw_value.get("overruns")
        if not isinstance(metrics, Mapping) or not isinstance(budgets, Mapping):
            continue
        normalized_metrics = {str(k): float(v or 0.0) for k, v in metrics.items()}
        normalized_budgets = {str(k): float(v or 0.0) for k, v in budgets.items()}
        payload = _normalize_snapshot_payload(
            view=view,
            metrics_ms=normalized_metrics,
            budgets_ms=normalized_budgets,
            overruns=(
                overruns
                if isinstance(overruns, Sequence) and not isinstance(overruns, (str, bytes))
                else []
            ),
        )
        # Keep the latest timestamp seen in history for this snapshot key when available.
        latest_seen = latest_seen_by_key.get(key, "")
        if latest_seen:
            payload["captured_at_utc"] = latest_seen
        out[key] = dict(payload)
    return out


def render_perf_footer(
    *,
    snapshot_key: str,
    view: str,
    ordered_blocks: Sequence[str],
    metrics_ms: Mapping[str, float],
    budgets_ms: Mapping[str, float],
    caption_prefix: str = "Perf",
    emit_captions: bool = True,
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
    payload = _normalize_snapshot_payload(
        view=str(view),
        metrics_ms=normalized_metrics,
        budgets_ms=normalized_budgets,
        overruns=overruns,
    )
    st.session_state[str(snapshot_key)] = payload
    _append_perf_history(snapshot_key=str(snapshot_key), payload=payload)
    if emit_captions and parts:
        st.caption(f"{caption_prefix} {view}: {' · '.join(parts)}")
    if emit_captions and overruns:
        st.caption(f"Budget excedido en: {', '.join(overruns)}")
    return overruns
