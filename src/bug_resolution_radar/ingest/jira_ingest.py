from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import Settings
from ..schema import IssuesDocument, NormalizedIssue
from ..utils import now_iso, parse_criticality_map
from .jira_session import get_jira_session_cookie


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    r = session.request(method, url, timeout=30, **kwargs)
    if r.status_code in (429, 503):
        raise RuntimeError("rate limited")
    return r


def ingest_jira(
    settings: Settings,
    cookie_manual: Optional[str],
    dry_run: bool = False,
    existing_doc: Optional[IssuesDocument] = None,
) -> Tuple[bool, str, Optional[IssuesDocument]]:
    if not settings.JIRA_BASE_URL or not settings.JIRA_PROJECT_KEY:
        return False, "Configura JIRA_BASE_URL y JIRA_PROJECT_KEY.", None

    jql = settings.JIRA_JQL.strip() or f'project = "{settings.JIRA_PROJECT_KEY}" ORDER BY updated DESC'
    base = settings.JIRA_BASE_URL.rstrip("/")
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    cookie = cookie_manual
    if not cookie:
        try:
            cookie = get_jira_session_cookie(browser=settings.JIRA_BROWSER, domain=settings.JIRA_COOKIE_DOMAIN)
        except Exception as e:
            return False, f"No se pudo leer cookie del navegador. Usa fallback manual. Detalle: {e}", None

    if not cookie:
        return False, "Cookie Jira vacía. Usa fallback manual.", None

    session.headers.update({"Cookie": cookie})

    if dry_run:
        url = f"{base}/rest/api/3/myself"
        r = _request(session, "GET", url)
        if r.status_code == 200:
            me = r.json()
            return True, f"OK Jira: autenticado como {me.get('displayName','(unknown)')}", None
        return False, f"Error Jira ({r.status_code}): {r.text[:200]}", None

    start_at = 0
    max_results = 100
    issues: List[NormalizedIssue] = []
    crit_map = parse_criticality_map(settings.CRITICALITY_MAP)

    while True:
        url = f"{base}/rest/api/3/search"
        payload = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": [
                "summary","status","issuetype","priority","created","updated","resolutiondate",
                "assignee","reporter","labels","components","resolution",
            ],
        }
        r = _request(session, "POST", url, json=payload)
        if r.status_code != 200:
            return False, f"Error Jira search ({r.status_code}): {r.text[:200]}", None
        data = r.json()

        for it in data.get("issues", []):
            fields = it.get("fields") or {}
            priority = (fields.get("priority") or {}).get("name", "") if fields.get("priority") else ""
            criticality = crit_map.get(priority, "")
            labels = fields.get("labels") or []
            components = [c.get("name","") for c in (fields.get("components") or [])]
            resolution = (fields.get("resolution") or {}).get("name", "") if fields.get("resolution") else ""
            res_type = resolution

            affected = 0  # placeholder (si tienes un customfield, lo añadimos)
            is_master = (settings.MASTER_LABEL.lower() in [l.lower() for l in labels]) or (
                affected > int(settings.MASTER_AFFECTED_CLIENTS_THRESHOLD)
            )

            issues.append(
                NormalizedIssue(
                    key=it.get("key",""),
                    summary=fields.get("summary",""),
                    status=(fields.get("status") or {}).get("name",""),
                    type=(fields.get("issuetype") or {}).get("name",""),
                    priority=priority,
                    criticality=criticality,
                    created=fields.get("created"),
                    updated=fields.get("updated"),
                    resolved=fields.get("resolutiondate"),
                    assignee=(fields.get("assignee") or {}).get("displayName","") if fields.get("assignee") else "",
                    reporter=(fields.get("reporter") or {}).get("displayName","") if fields.get("reporter") else "",
                    labels=labels,
                    components=components,
                    affected_clients_count=affected,
                    is_master=is_master,
                    resolution=resolution,
                    resolution_type=res_type,
                    url=f"{base}/browse/{it.get('key','')}",
                )
            )

        start_at += max_results
        if start_at >= int(data.get("total", 0)):
            break

    doc = existing_doc or IssuesDocument.empty()
    doc.schema_version = "1.0"
    doc.ingested_at = now_iso()
    doc.jira_base_url = base
    doc.project_key = settings.JIRA_PROJECT_KEY
    doc.query = jql

    merged = {i.key: i for i in doc.issues}
    for i in issues:
        merged[i.key] = i
    doc.issues = list(merged.values())

    return True, f"Ingesta Jira OK: {len(issues)} issues (merge total {len(doc.issues)})", doc
