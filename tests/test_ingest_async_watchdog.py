from __future__ import annotations

import importlib
import time
from pathlib import Path
from typing import Any

from bug_resolution_radar.config import Settings, build_source_id

ingest_async = importlib.import_module("bug_resolution_radar.services.ingest_async")


def _reset_state() -> None:
    with ingest_async._LOCK:
        ingest_async._PROGRESS.clear()
        ingest_async._RUNNING_WORKERS.clear()


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        DATA_PATH=str((tmp_path / "issues.json").resolve()),
        HELIX_DATA_PATH=str((tmp_path / "helix.json").resolve()),
        JIRA_SOURCES_JSON='[{"country":"España","alias":"Core","jql":"project = RADAR"}]',
    )


def test_get_ingest_progress_marks_orphan_running_job_as_error() -> None:
    _reset_state()

    run_id, _ = ingest_async._start_progress("jira", total_sources=1, max_run_seconds=600)
    assert int(run_id) > 0

    snapshot = ingest_async.get_ingest_progress("jira")
    assert snapshot["state"] == "error"
    assert snapshot["active"] is False
    assert "watchdog" in str(snapshot["summary"]).lower()
    assert snapshot["messages"]


def test_start_ingest_job_recovers_stale_running_state_and_restarts(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    _reset_state()
    settings = _settings(tmp_path)
    source_id = build_source_id("jira", "España", "Core")

    old_run_id, _ = ingest_async._start_progress("jira", total_sources=1, max_run_seconds=1)
    with ingest_async._LOCK:
        entry = ingest_async._entry("jira")
        entry.started_monotonic = float(time.monotonic() - 10.0)

    monkeypatch.setattr(
        ingest_async,
        "run_jira_ingest",
        lambda *args, **kwargs: {
            "state": "success",
            "summary": "ok",
            "success_count": 1,
            "total_sources": 1,
            "messages": [{"ok": True, "message": "ok"}],
        },
    )

    started = ingest_async.start_ingest_job(
        "jira",
        settings=settings,
        selected_sources=[{"source_id": source_id, "country": "España", "alias": "Core"}],
    )
    assert started["started"] is True
    assert int(started["runId"]) == int(old_run_id) + 1

    deadline = time.monotonic() + 2.0
    latest = started
    while time.monotonic() < deadline:
        latest = ingest_async.get_ingest_progress("jira")
        if latest["state"] != "running":
            break
        time.sleep(0.02)
    assert latest["state"] == "success"
