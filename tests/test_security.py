from __future__ import annotations

import pytest

from bug_resolution_radar.common.security import sanitize_cookie_header, validate_service_base_url


def test_validate_service_base_url_accepts_https_and_normalizes() -> None:
    out = validate_service_base_url(
        "https://jira.example.com/jira/?foo=bar#frag",
        service_name="Jira",
    )
    assert out == "https://jira.example.com/jira"


@pytest.mark.parametrize(
    "url",
    [
        "http://jira.example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://10.0.0.12",
        "https://user:pass@jira.example.com",
        "",
    ],
)
def test_validate_service_base_url_rejects_insecure_or_risky_hosts(url: str) -> None:
    with pytest.raises(ValueError):
        validate_service_base_url(url, service_name="Jira")


def test_sanitize_cookie_header_removes_invalid_pairs() -> None:
    out = sanitize_cookie_header("a=1; bad name=2; __Host-id=abc; ; x=y")
    assert out == "a=1; __Host-id=abc; x=y"


def test_sanitize_cookie_header_rejects_header_injection() -> None:
    assert sanitize_cookie_header("a=1\r\nX-Evil: yes") is None
    assert sanitize_cookie_header("  ") is None
    assert sanitize_cookie_header(None) is None
