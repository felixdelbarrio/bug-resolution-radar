from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from bug_resolution_radar.api.app import create_app
from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.telemetry import TelemetryStore, sanitize_event


def test_sanitize_event_keeps_only_diagnostic_fields() -> None:
    event = sanitize_event(
        {
            "layer": "frontend",
            "name": "api_request",
            "route": "/api/issues",
            "status": "error",
            "durationMs": 123.456,
            "summary": "contenido sensible",
            "details": {
                "metric": "render",
                "issueKey": "RAD-123",
                "message": "cookie=secret",
            },
        }
    )

    assert event["durationMs"] == 123.46
    assert event["details"] == {"metric": "render"}
    assert "summary" not in event
    assert "RAD-123" not in json.dumps(event)
    assert "secret" not in json.dumps(event)

    note_event = sanitize_event({"route": "/api/notes/RAD-123/entries/abc123"})
    assert note_event["route"] == "/api/notes/:id/entries/:id"


def test_store_builds_backend_and_frontend_summary(tmp_path: Path) -> None:
    store = TelemetryStore(tmp_path / "events.jsonl")
    store.append_many(
        [
            {
                "layer": "backend",
                "name": "api_request",
                "route": "/api/bootstrap",
                "durationMs": 100,
                "status": "success",
            },
            {
                "layer": "frontend",
                "name": "api_request",
                "route": "/api/bootstrap",
                "durationMs": 200,
                "status": "error",
            },
        ]
    )

    summary = store.summary(days=30)
    exported = store.export(days=30)

    assert summary["eventCount"] == 2
    assert summary["errorCount"] == 1
    assert summary["averageDurationMs"] == 150
    assert summary["byLayer"] == {"backend": 1, "frontend": 1}
    assert exported["privacy"]["localOnly"] is True
    assert exported["methodology"]["durationStatisticsExcludeZero"] is True
    assert len(exported["events"]) == 2


def test_api_accepts_sanitized_events_and_exports_json(tmp_path: Path, monkeypatch) -> None:
    telemetry_file = tmp_path / "telemetry.jsonl"
    export_dir = tmp_path / "configured-downloads"
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_TELEMETRY_PATH", str(telemetry_file))
    monkeypatch.setattr(
        "bug_resolution_radar.api.app.load_settings",
        lambda: Settings(REPORT_PPT_DOWNLOAD_DIR=str(export_dir)),
    )
    client = TestClient(create_app())

    accepted = client.post(
        "/api/telemetry/events",
        json={
            "events": [
                {
                    "layer": "frontend",
                    "name": "client_error",
                    "status": "error",
                    "durationMs": 12,
                    "details": {"message": "do not persist", "metric": "render"},
                }
            ]
        },
    )
    summary = client.get("/api/telemetry/summary?days=30")
    exported = client.post("/api/telemetry/export/save", json={"days": 30})

    assert accepted.status_code == 200
    assert accepted.json() == {"accepted": 1}
    assert summary.json()["eventCount"] == 1
    assert summary.json()["errorCount"] == 1
    assert exported.status_code == 200
    saved_path = Path(exported.json()["savedPath"])
    assert saved_path.parent == export_dir
    assert saved_path.suffix == ".json"
    saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert "do not persist" not in saved_path.read_text(encoding="utf-8")
    assert saved_payload["events"][0]["details"] == {"metric": "render"}
