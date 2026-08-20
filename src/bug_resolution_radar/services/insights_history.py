"""Synchronize operational measurements with the persistent insights cache."""

from __future__ import annotations

from threading import RLock
from typing import Any, Sequence

from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.insights_learning_store import (
    InsightsLearningStore,
    default_learning_path,
    learning_scope_key,
)

_HISTORY_LOCK = RLock()


def history_source_token(source_ids: Sequence[str]) -> str:
    clean = sorted(
        {str(source_id or "").strip() for source_id in source_ids if str(source_id or "").strip()}
    )
    return clean[0] if len(clean) == 1 else "*"


def record_scope_measurement(
    settings: Settings,
    *,
    country: str,
    source_ids: Sequence[str],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Record a distinct snapshot and return the prior comparable measurement."""
    source_token = history_source_token(source_ids)
    scope = learning_scope_key(country, source_token)
    with _HISTORY_LOCK:
        store = InsightsLearningStore(default_learning_path(settings))
        store.load()
        baseline, changed = store.record_snapshot(
            scope,
            snapshot=snapshot,
            country=country,
            source_id=source_token,
        )
        if changed:
            store.save()
    return baseline
