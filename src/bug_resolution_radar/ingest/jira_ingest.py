from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings, build_source_id, supported_countries
from ..schema import IssuesDocument, NormalizedIssue
from ..security import sanitize_cookie_header, validate_service_base_url
from ..utils import now_iso
from .jira_session import get_jira_session_cookie


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _request(session: requests.Session, method: str, url: str, **kwargs: Any) -> requests.Response:
    r = session.request(method, url, timeout=30, **kwargs)
    if r.status_code in (429, 503):
        raise RuntimeError("rate limited")
    return r


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

    alias = "Jira principal"
    country = fallback_country
    jql = str(settings.JIRA_JQL or "").strip()
    source_id = build_source_id("jira", country, alias)
    return country, alias, source_id, jql


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

    try:
        host = urlparse(base).hostname or ""
        cookie = get_jira_session_cookie(browser=settings.JIRA_BROWSER, host=host)
    except Exception as e:
        return (
            False,
            f"{source_label}: no se pudo leer cookie de Jira en '{settings.JIRA_BROWSER}'. Detalle: {e}",
            None,
        )
    cookie = sanitize_cookie_header(cookie)
    if not cookie:
        return (
            False,
            f"{source_label}: no se encontró cookie Jira válida en '{settings.JIRA_BROWSER}'.",
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
                    url=f"{base}/browse/{it.get('key','')}",
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
