"""Persistent per-source circuit breaker for ingestion hardening."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..common.utils import now_iso

_STATE_LOCK = threading.Lock()


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if token in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if token in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _source_key(connector: str, source_id: str) -> str:
    return f"{str(connector or '').strip().lower()}::{str(source_id or '').strip().lower()}"


def _ts_to_iso(ts: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class CircuitDecision:
    allowed: bool
    reason: str
    consecutive_failures: int
    recent_failures: int
    open_until_ts: float
    open_until_iso: str


class IngestCircuitBreaker:
    """Fail-fast guard for unstable sources with cooldown and persistence."""

    def __init__(
        self,
        *,
        enabled: Optional[bool] = None,
        state_path: Optional[str] = None,
        failure_threshold: Optional[int] = None,
        window_seconds: Optional[int] = None,
        cooldown_seconds: Optional[int] = None,
        max_failure_events: Optional[int] = None,
    ) -> None:
        self.enabled = (
            _coerce_bool(os.getenv("INGEST_CIRCUIT_ENABLED"), default=True)
            if enabled is None
            else bool(enabled)
        )
        self.state_path = str(state_path or "").strip() or str(
            os.getenv("INGEST_CIRCUIT_STATE_PATH", "data/observability/ingest_circuit_state.json")
        )
        self.failure_threshold = max(
            1,
            (
                _coerce_int(os.getenv("INGEST_CIRCUIT_FAILURE_THRESHOLD"), 3)
                if failure_threshold is None
                else int(failure_threshold)
            ),
        )
        self.window_seconds = max(
            1,
            (
                _coerce_int(os.getenv("INGEST_CIRCUIT_WINDOW_SECONDS"), 1800)
                if window_seconds is None
                else int(window_seconds)
            ),
        )
        self.cooldown_seconds = max(
            1,
            (
                _coerce_int(os.getenv("INGEST_CIRCUIT_COOLDOWN_SECONDS"), 900)
                if cooldown_seconds is None
                else int(cooldown_seconds)
            ),
        )
        self.max_failure_events = max(
            10,
            (
                _coerce_int(os.getenv("INGEST_CIRCUIT_MAX_FAILURE_EVENTS"), 120)
                if max_failure_events is None
                else int(max_failure_events)
            ),
        )

    def _default_state(self) -> Dict[str, Any]:
        return {"schema_version": "1.0", "updated_at": now_iso(), "sources": {}}

    def _load_state(self) -> Dict[str, Any]:
        path = Path(self.state_path)
        if not path.exists():
            return self._default_state()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_state()
        if not isinstance(payload, dict):
            return self._default_state()
        sources = payload.get("sources")
        if not isinstance(sources, dict):
            payload["sources"] = {}
        return payload

    def _save_state(self, state: Dict[str, Any]) -> None:
        path = Path(self.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = now_iso()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(state, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        tmp.replace(path)

    def _prune_failures(self, failures: List[float], *, now_ts: float) -> List[float]:
        lower = float(now_ts) - float(self.window_seconds)
        pruned = [float(ts) for ts in failures if float(ts) >= lower]
        if len(pruned) > self.max_failure_events:
            pruned = pruned[-self.max_failure_events :]
        return pruned

    def _decision_from_entry(self, entry: Dict[str, Any], *, now_ts: float) -> CircuitDecision:
        failures = self._prune_failures(list(entry.get("failures") or []), now_ts=now_ts)
        consecutive = max(0, _coerce_int(entry.get("consecutive_failures"), 0))
        open_until = float(entry.get("open_until_ts") or 0.0)
        if open_until > float(now_ts):
            return CircuitDecision(
                allowed=False,
                reason="open",
                consecutive_failures=consecutive,
                recent_failures=len(failures),
                open_until_ts=open_until,
                open_until_iso=_ts_to_iso(open_until),
            )
        return CircuitDecision(
            allowed=True,
            reason="closed",
            consecutive_failures=consecutive,
            recent_failures=len(failures),
            open_until_ts=open_until,
            open_until_iso=_ts_to_iso(open_until) if open_until > 0 else "",
        )

    def allow(
        self, *, connector: str, source_id: str, now_ts: Optional[float] = None
    ) -> CircuitDecision:
        if not self.enabled:
            return CircuitDecision(
                allowed=True,
                reason="disabled",
                consecutive_failures=0,
                recent_failures=0,
                open_until_ts=0.0,
                open_until_iso="",
            )
        key = _source_key(connector, source_id)
        now_value = float(time.time() if now_ts is None else now_ts)
        with _STATE_LOCK:
            state = self._load_state()
            sources = state.setdefault("sources", {})
            if not isinstance(sources, dict):
                sources = {}
                state["sources"] = sources
            entry = sources.setdefault(
                key,
                {
                    "failures": [],
                    "consecutive_failures": 0,
                    "open_until_ts": 0.0,
                    "last_failure_message": "",
                    "last_failure_at": "",
                    "last_success_at": "",
                },
            )
            entry["failures"] = self._prune_failures(
                list(entry.get("failures") or []), now_ts=now_value
            )
            open_until = float(entry.get("open_until_ts") or 0.0)
            # Cooldown elapsed: close circuit and allow a trial run.
            if open_until > 0 and open_until <= now_value:
                entry["open_until_ts"] = 0.0
            self._save_state(state)
            return self._decision_from_entry(entry, now_ts=now_value)

    def record_success(
        self,
        *,
        connector: str,
        source_id: str,
        now_ts: Optional[float] = None,
    ) -> CircuitDecision:
        if not self.enabled:
            return CircuitDecision(
                allowed=True,
                reason="disabled",
                consecutive_failures=0,
                recent_failures=0,
                open_until_ts=0.0,
                open_until_iso="",
            )
        key = _source_key(connector, source_id)
        now_value = float(time.time() if now_ts is None else now_ts)
        with _STATE_LOCK:
            state = self._load_state()
            sources = state.setdefault("sources", {})
            if not isinstance(sources, dict):
                sources = {}
                state["sources"] = sources
            entry = sources.setdefault(key, {})
            entry["failures"] = []
            entry["consecutive_failures"] = 0
            entry["open_until_ts"] = 0.0
            entry["last_success_at"] = _ts_to_iso(now_value)
            entry["last_failure_message"] = ""
            self._save_state(state)
            return self._decision_from_entry(entry, now_ts=now_value)

    def record_failure(
        self,
        *,
        connector: str,
        source_id: str,
        message: str,
        now_ts: Optional[float] = None,
    ) -> CircuitDecision:
        if not self.enabled:
            return CircuitDecision(
                allowed=True,
                reason="disabled",
                consecutive_failures=0,
                recent_failures=0,
                open_until_ts=0.0,
                open_until_iso="",
            )
        key = _source_key(connector, source_id)
        now_value = float(time.time() if now_ts is None else now_ts)
        with _STATE_LOCK:
            state = self._load_state()
            sources = state.setdefault("sources", {})
            if not isinstance(sources, dict):
                sources = {}
                state["sources"] = sources
            entry = sources.setdefault(
                key,
                {
                    "failures": [],
                    "consecutive_failures": 0,
                    "open_until_ts": 0.0,
                    "last_failure_message": "",
                    "last_failure_at": "",
                    "last_success_at": "",
                },
            )
            recent_failures = self._prune_failures(
                list(entry.get("failures") or []), now_ts=now_value
            )
            had_recent_failure = bool(recent_failures)
            recent_failures.append(now_value)
            failures = self._prune_failures(recent_failures, now_ts=now_value)
            entry["failures"] = failures
            previous_consecutive = max(0, _coerce_int(entry.get("consecutive_failures"), 0))
            consecutive = (previous_consecutive + 1) if had_recent_failure else 1
            entry["consecutive_failures"] = consecutive
            entry["last_failure_message"] = str(message or "").strip()
            entry["last_failure_at"] = _ts_to_iso(now_value)
            should_open = (
                consecutive >= self.failure_threshold and len(failures) >= self.failure_threshold
            )
            if should_open:
                entry["open_until_ts"] = now_value + float(self.cooldown_seconds)
            self._save_state(state)
            return self._decision_from_entry(entry, now_ts=now_value)
