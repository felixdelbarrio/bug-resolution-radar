from __future__ import annotations

import pytest

from bug_resolution_radar.ingest.helix_session import get_helix_session_cookie
from bug_resolution_radar.ingest.jira_session import get_jira_session_cookie


def test_jira_session_cookie_manual_mode_uses_header_without_browser_access(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_COOKIE_SOURCE", "manual")
    monkeypatch.setenv("JIRA_COOKIE_HEADER", "JSESSIONID=abc; atlassian.xsrf.token=xyz")

    cookie = get_jira_session_cookie(browser="chrome", host="jira.example.com")

    assert cookie is not None
    assert "JSESSIONID=abc" in cookie


def test_helix_session_cookie_manual_mode_uses_header_without_browser_access(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_COOKIE_SOURCE", "manual")
    monkeypatch.setenv("HELIX_COOKIE_HEADER", "JSESSIONID=abc; XSRF-TOKEN=xyz; loginId=test-user")

    cookie = get_helix_session_cookie(browser="chrome", host="itsmhelixbbva-smartit.onbmc.com")

    assert cookie is not None
    assert "JSESSIONID=abc" in cookie
    assert "XSRF-TOKEN=xyz" in cookie


def test_jira_session_cookie_manual_mode_requires_cookie_header(monkeypatch) -> None:
    monkeypatch.setenv("JIRA_COOKIE_SOURCE", "manual")
    monkeypatch.delenv("JIRA_COOKIE_HEADER", raising=False)

    with pytest.raises(ValueError, match="JIRA_COOKIE_SOURCE=manual"):
        get_jira_session_cookie(browser="chrome", host="jira.example.com")


def test_helix_session_cookie_manual_mode_requires_cookie_header(monkeypatch) -> None:
    monkeypatch.setenv("HELIX_COOKIE_SOURCE", "manual")
    monkeypatch.delenv("HELIX_COOKIE_HEADER", raising=False)

    with pytest.raises(ValueError, match="HELIX_COOKIE_SOURCE=manual"):
        get_helix_session_cookie(browser="chrome", host="itsmhelixbbva-smartit.onbmc.com")
