"""Async ingestion progress tracker for the React ingestion workspace."""

from __future__ import annotations

import os
import threading
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
    messages: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    result: Dict[str, Any] | None = None


_LOCK = threading.Lock()
_PROGRESS: Dict[str, _IngestProgress] = {}


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
        "summary": str(entry.summary or ""),
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


def _start_progress(connector: str, *, total_sources: int) -> tuple[int, Dict[str, Any]] | None:
    key = _normalize_connector(connector)
    with _LOCK:
        entry = _entry(key)
        if entry.state == "running":
            return None
        entry.run_id = int(entry.run_id) + 1
        entry.state = "running"
        entry.started_at = now_iso()
        entry.finished_at = ""
        entry.total_sources = max(0, int(total_sources))
        entry.completed_sources = 0
        entry.success_count = 0
        entry.messages = []
        entry.summary = ""
        entry.result = None
        return int(entry.run_id), _snapshot(entry)


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
        entry.result = {
            "state": "error",
            "summary": entry.summary,
            "success_count": int(entry.success_count),
            "total_sources": int(entry.total_sources),
            "messages": [dict(msg) for msg in list(entry.messages or [])],
        }


def get_ingest_progress(connector: str) -> Dict[str, Any]:
    key = _normalize_connector(connector)
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
    started = _start_progress(key, total_sources=len(sources))
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

    threading.Thread(target=_worker, name=f"{key}-ingest-worker", daemon=True).start()
    return {"started": True, **initial_snapshot}
