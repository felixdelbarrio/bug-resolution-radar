from __future__ import annotations

from bug_resolution_radar.ui.pages import ingest_page


def _reset_progress_state() -> None:
    with ingest_page._INGEST_PROGRESS_LOCK:
        ingest_page._INGEST_PROGRESS_BY_CONNECTOR.clear()


def test_progress_start_clears_previous_messages() -> None:
    _reset_progress_state()

    run_id_1 = ingest_page._progress_start("jira", total_sources=2)
    assert run_id_1 is not None
    ingest_page._progress_append_message(
        "jira", ok=True, msg="mensaje run 1", count_source=True, run_id=run_id_1
    )
    ingest_page._progress_finish("jira", state="success", summary="run 1 ok", run_id=run_id_1)

    run_id_2 = ingest_page._progress_start("jira", total_sources=1)
    assert run_id_2 is not None
    snapshot = ingest_page._progress_snapshot("jira")

    assert int(snapshot["run_id"]) == int(run_id_2)
    assert snapshot["state"] == "running"
    assert int(snapshot["completed_sources"]) == 0
    assert list(snapshot["messages"]) == []


def test_progress_ignores_stale_messages_from_previous_run() -> None:
    _reset_progress_state()

    run_id_1 = ingest_page._progress_start("helix", total_sources=1)
    assert run_id_1 is not None
    ingest_page._progress_finish("helix", state="success", summary="run 1 ok", run_id=run_id_1)

    run_id_2 = ingest_page._progress_start("helix", total_sources=1)
    assert run_id_2 is not None

    ingest_page._progress_append_message(
        "helix", ok=True, msg="mensaje viejo", count_source=True, run_id=run_id_1
    )
    ingest_page._progress_finish("helix", state="success", summary="run viejo", run_id=run_id_1)

    snapshot_running = ingest_page._progress_snapshot("helix")
    assert int(snapshot_running["run_id"]) == int(run_id_2)
    assert snapshot_running["state"] == "running"
    assert list(snapshot_running["messages"]) == []

    ingest_page._progress_append_message(
        "helix", ok=True, msg="mensaje actual", count_source=True, run_id=run_id_2
    )
    ingest_page._progress_finish("helix", state="success", summary="run 2 ok", run_id=run_id_2)
    snapshot_done = ingest_page._progress_snapshot("helix")
    assert snapshot_done["state"] == "success"
    assert list(snapshot_done["messages"]) == [(True, "mensaje actual")]
