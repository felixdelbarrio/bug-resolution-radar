"""Helix ingestion pipeline and normalization routines."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import urlparse

import requests
from requests.exceptions import SSLError
from tenacity import RetryError, retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import build_source_id
from ..schema_helix import HelixDocument, HelixWorkItem
from ..security import sanitize_cookie_header, validate_service_base_url
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


def _utc_year_create_date_range_ms(year: Optional[Any] = None) -> Tuple[int, int, int]:
    year_int = _coerce_int(year, 0) if year is not None else 0
    if year_int < 1970:
        year_int = datetime.now(timezone.utc).year

    start_dt = datetime(year_int, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(year_int + 1, 1, 1, 0, 0, 0, 0, tzinfo=timezone.utc)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000) - 1
    return start_ms, end_ms, year_int


def _build_filter_criteria(
    organization: str, create_start_ms: int, create_end_ms: int
) -> Dict[str, Any]:
    return {
        "organizations": [str(organization or "").strip()],
        "createDateRanges": [{"start": int(create_start_ms), "end": int(create_end_ms)}],
    }


def _iso_from_epoch_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


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
        (
            connect_timeout
            if connect_timeout is not None
            else os.getenv("HELIX_CONNECT_TIMEOUT", "10")
        ),
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
            (
                proxy_min_read_timeout
                if proxy_min_read_timeout is not None
                else os.getenv("HELIX_PROXY_MIN_READ_TIMEOUT", "120")
            ),
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
        (
            dryrun_connect_timeout
            if dryrun_connect_timeout is not None
            else os.getenv("HELIX_DRYRUN_CONNECT_TIMEOUT", str(connect_to))
        ),
        connect_to,
    )

    # mínimo 60s por defecto en dry-run
    r = _coerce_float(
        (
            dryrun_read_timeout
            if dryrun_read_timeout is not None
            else os.getenv("HELIX_DRYRUN_READ_TIMEOUT", str(max(read_to, 60.0)))
        ),
        max(read_to, 60.0),
    )

    return c, r


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(
        lambda e: isinstance(
            e,
            (RuntimeError, requests.exceptions.ConnectionError),
        )
        and not isinstance(e, requests.exceptions.SSLError)
    ),
)
def _request(
    session: requests.Session,
    method: str,
    url: str,
    timeout: Tuple[float, float],
    **kwargs: Any,
) -> requests.Response:
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
        return None

    for c in session.cookies:
        if getattr(c, "name", "") == name and getattr(c, "value", ""):
            return str(c.value)
    return None


def _retry_root_cause(e: RetryError) -> str:
    try:
        last = e.last_attempt.exception()
        if last is not None:
            return f"{type(last).__name__}: {last}"
    except Exception as ex:
        return f"{type(ex).__name__}: {ex}"
    return str(e)


def _looks_like_sso_redirect(resp: requests.Response) -> bool:
    final_url = (getattr(resp, "url", "") or "").lower()
    body = (getattr(resp, "text", "") or "")[:2000].lower()
    if "-rsso." in final_url or "/rsso/" in final_url:
        return True
    markers = (
        "redirecting to single sign-on",
        "/rsso/start",
        'name="goto"',
        "name='goto'",
    )
    return any(m in body for m in markers)


def _short_text(s: str, max_chars: int = 240) -> str:
    txt = (s or "").replace("\n", " ").replace("\r", " ").strip()
    if len(txt) <= max_chars:
        return txt
    return txt[:max_chars] + "..."


def _is_timeout_text(s: str) -> bool:
    t = (s or "").lower()
    return "timeout" in t or "timed out" in t or "read timed out" in t


def _has_auth_cookie(cookie_names: List[str]) -> bool:
    wanted = {"jsessionid", "xsrf-token", "loginid", "sso.session.restore.cookies", "route"}
    got = {str(x).strip().lower() for x in cookie_names}
    return any(x in got for x in wanted)


def _item_merge_key(item: HelixWorkItem) -> str:
    sid = str(item.source_id or "").strip().lower()
    item_id = str(item.id or "").strip().upper()
    if sid:
        return f"{sid}::{item_id}"
    return item_id


def ingest_helix(
    helix_base_url: str,
    browser: str,
    organization: str,
    country: str = "",
    source_alias: str = "",
    source_id: str = "",
    proxy: str = "",
    ssl_verify: str = "",
    ca_bundle: str = "",
    chunk_size: int = 75,
    create_date_year: Any = None,
    connect_timeout: Any = None,
    read_timeout: Any = None,
    proxy_min_read_timeout: Any = None,
    dryrun_connect_timeout: Any = None,
    dryrun_read_timeout: Any = None,
    max_read_timeout: Any = None,
    min_chunk_size: Any = None,
    max_pages: Any = None,
    max_ingest_seconds: Any = None,
    dry_run: bool = False,
    existing_doc: Optional[HelixDocument] = None,
) -> Tuple[bool, str, Optional[HelixDocument]]:
    country_value = str(country or "").strip()
    alias_value = str(source_alias or "").strip() or "Helix principal"
    source_id_value = str(source_id or "").strip()
    if not source_id_value:
        source_id_value = build_source_id("helix", country_value or "default", alias_value)
    source_label = f"{country_value} · {alias_value}" if country_value else f"Helix · {alias_value}"

    if not organization:
        return False, f"{source_label}: configura organization.", None

    try:
        base = validate_service_base_url(helix_base_url, service_name="Helix")
    except ValueError as e:
        return False, f"{source_label}: {e}", None

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

    try:
        cookie = get_helix_session_cookie(browser=browser, host=host)
    except Exception as e:
        return (
            False,
            f"{source_label}: no se pudo leer cookie Helix en '{browser}'. Detalle: {e}",
            None,
        )
    cookie = sanitize_cookie_header(cookie)
    if not cookie:
        return False, f"{source_label}: no se encontró cookie Helix válida en '{browser}'.", None

    cookie_names = _cookies_to_jar(session, cookie, host=host)
    if not _has_auth_cookie(cookie_names):
        return (
            False,
            f"{source_label}: no se detectaron cookies de sesión Helix/SmartIT válidas. "
            f"cookies_cargadas={cookie_names}. "
            "Abre Helix en el navegador seleccionado y vuelve a autenticarte.",
            None,
        )

    preflight: Optional[requests.Response] = None
    if not dry_run:
        try:
            preflight = session.get(f"{base}/app/", timeout=(5, 15))
        except requests.RequestException:
            preflight = None

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
    create_start_ms, create_end_ms, create_year = _utc_year_create_date_range_ms(create_date_year)
    filter_criteria = _build_filter_criteria(org, create_start_ms, create_end_ms)

    def make_body(start_index: int, page_chunk_size: Optional[int] = None) -> Dict[str, Any]:
        size = int(page_chunk_size if page_chunk_size is not None else chunk_size)
        return {
            "filterCriteria": filter_criteria,
            "attributeNames": attribute_names,
            "chunkInfo": {"startIndex": int(start_index), "chunkSize": size},
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
                    f"{source_label}: timeout Helix (dry-run rápido) en /app/. "
                    f"Detalle: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                    f"timeout(connect/read)={probe_connect}/{probe_read}",
                    None,
                )
            except SSLError as e:
                return (
                    False,
                    f"{source_label}: error SSL en Helix (dry-run rápido): {e} | "
                    f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                    None,
                )
            except requests.exceptions.RequestException as e:
                return (
                    False,
                    f"{source_label}: error de red en Helix (dry-run rápido): "
                    f"{type(e).__name__}: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                    None,
                )

        if _looks_like_sso_redirect(preflight):
            return (
                False,
                f"{source_label}: Helix no autenticado (redirección a SSO en /app/). "
                f"cookies_cargadas={cookie_names} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        if preflight.status_code >= 400:
            return (
                False,
                f"{source_label}: Helix dry-run rápido falló en /app/ "
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
            f"{source_label}: OK Helix (sesión web accesible, test rápido).",
            None,
        )

    # -----------------------------
    # Ingest real
    # -----------------------------
    items: List[HelixWorkItem] = []
    start = 0
    base_chunk_size = max(1, int(chunk_size))
    current_chunk_size = base_chunk_size
    min_chunk_limit = max(
        1,
        _coerce_int(
            (
                min_chunk_size
                if min_chunk_size is not None
                else os.getenv("HELIX_MIN_CHUNK_SIZE", "10")
            ),
            10,
        ),
    )
    min_chunk_limit = min(min_chunk_limit, base_chunk_size)
    current_read_to = read_to
    max_read_to = max(
        current_read_to,
        _coerce_float(
            (
                max_read_timeout
                if max_read_timeout is not None
                else os.getenv("HELIX_MAX_READ_TIMEOUT", "120")
            ),
            120.0,
        ),
    )

    seen_ids: set = set()
    started_at = time.monotonic()
    max_pages_limit = _coerce_int(
        max_pages if max_pages is not None else os.getenv("HELIX_MAX_PAGES", "200"),
        200,
    )
    max_elapsed_seconds = _coerce_float(
        (
            max_ingest_seconds
            if max_ingest_seconds is not None
            else os.getenv("HELIX_MAX_INGEST_SECONDS", "900")
        ),
        900.0,
    )
    page = 0

    while True:
        elapsed = time.monotonic() - started_at
        if elapsed > max_elapsed_seconds:
            return (
                False,
                f"{source_label}: ingesta Helix abortada por tiempo máximo excedido "
                f"({elapsed:.1f}s > {max_elapsed_seconds:.1f}s). "
                f"Páginas={page}, items_nuevos={len(items)} | "
                f"chunk_actual={current_chunk_size} | read_timeout_actual={current_read_to:.1f}s | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        if page >= max_pages_limit:
            return (
                False,
                f"{source_label}: ingesta Helix abortada por demasiadas páginas. "
                f"max_pages={max_pages_limit} | páginas={page} | items_nuevos={len(items)} | "
                f"chunk_actual={current_chunk_size} | read_timeout_actual={current_read_to:.1f}s | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        try:
            r = _request(
                session,
                "POST",
                endpoint,
                json=make_body(start, current_chunk_size),
                timeout=(connect_to, current_read_to),
            )
        except RetryError as e:
            cause = _retry_root_cause(e)
            if _is_timeout_text(cause):
                if current_chunk_size > min_chunk_limit:
                    current_chunk_size = max(min_chunk_limit, current_chunk_size // 2)
                    continue
                if current_read_to < max_read_to:
                    current_read_to = min(
                        max_read_to, max(current_read_to + 5.0, current_read_to * 1.5)
                    )
                    continue
            if "rate limited" in cause.lower():
                return (
                    False,
                    f"{source_label}: Helix responde con rate limit tras reintentos agotados. "
                    f"Causa: {cause} | endpoint={endpoint} | "
                    f"chunk={current_chunk_size} | timeout(connect/read)={connect_to}/{current_read_to}",
                    None,
                )
            return (
                False,
                f"{source_label}: timeout en Helix (reintentos agotados). "
                f"Causa: {cause} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                f"timeout(connect/read)={connect_to}/{current_read_to} | "
                f"chunk={current_chunk_size} | min_chunk={min_chunk_limit} | max_read_timeout={max_read_to} | "
                f"endpoint={endpoint}",
                None,
            )
        except requests.exceptions.Timeout as e:
            if current_chunk_size > min_chunk_limit:
                current_chunk_size = max(min_chunk_limit, current_chunk_size // 2)
                continue
            if current_read_to < max_read_to:
                current_read_to = min(
                    max_read_to, max(current_read_to + 5.0, current_read_to * 1.5)
                )
                continue
            return (
                False,
                f"{source_label}: timeout en Helix. "
                f"Detalle: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc} | "
                f"timeout(connect/read)={connect_to}/{current_read_to} | "
                f"chunk={current_chunk_size} | min_chunk={min_chunk_limit} | max_read_timeout={max_read_to}",
                None,
            )
        except SSLError as e:
            return (
                False,
                f"{source_label}: error SSL en Helix: {e} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )
        except requests.exceptions.RequestException as e:
            return (
                False,
                f"{source_label}: error de red en Helix: "
                f"{type(e).__name__}: {e} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        page += 1

        if r.status_code != 200:
            return (
                False,
                f"{source_label}: error Helix ({r.status_code}): {r.text[:800]} | "
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
            values_raw = it.get("values")
            values: Dict[str, Any] = cast(
                Dict[str, Any], values_raw if isinstance(values_raw, dict) else it
            )
            wid = str(
                values.get("displayId") or values.get("id") or values.get("workItemId") or ""
            ).strip()
            if not wid:
                continue
            if wid in seen_ids:
                continue

            seen_ids.add(wid)
            new_in_page += 1

            assignee = values.get("assignee") or values.get("assigneeName") or ""
            if isinstance(assignee, dict):
                assignee = (
                    assignee.get("fullName")
                    or assignee.get("displayName")
                    or assignee.get("name")
                    or ""
                )

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
                    country=country_value,
                    source_alias=alias_value,
                    source_id=source_id_value,
                )
            )

        if new_in_page == 0:
            break

        start += int(current_chunk_size)

        if total is not None and (start >= total or len(seen_ids) >= total):
            break
        if len(batch) < int(current_chunk_size):
            break

    doc = existing_doc or HelixDocument.empty()
    doc.schema_version = "1.0"
    doc.ingested_at = now_iso()
    doc.helix_base_url = base
    create_start_iso = _iso_from_epoch_ms(create_start_ms)
    create_end_iso = _iso_from_epoch_ms(create_end_ms)
    doc.query = (
        f"organizations in [{org}] and createDate in [{create_start_iso} .. {create_end_iso}]"
        f" (year={create_year})"
    )

    merged = {_item_merge_key(i): i for i in doc.items}
    for i in items:
        merged[_item_merge_key(i)] = i
    doc.items = list(merged.values())

    return (
        True,
        f"{source_label}: ingesta Helix OK ({len(items)} items, merge total {len(doc.items)}).",
        doc,
    )
