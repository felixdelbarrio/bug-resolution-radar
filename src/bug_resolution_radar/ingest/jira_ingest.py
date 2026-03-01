"""Jira ingestion pipeline using configured JQL sources."""

from __future__ import annotations

import os
import re
import time
from html import unescape
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
from .jira_session import get_jira_session_cookie


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _request(session: requests.Session, method: str, url: str, **kwargs: Any) -> requests.Response:
    r = session.request(method, url, timeout=30, **kwargs)
    if r.status_code in (429, 502, 503, 504):
        raise RuntimeError(f"transient jira status {r.status_code}")
    return r


def _open_url_in_configured_browser(url: str, browser: str) -> bool:
    return _open_url_in_browser(url=url, browser=browser)


def _is_target_page_open_in_configured_browser(url: str, browser: str) -> Optional[bool]:
    return _is_target_page_open_in_browser(url=url, browser=browser)


def _ensure_target_page_open_in_configured_browser(url: str, browser: str) -> bool:
    is_open = _is_target_page_open_in_configured_browser(url, browser)
    if is_open is True:
        return True
    if is_open is False:
        return _open_url_in_configured_browser(url, browser)
    return False


def _dedupe_keep_order(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = str(value or "").strip().rstrip("/")
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        out.append(candidate)
    return out


def _build_jira_base_candidates(base: str) -> List[str]:
    normalized = str(base or "").strip().rstrip("/")
    if not normalized:
        return []

    parsed = urlparse(normalized)
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    path = str(parsed.path or "").strip()
    path_lower = path.rstrip("/").lower()

    candidates: List[str] = [normalized]
    # If a full issue/page URL was pasted as base (e.g. /browse/ABC-123),
    # include origin first because API endpoints hang from the Jira root.
    if path_lower and path_lower != "/jira":
        candidates.append(origin)
    if not normalized.endswith("/jira"):
        candidates.append(normalized + "/jira")
    if origin:
        candidates.append(origin + "/jira")
        if path_lower == "/jira":
            candidates.append(origin)
    return _dedupe_keep_order(candidates)


def _default_jira_login_url(base: str) -> str:
    normalized = str(base or "").strip().rstrip("/")
    parsed = urlparse(normalized)
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    path = str(parsed.path or "").strip().rstrip("/")
    if path and path.lower() != "/jira" and origin:
        return f"{origin}/jira/secure/Dashboard.jspa"
    jira_web_base = normalized if normalized.endswith("/jira") else f"{normalized}/jira"
    return f"{jira_web_base}/secure/Dashboard.jspa"


def _jira_api_bases(base_candidates: List[str]) -> List[str]:
    api_versions = ("3", "2", "latest")
    out: List[str] = []
    for b in base_candidates:
        for api_ver in api_versions:
            out.append(f"{b}/rest/api/{api_ver}")
    return _dedupe_keep_order(out)


def _jira_search_request(
    session: requests.Session, api_base: str, payload: Dict[str, Any]
) -> requests.Response:
    endpoints = ("search", "search/jql")
    last: Optional[requests.Response] = None
    for endpoint in endpoints:
        rr = _request(session, "POST", f"{api_base}/{endpoint}", json=payload)
        last = rr
        if rr.status_code == 404:
            continue
        return rr
    assert last is not None
    return last


def _looks_like_html(text: str) -> bool:
    probe = str(text or "").strip().lower()
    if not probe:
        return False
    return ("<html" in probe) or ("<!doctype html" in probe)


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


def _jira_description_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        txt = value.strip()
        if "<" in txt and ">" in txt:
            return _jira_html_to_text(txt)
        return txt

    parts: list[str] = []

    def _walk(node: object) -> None:
        if node is None:
            return
        if isinstance(node, str):
            if node:
                parts.append(node)
            return
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if isinstance(node, dict):
            txt = node.get("text")
            if isinstance(txt, str) and txt:
                parts.append(txt)
            _walk(node.get("content"))
            t = str(node.get("type") or "").strip().lower()
            if t in {
                "paragraph",
                "heading",
                "listitem",
                "bulletlist",
                "orderedlist",
                "blockquote",
                "codeblock",
                "tablecell",
                "tablerow",
                "hardbreak",
            }:
                parts.append("\n")

    _walk(value)
    if not parts:
        return ""
    text = "".join(parts)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _jira_html_to_text(value: str) -> str:
    txt = str(value or "").strip()
    if not txt:
        return ""
    txt = re.sub(r"(?i)<br\s*/?>", "\n", txt)
    txt = re.sub(r"(?i)</p\s*>", "\n", txt)
    txt = re.sub(r"(?i)</h[1-6]\s*>", "\n", txt)
    txt = re.sub(r"(?i)</div\s*>", "\n", txt)
    txt = re.sub(r"(?i)<li[^>]*>", "- ", txt)
    txt = re.sub(r"(?i)</li\s*>", "\n", txt)
    txt = re.sub(r"(?is)<style.*?>.*?</style>", " ", txt)
    txt = re.sub(r"(?is)<script.*?>.*?</script>", " ", txt)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    txt = unescape(txt)
    txt = txt.replace("\r", "")
    txt = re.sub(r"[ \t\f\v]+", " ", txt)
    txt = re.sub(r"\n[ \t]+", "\n", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _bootstrap_jira_cookie_from_browser(
    *,
    browser: str,
    host: str,
    login_url: str,
    wait_seconds: int,
    poll_seconds: float,
    page_already_ensured: bool = False,
) -> Optional[str]:
    try:
        existing = get_jira_session_cookie(browser=browser, host=host)
    except Exception:
        existing = None
    existing = sanitize_cookie_header(existing)
    if existing and _has_jira_auth_cookie(_cookie_names_from_header(existing)):
        return existing

    if not page_already_ensured:
        page_already_ensured = _ensure_target_page_open_in_configured_browser(login_url, browser)
        if not page_already_ensured:
            _open_url_in_configured_browser(login_url, browser)

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

    base_candidates = _build_jira_base_candidates(base)
    api_candidates = _jira_api_bases(base_candidates)
    login_url = str(os.getenv("JIRA_BROWSER_LOGIN_URL", "")).strip() or _default_jira_login_url(
        base
    )
    wait_seconds = max(5, int(float(os.getenv("JIRA_BROWSER_LOGIN_WAIT_SECONDS", "90"))))
    poll_seconds = max(0.5, float(os.getenv("JIRA_BROWSER_LOGIN_POLL_SECONDS", "2")))
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
            page_already_ensured=False,
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
        for trial_api_base in api_candidates:
            url = f"{trial_api_base}/myself"
            r = _request(session, "GET", url)
            if r.status_code == 200:
                me = r.json()
                who = me.get("displayName") or me.get("name") or "(unknown)"
                return True, f"{source_label}: OK Jira autenticado como {who}", None
            attempts.append(f"{trial_api_base} => {r.status_code}")
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
            api_base = api_candidates[0] if api_candidates else f"{base}/rest/api/3"

        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            # Jira DC/Server REST v2 expects expand as array in POST payload.
            "expand": ["renderedFields"],
            "fields": [
                "summary",
                "description",
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
        r = _jira_search_request(session, api_base, payload)
        if r.status_code == 404:
            # Try alternate API versions and/or /jira context path.
            for trial in api_candidates:
                if trial == api_base:
                    continue
                rr = _jira_search_request(session, trial, payload)
                if rr.status_code == 200:
                    api_base = trial
                    r = rr
                    break
        if r.status_code != 200:
            hint = ""
            if r.status_code == 404 and _looks_like_html(r.text):
                hint = " Revisa JIRA_BASE_URL: usa la URL base de Jira (sin rutas como /browse/INC-123)."
            return (
                False,
                f"{source_label}: error Jira search ({r.status_code}): {r.text[:200]}{hint}",
                None,
            )
        data = r.json()

        for it in data.get("issues", []):
            fields = it.get("fields") or {}
            rendered_fields = it.get("renderedFields") or {}
            priority = (
                (fields.get("priority") or {}).get("name", "") if fields.get("priority") else ""
            ).strip()
            labels = fields.get("labels") or []
            components = [c.get("name", "") for c in (fields.get("components") or [])]
            resolution = (
                (fields.get("resolution") or {}).get("name", "") if fields.get("resolution") else ""
            )
            res_type = resolution
            desc_text = _jira_description_to_text(fields.get("description"))
            if not desc_text:
                desc_text = _jira_description_to_text(rendered_fields.get("description"))

            issues.append(
                NormalizedIssue(
                    key=it.get("key", ""),
                    summary=fields.get("summary", ""),
                    description=desc_text,
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
