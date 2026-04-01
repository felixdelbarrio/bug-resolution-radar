"""Constants and semantic labels used across dashboard sections."""

from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

# Single source of truth for dashboard status ordering.
CANONICAL_STATUS_ORDER: Tuple[str, ...] = (
    "New",
    "Analysing",
    "Ready",
    "Blocked",
    "En progreso",
    "To Rework",
    "Test",
    "Ready To Verify",
    "Accepted",
    "Ready to Deploy",
    "Deployed",
)

# Shared chart labels to avoid wording drift between dashboard destinations.
Y_AXIS_LABEL_OPEN_ISSUES = "Incidencias abiertas"
Y_AXIS_LABEL_FINALIZED_ISSUES = "Incidencias finalizadas"


def canonical_status_order() -> List[str]:
    return list(CANONICAL_STATUS_ORDER)


def canonical_status_rank_map() -> Dict[str, int]:
    return {status.lower(): idx for idx, status in enumerate(CANONICAL_STATUS_ORDER)}


def order_statuses_canonical(statuses: Iterable[str]) -> List[str]:
    """Order statuses by canonical flow while preserving relative order for unknown states."""
    rank_map = canonical_status_rank_map()

    def key_fn(pair: tuple[int, str]) -> tuple[int, int]:
        idx, status = pair
        key = str(status or "").strip().lower()
        return (rank_map.get(key, 10_000), idx)

    return [status for _, status in sorted(enumerate(list(statuses or [])), key=key_fn)]
