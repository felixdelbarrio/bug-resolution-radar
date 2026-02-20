"""Constants and semantic labels used across dashboard sections."""

from __future__ import annotations

from typing import Dict, List, Tuple

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


def canonical_status_order() -> List[str]:
    return list(CANONICAL_STATUS_ORDER)


def canonical_status_rank_map() -> Dict[str, int]:
    return {status.lower(): idx for idx, status in enumerate(CANONICAL_STATUS_ORDER)}
