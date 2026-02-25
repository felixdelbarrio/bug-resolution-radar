"""Helix ingestion pipeline and normalization routines."""

from __future__ import annotations

import os
import re
import subprocess
import time
import webbrowser
from datetime import datetime, timezone
from platform import system as platform_system
from typing import Any, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import urlparse

import requests
from requests.exceptions import SSLError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ..config import build_source_id
from ..common.security import sanitize_cookie_header, validate_service_base_url
from ..common.utils import now_iso
from ..models.schema_helix import HelixDocument, HelixWorkItem
from .helix_mapper import (
    is_allowed_helix_business_incident_type,
    map_helix_values_to_item,
)
from .helix_session import get_helix_session_cookie

_ARSQL_BUSINESS_INCIDENT_TYPE_FIELD_CANDIDATES: tuple[str, ...] = (
    "BBVA_Tipo_de_Incidencia",
    "BBVA_TipoDeIncidencia",
    "BBVA_TipoIncidencia",
    "BBVA_TypeOfIncident",
    "BBVA_IncidentType",
    "Tipo_de_Incidencia",
)
_ARSQL_ENVIRONMENT_FIELD_CANDIDATES: tuple[str, ...] = (
    "BBVA_Environment",
    "BBVA_Entorno",
    "Entorno",
)
_ARSQL_OFFICIAL_BUSINESS_INCIDENT_TYPES: tuple[str, ...] = (
    "Incidencia",
    "Consulta",
    "Evento Monitorización",
)
_ARSQL_OFFICIAL_ENVIRONMENTS: tuple[str, ...] = ("Production",)
_ARSQL_OFFICIAL_TIME_FIELDS: tuple[str, ...] = ("Submit Date",)


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


def _csv_list(value: Any, default: str = "") -> List[str]:
    raw = default if value is None else value
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    txt = str(raw or "").strip()
    if not txt:
        return []
    return [x.strip() for x in txt.split(",") if x.strip()]


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
    organization: str,
    create_start_ms: int,
    create_end_ms: int,
    *,
    status_mappings: Optional[List[str]] = None,
    incident_types: Optional[List[str]] = None,
    priorities: Optional[List[str]] = None,
    companies: Optional[List[Dict[str, str]]] = None,
    risk_level: Optional[List[str]] = None,
) -> Dict[str, Any]:
    criteria: Dict[str, Any] = {
        "organizations": [str(organization or "").strip()],
        "createDateRanges": [{"start": int(create_start_ms), "end": int(create_end_ms)}],
    }
    if status_mappings:
        criteria["statusMappings"] = [str(x).strip() for x in status_mappings if str(x).strip()]
    if incident_types:
        criteria["incidentTypes"] = [str(x).strip() for x in incident_types if str(x).strip()]
    if priorities:
        criteria["priorities"] = [str(x).strip() for x in priorities if str(x).strip()]
    if companies:
        valid_companies: List[Dict[str, str]] = []
        for row in companies:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if name:
                valid_companies.append({"name": name})
        if valid_companies:
            criteria["companies"] = valid_companies
    if risk_level:
        criteria["riskLevel"] = [str(x).strip() for x in risk_level if str(x).strip()]
    return criteria


