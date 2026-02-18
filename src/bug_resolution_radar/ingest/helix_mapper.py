"""Helix-to-canonical mapping helpers used between API payload and JSON persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Any, Dict, Optional

from bug_resolution_radar.schema_helix import HelixWorkItem


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
    "resolved": "Ready to Deploy",
    "closed": "Deployed",
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
    "cerrado": "Deployed",
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
    "resuelto": "Ready to Deploy",
    "revision": "Ready To Verify",
    "terminado": "Deployed",
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


def map_helix_status(raw_status: Any) -> str:
    """Map Helix workflow statuses into dashboard canonical statuses."""
    token = _normalize_token(raw_status)
    if not token:
        return "New"

    explicit = _STATUS_MAP.get(token)
    if explicit:
        return explicit

    if any(t in token for t in _CLOSED_TOKENS):
        return "Deployed"
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
            or ((value.get("company") or {}).get("name") if isinstance(value.get("company"), dict) else "")
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


def map_helix_values_to_item(
    *,
    values: Dict[str, Any],
    base_url: str,
    country: str,
    source_alias: str,
    source_id: str,
) -> Optional[HelixWorkItem]:
    """Build a HelixWorkItem with canonicalized fields from one API object."""
    wid = _as_text(values.get("displayId") or values.get("id") or values.get("workItemId"))
    if not wid:
        return None

    raw_status = _extract_text(values.get("status"))
    raw_priority = _extract_text(values.get("priority"))
    return HelixWorkItem(
        id=wid,
        summary=_as_text(values.get("summary") or values.get("description")),
        status=map_helix_status(raw_status),
        status_raw=raw_status,
        priority=map_helix_priority(raw_priority),
        incident_type=_extract_text(values.get("incidentType")),
        service=_extract_text(values.get("service")),
        impacted_service=_extract_text(values.get("impactedService")),
        assignee=_extract_person_name(values.get("assignee") or values.get("assigneeName")),
        customer_name=_extract_customer_name(
            values.get("customerName") or values.get("customer") or values.get("company")
        ),
        # Explicitly ignored in canonical VRR mapping for this geography.
        sla_status="",
        target_date=values.get("targetDate"),
        last_modified=values.get("lastModifiedDate") or values.get("lastModified"),
        start_datetime=_to_iso_datetime(_extract_custom_attr(values, "bbva_startdatetime")),
        closed_date=_to_iso_datetime(_extract_custom_attr(values, "bbva_closeddate")),
        matrix_service_n1=_extract_custom_attr(values, "bbva_matrixservicen1"),
        source_service_n1=_extract_custom_attr(values, "bbva_sourceservicen1"),
        url=f"{base_url}/app/#/ticket-console",
        country=country,
        source_alias=source_alias,
        source_id=source_id,
    )
