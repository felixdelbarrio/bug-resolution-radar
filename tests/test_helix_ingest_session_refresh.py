from __future__ import annotations

import re
from typing import Any

import pytest
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


@pytest.fixture(autouse=True)
def _default_arsql_setup(monkeypatch: Any) -> None:
    monkeypatch.setenv("HELIX_ARSQL_DATASOURCE_UID", "ZFPVLzQnz")
    monkeypatch.setenv("HELIX_ARSQL_BASE_URL", "https://itsmhelixbbva-ir1.onbmc.com")
    monkeypatch.delenv("HELIX_ARSQL_DASHBOARD_URL", raising=False)


def test_is_session_expired_response_detects_known_error_marker() -> None:
    resp = _FakeResponse(
        403,
        text='{"error":"MOBILITY_ERROR_SESSION_EXPIRED"}',
        payload={"error": "MOBILITY_ERROR_SESSION_EXPIRED"},
    )

    assert helix_mod._is_session_expired_response(resp) is True


def test_ingest_helix_refreshes_session_and_retries_once(monkeypatch: Any) -> None:
    columns = list(helix_mod._ARSQL_SELECT_ALIASES)
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
                "columns": columns,
                "rows": [
                    [
                        "INC0001",
                        "Low",
                        "Issue de prueba",
                        "Open",
                        "Ana",
                        "Incidencia",
                        "Service A",
                        "Impact A",
                        "BBVA México",
                        "ENTERPRISE WEB",
                        "ENTERPRISE WEB",
                        1704067200000,
                        None,
                        1704067200000,
                        1704067200000,
                        "IDGTEST0001",
                    ]
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
        browser="chrome",
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
        return _FakeResponse(
            200, payload={"columns": list(helix_mod._ARSQL_SELECT_ALIASES), "rows": []}
        )

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
        browser="chrome",
        chunk_size=75,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert captured_bodies
    body = captured_bodies[0]
    assert body["output_type"] == "Table"
    assert "sql" in body
    sql = str(body["sql"])
    assert "FROM `HPD:Help Desk`" in sql
    assert "LIMIT 75 OFFSET 0" in sql
    assert "`HPD:Help Desk`.`BBVA_SourceServiceN1` IN ('ENTERPRISE WEB')" in sql
    assert "`HPD:Help Desk`.`BBVA_SourceServiceBUUG` IN ('BBVA México')" in sql


def test_ingest_helix_paginates_when_batch_is_smaller_than_requested_chunk(
    monkeypatch: Any,
) -> None:
    captured_offsets = []
    columns = list(helix_mod._ARSQL_SELECT_ALIASES)

    def _row(prefix: str, idx: int) -> list[Any]:
        return [
            f"{prefix}{idx}",
            "Low",
            f"Issue {prefix}{idx}",
            "Open",
            "Ana",
            "Incidencia",
            "Service A",
            "Impact A",
            "BBVA México",
            "ENTERPRISE WEB",
            "ENTERPRISE WEB",
            1704067200000,
            None,
            1704067200000,
            1704067200000,
            f"IDG{prefix}{idx}",
        ]

    responses = [
        _FakeResponse(
            200,
            payload={
                "total": 50,
                "columns": columns,
                "rows": [_row("INC-A-", i) for i in range(25)],
            },
        ),
        _FakeResponse(
            200,
            payload={
                "total": 50,
                "columns": columns,
                "rows": [_row("INC-B-", i) for i in range(25)],
            },
        ),
    ]

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        body = kwargs.get("json") or {}
        sql = str(body.get("sql") or "")
        match = re.search(r"OFFSET\s+(\d+)", sql, flags=re.IGNORECASE)
        captured_offsets.append(int(match.group(1)) if match else -1)
        return responses.pop(0)

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(
        helix_mod,
        "get_helix_session_cookie",
        lambda browser, host: "JSESSIONID=abc; XSRF-TOKEN=xyz; loginId=test-user",
    )
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)

    ok, msg, doc = helix_mod.ingest_helix(
        browser="chrome",
        chunk_size=75,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert doc is not None
    assert len(doc.items) == 50
    # First page starts at 0; second should advance by effective batch (25), not requested chunk (75).
    assert captured_offsets == [0, 25]


def test_ingest_helix_arsql_paginates_with_offset(monkeypatch: Any) -> None:
    offsets: list[int] = []
    columns = list(helix_mod._ARSQL_SELECT_ALIASES)
    responses = [
        _FakeResponse(
            200,
            payload={
                "columns": columns,
                "rows": [
                    [
                        "INC1001",
                        "Low",
                        "Issue A",
                        "Assigned",
                        "Ana",
                        "User Service Restoration",
                        "Service A",
                        "Impact A",
                        "BBVA México",
                        "ENTERPRISE WEB",
                        "ENTERPRISE WEB",
                        1704067200000,
                        None,
                        1704067200000,
                        1704067200000,
                        "IDGE189LA8XVSATJYQ1ATJYQ1AVIXN",
                    ],
                    [
                        "INC1002",
                        "High",
                        "Issue B",
                        "Closed",
                        "Luis",
                        "Security Incident",
                        "Service B",
                        "Impact B",
                        "BBVA México",
                        "ENTERPRISE WEB",
                        "ENTERPRISE WEB",
                        1704067200000,
                        1704153600000,
                        1704153600000,
                        1704067200000,
                        "IDGEXAMPLE0000002",
                    ],
                ],
            },
        ),
        _FakeResponse(
            200,
            payload={
                "columns": columns,
                "rows": [
                    [
                        "INC1003",
                        "Moderate",
                        "Issue C",
                        "Resolved",
                        "Noe",
                        "User Service Restoration",
                        "Service C",
                        "Impact C",
                        "BBVA México",
                        "ENTERPRISE WEB",
                        "ENTERPRISE WEB",
                        1704067200000,
                        None,
                        1704240000000,
                        1704067200000,
                        "IDGEXAMPLE0000003",
                    ]
                ],
            },
        ),
        _FakeResponse(200, payload={"columns": columns, "rows": []}),
    ]

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        body = kwargs.get("json") or {}
        sql = str(body.get("sql") or "")
        match = re.search(r"OFFSET\s+(\d+)", sql, flags=re.IGNORECASE)
        offsets.append(int(match.group(1)) if match else -1)
        return responses.pop(0)

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(
        helix_mod,
        "get_helix_session_cookie",
        lambda browser, host: "apt.uid=abc; apt.sid=def; RSSO_OIDC_1=ghi",
    )
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)
    monkeypatch.setenv("HELIX_ARSQL_DATASOURCE_UID", "ZFPVLzQnz")
    monkeypatch.setenv("HELIX_ARSQL_BASE_URL", "https://itsmhelixbbva-ir1.onbmc.com")
    monkeypatch.setenv("HELIX_ARSQL_LIMIT", "2")
    monkeypatch.setenv("HELIX_ARSQL_SOURCE_SERVICE_N1", "ENTERPRISE WEB")

    ok, msg, doc = helix_mod.ingest_helix(
        browser="chrome",
        chunk_size=2,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert doc is not None
    assert len(doc.items) == 3
    assert doc.items[0].url.endswith("/app/#/incidentPV/IDGE189LA8XVSATJYQ1ATJYQ1AVIXN")
    assert offsets == [0, 2, 3]


def test_ingest_helix_arsql_pages_when_tenant_ignores_requested_limit(monkeypatch: Any) -> None:
    offsets: list[int] = []
    columns = list(helix_mod._ARSQL_SELECT_ALIASES)
    base_row = [
        "INC",
        "Low",
        "Issue",
        "Assigned",
        "Ana",
        "User Service Restoration",
        "Service A",
        "Impact A",
        "BBVA México",
        "ENTERPRISE WEB",
        "ENTERPRISE WEB",
        1704067200000,
        None,
        1704067200000,
        1704067200000,
        "IDGBASE0000",
    ]

    def make_row(prefix: str, idx: int) -> list[Any]:
        row = list(base_row)
        row[0] = f"{prefix}{idx}"
        row[2] = f"Issue {prefix}{idx}"
        row[-1] = f"IDG{prefix}{idx}"
        return row

    responses = [
        _FakeResponse(
            200,
            payload={
                "columns": columns,
                "rows": [make_row("INC-A-", i) for i in range(25)],
            },
        ),
        _FakeResponse(
            200,
            payload={
                "columns": columns,
                "rows": [make_row("INC-B-", i) for i in range(25)],
            },
        ),
        _FakeResponse(200, payload={"columns": columns, "rows": []}),
    ]

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        body = kwargs.get("json") or {}
        sql = str(body.get("sql") or "")
        match = re.search(r"OFFSET\s+(\d+)", sql, flags=re.IGNORECASE)
        offsets.append(int(match.group(1)) if match else -1)
        return responses.pop(0)

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(
        helix_mod,
        "get_helix_session_cookie",
        lambda browser, host: "apt.uid=abc; apt.sid=def; RSSO_OIDC_1=ghi",
    )
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)
    monkeypatch.setenv("HELIX_ARSQL_DATASOURCE_UID", "ZFPVLzQnz")
    monkeypatch.setenv("HELIX_ARSQL_BASE_URL", "https://itsmhelixbbva-ir1.onbmc.com")
    monkeypatch.setenv("HELIX_ARSQL_LIMIT", "500")
    monkeypatch.setenv("HELIX_ARSQL_SOURCE_SERVICE_N1", "ENTERPRISE WEB")

    ok, msg, doc = helix_mod.ingest_helix(
        browser="chrome",
        chunk_size=500,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert doc is not None
    assert len(doc.items) == 50
    assert offsets == [0, 25, 50]


def test_ingest_helix_arsql_autodiscovers_datasource_uid(monkeypatch: Any) -> None:
    called_urls: list[str] = []

    def fake_request(
        session: requests.Session, method: str, url: str, timeout: Any, **kwargs: Any
    ) -> _FakeResponse:
        called_urls.append(url)
        return _FakeResponse(
            200, payload={"columns": list(helix_mod._ARSQL_SELECT_ALIASES), "rows": []}, url=url
        )

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        if url.endswith("/dashboards/api/datasources"):
            return _FakeResponse(
                200,
                payload=[
                    {"uid": "abc123", "type": "prometheus"},
                    {
                        "uid": "ZFPVLzQnz",
                        "type": "arsys",
                        "url": "/api/arsys/v1.0/report/arsqlquery",
                    },
                ],
                url=url,
            )
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(
        helix_mod,
        "get_helix_session_cookie",
        lambda browser, host: "apt.uid=abc; apt.sid=def; RSSO_OIDC_1=ghi",
    )
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)
    monkeypatch.setenv("HELIX_ARSQL_BASE_URL", "https://itsmhelixbbva-ir1.onbmc.com")
    monkeypatch.delenv("HELIX_ARSQL_DATASOURCE_UID", raising=False)

    ok, msg, _ = helix_mod.ingest_helix(
        browser="chrome",
        chunk_size=75,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert called_urls
    assert (
        "/dashboards/api/datasources/proxy/uid/ZFPVLzQnz/api/arsys/v1.0/report/arsqlquery"
        in called_urls[0]
    )


def test_ingest_helix_arsql_infers_ir1_host_and_uses_dashboards_preflight(monkeypatch: Any) -> None:
    called_urls: list[str] = []
    get_urls: list[str] = []

    def fake_request(
        session: requests.Session, method: str, url: str, timeout: Any, **kwargs: Any
    ) -> _FakeResponse:
        called_urls.append(url)
        return _FakeResponse(
            200, payload={"columns": list(helix_mod._ARSQL_SELECT_ALIASES), "rows": []}, url=url
        )

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        get_urls.append(url)
        if url == "https://itsmhelixbbva-ir1.onbmc.com/dashboards/api/datasources":
            return _FakeResponse(
                200,
                payload=[{"uid": "ZFPVLzQnz", "type": "bmchelix-ade-datasource"}],
                url=url,
            )
        if url == "https://itsmhelixbbva-smartit.onbmc.com/dashboards/api/datasources":
            return _FakeResponse(404, text="not found", url=url)
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(
        helix_mod,
        "get_helix_session_cookie",
        lambda browser, host: "apt.uid=abc; apt.sid=def; RSSO_OIDC_1=ghi",
    )
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)
    monkeypatch.delenv("HELIX_ARSQL_BASE_URL", raising=False)
    monkeypatch.delenv("HELIX_ARSQL_DATASOURCE_UID", raising=False)
    monkeypatch.delenv("HELIX_ARSQL_DASHBOARD_URL", raising=False)
    monkeypatch.setenv(
        "HELIX_DASHBOARD_URL",
        "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console",
    )

    ok, msg, _ = helix_mod.ingest_helix(
        browser="chrome",
        chunk_size=75,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert get_urls
    assert get_urls[0] == "https://itsmhelixbbva-ir1.onbmc.com/dashboards/"
    assert called_urls
    assert called_urls[0].startswith(
        "https://itsmhelixbbva-ir1.onbmc.com/dashboards/api/datasources/proxy/uid/ZFPVLzQnz/"
    )


def test_ingest_helix_bootstraps_browser_when_cookie_missing(monkeypatch: Any) -> None:
    opened_urls: list[str] = []

    def fake_open(url: str, browser: str) -> bool:
        opened_urls.append(f"{browser}:{url}")
        return True

    def fake_cookie(browser: str, host: str) -> str:
        if not opened_urls:
            return ""
        return "JSESSIONID=abc; XSRF-TOKEN=xyz; loginId=test-user"

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            200, payload={"columns": list(helix_mod._ARSQL_SELECT_ALIASES), "rows": []}
        )

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_open_url_in_configured_browser", fake_open)
    monkeypatch.setattr(
        helix_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: False,
    )
    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(helix_mod, "get_helix_session_cookie", fake_cookie)
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)
    monkeypatch.setenv("HELIX_BROWSER_LOGIN_WAIT_SECONDS", "5")
    monkeypatch.setenv("HELIX_BROWSER_LOGIN_POLL_SECONDS", "0.5")

    ok, msg, _ = helix_mod.ingest_helix(
        browser="chrome",
        chunk_size=75,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert opened_urls
    assert "/dashboards/" in opened_urls[0]


def test_ingest_helix_does_not_open_browser_when_target_page_is_already_open(
    monkeypatch: Any,
) -> None:
    opened_urls: list[str] = []

    def fake_open(url: str, browser: str) -> bool:
        opened_urls.append(f"{browser}:{url}")
        return True

    def fake_cookie(browser: str, host: str) -> str:
        return "JSESSIONID=abc; XSRF-TOKEN=xyz; loginId=test-user"

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            200, payload={"columns": list(helix_mod._ARSQL_SELECT_ALIASES), "rows": []}
        )

    def fake_get(self: requests.Session, url: str, timeout: Any) -> _FakeResponse:
        return _FakeResponse(200, text="ok", payload={"ok": True}, url=url)

    monkeypatch.setattr(helix_mod, "_open_url_in_configured_browser", fake_open)
    monkeypatch.setattr(
        helix_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )
    monkeypatch.setattr(helix_mod, "_request", fake_request)
    monkeypatch.setattr(helix_mod, "get_helix_session_cookie", fake_cookie)
    monkeypatch.setattr(requests.Session, "get", fake_get, raising=True)

    ok, msg, _ = helix_mod.ingest_helix(
        browser="chrome",
        chunk_size=75,
        dry_run=False,
        create_date_year=2026,
    )

    assert ok is True
    assert "ingesta Helix OK" in msg
    assert opened_urls == []


def test_ingest_helix_does_not_open_invalid_dashboards_url_when_host_missing(
    monkeypatch: Any,
) -> None:
    opened_urls: list[str] = []

    def fake_open(url: str, browser: str) -> bool:
        opened_urls.append(f"{browser}:{url}")
        return True

    monkeypatch.delenv("HELIX_ARSQL_BASE_URL", raising=False)
    monkeypatch.delenv("HELIX_DASHBOARD_URL", raising=False)
    monkeypatch.delenv("HELIX_ARSQL_DASHBOARD_URL", raising=False)
    monkeypatch.setattr(helix_mod, "_open_url_in_configured_browser", fake_open)

    ok, msg, _ = helix_mod.ingest_helix(
        browser="chrome",
        chunk_size=75,
        dry_run=True,
        create_date_year=2026,
    )

    assert ok is False
    assert "no se pudo resolver host ARSQL" in msg
    assert opened_urls == []