def _iso_from_epoch_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _open_url_in_configured_browser(url: str, browser: str) -> bool:
    b = str(browser or "").strip().lower()
    browser_names = (
        ["chrome", "google-chrome", "google chrome"]
        if b == "chrome"
        else ["edge", "msedge", "microsoft-edge", "microsoft edge"]
    )
    for name in browser_names:
        try:
            ctl = webbrowser.get(name)
            if ctl.open(url, new=2, autoraise=True):
                return True
        except Exception:
            continue

    platform = platform_system().lower()
    if platform == "darwin":
        app_name = "Google Chrome" if b == "chrome" else "Microsoft Edge"
        try:
            subprocess.Popen(
                ["open", "-a", app_name, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            pass

    if platform == "linux":
        bins = (
            ["google-chrome", "chrome", "chromium"]
            if b == "chrome"
            else ["microsoft-edge", "msedge"]
        )
        for bin_name in bins:
            try:
                subprocess.Popen(
                    [bin_name, url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue

    try:
        return bool(webbrowser.open(url, new=2, autoraise=True))
    except Exception:
        return False


_ARSQL_SELECT_ALIASES: List[str] = [
    "id",
    "priority",
    "summary",
    "status",
    "assignee",
    "incidentType",
    "service",
    "impactedService",
    "customerName",
    "bbva_matrixservicen1",
    "bbva_sourceservicen1",
    "bbva_startdatetime",
    "bbva_closeddate",
    "lastModifiedDate",
    "targetDate",
    "workItemId",
]


def _resolve_helix_query_mode(value: Any, *, has_arsql_uid: bool) -> str:
    token = str(value or "").strip().lower()
    if token in {"person_workitems", "person", "workitems", "v2"}:
        return "person_workitems"
    if token in {"arsql", "arsqlquery", "report_arsql", "dashboard_arsql"}:
        return "arsql"
    if token == "auto":
        return "arsql" if has_arsql_uid else "person_workitems"
    return "arsql" if has_arsql_uid else "person_workitems"


def _sql_quote(value: str) -> str:
    return "'" + str(value or "").replace("'", "''") + "'"


def _sql_in_filter(field_sql: str, values: Optional[List[str]]) -> Optional[str]:
    cleaned = [str(v or "").strip() for v in (values or []) if str(v or "").strip()]
    if not cleaned:
        return None
    quoted = ", ".join(_sql_quote(v) for v in cleaned)
    return f"{field_sql} IN ({quoted})"


def _build_arsql_endpoint(base_root: str, datasource_uid: str) -> str:
    root = str(base_root or "").strip().rstrip("/")
    uid = str(datasource_uid or "").strip()
    return f"{root}/dashboards/api/datasources/proxy/uid/{uid}/api/arsys/v1.0/report/arsqlquery"


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


def _dedup_non_empty(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        txt = str(item or "").strip()
        if not txt or txt in seen:
            continue
        out.append(txt)
        seen.add(txt)
    return out


def _uid_from_path(value: str) -> str:
    txt = str(value or "").strip()
    if not txt:
        return ""
    m = re.search(r"/uid/([A-Za-z0-9_-]{4,})", txt)
    if m:
        return str(m.group(1)).strip()
    return ""


def _pick_arsql_datasource_uid(payload: Any) -> str:
    rows: List[Dict[str, Any]] = []
    stack: List[Any] = [payload]
    seen_ids: set[int] = set()

    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            nid = id(node)
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            rows.append(node)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
            continue
        if isinstance(node, list):
            nid = id(node)
            if nid in seen_ids:
                continue
            seen_ids.add(nid)
            for value in node:
                if isinstance(value, (dict, list)):
                    stack.append(value)

    best_uid = ""
    best_score = -1
    fallback_uids: List[str] = []
    for row in rows:
        uid = str(row.get("uid") or "").strip()
        if not uid:
            uid = _uid_from_path(
                str(
                    row.get("url")
                    or row.get("path")
                    or row.get("apiUrl")
                    or row.get("proxyUrl")
                    or ""
                ).strip()
            )
        if not uid:
            continue
        fallback_uids.append(uid)

        blob = " ".join(
            str(row.get(k) or "")
            for k in (
                "type",
                "name",
                "pluginId",
                "typeName",
                "url",
                "path",
                "apiUrl",
                "access",
            )
        ).lower()
        score = 0
        if "datasource" in blob:
            score += 2
        if "bmchelix-ade-datasource" in blob:
            score += 8
        if "arsys" in blob:
            score += 12
        if "/api/arsys/" in blob:
            score += 8
        if "report/arsqlquery" in blob:
            score += 8
        if str(row.get("isDefault")).strip().lower() == "true":
            score += 1
        if str(row.get("access") or "").strip().lower() == "proxy":
            score += 1
        if score <= 0:
            continue
        if score > best_score:
            best_uid = uid
            best_score = score

    if best_uid:
        return best_uid

    dedup_fallback = _dedup_non_empty(fallback_uids)
    if len(dedup_fallback) == 1:
        return dedup_fallback[0]
    return ""


def _discover_arsql_datasource_uid(
    session: requests.Session,
    *,
    scheme: str,
    host: str,
    timeout: Tuple[float, float],
) -> str:
    base = f"{scheme}://{host}"
    urls = [
        f"{base}/dashboards/api/datasources",
        f"{base}/dashboards/api/frontend/settings",
    ]
    for url in urls:
        try:
            resp = session.get(url, timeout=timeout)
        except requests.exceptions.RequestException:
            continue
        if resp.status_code != 200:
            continue
        try:
            payload = resp.json()
        except Exception:
            continue
        uid = _pick_arsql_datasource_uid(payload)
        if uid:
            return uid
    return ""


def _build_arsql_sql(
    *,
    create_start_ms: int,
    create_end_ms: int,
    limit: int,
    offset: int,
    include_all_fields: bool = True,
    disabled_fields: Optional[set[str]] = None,
    source_service_n1: Optional[List[str]] = None,
    source_service_n2: Optional[List[str]] = None,
    incident_types: Optional[List[str]] = None,
    companies: Optional[List[str]] = None,
    environments: Optional[List[str]] = None,
    time_fields: Optional[List[str]] = None,
) -> str:
    disabled = {str(x or "").strip() for x in (disabled_fields or set()) if str(x or "").strip()}

    def _is_disabled(field_name: str) -> bool:
        return str(field_name or "").strip() in disabled

    def _field_ref(field_name: str) -> str:
        return f"`HPD:Help Desk`.`{field_name}`"

    def _first_available_field(candidates: List[str]) -> Optional[str]:
        for name in candidates:
            if not _is_disabled(name):
                return name
        return None

    def _incident_type_filter_values(
        field_name: Optional[str], values: Optional[List[str]]
    ) -> List[str]:
        raw_vals = [str(x).strip() for x in (values or []) if str(x).strip()]
        if not raw_vals:
            return []
        if str(field_name or "").strip() != "Service Type":
            return raw_vals
        out: List[str] = []
        seen: set[str] = set()
        for txt in raw_vals:
            token = re.sub(r"\s+", " ", txt.strip().lower())
            mapped: List[str]
            if token in {"incidencia", "incident", "incidence"}:
                mapped = ["Incident"]
            elif token in {"evento monitorizacion", "evento monitorización", "monitoring event"}:
                mapped = ["Monitoring Event", "Event", "Incident", "Evento Monitorización"]
            elif token in {"consulta", "consultation", "query", "question", "inquiry"}:
                mapped = ["Question", "Consultation", "Request", "Service Request"]
            else:
                mapped = [txt]
            for candidate in mapped:
                if candidate not in seen:
                    seen.add(candidate)
                    out.append(candidate)
        return out

    def _environment_filter_values(
        field_name: Optional[str], values: Optional[List[str]]
    ) -> List[str]:
        raw_vals = [str(x).strip() for x in (values or []) if str(x).strip()]
        if not raw_vals:
            return []
        # Canonicalize Spanish/English variants to tenant-friendly values.
        if str(field_name or "").strip() in {"BBVA_Environment", "BBVA_Entorno", "Entorno"}:
            out: List[str] = []
            seen: set[str] = set()
            for txt in raw_vals:
                token = re.sub(r"\s+", " ", txt.strip().lower())
                mapped: List[str]
                if token in {"produccion", "producción", "production"}:
                    mapped = ["Production", "Producción"]
                else:
                    mapped = [txt]
                for candidate in mapped:
                    if candidate not in seen:
                        seen.add(candidate)
                        out.append(candidate)
            return out
        return raw_vals

    def _select_alias(
        field_name: str,
        alias: str,
        *,
        fallback_sql: str = "''",
        assignee_case_when_blank: bool = False,
    ) -> str:
        if _is_disabled(field_name):
            return f"{fallback_sql} AS `{alias}`"
        ref = _field_ref(field_name)
        if assignee_case_when_blank:
            return f"CASE WHEN {ref} IS NULL THEN ' ' ELSE {ref} END AS `{alias}`"
        return f"{ref} AS `{alias}`"

    start_sec = int(max(0, create_start_ms) // 1000)
    end_sec = int(max(start_sec, create_end_ms) // 1000)
    start_ms = int(max(0, create_start_ms))
    end_ms = int(max(start_ms, create_end_ms))

    def _time_window(field_sql: str) -> str:
        # Tenants differ on whether epoch fields are returned/stored in seconds or milliseconds.
        # Keep the window unit-agnostic by matching both ranges.
        return (
            f"({field_sql} BETWEEN {start_sec} AND {end_sec} "
            f"OR {field_sql} BETWEEN {start_ms} AND {end_ms})"
        )

    where_parts: List[str] = []
    if not _is_disabled("BBVA_MarcaSmartIT"):
        where_parts.append(f"{_field_ref('BBVA_MarcaSmartIT')} = 'SmartIT'")
    where_parts.append(f"{_field_ref('Incident Number')} IS NOT NULL")

    default_time_field_candidates = [
        "Submit Date",
        "Last Modified Date",
        "BBVA_StartDateTime",
        "Closed Date",
        "Last Resolved Date",
    ]
    requested_time_fields = [str(x).strip() for x in (time_fields or []) if str(x).strip()]
    time_field_candidates = requested_time_fields or default_time_field_candidates
    time_clauses = [
        _time_window(_field_ref(field_name))
        for field_name in time_field_candidates
        if not _is_disabled(field_name)
    ]
    if time_clauses:
        where_parts.append("(" + " OR ".join(time_clauses) + ")")

    source_filter_field = _first_available_field(["BBVA_SourceServiceN1", "BBVA_MatrixServiceN1"])
    source_filter = (
        _sql_in_filter(_field_ref(source_filter_field), source_service_n1)
        if source_filter_field
        else None
    )
    if source_filter:
        where_parts.append(source_filter)

    source_filter_field_n2 = _first_available_field(["BBVA_SourceServiceN2", "BBVA_MatrixServiceN2"])
    source_filter_n2 = (
        _sql_in_filter(_field_ref(source_filter_field_n2), source_service_n2)
        if source_filter_field_n2
        else None
    )
    if source_filter_n2:
        where_parts.append(source_filter_n2)

    incident_type_field = _first_available_field(
        list(_ARSQL_BUSINESS_INCIDENT_TYPE_FIELD_CANDIDATES) + ["Service Type"]
    )
    incident_type_filter_values = _incident_type_filter_values(incident_type_field, incident_types)
    incident_type_filter = (
        _sql_in_filter(_field_ref(incident_type_field), incident_type_filter_values)
        if incident_type_field
        else None
    )
    if incident_type_filter:
        where_parts.append(incident_type_filter)

    # Official Enterprise Web exports filter by "Servicio Origen - BU/UG", not by recognizer/customer company.
    company_filter_field = _first_available_field(
        ["BBVA_SourceServiceBUUG", "BBVA_SourceServiceCompany", "Contact Company"]
    )
    company_filter = (
        _sql_in_filter(_field_ref(company_filter_field), companies)
        if company_filter_field
        else None
    )
    if company_filter:
        where_parts.append(company_filter)

    environment_filter_field = _first_available_field(list(_ARSQL_ENVIRONMENT_FIELD_CANDIDATES))
    environment_filter_values = _environment_filter_values(environment_filter_field, environments)
    environment_filter = (
        _sql_in_filter(_field_ref(environment_filter_field), environment_filter_values)
        if environment_filter_field
        else None
    )
    if environment_filter:
        where_parts.append(environment_filter)

    where_sql = " AND ".join(where_parts)
    safe_limit = max(1, int(limit))
    safe_offset = max(0, int(offset))

    extra_select = ", *" if include_all_fields else ""
    order_by_field = (
        _first_available_field(
            [
                "Submit Date",
                "Last Modified Date",
                "Closed Date",
                "Last Resolved Date",
                "Incident Number",
            ]
        )
        or "Incident Number"
    )
    incident_type_select_sql = (
        _select_alias(incident_type_field, "incidentType")
        if incident_type_field
        else "'' AS `incidentType`"
    )

    return (
        "SELECT "
        f"{_select_alias('Incident Number', 'id')}, "
        f"{_select_alias('Priority', 'priority')}, "
        f"{_select_alias('Description', 'summary')}, "
        f"{_select_alias('Status', 'status')}, "
        f"{_select_alias('Assignee', 'assignee', assignee_case_when_blank=True)}, "
        f"{incident_type_select_sql}, "
        f"{_select_alias('ServiceCI', 'service')}, "
        f"{_select_alias('HPD_CI', 'impactedService')}, "
        f"{_select_alias('Contact Company', 'customerName')}, "
        f"{_select_alias('BBVA_MatrixServiceN1', 'bbva_matrixservicen1')}, "
        f"{_select_alias('BBVA_SourceServiceN1', 'bbva_sourceservicen1')}, "
        f"{_select_alias('BBVA_StartDateTime', 'bbva_startdatetime')}, "
        f"{_select_alias('Closed Date', 'bbva_closeddate')}, "
        f"{_select_alias('Last Modified Date', 'lastModifiedDate')}, "
        f"{_select_alias('Submit Date', 'targetDate')}, "
        f"{_select_alias('InstanceId', 'workItemId')} "
        f"{extra_select} "
        "FROM `HPD:Help Desk` "
        f"WHERE {where_sql} "
        f"ORDER BY {_field_ref(order_by_field)} DESC "
        f"LIMIT {safe_limit} OFFSET {safe_offset}"
    )


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
        (read_timeout if read_timeout is not None else os.getenv("HELIX_READ_TIMEOUT", "30")),
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


def _column_name(column: Any, idx: int) -> str:
    if isinstance(column, str):
        name = column.strip()
        if name:
            return name
    if isinstance(column, dict):
        for key in ("name", "text", "title", "label", "field", "id"):
            name = str(column.get(key) or "").strip()
            if name:
                return name
    if idx < len(_ARSQL_SELECT_ALIASES):
        return _ARSQL_SELECT_ALIASES[idx]
    return f"col_{idx}"


def _rows_to_dicts(rows: List[Any], columns: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    names = (
        [_column_name(col, idx) for idx, col in enumerate(columns or [])]
        if columns is not None
        else list(_ARSQL_SELECT_ALIASES)
    )
    for row in rows:
        if isinstance(row, dict):
            out.append(dict(row))
            continue
        if not isinstance(row, (list, tuple)):
            continue
        item: Dict[str, Any] = {}
        for idx, value in enumerate(row):
            key = names[idx] if idx < len(names) else _column_name(None, idx)
            item[key] = value
        out.append(item)
    return out


def _frame_to_rows(frame: Dict[str, Any]) -> List[Dict[str, Any]]:
    schema = frame.get("schema")
    data = frame.get("data")
    fields = (schema or {}).get("fields") if isinstance(schema, dict) else None
    values = (data or {}).get("values") if isinstance(data, dict) else None
    if not isinstance(values, list):
        return []

    field_names = (
        [_column_name(col, idx) for idx, col in enumerate(fields)]
        if isinstance(fields, list)
        else []
    )
    row_count = 0
    for col in values:
        if isinstance(col, list):
            row_count = max(row_count, len(col))
    if row_count <= 0:
        return []

    rows: List[Dict[str, Any]] = []
    for ridx in range(row_count):
        row: Dict[str, Any] = {}
        for cidx, col_values in enumerate(values):
            if not isinstance(col_values, list):
                continue
            key = field_names[cidx] if cidx < len(field_names) else _column_name(None, cidx)
            row[key] = col_values[ridx] if ridx < len(col_values) else None
        rows.append(row)
    return rows


def _extract_arsql_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        out: List[Dict[str, Any]] = []
        for x in payload:
            out.extend(_extract_arsql_rows(x))
        return out

    if not isinstance(payload, dict):
        return []

    # AR API style
    entries = payload.get("entries")
    if isinstance(entries, list):
        out_entries: List[Dict[str, Any]] = []
        for row in entries:
            if not isinstance(row, dict):
                continue
            values = row.get("values")
            if isinstance(values, dict):
                out_entries.append(values)
            else:
                out_entries.append(row)
        if out_entries:
            return out_entries

    rows = payload.get("rows")
    if isinstance(rows, list):
        columns_raw = (
            payload.get("columns")
            or payload.get("fields")
            or payload.get("columnMetadata")
            or payload.get("meta")
        )
        columns = columns_raw if isinstance(columns_raw, list) else None
        got_rows = _rows_to_dicts(rows, columns)
        if got_rows:
            return got_rows

    frames = payload.get("frames")
    if isinstance(frames, list):
        out_frames: List[Dict[str, Any]] = []
        for frame in frames:
            if isinstance(frame, dict):
                out_frames.extend(_frame_to_rows(frame))
        if out_frames:
            return out_frames

    results = payload.get("results")
    if isinstance(results, dict):
        out_results: List[Dict[str, Any]] = []
        for v in results.values():
            out_results.extend(_extract_arsql_rows(v))
        if out_results:
            return out_results

    for vv in payload.values():
        if isinstance(vv, (dict, list)):
            got = _extract_arsql_rows(vv)
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


def _arsql_missing_field_name_from_payload(payload: Any) -> str:
    messages: List[Dict[str, Any]] = []
    if isinstance(payload, list):
        messages = [x for x in payload if isinstance(x, dict)]
    elif isinstance(payload, dict):
        for key in ("messages", "errors", "items"):
            seq = payload.get(key)
            if isinstance(seq, list):
                messages.extend(x for x in seq if isinstance(x, dict))
        if not messages:
            messages = [payload]

    for msg in messages:
        joined = " ".join(
            str(msg.get(k) or "")
            for k in ("messageType", "messageText", "messageAppendedText", "messageNumber")
        ).lower()
        if "field does not exist" not in joined:
            continue
        appended = str(msg.get("messageAppendedText") or "")
        m = re.search(r"<([^>]+)>", appended)
        if m:
            return str(m.group(1) or "").strip()
        for key in ("field", "fieldName", "column", "name"):
            cand = str(msg.get(key) or "").strip()
            if cand:
                return cand
    return ""


def _arsql_missing_field_name_from_response(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except Exception:
        payload = None
    name = _arsql_missing_field_name_from_payload(payload)
    if name:
        return name
    return ""


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


def _looks_like_session_expired_text(text: str) -> bool:
    body = (text or "").lower()
    markers = (
        "mobility_error_session_expired",
        "session_expired",
        "session expired",
        "sesion expirada",
    )
    return any(m in body for m in markers)


def _is_session_expired_response(resp: requests.Response) -> bool:
    if getattr(resp, "status_code", 0) not in (401, 403):
        return False

    if _looks_like_session_expired_text(getattr(resp, "text", "") or ""):
        return True

    try:
        payload = resp.json()
    except Exception:
        return False

    if isinstance(payload, dict):
        joined = " ".join(
            str(payload.get(k) or "") for k in ("error", "message", "detail", "code")
        ).strip()
        return _looks_like_session_expired_text(joined)
    return False


def _short_text(s: str, max_chars: int = 240) -> str:
    txt = (s or "").replace("\n", " ").replace("\r", " ").strip()
    if len(txt) <= max_chars:
        return txt
    return txt[:max_chars] + "..."


def _is_timeout_text(s: str) -> bool:
    t = (s or "").lower()
    return "timeout" in t or "timed out" in t or "read timed out" in t


def _has_auth_cookie(cookie_names: List[str]) -> bool:
    wanted = {
        "jsessionid",
        "xsrf-token",
        "loginid",
        "sso.session.restore.cookies",
        "route",
        "apt.uid",
        "apt.sid",
    }
    got = {str(x).strip().lower() for x in cookie_names}
    if any(x in got for x in wanted):
        return True
    if any(name.startswith("rsso_oidc_") for name in got):
        return True
    if any(name.endswith("_prod") for name in got):
        return True
    return False


def _apply_xsrf_headers(session: requests.Session) -> None:
    xsrf = _get_cookie_anywhere(session, "XSRF-TOKEN")
    if not xsrf:
        return
    session.headers["X-Xsrf-Token"] = xsrf
    session.headers["X-XSRF-TOKEN"] = xsrf
    session.headers["X-CSRF-Token"] = xsrf


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
    service_origin_buug: Any = None,
    service_origin_n1: Any = None,
    service_origin_n2: Any = None,
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

    parsed = urlparse(base)
    base_host = parsed.hostname or ""
    base_scheme = parsed.scheme or "https"

    arsql_uid = str(os.getenv("HELIX_ARSQL_DATASOURCE_UID", "")).strip()
    query_mode = _resolve_helix_query_mode(
        os.getenv("HELIX_QUERY_MODE", "arsql"),
        has_arsql_uid=bool(arsql_uid),
    )

    host = base_host
    scheme = base_scheme
    endpoint = f"{base}/rest/v2/person/workitems/get"
    preflight_url = f"{base}/app/"
    preflight_name = "/app/"
    arsql_base_root = ""
    arsql_base_candidates: List[str] = []
    # SmartIT ticket console is the right "safe landing" URL for work items.
    # HELIX_DASHBOARD_URL is used only for ARSQL login bootstrap, not for issue links.
    ticket_console_url = f"{base}/app/#/ticket-console"
    dashboard_url_cfg = str(os.getenv("HELIX_DASHBOARD_URL", "")).strip()
    login_bootstrap_url = ticket_console_url
    arsql_dashboard_path_default = "/dashboards/"

    if query_mode == "arsql":
        grafana_org_id_cfg = str(os.getenv("HELIX_ARSQL_GRAFANA_ORG_ID", "")).strip()
        arsql_dashboard_url_cfg = str(os.getenv("HELIX_ARSQL_DASHBOARD_URL", "")).strip()
        if not arsql_dashboard_url_cfg:
            generic_dashboard_url = dashboard_url_cfg
            if "/dashboards/" in generic_dashboard_url:
                arsql_dashboard_url_cfg = generic_dashboard_url
        arsql_base_url_raw = str(os.getenv("HELIX_ARSQL_BASE_URL", "")).strip()
        if arsql_base_url_raw:
            try:
                arsql_base_url = validate_service_base_url(
                    arsql_base_url_raw, service_name="Helix ARSQL"
                )
            except ValueError as e:
                return False, f"{source_label}: {e}", None
            arsql_base_candidates = [arsql_base_url]
        else:
            inferred_roots: List[str] = []
            dashboard_root = _root_from_url(arsql_dashboard_url_cfg)
            if dashboard_root:
                inferred_roots.append(dashboard_root)
            if "-smartit." in base_host:
                inferred_roots.append(
                    f"{base_scheme}://{base_host.replace('-smartit.', '-ir1.', 1)}"
                )
            inferred_roots.append(f"{base_scheme}://{base_host}")
            arsql_base_candidates = _dedup_non_empty(inferred_roots)
            arsql_base_url = arsql_base_candidates[0] if arsql_base_candidates else ""
            if not arsql_base_url:
                return False, f"{source_label}: no se pudo resolver host ARSQL.", None

        arsql_parsed = urlparse(arsql_base_url)
        host = arsql_parsed.hostname or base_host
        scheme = arsql_parsed.scheme or base_scheme
        arsql_base_root = f"{scheme}://{host}"
        if not arsql_base_candidates:
            arsql_base_candidates = [arsql_base_root]
        endpoint = _build_arsql_endpoint(arsql_base_root, arsql_uid) if arsql_uid else ""
        preflight_url = f"{arsql_base_root}/dashboards/"
        preflight_name = "/dashboards/"

        if host == "itsmhelixbbva-ir1.onbmc.com":
            org_id = grafana_org_id_cfg or "1175563307"
            arsql_dashboard_path_default = (
                "/dashboards/d/c6683c35-c8e4-4192-ac83-b63feab9599d/"
                f"bbva-incident-report?orgId={org_id}"
            )
        login_bootstrap_url = arsql_dashboard_url_cfg or (
            dashboard_url_cfg
            if dashboard_url_cfg
            else f"{arsql_base_root}{arsql_dashboard_path_default}"
        )

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
            "Referer": preflight_url,
            "X-Requested-With": "XMLHttpRequest",
            "X-Requested-By": "undefined" if query_mode == "arsql" else "SmartIT",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
        }
    )
    if query_mode == "arsql":
        session.headers["X-AR-Client-Type"] = str(
            os.getenv("HELIX_ARSQL_CLIENT_TYPE", "4021")
        ).strip()
        ds_auth = str(os.getenv("HELIX_ARSQL_DS_AUTH", "IMS-JWT JWT PLACEHOLDER")).strip()
        if ds_auth:
            session.headers["X-DS-Authorization"] = ds_auth
        grafana_org_id = str(os.getenv("HELIX_ARSQL_GRAFANA_ORG_ID", "")).strip()
        if grafana_org_id:
            session.headers["X-Grafana-Org-Id"] = grafana_org_id
        grafana_device_id = str(os.getenv("HELIX_ARSQL_GRAFANA_DEVICE_ID", "")).strip()
        if grafana_device_id:
            session.headers["X-Grafana-Device-Id"] = grafana_device_id

    login_wait_seconds = max(
        5,
        _coerce_int(os.getenv("HELIX_BROWSER_LOGIN_WAIT_SECONDS", "90"), 90),
    )
    login_poll_seconds = max(
        0.5,
        _coerce_float(os.getenv("HELIX_BROWSER_LOGIN_POLL_SECONDS", "2"), 2.0),
    )

    def _bootstrap_cookie_from_browser() -> Optional[str]:
        try:
            existing = get_helix_session_cookie(browser=browser, host=host)
        except Exception:
            existing = None
        existing = sanitize_cookie_header(existing)
        if existing and _has_auth_cookie(_cookie_names_from_header(existing)):
            return existing

        _open_url_in_configured_browser(login_bootstrap_url, browser)
        deadline = time.monotonic() + float(login_wait_seconds)
        while time.monotonic() < deadline:
            try:
                candidate = get_helix_session_cookie(browser=browser, host=host)
            except Exception:
                candidate = None
            candidate = sanitize_cookie_header(candidate)
            if candidate and _has_auth_cookie(_cookie_names_from_header(candidate)):
                return candidate
            time.sleep(login_poll_seconds)
        return None

    try:
        cookie = get_helix_session_cookie(browser=browser, host=host)
        cookie_error = ""
    except Exception as e:
        cookie = None
        cookie_error = str(e)
    cookie = sanitize_cookie_header(cookie)
    cookie_names_from_header = _cookie_names_from_header(cookie or "")
    if not cookie or not _has_auth_cookie(cookie_names_from_header):
        bootstrapped_cookie = _bootstrap_cookie_from_browser()
        if bootstrapped_cookie:
            cookie = bootstrapped_cookie
            cookie_names_from_header = _cookie_names_from_header(cookie)

    if not cookie:
        details = f" Detalle: {cookie_error}" if cookie_error else ""
        return (
            False,
            f"{source_label}: no se encontró cookie Helix válida en '{browser}'.{details}",
            None,
        )

    cookie_names = _cookies_to_jar(session, cookie, host=host)
    if not _has_auth_cookie(cookie_names):
        return (
            False,
            f"{source_label}: no se detectaron cookies de sesión Helix/SmartIT válidas. "
            f"cookies_cargadas={cookie_names}. "
            "Abre Helix en el navegador seleccionado y vuelve a autenticarte.",
            None,
        )

    def _refresh_auth_session(trigger: str) -> Tuple[bool, str]:
        try:
            fresh_cookie = get_helix_session_cookie(browser=browser, host=host)
            cookie_refresh_error = ""
        except Exception as e:
            fresh_cookie = None
            cookie_refresh_error = str(e)

        fresh_cookie = sanitize_cookie_header(fresh_cookie)
        if not fresh_cookie or not _has_auth_cookie(_cookie_names_from_header(fresh_cookie)):
            bootstrapped_cookie = _bootstrap_cookie_from_browser()
            if bootstrapped_cookie:
                fresh_cookie = bootstrapped_cookie

        if not fresh_cookie:
            detail = f" Detalle: {cookie_refresh_error}" if cookie_refresh_error else ""
            return (
                False,
                f"{source_label}: no se encontró cookie Helix válida en '{browser}' ({trigger})."
                f"{detail}",
            )

        try:
            session.cookies.clear()
        except Exception:
            pass

        refreshed_cookie_names = _cookies_to_jar(session, fresh_cookie, host=host)
        if not _has_auth_cookie(refreshed_cookie_names):
            bootstrapped_cookie = _bootstrap_cookie_from_browser()
            if bootstrapped_cookie:
                try:
                    session.cookies.clear()
                except Exception:
                    pass
                refreshed_cookie_names = _cookies_to_jar(session, bootstrapped_cookie, host=host)
            if not _has_auth_cookie(refreshed_cookie_names):
                return (
                    False,
                    f"{source_label}: no se detectaron cookies de sesión Helix/SmartIT válidas tras "
                    f"refresco ({trigger}). cookies_cargadas={refreshed_cookie_names}.",
                )

        try:
            refresh_preflight = session.get(preflight_url, timeout=(5, 15))
        except requests.exceptions.Timeout as e:
            return (
                False,
                f"{source_label}: timeout validando sesión Helix tras refresco ({trigger}). "
                f"Detalle: {e}",
            )
        except SSLError as e:
            return (
                False,
                f"{source_label}: error SSL validando sesión Helix tras refresco ({trigger}): {e}",
            )
        except requests.exceptions.RequestException as e:
            return (
                False,
                f"{source_label}: error de red validando sesión Helix tras refresco ({trigger}): "
                f"{type(e).__name__}: {e}",
            )

        if _looks_like_sso_redirect(refresh_preflight):
            bootstrapped_cookie = _bootstrap_cookie_from_browser()
            if bootstrapped_cookie:
                try:
                    session.cookies.clear()
                except Exception:
                    pass
                _cookies_to_jar(session, bootstrapped_cookie, host=host)
                _apply_xsrf_headers(session)
                retry_preflight: Optional[requests.Response]
                try:
                    retry_preflight = session.get(preflight_url, timeout=(5, 15))
                except requests.exceptions.RequestException:
                    retry_preflight = None
                if retry_preflight is not None:
                    refresh_preflight = retry_preflight
            if _looks_like_sso_redirect(refresh_preflight):
                return (
                    False,
                    f"{source_label}: Helix no autenticado tras refresco ({trigger}). "
                    f"Abre Helix en '{browser}' y vuelve a autenticarte.",
                )

        if refresh_preflight.status_code >= 400:
            return (
                False,
                f"{source_label}: Helix devolvió {refresh_preflight.status_code} en "
                f"{preflight_name} tras refresco ({trigger}): {_short_text(refresh_preflight.text)}",
            )

        _apply_xsrf_headers(session)
        return True, ""

    preflight: Optional[requests.Response] = None
    if not dry_run:
        try:
            preflight = session.get(preflight_url, timeout=(5, 15))
        except requests.RequestException:
            preflight = None

    _apply_xsrf_headers(session)

    if not dry_run and preflight is not None and _looks_like_sso_redirect(preflight):
        refreshed_ok, refreshed_msg = _refresh_auth_session("preflight_sso_redirect")
        if not refreshed_ok:
            return (
                False,
                f"{refreshed_msg} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

    org = (organization or "").strip()
    create_start_ms, create_end_ms, create_year = _utc_year_create_date_range_ms(create_date_year)
    if query_mode == "arsql":
        # Enterprise Web official extraction criteria: current natural year by creation date
        # (Submit Date), Production environment, and business types present in the official
        # workbook. Keep these fixed to avoid drift between app ingestion/export and the
        # reference Excel.
        incident_types_filter = list(_ARSQL_OFFICIAL_BUSINESS_INCIDENT_TYPES)
        allowed_business_incident_types = list(_ARSQL_OFFICIAL_BUSINESS_INCIDENT_TYPES)
        arsql_environments_filter = list(_ARSQL_OFFICIAL_ENVIRONMENTS)
        arsql_time_fields = list(_ARSQL_OFFICIAL_TIME_FIELDS)
    else:
        incident_types_filter = _csv_list(
            os.getenv("HELIX_FILTER_INCIDENT_TYPES"),
            "User Service Restoration,Security Incident",
        )
        allowed_business_incident_types = []
        arsql_environments_filter = []
        arsql_time_fields = []
    buug_names = (
        _csv_list(service_origin_buug, "")
        if service_origin_buug is not None
        else _csv_list(os.getenv("HELIX_FILTER_COMPANIES"), "BBVA México")
    )
    companies_filter = [{"name": name} for name in buug_names]

    attribute_names = [
        "slaStatus",
        "priority",
        "incidentType",
        "id",
        "assignee",
        "status",
        "summary",
        "service",
    ]
    custom_attribute_names = [
        "bbva_closeddate",
        "bbva_matrixservicen1",
        "bbva_sourceservicen1",
        "bbva_startdatetime",
    ]

    filter_criteria = _build_filter_criteria(
        org,
        create_start_ms,
        create_end_ms,
        status_mappings=_csv_list(os.getenv("HELIX_FILTER_STATUS_MAPPINGS"), "open,close"),
        incident_types=incident_types_filter,
        # Some Helix tenants reject unknown priority literals (ARException 1588).
        # Keep priorities unfiltered by default; allow opt-in through env override.
        priorities=_csv_list(os.getenv("HELIX_FILTER_PRIORITIES"), ""),
        companies=companies_filter,
    )

    arsql_source_service_n1 = _csv_list(
        (
            service_origin_n1
            if service_origin_n1 is not None
            else os.getenv("HELIX_ARSQL_SOURCE_SERVICE_N1")
        ),
        "ENTERPRISE WEB" if query_mode == "arsql" else "",
    )
    arsql_source_service_n2 = _csv_list(
        (
            service_origin_n2
            if service_origin_n2 is not None
            else os.getenv("HELIX_ARSQL_SOURCE_SERVICE_N2")
        ),
        "",
    )
    arsql_companies = [str(r.get("name") or "").strip() for r in companies_filter if r]
    arsql_include_all_fields = _parse_bool(
        os.getenv("HELIX_ARSQL_SELECT_ALL_FIELDS", "true"),
        default=True,
    )
    arsql_wide_fallback_used = False
    arsql_disabled_fields: set[str] = set()

    def make_body(start_index: int, page_chunk_size: Optional[int] = None) -> Dict[str, Any]:
        size = int(page_chunk_size if page_chunk_size is not None else chunk_size)
        if query_mode == "arsql":
            sql = _build_arsql_sql(
                create_start_ms=create_start_ms,
                create_end_ms=create_end_ms,
                limit=size,
                offset=int(start_index),
                include_all_fields=arsql_include_all_fields,
                disabled_fields=arsql_disabled_fields,
                source_service_n1=arsql_source_service_n1,
                source_service_n2=arsql_source_service_n2,
                incident_types=incident_types_filter,
                companies=arsql_companies,
                environments=arsql_environments_filter,
                time_fields=arsql_time_fields,
            )
            return {
                "date_format": "DD/MM/YYYY",
                "date_time_format": "DD/MM/YYYY HH:MM:SS",
                "output_type": "Table",
                "sql": sql,
            }
        return {
            "filterCriteria": filter_criteria,
            "attributeNames": attribute_names,
            "chunkInfo": {"startIndex": int(start_index), "chunkSize": size},
            "customAttributeNames": custom_attribute_names,
            "sortInfo": {},
        }

    connect_to, read_to = _get_timeouts(
        has_proxy=has_proxy,
        connect_timeout=connect_timeout,
        read_timeout=read_timeout,
        proxy_min_read_timeout=proxy_min_read_timeout,
    )
    discovery_timeout = (min(connect_to, 5.0), min(max(read_to, 5.0), 20.0))

    def _sync_arsql_origin_headers() -> None:
        session.headers["Origin"] = f"{scheme}://{host}"
        session.headers["Referer"] = preflight_url

    def _load_cookie_for_host(target_host: str) -> bool:
        host_value = str(target_host or "").strip()
        if not host_value:
            return False
        try:
            fresh = get_helix_session_cookie(browser=browser, host=host_value)
        except Exception:
            fresh = None
        fresh = sanitize_cookie_header(fresh)
        if not fresh or not _has_auth_cookie(_cookie_names_from_header(fresh)):
            return False
        _cookies_to_jar(session, fresh, host=host_value)
        _apply_xsrf_headers(session)
        return True

    def _discover_uid_across_candidates() -> Tuple[str, str]:
        roots = _dedup_non_empty(arsql_base_candidates + [arsql_base_root])
        for root in roots:
            parsed_root = urlparse(root)
            candidate_scheme = str(parsed_root.scheme or "").strip() or scheme
            candidate_host = str(parsed_root.hostname or "").strip() or host
            if not candidate_host:
                continue
            _load_cookie_for_host(candidate_host)
            uid = _discover_arsql_datasource_uid(
                session,
                scheme=candidate_scheme,
                host=candidate_host,
                timeout=discovery_timeout,
            )
            if uid:
                return uid, f"{candidate_scheme}://{candidate_host}"
        return "", arsql_base_root

    if query_mode == "arsql" and not arsql_uid:
        arsql_uid, discovered_root = _discover_uid_across_candidates()
        if arsql_uid:
            arsql_base_root = discovered_root or arsql_base_root
            discovered_parsed = urlparse(arsql_base_root)
            host = discovered_parsed.hostname or host
            scheme = discovered_parsed.scheme or scheme
            preflight_url = f"{arsql_base_root}/dashboards/"
            preflight_name = "/dashboards/"
            _sync_arsql_origin_headers()
        if not arsql_uid:
            bootstrapped_cookie = _bootstrap_cookie_from_browser()
            if bootstrapped_cookie:
                try:
                    session.cookies.clear()
                except Exception:
                    pass
                _cookies_to_jar(session, bootstrapped_cookie, host=host)
                _apply_xsrf_headers(session)
                arsql_uid, discovered_root = _discover_uid_across_candidates()
                if arsql_uid:
                    arsql_base_root = discovered_root or arsql_base_root
                    discovered_parsed = urlparse(arsql_base_root)
                    host = discovered_parsed.hostname or host
                    scheme = discovered_parsed.scheme or scheme
                    preflight_url = f"{arsql_base_root}/dashboards/"
                    preflight_name = "/dashboards/"
                    _sync_arsql_origin_headers()
        if not arsql_uid:
            return (
                False,
                f"{source_label}: HELIX_QUERY_MODE=arsql no pudo autodetectar datasource uid. "
                "Configura HELIX_ARSQL_DATASOURCE_UID o abre antes un dashboard Helix y reintenta.",
                None,
            )
        endpoint = _build_arsql_endpoint(
            arsql_base_root or f"{scheme}://{host}",
            arsql_uid,
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

        # Test rápido: valida sesión/autenticación contra una URL ligera.
        # Evita ejecutar la query pesada solo para probar conexión.
        probe_connect = max(1.0, min(dry_c, 5.0))
        probe_read = max(3.0, min(dry_r, 15.0))

        if preflight is None:
            try:
                preflight = session.get(preflight_url, timeout=(probe_connect, probe_read))
            except requests.exceptions.Timeout as e:
                return (
                    False,
                    f"{source_label}: timeout Helix (dry-run rápido) en {preflight_name}. "
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
                f"{source_label}: Helix no autenticado (redirección a SSO en {preflight_name}). "
                f"cookies_cargadas={cookie_names} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        if preflight.status_code >= 400:
            return (
                False,
                f"{source_label}: Helix dry-run rápido falló en {preflight_name} "
                f"({preflight.status_code}): {_short_text(preflight.text)} | "
                f"cookies_cargadas={cookie_names} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        _apply_xsrf_headers(session)

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
    arsql_limit = max(
        1,
        _coerce_int(
            os.getenv("HELIX_ARSQL_LIMIT", str(chunk_size)),
            max(1, int(chunk_size)),
        ),
    )
    base_chunk_size = arsql_limit if query_mode == "arsql" else max(1, int(chunk_size))
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
    filtered_out_by_business_incident_type = 0
    filtered_out_by_environment = 0
    max_session_refreshes = max(
        0,
        _coerce_int(os.getenv("HELIX_MAX_SESSION_REFRESHES", "1"), 1),
    )
    session_refreshes = 0

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

        if r.status_code != 200:
            if query_mode == "arsql":
                missing_field = _arsql_missing_field_name_from_response(r)
                if missing_field and missing_field not in arsql_disabled_fields:
                    arsql_disabled_fields.add(missing_field)
                    continue
            if (
                query_mode == "arsql"
                and arsql_include_all_fields
                and not arsql_wide_fallback_used
                and page <= 1
                and r.status_code in (400, 422)
            ):
                arsql_include_all_fields = False
                arsql_wide_fallback_used = True
                continue
            if _is_session_expired_response(r):
                if session_refreshes >= max_session_refreshes:
                    return (
                        False,
                        f"{source_label}: error Helix ({r.status_code}) por sesión expirada "
                        f"y se agotaron los refrescos de sesión. "
                        f"Detalle: {_short_text(r.text)} | proxy={helix_proxy or '(sin proxy)'} | "
                        f"verify={verify_desc}",
                        None,
                    )
                refreshed_ok, refreshed_msg = _refresh_auth_session("session_expired")
                if not refreshed_ok:
                    return (
                        False,
                        f"{refreshed_msg} | proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                        None,
                    )
                session_refreshes += 1
                continue
            return (
                False,
                f"{source_label}: error Helix ({r.status_code}): {r.text[:800]} | "
                f"proxy={helix_proxy or '(sin proxy)'} | verify={verify_desc}",
                None,
            )

        page += 1

        data = r.json()
        batch = _extract_arsql_rows(data) if query_mode == "arsql" else _extract_objects(data)
        if not batch:
            break

        total = _extract_total(data)

        new_in_page = 0
        for it in batch:
            if query_mode == "arsql":
                values = cast(Dict[str, Any], it if isinstance(it, dict) else {})
            else:
                values_raw = it.get("values")
                values = cast(Dict[str, Any], values_raw if isinstance(values_raw, dict) else it)
            mapped_item = map_helix_values_to_item(
                values=values,
                base_url=base,
                country=country_value,
                source_alias=alias_value,
                source_id=source_id_value,
                ticket_console_url=ticket_console_url,
            )
            if mapped_item is None:
                continue
            if (
                query_mode == "arsql"
                and allowed_business_incident_types
                and not is_allowed_helix_business_incident_type(mapped_item.incident_type)
            ):
                filtered_out_by_business_incident_type += 1
                continue
            if query_mode == "arsql" and arsql_environments_filter:
                env_raw = ""
                raw_fields = mapped_item.raw_fields or {}
                for env_key in ("BBVA_Environment", "BBVA_Entorno", "Entorno"):
                    env_candidate = str(raw_fields.get(env_key) or "").strip()
                    if env_candidate:
                        env_raw = env_candidate
                        break
                env_token = re.sub(r"\s+", " ", env_raw.strip().lower())
                allowed_env_tokens = {
                    re.sub(r"\s+", " ", str(x).strip().lower())
                    for x in arsql_environments_filter
                    if str(x).strip()
                }
                if env_token in {"producción", "produccion"}:
                    env_token = "production"
                if "produccion" in allowed_env_tokens or "producción" in allowed_env_tokens:
                    allowed_env_tokens.add("production")
                if allowed_env_tokens and env_token and env_token not in allowed_env_tokens:
                    filtered_out_by_environment += 1
                    continue
            wid = str(mapped_item.id or "").strip()
            if wid in seen_ids:
                continue

            seen_ids.add(wid)
            new_in_page += 1
            items.append(mapped_item)

        if new_in_page == 0:
            break

        batch_size = len(batch)
        if batch_size <= 0:
            break
        # Advance using the effective batch size returned by Helix. Some tenants ignore
        # requested chunkSize and return a fixed page size.
        start += int(batch_size)

        if total is not None and (start >= total or len(seen_ids) >= total):
            break
        if total is None and batch_size < current_chunk_size:
            if query_mode != "arsql":
                break
            # Some tenants enforce a fixed page size (e.g. 25 rows) regardless of requested LIMIT.
            # In that case, keep paging using the effective page size until the API returns empty.
            current_chunk_size = int(batch_size)

    doc = existing_doc or HelixDocument.empty()
    doc.schema_version = "1.0"
    doc.ingested_at = now_iso()
    # Persist SmartIT base URL so UI links always land in the incident console.
    doc.helix_base_url = base
    create_start_iso = _iso_from_epoch_ms(create_start_ms)
    create_end_iso = _iso_from_epoch_ms(create_end_ms)
    status_mappings_q = (
        ",".join(cast(List[str], filter_criteria.get("statusMappings", []))) or "all"
    )
    incident_types_q = ",".join(cast(List[str], filter_criteria.get("incidentTypes", []))) or "all"
    priorities_q = ",".join(cast(List[str], filter_criteria.get("priorities", []))) or "all"
    company_rows = cast(List[Dict[str, str]], filter_criteria.get("companies", []))
    companies_q = ",".join(str(r.get("name") or "").strip() for r in company_rows if r) or "all"
    if query_mode == "arsql":
        source_service_n1_q = ",".join(arsql_source_service_n1) or "all"
        source_service_n2_q = ",".join(arsql_source_service_n2) or "all"
        arsql_environments_q = ",".join(arsql_environments_filter) or "all"
        arsql_time_fields_q = ",".join(arsql_time_fields) or "default"
        select_mode_q = "wide" if arsql_include_all_fields else "narrow"
        disabled_fields_q = ",".join(sorted(arsql_disabled_fields)) or "none"
        doc.query = (
            "mode=arsql; "
            f"arsql_root={arsql_base_root}; "
            f"createDate in [{create_start_iso} .. {create_end_iso}] (year={create_year}); "
            f"timeFields=[{arsql_time_fields_q}]; "
            f"sourceServiceN1=[{source_service_n1_q}]; "
            f"sourceServiceN2=[{source_service_n2_q}]; "
            f"incidentTypes=[{incident_types_q}]; companies=[{companies_q}]; environments=[{arsql_environments_q}]; "
            f"postFilterBusinessIncidentTypes=[{','.join(allowed_business_incident_types) or 'all'}]; "
            f"page_limit={base_chunk_size}; "
            f"select={select_mode_q}; "
            f"disabled_fields=[{disabled_fields_q}]"
        )
    else:
        doc.query = (
            f"organizations in [{org}] and createDate in [{create_start_iso} .. {create_end_iso}]"
            f" (year={create_year}); statusMappings=[{status_mappings_q}]; "
            f"incidentTypes=[{incident_types_q}]; priorities=[{priorities_q}]; "
            f"companies=[{companies_q}]; "
            f"postFilterBusinessIncidentTypes=[{','.join(allowed_business_incident_types) or 'all'}]"
        )

    merged = {_item_merge_key(i): i for i in doc.items}
    for i in items:
        merged[_item_merge_key(i)] = i
    doc.items = list(merged.values())

    return (
        True,
        (
            f"{source_label}: ingesta Helix OK ({len(items)} items, merge total {len(doc.items)}). "
            f"Filtrados por tipo (negocio): {filtered_out_by_business_incident_type}. "
            f"Filtrados por entorno: {filtered_out_by_environment}."
        ),
        doc,
    )
