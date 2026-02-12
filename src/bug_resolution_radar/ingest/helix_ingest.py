from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from ..schema_helix import HelixDocument, HelixWorkItem
from ..utils import now_iso
from .helix_session import get_helix_session_cookie


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    r = session.request(method, url, timeout=30, **kwargs)
    if r.status_code in (429, 503):
        raise RuntimeError("rate limited")
    return r


def _pick_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []

    for k in ("workItems", "items", "entries", "records", "results"):
        v = payload.get(k)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]

    for v in payload.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            return v  # type: ignore[return-value]
    return []


def _cookies_to_jar(session: requests.Session, cookie_header: str, host: str) -> List[str]:
    smartit_path_names = {
        "JSESSIONID",
        "XSRF-TOKEN",
        "loginId",
        "sso.session.restore.cookies",
        "route",
    }

    names: List[str] = []

    for part in (cookie_header or "").split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue

        names.append(name)
        path = "/smartit" if name in smartit_path_names else "/"

        # host-only
        session.cookies.set(name, value, domain=host, path=path)

        # fallback sin dominio
        session.cookies.set(name, value, path=path)

        # dominio padre típico (.onbmc.com)
        parts = host.split(".")
        if len(parts) >= 3:
            parent = "." + ".".join(parts[-3:])
            session.cookies.set(name, value, domain=parent, path=path)  # type: ignore[arg-type]

    return sorted(set(names))


def _get_cookie_anywhere(session: requests.Session, name: str) -> Optional[str]:
    try:
        v = session.cookies.get(name)  # type: ignore[arg-type]
        if v:
            return str(v)
    except Exception:
        pass

    for c in session.cookies:
        if getattr(c, "name", "") == name and getattr(c, "value", ""):
            return str(c.value)
    return None


def ingest_helix(
    helix_base_url: str,
    browser: str,
    organization: str,
    proxy: str = "",
    cookie_manual: Optional[str] = None,
    chunk_size: int = 75,
    dry_run: bool = False,
    existing_doc: Optional[HelixDocument] = None,
) -> Tuple[bool, str, Optional[HelixDocument]]:
    if not helix_base_url:
        return False, "Configura HELIX_BASE_URL.", None
    if not organization:
        return False, "Configura el filtro de organización (organization).", None

    base = helix_base_url.rstrip("/")
    if base.endswith("/app"):
        base = base[:-4]

    endpoint = f"{base}/rest/v2/person/workitems/get"
    parsed = urlparse(base)
    host = parsed.hostname or ""
    scheme = parsed.scheme or "https"

    session = requests.Session()

    helix_proxy = (proxy or os.getenv("HELIX_PROXY", "")).strip()
    if helix_proxy:
        session.proxies.update({"http": helix_proxy, "https": helix_proxy})

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Origin": f"{scheme}://{host}",
            "Referer": f"{base}/app/",
            "X-Requested-With": "XMLHttpRequest",
            "X-Requested-By": "SmartIT",
        }
    )

    cookie = cookie_manual
    if not cookie:
        try:
            cookie = get_helix_session_cookie(browser=browser, host=host)
            if not cookie:
                other = "edge" if browser == "chrome" else "chrome"
                cookie = get_helix_session_cookie(browser=other, host=host)
        except Exception as e:
            return False, f"No se pudo leer cookie del navegador. Usa cookie manual. Detalle: {e}", None

    if not cookie:
        return False, "Cookie Helix vacía. Usa fallback manual.", None

    cookie_names = _cookies_to_jar(session, cookie, host=host)

    # Warm-up (puede refrescar cookies / sesión)
    try:
        _request(session, "GET", f"{base}/app/")
    except Exception:
        pass

    xsrf = _get_cookie_anywhere(session, "XSRF-TOKEN")
    if xsrf:
        session.headers["X-XSRF-TOKEN"] = xsrf
        session.headers["X-CSRF-Token"] = xsrf

    attribute_names = [
        "priority",
        "id",
        "targetDate",
        "status",
        "customerName",
        "assignee",
        "summary",
        "lastModifiedDate",
    ]

    org = (organization or "").strip()

    def make_body(start_index: int) -> Dict[str, Any]:
        # ✅ body “clonado” de DevTools (incluye customAttributeNames)
        return {
            "filterCriteria": {"organizations": [org]},
            "attributeNames": attribute_names,
            "chunkInfo": {"startIndex": start_index, "chunkSize": int(chunk_size)},
            "customAttributeNames": [],
            "sortingInfo": {},
        }

    if dry_run:
        body = make_body(0)
        r = _request(session, "POST", endpoint, json=body)
        if r.status_code != 200:
            return (
                False,
                "Helix dry-run falló "
                f"({r.status_code}): {r.text[:800]} | "
                f"cookies_cargadas={cookie_names} | "
                f"proxy={helix_proxy or '(sin proxy)'} | "
                f"xsrf={'sí' if bool(xsrf) else 'no'} | "
                f"endpoint={endpoint} | "
                f"body={json.dumps(body, ensure_ascii=False)}",
                None,
            )
        return True, "OK Helix: autenticación válida y endpoint responde 200.", None

    items: List[HelixWorkItem] = []
    start = 0

    while True:
        r = _request(session, "POST", endpoint, json=make_body(start))
        if r.status_code != 200:
            return False, f"Error Helix ({r.status_code}): {r.text[:800]}", None

        data = r.json()
        batch = _pick_items(data)
        if not batch:
            break

        for it in batch:
            values = it.get("values") if isinstance(it.get("values"), dict) else it

            wid = str(values.get("id") or values.get("workItemId") or values.get("displayId") or "").strip()
            if not wid:
                continue

            assignee = values.get("assignee") or values.get("assigneeName") or ""
            if isinstance(assignee, dict):
                assignee = assignee.get("displayName") or assignee.get("name") or ""

            items.append(
                HelixWorkItem(
                    id=wid,
                    summary=str(values.get("summary") or values.get("description") or "").strip(),
                    status=str(values.get("status") or "").strip(),
                    priority=str(values.get("priority") or "").strip(),
                    assignee=str(assignee or "").strip(),
                    customer_name=str(values.get("customerName") or values.get("customer") or "").strip(),
                    target_date=values.get("targetDate"),
                    last_modified=values.get("lastModifiedDate") or values.get("lastModified"),
                    url=f"{base}/app/#/ticket-console",
                )
            )

        total = None
        if isinstance(data, dict):
            for k in ("total", "totalSize", "totalCount", "countTotal"):
                if isinstance(data.get(k), int):
                    total = int(data[k])
                    break

        start += int(chunk_size)
        if total is not None and start >= total:
            break
        if len(batch) < int(chunk_size):
            break

    doc = existing_doc or HelixDocument.empty()
    doc.schema_version = "1.0"
    doc.ingested_at = now_iso()
    doc.helix_base_url = base
    doc.query = f"organizations in [{org}]"

    merged = {i.id: i for i in doc.items}
    for i in items:
        merged[i.id] = i
    doc.items = list(merged.values())

    return True, f"Ingesta Helix OK: {len(items)} items (merge total {len(doc.items)})", doc
