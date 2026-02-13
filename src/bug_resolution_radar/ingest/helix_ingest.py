# src/bug_resolution_radar/ingest/helix_ingest.py
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import requests
from requests.exceptions import SSLError
from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..schema_helix import HelixDocument, HelixWorkItem
from ..utils import now_iso
from .helix_session import get_helix_session_cookie


def _parse_bool(value: Union[str, bool, None], default: bool = True) -> bool:
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


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _get_timeouts(
    has_proxy: bool,
    connect_timeout: Any = None,
    read_timeout: Any = None,
    proxy_min_read_timeout: Any = None,
) -> Tuple[float, float]:
    """
    Timeouts separados (connect/read). Ajustables por env.
    Si hay proxy, por defecto elevamos el read-timeout porque suele añadir latencia.
    """
    connect = _coerce_float(
        connect_timeout if connect_timeout is not None else os.getenv("HELIX_CONNECT_TIMEOUT", "10"),
        10.0,
    )

    # base read (sin proxy)
    read = _coerce_float(
        read_timeout if read_timeout is not None else os.getenv("HELIX_READ_TIMEOUT", "30"),
        30.0,
    )

    if has_proxy:
        # mínimo recomendado con proxy (ajustable)
        min_proxy_read = _coerce_float(
            proxy_min_read_timeout
            if proxy_min_read_timeout is not None
            else os.getenv("HELIX_PROXY_MIN_READ_TIMEOUT", "120"),
            120.0,
        )
        read = max(read, min_proxy_read)

    return connect, read


def _dry_run_timeouts(
    connect_to: float,
    read_to: float,
    dryrun_connect_timeout: Any = None,
    dryrun_read_timeout: Any = None,
) -> Tuple[float, float]:
    """
    En dry-run no reintentamos, pero tampoco queremos cortar demasiado pronto.
    """
    c = _coerce_float(
        dryrun_connect_timeout
        if dryrun_connect_timeout is not None
        else os.getenv("HELIX_DRYRUN_CONNECT_TIMEOUT", str(connect_to)),
        connect_to,
    )

    # mínimo 60s por defecto en dry-run
    r = _coerce_float(
        dryrun_read_timeout
        if dryrun_read_timeout is not None
        else os.getenv("HELIX_DRYRUN_READ_TIMEOUT", str(max(read_to, 60.0))),
        max(read_to, 60.0),
    )

    return c, r


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(
        lambda e: isinstance(
            e,
            (RuntimeError, requests.exceptions.ConnectionError, requests.exceptions.Timeout),
        )
        and not isinstance(e, requests.exceptions.SSLError)
    ),
)
def _request(session: requests.Session, method: str, url: str, timeout: Tuple[float, float], **kwargs) -> requests.Response:
    r = session.request(method, url, timeout=timeout, **kwargs)
    if r.status_code in (429, 503):
        raise RuntimeError("rate limited")
    return r


def _extract_objects(payload: Any) -> List[Dict[str, Any]]:
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
    if isinstance(payload, dict):
        for k in ("total", "totalSize", "totalCount", "countTotal"):
            if isinstance(payload.get(k), int):
                return int(payload[k])
        for v in payload.values():
            got = _extract_total(v)
            if got is not None:
                return got
        return None

    if isinstance(payload, list):
        for it in payload:
            got = _extract_total(it)
            if got is not None:
                return got
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

        session.cookies.set(name, value, domain=host, path=path)
        session.cookies.set(name, value, path=path)

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


def _retry_root_cause(e: RetryError) -> str:
    try:
        last = e.last_attempt.exception()
        if last is not None:
            return f"{type(last).__name__}: {last}"
    except Exception:
        pass
    return str(e)


def _looks_like_sso_redirect(resp: requests.Response) -> bool:
    final_url = (getattr(resp, "url", "") or "").lower()
    body = (getattr(resp, "text", "") or "")[:2000].lower()
    if "-rsso." in final_url or "/rsso/" in final_url:
        return True
    markers = (
        "redirecting to single sign-on",
        "/rsso/start",
        "name=\"goto\"",
        "name='goto'",
    )
    return any(m in body for m in markers)


def _short_text(s: str, max_chars: int = 240) -> str:
    txt = (s or "").replace("\n", " ").replace("\r", " ").strip()
    if len(txt) <= max_chars:
        return txt
    return txt[:max_chars] + "..."


def _has_auth_cookie(cookie_names: List[str]) -> bool:
    wanted = {"jsessionid", "xsrf-token", "loginid", "sso.session.restore.cookies", "route"}
    got = {str(x).strip().lower() for x in cookie_names}
    return any(x in got for x in wanted)


