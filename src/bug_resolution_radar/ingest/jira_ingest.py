"""Jira ingestion pipeline using configured JQL sources."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..common.security import sanitize_cookie_header, validate_service_base_url
from ..common.utils import now_iso
from ..config import Settings, build_source_id, jira_sources, supported_countries
from ..models.schema import IssuesDocument, NormalizedIssue
from .browser_runtime import (
    is_target_page_open_in_configured_browser as _is_target_page_open_in_browser,
)
from .browser_runtime import (
    open_url_in_configured_browser as _open_url_in_browser,
)
from .browser_runtime import (
    open_urls_in_configured_browser as _open_urls_in_browser,
)
from .jira_session import get_jira_session_cookie


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _request(session: requests.Session, method: str, url: str, **kwargs: Any) -> requests.Response:
    r = session.request(method, url, timeout=30, **kwargs)
    if r.status_code in (429, 503):
        raise RuntimeError("rate limited")
    return r


def _open_url_in_configured_browser(url: str, browser: str) -> bool:
    return _open_url_in_browser(url=url, browser=browser)


def _is_target_page_open_in_configured_browser(url: str, browser: str) -> Optional[bool]:
    return _is_target_page_open_in_browser(url=url, browser=browser)


def _root_from_url(url: str) -> str:
    txt = str(url or "").strip()
    if not txt:
        return ""
    parsed = urlparse(txt)
    scheme = str(parsed.scheme or "").strip()
    host = str(parsed.hostname or "").strip()
    if not scheme or not host:
        return ""
    return f"{scheme}://{host}"


def _open_urls_in_configured_browser(urls: List[str], browser: str) -> int:
    return int(_open_urls_in_browser(urls=urls, browser=browser))


def _ensure_target_page_open_in_configured_browser(url: str, browser: str) -> bool:
    is_open = _is_target_page_open_in_configured_browser(url, browser)
    if is_open is True:
        return True
    if is_open is False:
        return _open_url_in_configured_browser(url, browser)
    return False


def _jira_cookie_bootstrap_urls(login_url: str) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for candidate in [str(login_url or "").strip(), _root_from_url(login_url)]:
        txt = str(candidate or "").strip()
        if not txt or txt in seen:
            continue
        seen.add(txt)
        out.append(txt)
    return out


def _cookie_names_from_header(cookie_header: str) -> List[str]:
    names: List[str] = []
    for part in (cookie_header or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name = part.split("=", 1)[0].strip()
        if name:
            names.append(name)
    return sorted(set(names))


def _has_jira_auth_cookie(cookie_names: List[str]) -> bool:
    got = {str(x).strip().lower() for x in cookie_names}
    if not got:
        return False
    wanted = {
        "jsessionid",
        "atlassian.xsrf.token",
        "atlassian.account.id",
        "cloud.session.token",
        "seraph.rememberme.cookie",
    }
    if any(x in got for x in wanted):
        return True
    if any(name.startswith("atlassian.") for name in got):
        return True
    return True


def _bootstrap_jira_cookie_from_browser(
    *,
    browser: str,
    host: str,
    login_url: str,
    wait_seconds: int,
    poll_seconds: float,
    page_already_ensured: bool = False,
) -> Optional[str]:
    if not page_already_ensured:
        page_already_ensured = _ensure_target_page_open_in_configured_browser(login_url, browser)
    if not page_already_ensured:
        _open_urls_in_configured_browser(_jira_cookie_bootstrap_urls(login_url), browser)

    try:
        existing = get_jira_session_cookie(browser=browser, host=host)
    except Exception:
        existing = None
    existing = sanitize_cookie_header(existing)
    if existing and _has_jira_auth_cookie(_cookie_names_from_header(existing)):
        return existing

    deadline = time.monotonic() + float(wait_seconds)
    while time.monotonic() < deadline:
        try:
            candidate = get_jira_session_cookie(browser=browser, host=host)
        except Exception:
            candidate = None
        candidate = sanitize_cookie_header(candidate)
        if candidate and _has_jira_auth_cookie(_cookie_names_from_header(candidate)):
            return candidate
        time.sleep(poll_seconds)
    return None


def _resolve_source_scope(
    settings: Settings, source: Optional[Dict[str, str]]
) -> Tuple[str, str, str, str]:
    countries = supported_countries(settings)
    fallback_country = countries[0] if countries else "México"

    if source:
        country = str(source.get("country") or "").strip() or fallback_country
        alias = str(source.get("alias") or "").strip() or "Jira principal"
        jql = str(source.get("jql") or "").strip()
        source_id = str(source.get("source_id") or "").strip() or build_source_id(
            "jira", country, alias
        )
        return country, alias, source_id, jql

    configured_sources = jira_sources(settings)
    if configured_sources:
        primary = configured_sources[0]
        country = str(primary.get("country") or "").strip() or fallback_country
        alias = str(primary.get("alias") or "").strip() or "Jira principal"
        jql = str(primary.get("jql") or "").strip()
        source_id = str(primary.get("source_id") or "").strip() or build_source_id(
            "jira", country, alias
        )
        return country, alias, source_id, jql

    alias = "Jira principal"
    source_id = build_source_id("jira", fallback_country, alias)
    return fallback_country, alias, source_id, ""


def _merge_key(issue: NormalizedIssue) -> str:
    sid = str(issue.source_id or "").strip().lower()
    key = str(issue.key or "").strip().upper()
    if sid:
        return f"{sid}::{key}"
    return key


def ingest_jira(
    settings: Settings,
    dry_run: bool = False,
    existing_doc: Optional[IssuesDocument] = None,
    source: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str, Optional[IssuesDocument]]:
    country, alias, source_id, jql = _resolve_source_scope(settings, source)
    source_label = f"{country} · {alias}"

    if not jql:
        return False, f"{source_label}: configura JQL obligatorio para la fuente Jira.", None

    try:
        base = validate_service_base_url(settings.JIRA_BASE_URL, service_name="Jira")
    except ValueError as e:
        return False, f"{source_label}: {e}", None

    # Jira accepts whitespace, but sending a single-line JQL avoids issues with env/UI formatting.
    jql = jql.replace("\r", " ").replace("\n", " ")
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    base_candidates: List[str] = [base]
    if not base.endswith("/jira"):
        base_candidates.append(base + "/jira")

    jira_web_base = base if base.endswith("/jira") else f"{base}/jira"
    login_url = str(os.getenv("JIRA_BROWSER_LOGIN_URL", "")).strip() or (
        f"{jira_web_base}/secure/Dashboard.jspa"
    )
    wait_seconds = max(5, int(float(os.getenv("JIRA_BROWSER_LOGIN_WAIT_SECONDS", "90"))))
    poll_seconds = max(0.5, float(os.getenv("JIRA_BROWSER_LOGIN_POLL_SECONDS", "2")))
    pre_cookie_page_ready = _ensure_target_page_open_in_configured_browser(
        login_url, settings.JIRA_BROWSER
    )

    try:
        host = urlparse(base).hostname or ""
        cookie = get_jira_session_cookie(browser=settings.JIRA_BROWSER, host=host)
        cookie_error = ""
    except Exception as e:
        cookie = None
        cookie_error = str(e)
    cookie = sanitize_cookie_header(cookie)
    cookie_names = _cookie_names_from_header(cookie or "")
    if not cookie or not _has_jira_auth_cookie(cookie_names):
        bootstrapped_cookie = _bootstrap_jira_cookie_from_browser(
            browser=settings.JIRA_BROWSER,
            host=host,
            login_url=login_url,
            wait_seconds=wait_seconds,
            poll_seconds=poll_seconds,
            page_already_ensured=pre_cookie_page_ready,
        )
        if bootstrapped_cookie:
            cookie = bootstrapped_cookie

    if not cookie:
        details = f" Detalle: {cookie_error}" if cookie_error else ""
        return (
            False,
            f"{source_label}: no se encontró cookie Jira válida en '{settings.JIRA_BROWSER}'.{details}",
            None,
        )

    session.headers.update({"Cookie": cookie})

    if dry_run:
        attempts: List[str] = []
        for b in base_candidates:
            for api_ver in ("3", "2"):
                url = f"{b}/rest/api/{api_ver}/myself"
                r = _request(session, "GET", url)
                if r.status_code == 200:
                    me = r.json()
                    who = me.get("displayName") or me.get("name") or "(unknown)"
                    return True, f"{source_label}: OK Jira autenticado como {who}", None
                attempts.append(f"{api_ver}@{b} => {r.status_code}")
                # 404 often means wrong API version or missing context path; keep trying.
                if r.status_code == 404:
                    continue
        return (
            False,
            f"{source_label}: error Jira (no se encontró endpoint). Intentos: {', '.join(attempts)}. "
            f"Detalle: {r.text[:200]}",
            None,
        )

    start_at = 0
    max_results = 100
    issues: List[NormalizedIssue] = []

    api_base: Optional[str] = None
    while True:
        if api_base is None:
            # Autodetect the working API base on first request.
            api_base = f"{base}/rest/api/3"

        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": [
                "summary",
                "status",
                "issuetype",
                "priority",
                "created",
                "updated",
                "resolutiondate",
                "assignee",
                "reporter",
                "labels",
                "components",
                "resolution",
            ],
        }
        r = _request(session, "POST", f"{api_base}/search", json=payload)
        if r.status_code == 404:
            # Try alternate API versions and/or /jira context path.
            found = False
            for b in base_candidates:
                for api_ver in ("3", "2"):
                    trial = f"{b}/rest/api/{api_ver}"
                    rr = _request(session, "POST", f"{trial}/search", json=payload)
                    if rr.status_code == 200:
                        api_base = trial
                        r = rr
                        found = True
                        break
                if found:
                    break
        if r.status_code != 200:
            return (
                False,
                f"{source_label}: error Jira search ({r.status_code}): {r.text[:200]}",
                None,
            )
        data = r.json()

        for it in data.get("issues", []):
            fields = it.get("fields") or {}
            priority = (
                (fields.get("priority") or {}).get("name", "") if fields.get("priority") else ""
            ).strip()
            labels = fields.get("labels") or []
            components = [c.get("name", "") for c in (fields.get("components") or [])]
            resolution = (
                (fields.get("resolution") or {}).get("name", "") if fields.get("resolution") else ""
            )
            res_type = resolution

            issues.append(
                NormalizedIssue(
                    key=it.get("key", ""),
                    summary=fields.get("summary", ""),
                    status=((fields.get("status") or {}).get("name", "") or "").strip(),
                    type=((fields.get("issuetype") or {}).get("name", "") or "").strip(),
                    priority=priority,
                    created=fields.get("created"),
                    updated=fields.get("updated"),
                    resolved=fields.get("resolutiondate"),
                    assignee=(
                        (fields.get("assignee") or {}).get("displayName", "")
                        if fields.get("assignee")
                        else ""
                    ),
                    reporter=(
                        (fields.get("reporter") or {}).get("displayName", "")
                        if fields.get("reporter")
                        else ""
                    ),
                    labels=labels,
                    components=components,
                    resolution=resolution,
                    resolution_type=res_type,
                    url=f"{base}/browse/{it.get('key', '')}",
                    country=country,
                    source_type="jira",
                    source_alias=alias,
                    source_id=source_id,
                )
            )

        start_at += max_results
        if start_at >= int(data.get("total", 0)):
            break

    doc = existing_doc or IssuesDocument.empty()
    doc.schema_version = "1.0"
    doc.ingested_at = now_iso()
    doc.jira_base_url = base
    doc.query = jql

    merged = {_merge_key(i): i for i in doc.issues}
    for i in issues:
        merged[_merge_key(i)] = i
    doc.issues = list(merged.values())

    return (
        True,
        f"{source_label}: ingesta Jira OK ({len(issues)} issues, merge total {len(doc.issues)}).",
        doc,
    )
