"""Persistent storage for cross-session insights learning state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.insights_learning_store import (
    InsightsLearningStore,
    default_learning_path,
    learning_payload_hash,
    learning_scope_key,
)

LEARNING_STATE_KEY = "__insights_learning_state"
LEARNING_INTERACTIONS_KEY = "__insights_interactions"
LEARNING_SCOPE_KEY = "__insights_learning_scope"
LEARNING_STORE_PATH_SESSION_KEY = "__insights_learning_store_path"
LEARNING_LAST_SAVED_HASH_KEY = "__insights_learning_last_saved_hash"
LEARNING_BASELINE_SNAPSHOT_KEY = "__insights_session_baseline_snapshot"
LEARNING_LATEST_SNAPSHOT_KEY = "__insights_latest_snapshot"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def ensure_learning_session_loaded(*, settings: Settings) -> None:
    """Hydrate in-memory learning state for current country/source scope."""
    country = str(st.session_state.get("workspace_country") or "").strip()
    source_id = str(st.session_state.get("workspace_source_id") or "").strip()
    scope = learning_scope_key(country, source_id)
    path = default_learning_path(settings)

    cur_scope = str(st.session_state.get(LEARNING_SCOPE_KEY) or "").strip()
    cur_path = str(st.session_state.get(LEARNING_STORE_PATH_SESSION_KEY) or "").strip()
    if (
        cur_scope == scope
        and cur_path == str(path)
        and isinstance(st.session_state.get(LEARNING_STATE_KEY), dict)
    ):
        return

    store = InsightsLearningStore(path)
    store.load()
    state, interactions, baseline_snapshot = store.get_scope_bundle(scope)

    st.session_state[LEARNING_STATE_KEY] = state
    st.session_state[LEARNING_INTERACTIONS_KEY] = int(interactions)
    st.session_state[LEARNING_SCOPE_KEY] = scope
    st.session_state[LEARNING_STORE_PATH_SESSION_KEY] = str(path)
    st.session_state[LEARNING_BASELINE_SNAPSHOT_KEY] = baseline_snapshot
    st.session_state[LEARNING_LATEST_SNAPSHOT_KEY] = baseline_snapshot
    st.session_state[LEARNING_LAST_SAVED_HASH_KEY] = learning_payload_hash(
        state=state,
        interactions=interactions,
        snapshot=baseline_snapshot,
    )


def persist_learning_session() -> None:
    """Persist current in-session learning state to disk for active scope."""
    scope = str(st.session_state.get(LEARNING_SCOPE_KEY) or "").strip()
    path_txt = str(st.session_state.get(LEARNING_STORE_PATH_SESSION_KEY) or "").strip()
    if not scope or not path_txt:
        return

    state = _as_dict(st.session_state.get(LEARNING_STATE_KEY))
    interactions = int(st.session_state.get(LEARNING_INTERACTIONS_KEY, 0) or 0)
    snapshot = _as_dict(st.session_state.get(LEARNING_LATEST_SNAPSHOT_KEY))
    payload_hash = learning_payload_hash(state=state, interactions=interactions, snapshot=snapshot)
    if payload_hash == str(st.session_state.get(LEARNING_LAST_SAVED_HASH_KEY) or ""):
        return

    country = str(st.session_state.get("workspace_country") or "").strip()
    source_id = str(st.session_state.get("workspace_source_id") or "").strip()

    store = InsightsLearningStore(Path(path_txt))
    store.load()
    store.set_scope(
        scope,
        state=state,
        interactions=interactions,
        country=country,
        source_id=source_id,
        snapshot=snapshot,
    )
    store.save()
    st.session_state[LEARNING_LAST_SAVED_HASH_KEY] = payload_hash


def set_learning_snapshot(snapshot: Dict[str, Any], *, persist: bool = False) -> None:
    st.session_state[LEARNING_LATEST_SNAPSHOT_KEY] = _as_dict(snapshot)
    if persist:
        persist_learning_session()


def increment_learning_interactions(step: int = 1, *, persist: bool = True) -> None:
    cur = int(st.session_state.get(LEARNING_INTERACTIONS_KEY, 0) or 0)
    st.session_state[LEARNING_INTERACTIONS_KEY] = cur + max(step, 0)
    if persist:
        persist_learning_session()
