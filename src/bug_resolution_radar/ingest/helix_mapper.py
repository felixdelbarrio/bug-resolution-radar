"""Helix-to-canonical mapping helpers used between API payload and JSON persistence."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from bug_resolution_radar.models.schema_helix import HelixWorkItem


def _normalize_token(value: Any) -> str:
    txt = str(value or "").strip().lower()
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _as_text(value: Any) -> str:
    return str(value or "").strip()


_INCIDENT_NUMBER_RE = re.compile(r"^INC\\d+", flags=re.IGNORECASE)
_SMARTIT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def _looks_like_incident_number(value: str) -> bool:
    return bool(_INCIDENT_NUMBER_RE.match(str(value or "").strip()))


def _looks_like_smartit_id(value: str) -> bool:
    txt = str(value or "").strip()
    if not txt or _looks_like_incident_number(txt):
        return False
    return bool(_SMARTIT_ID_RE.fullmatch(txt))


def _detect_smartit_id(values: Dict[str, Any]) -> str:
    """
    Best-effort detection of the SmartIT internal id used in `/incidentPV/<id>`.

    ARSQL tenants may return the internal id under different column names, or even
    as an unnamed trailing column (e.g. `col_14`). Prefer IDs starting with `IDG`,
    then fall back to keys that "sound like" ids.
    """
    for value in values.values():
        txt = _as_text(value)
        if txt.upper().startswith("IDG") and _looks_like_smartit_id(txt):
            return txt

    id_like_tokens = ("instance", "work", "guid", "entry", "id")
    for key, value in values.items():
        key_norm = _normalize_token(key)
        if not key_norm:
            continue
        if not any(tok in key_norm for tok in id_like_tokens):
            continue
        txt = _as_text(value)
        if _looks_like_smartit_id(txt):
            return txt

    for value in values.values():
        txt = _as_text(value)
        if _looks_like_smartit_id(txt):
            return txt
    return ""


def _extract_text(value: Any) -> str:
    if isinstance(value, dict):
        return _as_text(
            value.get("fullName")
            or value.get("displayName")
            or value.get("name")
            or value.get("label")
            or value.get("value")
            or value.get("id")
            or ""
        )
    if isinstance(value, list):
        parts = [_extract_text(v) for v in value]
        parts = [p for p in parts if p]
        if not parts:
            return ""
        # Keep order while removing duplicates.
        seen = set()
        ordered = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                ordered.append(p)
        return ", ".join(ordered)
    return _as_text(value)


_STATUS_MAP: Dict[str, str] = {
    "assigned": "Analysing",
    "resolved": "Resolved",
    "closed": "Closed",
    "new": "New",
    "open": "New",
    "in progress": "En progreso",
    "pending": "Analysing",
    "cancelled": "Accepted",
    "canceled": "Accepted",
    "rejected": "Accepted",
    "asignado": "Analysing",
    "asignado a proveedor": "Blocked",
    "autorizacion de aplicacion": "Blocked",
    "autorizacion de cierre": "Blocked",
    "autorizacion de construccion": "Blocked",
    "autorizacion de inicio": "Blocked",
    "autorizacion de planificacion": "Blocked",
    "autorizacion de prueba": "Blocked",
    "bajo investigacion": "Analysing",
    "borrador": "New",
    "cancelada": "Accepted",
    "cancelado": "Accepted",
    "cerrado": "Closed",
    "corregido": "Ready To Verify",
    "en cesta": "New",
    "en curso": "En progreso",
    "en implantacion": "Ready to Deploy",
    "en revision": "Ready To Verify",
    "enviado": "New",
    "esperando automaticas": "Blocked",
    "esperando autorizacion": "Blocked",
    "ninguna accion planificada": "Accepted",
    "nuevo": "New",
    "pendiente": "Analysing",
    "peticion de autorizacion": "Blocked",
    "peticion de cambio": "Analysing",
    "planificacion": "Analysing",
    "planificacion en curso": "Analysing",
    "planificado para correccion": "En progreso",
    "por fases": "En progreso",
    "programado": "Analysing",
    "pte autorizacion": "Blocked",
    "rechazado": "Accepted",
    "registrado": "New",
    "resuelto": "Resolved",
    "revision": "Ready To Verify",
    "terminado": "Closed",
}

_CLOSED_TOKENS = (
    "closed",
    "cerrado",
    "cerrada",
    "terminado",
    "terminada",
    "done",
    "completed",
)

_OPEN_TOKENS = ("open", "abierto", "abierta")

_BUSINESS_INCIDENT_TYPE_CANDIDATES = (
    "BBVA_Tipo_de_Incidencia",
    "BBVA_TipoDeIncidencia",
    "BBVA_TipoIncidencia",
    "BBVA_TypeOfIncident",
    "BBVA_IncidentType",
    "Tipo_de_Incidencia",
    "Tipo de Incidencia",
)


def map_helix_status(raw_status: Any) -> str:
    """Map Helix workflow statuses into dashboard canonical statuses."""
    token = _normalize_token(raw_status)
    if not token:
        return "New"

    explicit = _STATUS_MAP.get(token)
    if explicit:
        return explicit

    if any(t in token for t in _CLOSED_TOKENS):
        return "Closed"
    if any(t in token for t in _OPEN_TOKENS):
        return "New"
    return "New"


def map_helix_priority(raw_priority: Any) -> str:
    """Map Helix criticality labels into Jira-like priority values."""
    txt = _extract_text(raw_priority)
    token = _normalize_token(txt)
    if not token:
        return ""

    if token in {"very high", "critical", "muy alta", "muy alto", "critica", "critico"}:
        return "Highest"
    if token in {"high", "alta", "alto"}:
        return "High"
    if token in {"moderate", "medium", "media", "medio"}:
        return "Medium"
    if token in {"low", "baja", "bajo"}:
        return "Low"
    if token in {"very low", "lowest", "muy baja", "muy bajo"}:
        return "Lowest"
    return txt


def _extract_business_incident_type(values: Dict[str, Any]) -> str:
    for candidate in _BUSINESS_INCIDENT_TYPE_CANDIDATES:
        val = _extract_custom_attr(values, candidate)
        if val:
            return val
        direct = values.get(candidate)
        if direct not in (None, ""):
            txt = _extract_text(direct)
            if txt:
                return txt

    for key, val in values.items():
        key_token = _normalize_token(key)
        if not key_token:
            continue
        if "tecnolog" in key_token:
            continue
        if "tipo" in key_token and ("incid" in key_token or "incident" in key_token):
            txt = _extract_text(val)
            if txt:
                return txt
    return ""


def map_helix_incident_type(raw_incident_type: Any, values: Optional[Dict[str, Any]] = None) -> str:
    """Normalize business incident type to 'Incidencia' / 'Consulta' when detectable."""
    business_raw = _extract_business_incident_type(values or {})
    fallback_raw = _extract_text(raw_incident_type)

    for txt in (business_raw, fallback_raw):
        token = _normalize_token(txt)
        if not token:
            continue
        if (
            "evento" in token and "monitor" in token
            or token in {"monitoring event", "event monitoring"}
        ):
            return "Evento Monitorización"
        if "consulta" in token or token in {"consultation", "query", "question", "inquiry"}:
            return "Consulta"
        if (
            "incidencia" in token
            or "incident" in token
            or token in {"user service restoration", "security incident"}
        ):
            return "Incidencia"
        if txt:
            return txt
    return ""


def is_allowed_helix_business_incident_type(value: Any) -> bool:
    token = _normalize_token(value)
    return token in {"incidencia", "consulta", "evento monitorizacion"}


def _extract_person_name(value: Any) -> str:
    if isinstance(value, dict):
        return _as_text(
            value.get("fullName") or value.get("displayName") or value.get("name") or ""
        )
    return _as_text(value)


def _extract_customer_name(value: Any) -> str:
    if isinstance(value, dict):
        return _as_text(
            value.get("fullName")
            or value.get("displayName")
            or value.get("name")
            or (
                (value.get("company") or {}).get("name")
                if isinstance(value.get("company"), dict)
                else ""
            )
            or ""
        )
    return _as_text(value)


def _to_iso_datetime(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        epoch = float(value)
    else:
        txt = _as_text(value)
        if not txt:
            return None
        if re.fullmatch(r"\d{10,13}", txt):
            epoch = float(txt)
        else:
            return txt
    if epoch > 10_000_000_000:
        epoch = epoch / 1000.0
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except Exception:
        return _as_text(value) or None


def _extract_custom_attr(values: Dict[str, Any], attr_name: str) -> str:
    direct = values.get(attr_name)
    if direct not in (None, ""):
        return _extract_text(direct)

    attr_name_norm = str(attr_name or "").strip().lower()
    if not attr_name_norm:
        return ""

    # ARSQL responses may preserve original column casing instead of aliases.
    for key, val in values.items():
        if str(key or "").strip().lower() == attr_name_norm and val not in (None, ""):
            return _extract_text(val)

    for key in ("customFields", "customAttributes", "customAttributeValues", "customAttributeMap"):
        container = values.get(key)
        if isinstance(container, dict):
            for k, v in container.items():
                if str(k or "").strip().lower() == attr_name_norm:
                    return _extract_text(v)
        if isinstance(container, list):
            for row in container:
                if not isinstance(row, dict):
                    continue
                row_name = str(
                    row.get("name")
                    or row.get("attributeName")
                    or row.get("customAttributeName")
                    or row.get("field")
                    or ""
                ).strip()
                if row_name.lower() != attr_name_norm:
                    continue
                return _extract_text(
                    row.get("value")
                    or row.get("displayValue")
                    or row.get("text")
                    or row.get("values")
                    or ""
                )
    return ""


def _json_safe_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe_scalar(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe_scalar(v) for k, v in value.items()}
    return _extract_text(value)


def _raw_fields_snapshot(values: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in values.items():
        key = str(k or "").strip()
        if not key:
            continue
        # Keep snapshot sparse: most ARQL `SELECT *` fields are null/blank and storing
        # them inflates `helix_dump.json` (disk, memory, serialization time) without
        # adding value to the official export, which already creates headers even when
        # row values are missing.
        if v is None:
            continue
        if isinstance(v, str):
            if not v.strip():
                continue
            out[key] = v
            continue
        if isinstance(v, (bool, int)):
            out[key] = v
            continue
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                continue
            out[key] = v
            continue
        safe_value = _json_safe_scalar(v)
        if safe_value in (None, "", [], {}):
            continue
        out[key] = safe_value
    return out


def map_helix_values_to_item(
    *,
    values: Dict[str, Any],
    base_url: str,
    country: str,
    source_alias: str,
    source_id: str,
    ticket_console_url: str = "",
) -> Optional[HelixWorkItem]:
    """Build a HelixWorkItem with canonicalized fields from one API object."""
    display_id = _as_text(
        values.get("displayId") or values.get("displayID") or values.get("display_id")
    )
    raw_id = _as_text(values.get("id"))
    raw_work_item_id = _as_text(
        values.get("workItemId")
        or values.get("workItemID")
        or values.get("instanceId")
        or values.get("InstanceId")
        or values.get("instance_id")
        or values.get("workItemId")
    )

    incident_number = ""
    for candidate in (display_id, raw_id, raw_work_item_id):
        if _looks_like_incident_number(candidate):
            incident_number = candidate
            break
    if not incident_number:
        incident_number = display_id or raw_id or raw_work_item_id

    if not incident_number:
        return None

    smartit_id = ""
    for candidate in (raw_work_item_id, raw_id):
        if _looks_like_smartit_id(candidate):
            smartit_id = candidate
            break
    if not smartit_id:
        smartit_id = _detect_smartit_id(values)

    base = str(base_url or "").strip().rstrip("/")
    if smartit_id and base:
        url = f"{base}/app/#/incidentPV/{smartit_id}"
    else:
        url = str(ticket_console_url or f"{base}/app/#/ticket-console").strip()

    raw_status = _extract_text(values.get("status"))
    raw_priority = _extract_text(values.get("priority"))
    return HelixWorkItem(
        id=incident_number,
        summary=_as_text(values.get("summary") or values.get("description")),
        status=map_helix_status(raw_status),
        status_raw=raw_status,
        priority=map_helix_priority(raw_priority),
        incident_type=map_helix_incident_type(values.get("incidentType"), values),
        service=_extract_text(values.get("service")),
        impacted_service=_extract_text(values.get("impactedService")),
        assignee=_extract_person_name(values.get("assignee") or values.get("assigneeName")),
        customer_name=_extract_customer_name(
            values.get("customerName") or values.get("customer") or values.get("company")
        ),
        # Explicitly ignored in canonical VRR mapping for this geography.
        sla_status="",
        target_date=_to_iso_datetime(values.get("targetDate")),
        last_modified=_to_iso_datetime(
            values.get("lastModifiedDate") or values.get("lastModified")
        ),
        start_datetime=_to_iso_datetime(_extract_custom_attr(values, "bbva_startdatetime")),
        closed_date=_to_iso_datetime(_extract_custom_attr(values, "bbva_closeddate")),
        matrix_service_n1=_extract_custom_attr(values, "bbva_matrixservicen1"),
        source_service_n1=_extract_custom_attr(values, "bbva_sourceservicen1"),
        url=url,
        country=country,
        source_alias=source_alias,
        source_id=source_id,
        raw_fields=_raw_fields_snapshot(values),
    )
