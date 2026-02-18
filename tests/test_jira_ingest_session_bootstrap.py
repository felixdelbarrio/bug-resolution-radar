from __future__ import annotations

from typing import Any, Optional

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ingest import jira_ingest as jira_mod


class _FakeResponse:
    def __init__(self, status_code: int, *, payload: Optional[dict[str, Any]] = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


def _source() -> dict[str, str]:
    return {
        "country": "México",
        "alias": "MX Core",
        "source_id": "jira:mexico:mx-core",
        "jql": "project = 13008",
    }


def test_jira_does_not_open_browser_when_cookie_already_exists(monkeypatch: Any) -> None:
    opened: list[str] = []

    def fake_open(url: str, browser: str) -> bool:
        opened.append(f"{browser}:{url}")
        return True

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(200, payload={"displayName": "Tester"})

    monkeypatch.setattr(jira_mod, "_open_url_in_configured_browser", fake_open)
    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod, "get_jira_session_cookie", lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz"
    )

    ok, msg, _ = jira_mod.ingest_jira(
        settings=Settings(JIRA_BASE_URL="https://jira.globaldevtools.bbva.com", JIRA_BROWSER="chrome"),
        dry_run=True,
        source=_source(),
    )

    assert ok is True
    assert "OK Jira autenticado" in msg
    assert opened == []


def test_jira_opens_browser_only_when_cookie_missing(monkeypatch: Any) -> None:
    opened: list[str] = []
    cookie_values = [None, None, "JSESSIONID=abc; atlassian.xsrf.token=xyz"]

    def fake_open(url: str, browser: str) -> bool:
        opened.append(f"{browser}:{url}")
        return True

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(200, payload={"displayName": "Tester"})

    def fake_cookie(browser: str, host: str) -> str:
        value = cookie_values.pop(0) if cookie_values else "JSESSIONID=abc"
        return str(value or "")

    monkeypatch.setattr(jira_mod, "_open_url_in_configured_browser", fake_open)
    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(jira_mod, "get_jira_session_cookie", fake_cookie)
    monkeypatch.setenv("JIRA_BROWSER_LOGIN_WAIT_SECONDS", "5")
    monkeypatch.setenv("JIRA_BROWSER_LOGIN_POLL_SECONDS", "0.5")
    monkeypatch.delenv("JIRA_BROWSER_LOGIN_URL", raising=False)

    ok, msg, _ = jira_mod.ingest_jira(
        settings=Settings(JIRA_BASE_URL="https://jira.globaldevtools.bbva.com", JIRA_BROWSER="chrome"),
        dry_run=True,
        source=_source(),
    )

    assert ok is True
    assert "OK Jira autenticado" in msg
    assert opened
    assert "/secure/Dashboard.jspa" in opened[0]
