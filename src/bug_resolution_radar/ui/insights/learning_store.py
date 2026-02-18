"""Persistent storage for cross-session insights learning state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.utils import now_iso

LEARNING_STATE_KEY = "__insights_learning_state"
LEARNING_INTERACTIONS_KEY = "__insights_interactions"
LEARNING_SCOPE_KEY = "__insights_learning_scope"
LEARNING_STORE_PATH_SESSION_KEY = "__insights_learning_store_path"
LEARNING_LAST_SAVED_HASH_KEY = "__insights_learning_last_saved_hash"
LEARNING_BASELINE_SNAPSHOT_KEY = "__insights_session_baseline_snapshot"
LEARNING_LATEST_SNAPSHOT_KEY = "__insights_latest_snapshot"


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def learning_scope_key(country: str, source_id: str) -> str:
    c = str(country or "").strip() or "global"
    s = str(source_id or "").strip() or "all-sources"
    return f"{c}::{s}"


def default_learning_path(settings: Settings) -> Path:
    raw = str(getattr(settings, "INSIGHTS_LEARNING_PATH", "") or "").strip()
    if raw:
        return Path(raw)
    return Path("data/insights_learning.json")


def learning_payload_hash(
    *, state: Dict[str, Any], interactions: int, snapshot: Dict[str, Any]
) -> str:
    payload = {
        "state": _as_dict(state),
        "interactions": int(interactions),
        "snapshot": _as_dict(snapshot),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


class InsightsLearningStore:
    """Local JSON store with per-scope learning state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._raw: Dict[str, Any] = {"version": 1, "scopes": {}}

    def load(self) -> None:
        if not self.path.exists():
            self._raw = {"version": 1, "scopes": {}}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._raw = {"version": 1, "scopes": {}}
            return
        if not isinstance(data, dict):
            self._raw = {"version": 1, "scopes": {}}
            return
        scopes = data.get("scopes")
        if not isinstance(scopes, dict):
            scopes = {}
        self._raw = {"version": int(data.get("version", 1) or 1), "scopes": scopes}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._raw, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get_scope(self, scope: str) -> Tuple[Dict[str, Any], int]:
        scopes = _as_dict(self._raw.get("scopes"))
        record = _as_dict(scopes.get(scope))
        state = _as_dict(record.get("state"))
        interactions = _safe_int(record.get("interactions"), default=0)
        return state, interactions

    def get_scope_bundle(self, scope: str) -> Tuple[Dict[str, Any], int, Dict[str, Any]]:
        scopes = _as_dict(self._raw.get("scopes"))
        record = _as_dict(scopes.get(scope))
        state = _as_dict(record.get("state"))
        interactions = _safe_int(record.get("interactions"), default=0)
        snapshot = _as_dict(record.get("last_snapshot"))
        return state, interactions, snapshot

    def set_scope(
        self,
        scope: str,
        *,
        state: Dict[str, Any],
        interactions: int,
        country: str,
        source_id: str,
        snapshot: Dict[str, Any] | None = None,
    ) -> None:
        scopes = _as_dict(self._raw.get("scopes"))
        current = _as_dict(scopes.get(scope))
        resolved_snapshot = (
            _as_dict(snapshot)
            if isinstance(snapshot, dict)
            else _as_dict(current.get("last_snapshot"))
        )
        scopes[scope] = {
            "state": _as_dict(state),
            "interactions": int(interactions),
            "country": str(country or ""),
            "source_id": str(source_id or ""),
            "last_snapshot": resolved_snapshot,
            "updated_at": now_iso(),
        }
        self._raw["scopes"] = scopes
        self._raw["version"] = 1

    def remove_source(self, source_id: str) -> int:
        """Remove all scope records associated with a source id."""
        sid = str(source_id or "").strip()
        if not sid:
            return 0

        scopes = _as_dict(self._raw.get("scopes"))
        kept: Dict[str, Any] = {}
        removed = 0
        suffix = f"::{sid}"

        for scope_key, record in scopes.items():
            record_dict = _as_dict(record)
            rec_source_id = str(record_dict.get("source_id") or "").strip()
            scope_txt = str(scope_key or "")
            if rec_source_id == sid or (not rec_source_id and scope_txt.endswith(suffix)):
                removed += 1
                continue
            kept[scope_txt] = record_dict

        if removed > 0:
            self._raw["scopes"] = kept
            self._raw["version"] = 1

        return removed

    def count_source_scopes(self, source_id: str) -> int:
        """Count scope records associated with a source id."""
        sid = str(source_id or "").strip()
        if not sid:
            return 0

        scopes = _as_dict(self._raw.get("scopes"))
        suffix = f"::{sid}"
        count = 0
        for scope_key, record in scopes.items():
            record_dict = _as_dict(record)
            rec_source_id = str(record_dict.get("source_id") or "").strip()
            scope_txt = str(scope_key or "")
            if rec_source_id == sid or (not rec_source_id and scope_txt.endswith(suffix)):
                count += 1
        return count


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
