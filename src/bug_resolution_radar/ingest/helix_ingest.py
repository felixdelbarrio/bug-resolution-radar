# src/bug_resolution_radar/ingest/helix_ingest.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import requests
from requests.exceptions import SSLError
from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..schema_helix import HelixDocument, HelixWorkItem
from ..utils import now_iso
from .helix_session import get_helix_session_cookie


def _parse_bool(value: Union[str, bool, None], default: bool = True) -> bool:
    """
    Acepta: true/false, 1/0, yes/no, y/n, on/off (case-insensitive).
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def _get_timeouts() -> Tuple[float, float]:
    """
    Timeouts separados (connect/read). Ajustables por env.
    """
    try:
        connect = float(os.getenv("HELIX_CONNECT_TIMEOUT", "10"))
    except Exception:
        connect = 10.0
    try:
        read = float(os.getenv("HELIX_READ_TIMEOUT", "30"))
    except Exception:
        read = 30.0
    return connect, read


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    # SSL no se arregla reintentando: NO lo reintentamos.
    # Ojo: en requests SSLError hereda de ConnectionError, así que hay que excluirlo explícitamente.
    retry=retry_if_exception(
        lambda e: isinstance(
            e,
            (RuntimeError, requests.exceptions.ConnectionError, requests.exceptions.Timeout),
        )
        and not isinstance(e, requests.exceptions.SSLError)
    ),
)
def _request(session: requests.Session, method: str, url: str, **kwargs) -> requests.Response:
    """
    Request con tenacity y timeout (connect, read).
    Puedes pasar timeout explícito en kwargs para sobrescribir.
    """
    timeout = kwargs.pop("timeout", None)
    if timeout is None:
        timeout = _get_timeouts()  # (connect, read)

    r = session.request(method, url, timeout=timeout, **kwargs)

    if r.status_code in (429, 503):
        raise RuntimeError("rate limited")

    return r


def _extract_objects(payload: Any) -> List[Dict[str, Any]]:
    """
    Normaliza la respuesta de Helix/SmartIT:
    - SmartIT suele ser: [ { "items": [ { "objects": [ {...}, ... ] } ] } ]
      o dict con "items" -> [{"objects":[...]}]
    """
    if isinstance(payload, list):
        out: List[Dict[str, Any]] = []
        for x in payload:
            out.extend(_extract_objects(x))
        return out

    if not isinstance(payload, dict):
        return []

    v = payload.get("objects")
    if isinstance(v, list):
        return [x for x in v if isinstance(x, dict)]

    items = payload.get("items")
    if isinstance(items, list):
        out2: List[Dict[str, Any]] = []
        for it in items:
            out2.extend(_extract_objects(it))
        return out2

    for k in ("workItems", "entries", "records", "results"):
        v2 = payload.get(k)
        if isinstance(v2, list):
            out3: List[Dict[str, Any]] = []
            for it in v2:
                if isinstance(it, dict) and ("objects" in it or "items" in it):
                    out3.extend(_extract_objects(it))
                elif isinstance(it, dict):
                    out3.append(it)
            return out3

    for vv in payload.values():
        if isinstance(vv, (dict, list)):
            got = _extract_objects(vv)
            if got:
                return got

    return []


def _extract_total(payload: Any) -> Optional[int]:
    """
    SmartIT a veces devuelve total en el wrapper (dict) o dentro de una lista de wrappers.
    """
    wrappers: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        wrappers = [payload]
    elif isinstance(payload, list):
        wrappers = [x for x in payload if isinstance(x, dict)]

    for w in wrappers:
        for k in ("total", "totalSize", "totalCount", "countTotal"):
            if isinstance(w.get(k), int):
                return int(w[k])
    return None


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

        # fallback sin dominio explícito
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


def _format_retry_error(e: RetryError) -> str:
    # Tenacity encapsula la excepción original en e.last_attempt.exception()
    try:
        last = e.last_attempt.exception()
        if last is not None:
            return f"{type(last).__name__}: {last}"
    except Exception:
        pass
    return str(e)


def ingest_helix(
    helix_base_url: str,
    browser: str,
    organization: str,
    proxy: str = "",
    ssl_verify: str = "",
    ca_bundle: str = "",
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

    # -----------------------------
    # Proxy
    # -----------------------------
    helix_proxy = (proxy or os.getenv("HELIX_PROXY", "")).strip()
    if helix_proxy:
        session.proxies.update({"http": helix_proxy, "https": helix_proxy})

    # -----------------------------
    # SSL verify / CA bundle
    # -----------------------------
    verify_env = os.getenv("HELIX_SSL_VERIFY", "true")
    ca_env = os.getenv("HELIX_CA_BUNDLE", "")

    verify_bool = _parse_bool(ssl_verify or verify_env, default=True)
    ca_path = (ca_bundle or ca_env).strip()

    if ca_path:
        session.verify = ca_path
        verify_desc = f"ca_bundle:{ca_path}"
    else:
        session.verify = verify_bool
        verify_desc = "true" if verify_bool else "false"

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/141.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            "Origin": f"{scheme}://{host}",
            "Referer": f"{base}/app/",
            "X-Requested-With": "XMLHttpRequest",
            "X-Requested-By": "SmartIT",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }
    )

    # -----------------------------
    # Cookie
    # -----------------------------
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

    # Warm-up (no crítico)
    try:
        session.get(f"{base}/app/", timeout=(5, 10))
    except Exception:
        pass

    # CSRF token desde cookie (en captura: X-Xsrf-Token)
    xsrf = _get_cookie_anywhere(session, "XSRF-TOKEN")
    if xsrf:
        session.headers["X-Xsrf-Token"] = xsrf  # tal cual navegador
        session.headers["X-XSRF-TOKEN"] = xsrf  # compat
        session.headers["X-CSRF-Token"] = xsrf  # compat

    attribute_names = [
        "priority",
        "id",
        "targetDate",
        "slaStatus",
        "customerName",
        "assignee",
        "summary",
        "status",
        "lastModifiedDate",
    ]

    org = (organization or "").strip()

    def make_body(start_index: int) -> Dict[str, Any]:
        return {
            "filterCriteria": {"organizations": [org]},
            "attributeNames": attribute_names,
            "chunkInfo": {"startIndex": int(start_index), "chunkSize": int(chunk_size)},
            "customAttributeNames": [],
            "sortInfo": {},  # importante: sortInfo (no sortingInfo)
        }

    connect_to, read_to = _get_timeouts()

    # -----------------------------
    # Dry-run (SIN reintentos, timeout corto)
    # -----------------------------
    if dry_run:
        body = make_body(0)
        try:
            r = session.post(endpoint, json=body, timeout=(min(connect_to, 5.0), min(read_to, 10.0)))
        except SSLError as e:
            return (
                False,
                "Helix dry-run SSL error: "
                f"{e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )
        except requests.exceptions.Timeout as e:
            return (
                False,
                "Helix dry-run timeout: "
                f"{e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                f"connect/read={connect_to}/{read_to}",
                None,
            )
        except requests.exceptions.RequestException as e:
            return (
                False,
                "Helix dry-run request error: "
                f"{type(e).__name__}: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        if r.status_code != 200:
            return (
                False,
                "Helix dry-run falló "
                f"({r.status_code}): {r.text[:800]} | "
                f"cookies_cargadas={cookie_names} | "
                f"proxy={helix_proxy or '(sin proxy)'} | "
                f"verify={verify_desc} | "
                f"xsrf={'sí' if bool(xsrf) else 'no'} | "
                f"endpoint={endpoint} | "
                f"body={json.dumps(body, ensure_ascii=False)}",
                None,
            )

        return True, "OK Helix: autenticación válida y endpoint responde 200.", None

    # -----------------------------
    # Ingest real
    # -----------------------------
    items: List[HelixWorkItem] = []
    start = 0

    # airbags anti-bucle + anti-spinner
    seen_ids: set = set()
    max_pages = 200
    page = 0

    while True:
        page += 1
        if page > max_pages:
            return (
                False,
                f"Helix ingest abortado: max_pages={max_pages} (posible paginación ignorada). "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        try:
            r = _request(session, "POST", endpoint, json=make_body(start))
        except RetryError as e:
            return (
                False,
                "Helix request timeout (reintentos agotados): "
                f"{_format_retry_error(e)} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                f"connect/read={connect_to}/{read_to} | endpoint={endpoint}",
                None,
            )
        except SSLError as e:
            return (
                False,
                "Helix SSL error: "
                f"{e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )
        except requests.exceptions.Timeout as e:
            # por si entra sin RetryError (raro, pero posible si cambian decoradores)
            return (
                False,
                "Helix timeout: "
                f"{type(e).__name__}: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                f"connect/read={connect_to}/{read_to}",
                None,
            )
        except requests.exceptions.RequestException as e:
            return (
                False,
                "Helix request error: "
                f"{type(e).__name__}: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        if r.status_code != 200:
            return (
                False,
                f"Error Helix ({r.status_code}): {r.text[:800]} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        data = r.json()
        batch = _extract_objects(data)
        if not batch:
            break

        total = _extract_total(data)

        new_in_page = 0

        for it in batch:
            values = it.get("values") if isinstance(it.get("values"), dict) else it

            wid = str(values.get("displayId") or values.get("id") or values.get("workItemId") or "").strip()
            if not wid:
                continue

            if wid in seen_ids:
                continue
            seen_ids.add(wid)
            new_in_page += 1

            assignee = values.get("assignee") or values.get("assigneeName") or ""
            if isinstance(assignee, dict):
                assignee = assignee.get("fullName") or assignee.get("displayName") or assignee.get("name") or ""

            customer_name = values.get("customerName") or values.get("customer") or ""
            if isinstance(customer_name, dict):
                customer_name = (
                    customer_name.get("fullName")
                    or customer_name.get("displayName")
                    or customer_name.get("name")
                    or ""
                )

            items.append(
                HelixWorkItem(
                    id=wid,
                    summary=str(values.get("summary") or values.get("description") or "").strip(),
                    status=str(values.get("status") or "").strip(),
                    priority=str(values.get("priority") or "").strip(),
                    assignee=str(assignee or "").strip(),
                    customer_name=str(customer_name or "").strip(),
                    target_date=values.get("targetDate"),
                    last_modified=values.get("lastModifiedDate") or values.get("lastModified"),
                    url=f"{base}/app/#/ticket-console",
                )
            )

        # Si Helix ignora startIndex y siempre devuelve la misma página, aquí cortamos.
        if new_in_page == 0:
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
