from __future__ import annotations

from typing import Any

import requests

from bug_resolution_radar.ingest import helix_ingest as helix_mod


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        text: str = "",
        payload: Any = None,
        url: str = "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/",
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self.url = url

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("No JSON payload configured")
        return self._payload


def test_is_session_expired_response_detects_known_error_marker() -> None:
    resp = _FakeResponse(
        403,
        text='{"error":"MOBILITY_ERROR_SESSION_EXPIRED"}',
        payload={"error": "MOBILITY_ERROR_SESSION_EXPIRED"},
    )

    assert helix_mod._is_session_expired_response(resp) is True


def test_ingest_helix_refreshes_session_and_retries_once(monkeypatch: Any) -> None:
    responses = [
        _FakeResponse(
            403,
            text='{"error":"MOBILITY_ERROR_SESSION_EXPIRED"}',
            payload={"error": "MOBILITY_ERROR_SESSION_EXPIRED"},
        ),
        _FakeResponse(
            200,
            payload={
                "total": 1,
                "objects": [
                    {
                        "values": {
                            "id": "INC0001",
                            "summary": "Issue de prueba",
                            "status": "Open",
                        }
                    }
                ],
            },
        ),
    ]

    calls = {"request": 0, "preflight": 0}

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        calls["request"] += 1
        return responses.pop(0)

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        calls["preflight"] += 1
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(
        helix_mod,
        "get_helix_session_cookie",
        lambda browser, host: "JSESSIONID=abc; XSRF-TOKEN=xyz; loginId=test-user",
    )
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)

    ok, msg, doc = helix_mod.ingest_helix(
        helix_base_url="https://itsmhelixbbva-smartit.onbmc.com/smartit",
        browser="chrome",
        organization="ENTERPRISE WEB SYSTEMS SERVICE OWNER",
        chunk_size=1,
        dry_run=False,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert doc is not None
    assert len(doc.items) == 1
    assert calls["request"] == 2
    assert calls["preflight"] >= 2


def test_ingest_helix_sends_expected_body_shape(monkeypatch: Any) -> None:
    captured_bodies = []

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        captured_bodies.append(kwargs.get("json"))
        return _FakeResponse(200, payload={"total": 0, "objects": []})

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(
        helix_mod,
        "get_helix_session_cookie",
        lambda browser, host: "JSESSIONID=abc; XSRF-TOKEN=xyz; loginId=test-user",
    )
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)

    ok, msg, _ = helix_mod.ingest_helix(
        helix_base_url="https://itsmhelixbbva-smartit.onbmc.com/smartit",
        browser="chrome",
        organization="ENTERPRISE WEB SYSTEMS SERVICE OWNER",
        chunk_size=75,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert captured_bodies
    body = captured_bodies[0]
    assert body["attributeNames"] == [
        "slaStatus",
        "priority",
        "incidentType",
        "id",
        "assignee",
        "status",
        "summary",
        "service",
    ]
    assert body["customAttributeNames"] == [
        "bbva_closeddate",
        "bbva_matrixservicen1",
        "bbva_sourceservicen1",
        "bbva_startdatetime",
    ]
    assert body["chunkInfo"] == {"startIndex": 0, "chunkSize": 75}
    assert body["sortInfo"] == {}
    assert body["filterCriteria"]["statusMappings"] == ["open", "close"]
    assert body["filterCriteria"]["incidentTypes"] == [
        "User Service Restoration",
        "Security Incident",
    ]
    assert body["filterCriteria"]["organizations"] == ["ENTERPRISE WEB SYSTEMS SERVICE OWNER"]
    assert body["filterCriteria"]["priorities"] == ["High", "Low", "Medium", "Critical"]
    assert body["filterCriteria"]["companies"] == [{"name": "BBVA México"}]
    assert "riskLevel" not in body["filterCriteria"]
