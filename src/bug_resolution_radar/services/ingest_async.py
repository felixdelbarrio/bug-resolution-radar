"""Async ingestion progress tracker for the React ingestion workspace."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List

from bug_resolution_radar.common.utils import now_iso
from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.ingest_runner import run_helix_ingest, run_jira_ingest

_CONNECTORS = {"jira", "helix"}


@dataclass
class _IngestProgress:
    connector: str
    run_id: int = 0
    state: str = "idle"  # idle | running | success | partial | error
    started_at: str = ""
    finished_at: str = ""
    total_sources: int = 0
    completed_sources: int = 0
    success_count: int = 0
    current_source_label: str = ""
    current_source_index: int = 0
    messages: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    result: Dict[str, Any] | None = None
    started_monotonic: float = 0.0
    max_run_seconds: int = 0


_LOCK = threading.Lock()
_PROGRESS: Dict[str, _IngestProgress] = {}
_RUNNING_WORKERS: Dict[str, tuple[int, threading.Thread]] = {}


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return int(default)


def _resolve_max_run_seconds(settings: Settings, *, connector: str, total_sources: int) -> int:
    token = str(connector or "").strip().lower()
    env_specific = str(os.getenv(f"INGEST_ASYNC_MAX_RUN_SECONDS_{token.upper()}", "")).strip()
    env_general = str(os.getenv("INGEST_ASYNC_MAX_RUN_SECONDS", "")).strip()
    configured = _coerce_int(env_specific or env_general, 0)
    if configured > 0:
        return max(60, configured)

    safe_sources = max(1, int(total_sources or 0))
    if token == "helix":
        per_source = _coerce_int(getattr(settings, "HELIX_MAX_INGEST_SECONDS", 900), 900)
        grace = 180
    else:
        per_source = _coerce_int(os.getenv("JIRA_MAX_INGEST_SECONDS", "600"), 600)
        grace = 120
    per_source = max(60, per_source)
    return min(24 * 3600, per_source * safe_sources + grace)


def _normalize_connector(connector: str) -> str:
    token = str(connector or "").strip().lower()
    if token not in _CONNECTORS:
        raise ValueError("Conector de ingesta no soportado.")
    return token


def _entry(connector: str) -> _IngestProgress:
    key = _normalize_connector(connector)
    existing = _PROGRESS.get(key)
    if existing is not None:
        return existing
    fresh = _IngestProgress(connector=key)
    _PROGRESS[key] = fresh
    return fresh


def _snapshot(entry: _IngestProgress) -> Dict[str, Any]:
    now_mono = time.monotonic()
    elapsed = 0
    if (
        str(entry.state or "").strip().lower() == "running"
        and float(entry.started_monotonic or 0.0) > 0
    ):
        elapsed = max(0, int(now_mono - float(entry.started_monotonic)))
    return {
        "connector": entry.connector,
        "runId": int(entry.run_id),
        "state": str(entry.state or "idle"),
        "active": str(entry.state or "").strip().lower() == "running",
        "startedAt": str(entry.started_at or ""),
        "finishedAt": str(entry.finished_at or ""),
        "totalSources": int(entry.total_sources),
        "completedSources": int(entry.completed_sources),
        "successCount": int(entry.success_count),
        "currentSourceLabel": str(entry.current_source_label or ""),
        "currentSourceIndex": int(entry.current_source_index or 0),
        "elapsedSeconds": int(elapsed),
        "summary": str(entry.summary or ""),
        "maxRunSeconds": int(entry.max_run_seconds or 0),
        "messages": [dict(msg) for msg in list(entry.messages or [])],
        "result": dict(entry.result or {}) if isinstance(entry.result, dict) else entry.result,
    }


@contextmanager
def _sync_settings_to_process_env(settings: Settings) -> Iterator[None]:
    previous: Dict[str, tuple[bool, str]] = {}
    for key, value in settings.model_dump().items():
        env_key = str(key)
        exists = env_key in os.environ
        previous[env_key] = (exists, str(os.environ.get(env_key, "")))
        if value is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = str(value)
    try:
        yield
    finally:
        for env_key, snapshot in previous.items():
            existed, old_value = snapshot
            if existed:
                os.environ[env_key] = old_value
            else:
                os.environ.pop(env_key, None)


def _start_progress(
    connector: str,
    *,
    total_sources: int,
    max_run_seconds: int,
) -> tuple[int, Dict[str, Any]] | None:
    key = _normalize_connector(connector)
    started_at_iso = now_iso()
    started_monotonic = time.monotonic()
    with _LOCK:
        entry = _entry(key)
        if entry.state == "running":
            return None
        entry.run_id = int(entry.run_id) + 1
        entry.state = "running"
        entry.started_at = started_at_iso
        entry.finished_at = ""
        entry.total_sources = max(0, int(total_sources))
        entry.completed_sources = 0
        entry.success_count = 0
        entry.current_source_label = ""
        entry.current_source_index = 0
        entry.messages = []
        entry.summary = ""
        entry.result = None
        entry.started_monotonic = float(started_monotonic)
        entry.max_run_seconds = max(0, int(max_run_seconds))
        return int(entry.run_id), _snapshot(entry)


def _clear_running_worker(connector: str, *, run_id: int) -> None:
    worker_state = _RUNNING_WORKERS.get(connector)
    if worker_state is None:
        return
    worker_run_id, _ = worker_state
    if int(worker_run_id) != int(run_id):
        return
    _RUNNING_WORKERS.pop(connector, None)


def _recover_stuck_run_if_needed(connector: str) -> bool:
    key = _normalize_connector(connector)
    with _LOCK:
        entry = _entry(key)
        if entry.state != "running":
            return False

        worker_state = _RUNNING_WORKERS.get(key)
        worker_is_alive = False
        if worker_state is not None:
            worker_run_id, worker = worker_state
            worker_is_alive = int(worker_run_id) == int(entry.run_id) and bool(worker.is_alive())

        now_mono = time.monotonic()
        max_run = max(0, int(entry.max_run_seconds or 0))
        elapsed = max(0.0, now_mono - float(entry.started_monotonic or now_mono))
        timed_out = max_run > 0 and elapsed > float(max_run)
        orphaned = not worker_is_alive
        if not timed_out and not orphaned:
            return False

        detail = (
            f"Ingesta {key.upper()} marcada como huérfana; se liberó para relanzar."
            if orphaned and not timed_out
            else (
                f"Ingesta {key.upper()} superó el máximo de ejecución "
                f"({int(elapsed)}s > {max_run}s); se liberó para relanzar."
            )
        )
        entry.messages.append({"ok": False, "message": detail})
        entry.state = "error"
        entry.finished_at = now_iso()
        entry.summary = "La ingesta se detuvo por watchdog de ejecución."
        entry.current_source_label = ""
        entry.current_source_index = 0
        entry.result = {
            "state": "error",
            "summary": entry.summary,
            "success_count": int(entry.success_count),
            "total_sources": int(entry.total_sources),
            "messages": [dict(msg) for msg in list(entry.messages or [])],
        }
        _clear_running_worker(key, run_id=int(entry.run_id))
        return True


def _append_progress(
    connector: str,
    *,
    run_id: int,
    ok: bool,
    message: str,
    completed_sources: int,
    total_sources: int,
) -> None:
    key = _normalize_connector(connector)
    with _LOCK:
        entry = _entry(key)
        if int(entry.run_id) != int(run_id):
            return
        if entry.state != "running":
            return
        entry.total_sources = max(0, int(total_sources))
        entry.completed_sources = max(0, min(int(completed_sources), int(entry.total_sources)))
        if ok:
            entry.success_count = int(entry.success_count) + 1
        entry.messages.append({"ok": bool(ok), "message": str(message or "").strip()})


def _mark_source_started(
    connector: str,
    *,
    run_id: int,
    source_label: str,
    source_index: int,
    total_sources: int,
) -> None:
    key = _normalize_connector(connector)
    label = str(source_label or "").strip()
    with _LOCK:
        entry = _entry(key)
        if int(entry.run_id) != int(run_id):
            return
        if entry.state != "running":
            return
        entry.total_sources = max(0, int(total_sources))
        entry.current_source_label = label
        entry.current_source_index = max(0, int(source_index))
        if label:
            entry.messages.append(
                {
                    "ok": True,
                    "message": (
                        f"Iniciando {label} "
                        f"({max(1, int(source_index))}/{max(1, int(total_sources))})."
                    ),
                }
            )


def _finish_progress(connector: str, *, run_id: int, result: Dict[str, Any]) -> None:
    key = _normalize_connector(connector)
    normalized_result = dict(result or {})
    with _LOCK:
        entry = _entry(key)
        if int(entry.run_id) != int(run_id):
            return
        entry.state = str(normalized_result.get("state") or "error").strip().lower()
        entry.finished_at = now_iso()
        entry.summary = str(normalized_result.get("summary") or "").strip()
        entry.total_sources = int(
            normalized_result.get("total_sources") or entry.total_sources or 0
        )
        entry.current_source_label = ""
        entry.current_source_index = 0
        if int(entry.total_sources) > 0:
            entry.completed_sources = int(entry.total_sources)
        else:
            entry.completed_sources = max(0, int(entry.completed_sources))
        entry.success_count = int(
            normalized_result.get("success_count") or entry.success_count or 0
        )
        if not entry.messages:
            entry.messages = [
                {"ok": bool(item.get("ok")), "message": str(item.get("message") or "").strip()}
                for item in list(normalized_result.get("messages") or [])
            ]
        entry.result = normalized_result
        _clear_running_worker(key, run_id=run_id)


def _fail_progress(connector: str, *, run_id: int, detail: str) -> None:
    key = _normalize_connector(connector)
    with _LOCK:
        entry = _entry(key)
        if int(entry.run_id) != int(run_id):
            return
        entry.messages.append({"ok": False, "message": str(detail or "").strip()})
        entry.state = "error"
        entry.finished_at = now_iso()
        entry.summary = "La ingesta terminó con error."
        entry.current_source_label = ""
        entry.current_source_index = 0
        entry.result = {
            "state": "error",
            "summary": entry.summary,
            "success_count": int(entry.success_count),
            "total_sources": int(entry.total_sources),
            "messages": [dict(msg) for msg in list(entry.messages or [])],
        }
        _clear_running_worker(key, run_id=run_id)


def get_ingest_progress(connector: str) -> Dict[str, Any]:
    key = _normalize_connector(connector)
    _recover_stuck_run_if_needed(key)
    with _LOCK:
        return _snapshot(_entry(key))


def start_ingest_job(
    connector: str,
    *,
    settings: Settings,
    selected_sources: List[Dict[str, str]],
) -> Dict[str, Any]:
    key = _normalize_connector(connector)
    sources = [dict(source) for source in list(selected_sources or [])]
    _recover_stuck_run_if_needed(key)
    max_run_seconds = _resolve_max_run_seconds(
        settings,
        connector=key,
        total_sources=len(sources),
    )
    started = _start_progress(
        key,
        total_sources=len(sources),
        max_run_seconds=max_run_seconds,
    )
    if started is None:
        snapshot = get_ingest_progress(key)
        return {"started": False, **snapshot}

    run_id, initial_snapshot = started
    settings_snapshot = settings.model_copy(deep=True)

    def _worker() -> None:
        try:
            with _sync_settings_to_process_env(settings_snapshot):
                if key == "jira":
                    result = run_jira_ingest(
                        settings_snapshot,
                        selected_sources=sources,
                        on_source_start=lambda label, index, total: _mark_source_started(
                            key,
                            run_id=run_id,
                            source_label=label,
                            source_index=index,
                            total_sources=total,
                        ),
                        on_source_result=lambda ok, msg, completed, total: _append_progress(
                            key,
                            run_id=run_id,
                            ok=ok,
                            message=msg,
                            completed_sources=completed,
                            total_sources=total,
                        ),
                    )
                else:
                    result = run_helix_ingest(
                        settings_snapshot,
                        selected_sources=sources,
                        on_source_start=lambda label, index, total: _mark_source_started(
                            key,
                            run_id=run_id,
                            source_label=label,
                            source_index=index,
                            total_sources=total,
                        ),
                        on_source_result=lambda ok, msg, completed, total: _append_progress(
                            key,
                            run_id=run_id,
                            ok=ok,
                            message=msg,
                            completed_sources=completed,
                            total_sources=total,
                        ),
                    )
            _finish_progress(key, run_id=run_id, result=result)
        except Exception as exc:
            _fail_progress(
                key,
                run_id=run_id,
                detail=f"Error inesperado de orquestación {key.upper()}: {type(exc).__name__}: {exc}",
            )

    worker_thread = threading.Thread(target=_worker, name=f"{key}-ingest-worker", daemon=True)
    with _LOCK:
        _RUNNING_WORKERS[key] = (run_id, worker_thread)
    worker_thread.start()
    return {"started": True, **initial_snapshot}
