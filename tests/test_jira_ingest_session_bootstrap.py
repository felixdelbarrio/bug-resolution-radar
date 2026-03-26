from __future__ import annotations

from typing import Any, Optional

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ingest import jira_ingest as jira_mod


class _FakeResponse:
    def __init__(
        self, status_code: int, *, payload: Optional[dict[str, Any]] = None, text: str = ""
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeInvalidJSONResponse(_FakeResponse):
    def __init__(self, status_code: int, *, text: str = "") -> None:
        super().__init__(status_code=status_code, payload=None, text=text)
        self.headers = {"Content-Type": "text/html"}

    def json(self) -> dict[str, Any]:
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


class _FakeSession:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = list(statuses)
        self.calls = 0

    def request(self, method: str, url: str, timeout: int = 30, **kwargs: Any) -> _FakeResponse:
        self.calls += 1
        code = self.statuses.pop(0) if self.statuses else 200
        return _FakeResponse(code)


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
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )
    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod,
        "get_jira_session_cookie",
        lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz",
    )

    ok, msg, _ = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com", JIRA_BROWSER="chrome"
        ),
        dry_run=True,
        source=_source(),
    )

    assert ok is True
    assert "OK Jira autenticado" in msg
    assert opened == []


def test_jira_does_not_open_browser_when_cookie_exists_even_if_target_is_not_open(
    monkeypatch: Any,
) -> None:
    opened: list[str] = []

    def fake_open(url: str, browser: str) -> bool:
        opened.append(f"{browser}:{url}")
        return True

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(200, payload={"displayName": "Tester"})

    monkeypatch.setattr(jira_mod, "_open_url_in_configured_browser", fake_open)
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: False,
    )
    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod,
        "get_jira_session_cookie",
        lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz",
    )

    ok, msg, _ = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com", JIRA_BROWSER="chrome"
        ),
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
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: False,
    )
    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(jira_mod, "get_jira_session_cookie", fake_cookie)
    monkeypatch.setenv("JIRA_BROWSER_LOGIN_WAIT_SECONDS", "5")
    monkeypatch.setenv("JIRA_BROWSER_LOGIN_POLL_SECONDS", "0.5")
    monkeypatch.delenv("JIRA_BROWSER_LOGIN_URL", raising=False)

    ok, msg, _ = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com", JIRA_BROWSER="chrome"
        ),
        dry_run=True,
        source=_source(),
    )

    assert ok is True
    assert "OK Jira autenticado" in msg
    assert opened
    assert "/secure/Dashboard.jspa" in opened[0]


def test_jira_does_not_open_browser_when_target_page_is_already_open(monkeypatch: Any) -> None:
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
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )
    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(jira_mod, "get_jira_session_cookie", fake_cookie)
    monkeypatch.setenv("JIRA_BROWSER_LOGIN_WAIT_SECONDS", "5")
    monkeypatch.setenv("JIRA_BROWSER_LOGIN_POLL_SECONDS", "0.5")
    monkeypatch.delenv("JIRA_BROWSER_LOGIN_URL", raising=False)

    ok, msg, _ = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com", JIRA_BROWSER="chrome"
        ),
        dry_run=True,
        source=_source(),
    )

    assert ok is True
    assert "OK Jira autenticado" in msg
    assert opened == []


def test_jira_bootstrap_opens_single_login_url_when_target_status_is_unknown(
    monkeypatch: Any,
) -> None:
    opened: list[str] = []
    cookie_values = [None, None, None, "JSESSIONID=abc; atlassian.xsrf.token=xyz"]

    def fake_open(url: str, browser: str) -> bool:
        opened.append(f"{browser}:{url}")
        return True

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(200, payload={"displayName": "Tester"})

    def fake_cookie(browser: str, host: str) -> str:
        value = cookie_values.pop(0) if cookie_values else "JSESSIONID=abc"
        return str(value or "")

    monkeypatch.setattr(jira_mod, "_open_url_in_configured_browser", fake_open)
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: None,
    )
    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(jira_mod, "get_jira_session_cookie", fake_cookie)
    monkeypatch.setenv("JIRA_BROWSER_LOGIN_WAIT_SECONDS", "5")
    monkeypatch.setenv("JIRA_BROWSER_LOGIN_POLL_SECONDS", "0.5")

    ok, msg, _ = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com", JIRA_BROWSER="chrome"
        ),
        dry_run=True,
        source=_source(),
    )

    assert ok is True
    assert "OK Jira autenticado" in msg
    assert opened == ["chrome:https://jira.globaldevtools.bbva.com/jira/secure/Dashboard.jspa"]


def test_jira_dry_run_tries_origin_when_base_contains_issue_path(monkeypatch: Any) -> None:
    requested_urls: list[str] = []

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        url = str(args[2])
        requested_urls.append(url)
        if url == "https://jira.globaldevtools.bbva.com/rest/api/3/myself":
            return _FakeResponse(200, payload={"displayName": "Tester"})
        return _FakeResponse(404, text="<html><title>Oops, you've found a dead link</title></html>")

    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod,
        "get_jira_session_cookie",
        lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz",
    )
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )

    ok, msg, _ = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com/browse/ME-123",
            JIRA_BROWSER="chrome",
        ),
        dry_run=True,
        source=_source(),
    )

    assert ok is True
    assert "OK Jira autenticado" in msg
    assert "https://jira.globaldevtools.bbva.com/rest/api/3/myself" in requested_urls


