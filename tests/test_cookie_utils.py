from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bug_resolution_radar.ingest.cookie_utils import (
    build_cookie_header_for_hosts,
    candidate_domains_from_host,
    cookie_applies_to_host,
    load_cookie_jar,
)


@dataclass
class _Cookie:
    domain: str
    name: str
    value: str


def test_cookie_applies_to_host_matches_exact_and_subdomain() -> None:
    assert cookie_applies_to_host(".bbva.com", "jira.bbva.com") is True
    assert cookie_applies_to_host("jira.bbva.com", "jira.bbva.com") is True
    assert cookie_applies_to_host("bbva.com", "other.com") is False


def test_candidate_domains_from_host_orders_without_duplicates() -> None:
    assert candidate_domains_from_host("jira.globaldevtools.bbva.com") == [
        "jira.globaldevtools.bbva.com",
        "globaldevtools.bbva.com",
        "bbva.com",
    ]


def test_load_cookie_jar_handles_getter_errors() -> None:
    def _getter_fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("boom")

    assert load_cookie_jar(_getter_fail, domain_name="bbva.com") is None


def test_build_cookie_header_for_hosts_filters_and_preserves_first_value() -> None:
    jars = [
        [
            _Cookie(domain=".bbva.com", name="JSESSIONID", value="first"),
            _Cookie(domain=".other.com", name="IGNORE", value="x"),
        ],
        [
            _Cookie(domain=".bbva.com", name="JSESSIONID", value="second"),
            _Cookie(domain=".bbva.com", name="TOKEN", value="abc"),
        ],
    ]

    header = build_cookie_header_for_hosts(jars, hosts=["jira.globaldevtools.bbva.com"])

    assert header == "JSESSIONID=first; TOKEN=abc"


def test_build_cookie_header_for_hosts_returns_none_without_valid_hosts() -> None:
    jars = [[_Cookie(domain=".bbva.com", name="A", value="1")]]
    assert build_cookie_header_for_hosts(jars, hosts=[""]) is None