def ingest_helix(
    helix_base_url: str,
    browser: str,
    organization: str,
    proxy: str = "",
    ssl_verify: str = "",
    ca_bundle: str = "",
    cookie_manual: Optional[str] = None,
    chunk_size: int = 75,
    connect_timeout: Any = None,
    read_timeout: Any = None,
    proxy_min_read_timeout: Any = None,
    dryrun_connect_timeout: Any = None,
    dryrun_read_timeout: Any = None,
    max_pages: Any = None,
    max_ingest_seconds: Any = None,
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
    has_proxy = bool(helix_proxy)
    if has_proxy:
        session.proxies.update({"http": helix_proxy, "https": helix_proxy})

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

    cookie = cookie_manual
    if not cookie:
        try:
            cookie = get_helix_session_cookie(browser=browser, host=host)
            if not cookie:
                other = "edge" if browser == "chrome" else "chrome"
                cookie = get_helix_session_cookie(browser=other, host=host)
        except Exception as e:
            return False, f"No se pudo leer la cookie del navegador. Usa cookie manual. Detalle: {e}", None

    if not cookie:
        return False, "Cookie Helix vacía. Usa fallback manual.", None

    cookie_names = _cookies_to_jar(session, cookie, host=host)
    if not _has_auth_cookie(cookie_names):
        return (
            False,
            "No se detectaron cookies de sesión Helix/SmartIT válidas. "
            f"cookies_cargadas={cookie_names}. "
            "Abre Helix en el navegador seleccionado y vuelve a autenticarte; "
            "si persiste, usa cookie manual.",
            None,
        )

    preflight: Optional[requests.Response] = None
    if not dry_run:
        try:
            preflight = session.get(f"{base}/app/", timeout=(5, 15))
        except Exception:
            pass

    xsrf = _get_cookie_anywhere(session, "XSRF-TOKEN")
    if xsrf:
        session.headers["X-Xsrf-Token"] = xsrf
        session.headers["X-XSRF-TOKEN"] = xsrf
        session.headers["X-CSRF-Token"] = xsrf

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
            "sortInfo": {},
        }

    connect_to, read_to = _get_timeouts(
        has_proxy=has_proxy,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        proxy_min_read_timeout=proxy_min_read_timeout,
    )

    # -----------------------------
    # Dry-run
    # -----------------------------
    if dry_run:
        dry_c, dry_r = _dry_run_timeouts(
            connect_to,
            read_to,
            dryrun_connect_timeout=dryrun_connect_timeout,
            dryrun_read_timeout=dryrun_read_timeout,
        )

        # Test rápido: valida sesión/autenticación contra la app web.
        # Evita ejecutar la query pesada de workitems solo para probar conexión.
        probe_connect = max(1.0, min(dry_c, 5.0))
        probe_read = max(3.0, min(dry_r, 15.0))

        if preflight is None:
            try:
                preflight = session.get(f"{base}/app/", timeout=(probe_connect, probe_read))
            except requests.exceptions.Timeout as e:
                return (
                    False,
                    "Timeout en Helix (dry-run rápido): no respondió /app/. "
                    f"Detalle: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                    f"timeout(connect/read)={probe_connect}/{probe_read}",
                    None,
                )
            except SSLError as e:
                return (
                    False,
                    f"Error SSL en Helix (dry-run rápido): {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                    None,
                )
            except requests.exceptions.RequestException as e:
                return (
                    False,
                    "Error de red en Helix (dry-run rápido): "
                    f"{type(e).__name__}: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                    None,
                )

        if _looks_like_sso_redirect(preflight):
            return (
                False,
                "Helix no autenticado (redirección a SSO detectada en /app/). "
                f"cookies_cargadas={cookie_names} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        if preflight.status_code >= 400:
            return (
                False,
                "Helix dry-run rápido falló en /app/ "
                f"({preflight.status_code}): {_short_text(preflight.text)} | "
                f"cookies_cargadas={cookie_names} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        xsrf_now = _get_cookie_anywhere(session, "XSRF-TOKEN")
        if xsrf_now:
            session.headers["X-Xsrf-Token"] = xsrf_now
            session.headers["X-XSRF-TOKEN"] = xsrf_now
            session.headers["X-CSRF-Token"] = xsrf_now

        return (
            True,
            "OK Helix: sesión web accesible y autenticación aparentemente válida (test rápido).",
            None,
        )

    # -----------------------------
    # Ingest real
    # -----------------------------
    items: List[HelixWorkItem] = []
    start = 0

    seen_ids: set = set()
    started_at = time.monotonic()
    max_pages_limit = _coerce_int(
        max_pages if max_pages is not None else os.getenv("HELIX_MAX_PAGES", "200"),
        200,
    )
    max_elapsed_seconds = _coerce_float(
        max_ingest_seconds
        if max_ingest_seconds is not None
        else os.getenv("HELIX_MAX_INGEST_SECONDS", "900"),
        900.0,
    )
    page = 0

    while True:
        elapsed = time.monotonic() - started_at
        if elapsed > max_elapsed_seconds:
            return (
                False,
                "Ingesta Helix abortada por tiempo máximo excedido "
                f"({elapsed:.1f}s > {max_elapsed_seconds:.1f}s). "
                f"Páginas={page}, items_nuevos={len(items)} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        page += 1
        if page > max_pages_limit:
            return (
                False,
                "Ingesta Helix abortada: demasiadas páginas (posible paginación ignorada). "
                f"max_pages={max_pages_limit} | páginas={page - 1} | items_nuevos={len(items)} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        try:
            r = _request(session, "POST", endpoint, json=make_body(start), timeout=(connect_to, read_to))
        except RetryError as e:
            return (
                False,
                "Timeout en Helix (reintentos agotados): el servidor no respondió a tiempo. "
                f"Causa: {_retry_root_cause(e)} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                f"timeout(connect/read)={connect_to}/{read_to} | endpoint={endpoint}",
                None,
            )
        except requests.exceptions.Timeout as e:
            return (
                False,
                "Timeout en Helix: el servidor no respondió a tiempo. "
                f"Detalle: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                f"timeout(connect/read)={connect_to}/{read_to}",
                None,
            )
        except SSLError as e:
            return (
                False,
                f"Error SSL en Helix: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )
        except requests.exceptions.RequestException as e:
            return (
                False,
                "Error de red en Helix: "
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

        if new_in_page == 0:
            break

        start += int(chunk_size)

        if total is not None and (start >= total or len(seen_ids) >= total):
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