def test_jira_ingest_falls_back_to_latest_api(monkeypatch: Any) -> None:
    requested_urls: list[str] = []

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        method = str(args[1]).upper()
        url = str(args[2])
        requested_urls.append(url)
        if (
            method == "POST"
            and url == "https://jira.globaldevtools.bbva.com/rest/api/latest/search"
        ):
            return _FakeResponse(200, payload={"issues": [], "total": 0})
        return _FakeResponse(404, text="<html><title>Oops, you've found a dead link</title></html>")

    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod,
        "get_jira_session_cookie",
        lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz",
    )
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )

    ok, msg, doc = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com/browse/ME-123",
            JIRA_BROWSER="chrome",
        ),
        dry_run=False,
        source=_source(),
    )

    assert ok is True
    assert "ingesta Jira OK (0 issues" in msg
    assert doc is not None
    assert "https://jira.globaldevtools.bbva.com/rest/api/latest/search" in requested_urls


def test_jira_search_404_html_adds_base_url_hint(monkeypatch: Any) -> None:
    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            404, text="<!DOCTYPE html><html><title>Oops, you've found a dead link</title>"
        )

    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod,
        "get_jira_session_cookie",
        lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz",
    )
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )

    ok, msg, doc = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com/browse/ME-123",
            JIRA_BROWSER="chrome",
        ),
        dry_run=False,
        source=_source(),
    )

    assert ok is False
    assert doc is None
    assert "Revisa JIRA_BASE_URL" in msg
    assert "/browse/INC-123" in msg


def test_jira_search_payload_uses_expand_array(monkeypatch: Any) -> None:
    seen_expand: list[Any] = []

    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        method = str(args[1]).upper()
        url = str(args[2])
        if method == "POST" and "/search" in url:
            payload = dict(kwargs.get("json") or {})
            seen_expand.append(payload.get("expand"))
            return _FakeResponse(200, payload={"issues": [], "total": 0})
        return _FakeResponse(200, payload={"displayName": "Tester"})

    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod,
        "get_jira_session_cookie",
        lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz",
    )
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )

    ok, msg, doc = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com",
            JIRA_BROWSER="chrome",
        ),
        dry_run=False,
        source=_source(),
    )

    assert ok is True
    assert "ingesta Jira OK" in msg
    assert doc is not None
    assert seen_expand
    assert seen_expand[0] == ["renderedFields"]


def test_jira_dry_run_handles_non_json_myself_response(monkeypatch: Any) -> None:
    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        _ = kwargs
        method = str(args[1]).upper()
        url = str(args[2])
        if method == "GET" and url.endswith("/myself"):
            return _FakeInvalidJSONResponse(200, text="")
        return _FakeResponse(404, text="<html>dead link</html>")

    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod,
        "get_jira_session_cookie",
        lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz",
    )
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )

    ok, msg, doc = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com",
            JIRA_BROWSER="chrome",
        ),
        dry_run=True,
        source=_source(),
    )

    assert ok is False
    assert doc is None
    assert "respuesta no JSON" in msg


def test_jira_search_handles_http_200_with_invalid_json(monkeypatch: Any) -> None:
    def fake_request(*args: Any, **kwargs: Any) -> _FakeResponse:
        _ = kwargs
        method = str(args[1]).upper()
        url = str(args[2])
        if method == "POST" and "/search" in url:
            return _FakeInvalidJSONResponse(200, text="")
        return _FakeResponse(404, text="<html>dead link</html>")

    monkeypatch.setattr(jira_mod, "_request", fake_request)
    monkeypatch.setattr(
        jira_mod,
        "get_jira_session_cookie",
        lambda browser, host: "JSESSIONID=abc; atlassian.xsrf.token=xyz",
    )
    monkeypatch.setattr(
        jira_mod,
        "_is_target_page_open_in_configured_browser",
        lambda url, browser: True,
    )

    ok, msg, doc = jira_mod.ingest_jira(
        settings=Settings(
            JIRA_BASE_URL="https://jira.globaldevtools.bbva.com",
            JIRA_BROWSER="chrome",
        ),
        dry_run=False,
        source=_source(),
    )

    assert ok is False
    assert doc is None
    assert "respuesta no JSON" in msg


def test_request_retries_transient_502_until_success() -> None:
    session = _FakeSession([502, 502, 200])

    r = jira_mod._request(session, "GET", "https://jira.example.com/rest/api/2/myself")

    assert r.status_code == 200
    assert session.calls == 3


def test_request_does_not_retry_non_transient_status() -> None:
    session = _FakeSession([404, 200, 200])

    r = jira_mod._request(session, "GET", "https://jira.example.com/rest/api/2/myself")

    assert r.status_code == 404
    assert session.calls == 1
