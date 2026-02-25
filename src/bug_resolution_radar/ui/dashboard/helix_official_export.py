"""Helix issues export helpers aligned with the official Enterprise Web workbook shape.

This module keeps UI behavior unchanged and only affects the file generated when exporting
issues for Helix scopes. It builds:
1) an "official-style" sheet with the exact header order seen in the reference workbook
2) a raw ARQL sheet (all ingested fields) for traceability / gap analysis

The value mapping is best-effort and relies on the ingested `raw_fields` snapshot plus a few
canonical fallbacks. If ARQL returns localized/display column labels, most headers resolve
directly. If a tenant returns technical names, the raw sheet still preserves all values.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import pandas as pd

from bug_resolution_radar.schema_helix import HelixWorkItem

HELIX_OFFICIAL_EXCEL_COLUMNS: list[str] = [
    "Mes",
    "ID de la Incidencia",
    "Criticidad",
    "Título",
    "Fecha de creación",
    "Fecha actualización",
    "Estado",
    "Motivo de Estado",
    "Nota de Resolución",
    "Tipo de gestión",
    "Recognizer - Usuario Id",
    "Recognizer - Nombre",
    "Recognizer - E-Mail",
    "Recognizer - Teléfono",
    "Recognizer - BU/UG",
    "Recognizer - Organización",
    "Recognizer - Departamento",
    "Recognizer - Región",
    "Recognizer - Ubicación",
    "Recognizer - Sitio",
    "Servicio Origen - BU/UG",
    "Servicio Origen - Servicio N1",
    "Servicio Origen - Servicio N2",
    "Servicio Origen - Operativa",
    "Servicio Origen - Criticidad Real",
    "Servicio Origen - Tramo de Afectación",
    "Servicio Origen - Tipo de Impacto",
    "Servicio Origen - % de Impacto",
    "Servicio Causante - BU/UG",
    "Servicio Causante - Servicio N1",
    "Servicio Causante - Servicio N2",
    "Servicio Causante - Operativa",
    "Servicio Causante - Criticidad Real",
    "Servicio Causante - Tramo de Afectación",
    "Servicio Causante - Tipo de Impacto",
    "Servicio Causante - % de Impacto",
    "Servicio Matrix de Catalogación - BU/UG",
    "Servicio Matrix de Catalogación - Servicio N1",
    "Servicio Matrix de Catalogación - Servicio N2",
    "Servicio Matrix de Catalogación - Operativa",
    "Servicio Matrix de Catalogación - Criticidad Real",
    "Servicio Matrix de Catalogación - Tramo de Afectación",
    "Servicio Matrix de Catalogación - Tipo de Impacto",
    "Servicio Matrix de Catalogación - % de Impacto",
    "Tipo de Incidencia",
    "CI",
    "Causa Raíz Principal",
    "Causa Raíz Secundaria 1",
    "Causa Raíz Secundaria 2",
    "Causa Raíz Secundaria 3",
    "Descripción Ejecutiva Causa Raíz",
    "Descripción",
    "Incident Lead - BU/UG",
    "Incident Lead - Organización",
    "Incident Lead - Grupo Id",
    "Incident Lead - Grupo",
    "Incident Lead - Usuario Id",
    "Incident Lead - Nombre",
    "Service Desk - Empresa",
    "Service Desk - Organización",
    "Service Desk - Nombre",
    "Service Desk - Grupo",
    "Hub Technical Manager - Empresa",
    "Hub Technical Manager - Organización",
    "Hub Technical Manager - Nombre",
    "Hub Technical Manager - Grupo",
    "Incident Manager - BU/UG",
    "Incident Manager - Organización",
    "Incident Manager - Grupo Id",
    "Incident Manager - Grupo",
    "Incident Manager - Usuario Id",
    "Incident Manager - Nombre",
    "Involucrar a equipo no técnicos",
    "Línea de Negocio - BU/UG",
    "Línea de Negocio",
    "App/Component Owner",
    "Información Solicitada",
    "Motivo Cancelación",
    "Criticidad Manual",
    "Incidencia Multipaís",
    "Escalado JST",
    "Incidencia Recurrente",
    "Numero de Usuarios",
    "Tipo de Incidencia Tecnológica",
    "ID incidencia tercero",
    "Solicitud de Reasignación",
    "Fecha Hora Inicio",
    "Tier",
    "Descripción Ejecutiva",
    "Fecha y Hora de Apertura",
    "Impacto Final",
    "Prioridad Low",
    "Motivo de ajuste criticidad",
    "Negocio entidad nombre",
    "Negocio entidad ID",
    "Tipo de Ventana",
    "¿Incidencia ocasionada por cambio?",
    "Remitente",
    "Modificado Por",
    "Fecha de Cierre",
    "Instanceid",
    "Entorno",
    "Origen de la incidencia",
    "BOIL",
    "BOM",
    "Id Petición",
    "Fecha Resolución",
    "Incident Lead - Omega",
    "Incident Manager - Omega",
    "Fecha fin Impacto",
    "Clientes Afectados",
    "% Clientes Afectados",
    "% Transacciones Afectadas",
    "% Transacciones Media Diaria (€)",
    "Disponibilidad del dato",
    "Autenticidad del dato",
    "Integridad del dato",
    "Confidencialidad del dato",
    "Incidente reflejado en medios de comunicación",
    "Recibió quejas de forma repetitiva",
    "Incapacidad para cumplir requisitos regulatorios",
    "Probable pérdida de clientes o contrapartes financieras con un impacto material en el negocio de FE",
    "Geografía Pendiente",
    "España",
    "Italia",
    "Portugal",
    "Turquia",
    "Reino Unido",
    "Alemania",
    "Francia",
    "Curazao",
    "Bélgica",
    "Irlanda",
    "Finlandia",
    "Países Bajos",
    "Luxemburgo",
    "Suiza",
    "Rumanía",
    "Malta",
    "Chipre",
    "México",
    "Argentina",
    "Colombia",
    "Perú",
    "Uruguay",
    "Venezuela",
    "Paraguay",
    "Chile",
    "Brasil",
    "Bolivia",
    "Estados Unidos",
    "China",
    "Hong Kong",
    "Japón",
    "Corea del Sur",
    "Taiwan",
    "Singapur",
    "Costos Directos e Indirectos Incurridos",
    "Fecha Creación DORA",
    "Fecha Modificación DORA",
    "Tiempo pendiente",
    "(MTTR) sin pending",
    "EscaladoReguladorLocal",
    "PostMortem URL",
]

_CANONICAL_FALLBACKS: dict[str, Sequence[str]] = {
    "ID de la Incidencia": ("key", "id"),
    "Criticidad": ("priority",),
    "Título": ("summary",),
    "Fecha de creación": ("created",),
    "Fecha actualización": ("updated",),
    "Estado": ("status",),
    "Tipo de Incidencia": ("type",),
    "Descripción": ("summary",),
    "Fecha de Cierre": ("resolved",),
    "Fecha Resolución": ("resolved",),
    "Instanceid": ("source_id",),  # fallback placeholder if raw is missing
    "Entorno": ("country",),
}

_RAW_FALLBACKS: dict[str, Sequence[str]] = {
    "ID de la Incidencia": ("Incident Number", "id"),
    "Criticidad": ("Priority", "priority"),
    "Título": ("Description", "summary"),
    "Fecha de creación": ("Submit Date", "targetDate"),
    "Fecha actualización": ("Last Modified Date", "lastModifiedDate"),
    "Estado": ("Status", "status"),
    "Tipo de Incidencia": ("Service Type", "incidentType"),
    "Descripción": ("Detailed Decription", "Description", "summary"),
    "Fecha de Cierre": ("Closed Date", "BBVA_ClosedDate", "bbva_closeddate"),
    "Fecha Resolución": ("Last Resolved Date", "Fecha Resolución"),
    "Fecha Hora Inicio": ("BBVA_StartDateTime", "bbva_startdatetime"),
    "Servicio Origen - BU/UG": ("BBVA_SourceServiceBUUG",),
    "Servicio Origen - Servicio N1": ("BBVA_SourceServiceN1", "bbva_sourceservicen1"),
    "Servicio Matrix de Catalogación - Servicio N1": (
        "BBVA_MatrixServiceN1",
        "bbva_matrixservicen1",
    ),
    "CI": ("ServiceCI", "service", "HPD_CI", "impactedService"),
    "Instanceid": ("InstanceId", "workItemId"),
    "Entorno": ("BBVA_Entorno", "Entorno"),
    "PostMortem URL": ("PostMortem URL", "BBVA_PostMortemURL"),
}

_OFFICIAL_DATE_HEADERS: set[str] = {
    "Fecha de creación",
    "Fecha actualización",
    "Fecha Hora Inicio",
    "Fecha y Hora de Apertura",
    "Fecha de Cierre",
    "Fecha Resolución",
    "Fecha fin Impacto",
    "Fecha Creación DORA",
    "Fecha Modificación DORA",
}


def _norm_key(value: object) -> str:
    txt = str(value or "").strip()
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = txt.lower()
    txt = re.sub(r"[^a-z0-9]+", "", txt)
    return txt


def _jsonable_text(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _raw_lookup_build(raw_fields: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    exact = {str(k): v for k, v in raw_fields.items()}
    norm = {_norm_key(k): v for k, v in exact.items() if _norm_key(k)}
    return exact, norm


def _first_non_empty(values: Iterable[Any]) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value
            continue
        return value
    return ""


def _resolve_from_raw(
    header: str,
    *,
    raw_exact: Mapping[str, Any],
    raw_norm: Mapping[str, Any],
) -> Any:
    direct = raw_exact.get(header)
    if direct not in (None, ""):
        return direct

    norm_header = _norm_key(header)
    if norm_header and norm_header in raw_norm:
        return raw_norm[norm_header]

    for candidate in _RAW_FALLBACKS.get(header, ()):
        cand_exact = raw_exact.get(candidate)
        if cand_exact not in (None, ""):
            return cand_exact
        cand_norm = raw_norm.get(_norm_key(candidate))
        if cand_norm not in (None, ""):
            return cand_norm
    return ""


def _resolve_from_canonical(header: str, issue_row: Mapping[str, Any], item: HelixWorkItem) -> Any:
    if header == "ID de la Incidencia":
        return str(issue_row.get("key") or item.id or "").strip()
    if header == "Estado":
        return str(item.status_raw or issue_row.get("status") or "").strip()
    if header == "Fecha de creación":
        return _first_non_empty(
            [item.start_datetime, item.target_date, issue_row.get("created"), item.last_modified]
        )
    if header == "Fecha actualización":
        return _first_non_empty([item.last_modified, issue_row.get("updated")])
    if header == "Fecha de Cierre":
        return _first_non_empty([item.closed_date, issue_row.get("resolved")])
    if header == "Fecha Resolución":
        return _first_non_empty([item.closed_date, issue_row.get("resolved")])
    if header == "Servicio Origen - Servicio N1":
        return str(item.source_service_n1 or "").strip()
    if header == "Servicio Matrix de Catalogación - Servicio N1":
        return str(item.matrix_service_n1 or "").strip()
    if header == "Título":
        return str(item.summary or issue_row.get("summary") or "").strip()
    if header == "Criticidad":
        return str(issue_row.get("priority") or item.priority or "").strip()
    if header == "Tipo de Incidencia":
        return str(issue_row.get("type") or item.incident_type or "").strip()
    if header == "Descripción":
        return str(item.summary or issue_row.get("summary") or "").strip()

    for col in _CANONICAL_FALLBACKS.get(header, ()):
        val = issue_row.get(col)
        if val not in (None, ""):
            return val
    return ""


def _coerce_export_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return ""
        return value.tz_convert("UTC").isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return _jsonable_text(value)


def _coerce_excel_datetime(value: Any) -> Any:
    if value in (None, ""):
        return ""
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return ""
        if value.tzinfo is not None:
            return value.tz_convert("UTC").tz_localize(None).to_pydatetime()
        return value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    try:
        dt = pd.to_datetime(value, utc=True, errors="coerce")
    except Exception:
        return _coerce_export_scalar(value)
    if pd.isna(dt) or not isinstance(dt, pd.Timestamp):
        return _coerce_export_scalar(value)
    return dt.tz_convert("UTC").tz_localize(None).to_pydatetime()


def _month_from_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return ""
        return f"{int(value.month):02d}"
    txt = str(value).strip()
    if not txt:
        return ""
    try:
        dt = pd.to_datetime(txt, utc=True, errors="coerce")
    except Exception:
        dt = pd.NaT
    if pd.isna(dt):
        return ""
    if isinstance(dt, pd.Timestamp):
        return f"{int(dt.month):02d}"
    return ""


def build_helix_official_export_frames(
    filtered_issues_df: pd.DataFrame,
    *,
    helix_items_by_merge_key: Mapping[str, HelixWorkItem],
) -> Optional[tuple[pd.DataFrame, pd.DataFrame]]:
    """Build (official_sheet_df, raw_sheet_df) for a filtered Helix-only issues dataframe.

    Returns None when the input is empty, mixed-source, or no matching Helix raw rows are found.
    """
    if filtered_issues_df is None or filtered_issues_df.empty:
        return None
    if "source_type" not in filtered_issues_df.columns or "key" not in filtered_issues_df.columns:
        return None

    src_types = (
        filtered_issues_df["source_type"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .unique()
        .tolist()
    )
    src_types = [s for s in src_types if s]
    if not src_types or any(s != "helix" for s in src_types):
        return None

    if "source_id" not in filtered_issues_df.columns:
        return None

    official_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    raw_fields_populated = False

    for _, issue in filtered_issues_df.iterrows():
        issue_row = issue.to_dict()
        source_id = str(issue_row.get("source_id") or "").strip().lower()
        key = str(issue_row.get("key") or "").strip().upper()
        merge_key = f"{source_id}::{key}" if source_id else key
        item = helix_items_by_merge_key.get(merge_key)
        if item is None:
            continue

        raw_fields = dict(item.raw_fields or {})
        if raw_fields:
            raw_fields_populated = True
        raw_exact, raw_norm = _raw_lookup_build(raw_fields)

        official_row: dict[str, Any] = {}
        for header in HELIX_OFFICIAL_EXCEL_COLUMNS:
            raw_val = _resolve_from_raw(header, raw_exact=raw_exact, raw_norm=raw_norm)
            value = (
                raw_val
                if raw_val not in (None, "")
                else _resolve_from_canonical(header, issue_row=issue_row, item=item)
            )
            if header in _OFFICIAL_DATE_HEADERS:
                official_row[header] = _coerce_excel_datetime(value)
            else:
                official_row[header] = _coerce_export_scalar(value)

        if not official_row.get("Mes"):
            official_row["Mes"] = _month_from_value(
                _first_non_empty(
                    [
                        official_row.get("Fecha de creación"),
                        raw_exact.get("Submit Date"),
                        raw_exact.get("targetDate"),
                        item.start_datetime,
                    ]
                )
            )

        official_row["ID de la Incidencia"] = str(
            official_row.get("ID de la Incidencia") or issue_row.get("key") or item.id or ""
        ).strip()
        official_row["__item_url__"] = str(item.url or issue_row.get("url") or "").strip()
        official_rows.append(official_row)

        raw_row: dict[str, Any] = {str(k): _coerce_export_scalar(v) for k, v in raw_fields.items()}
        raw_row["ID de la Incidencia"] = str(issue_row.get("key") or item.id or "").strip()
        raw_row["__item_url__"] = str(item.url or issue_row.get("url") or "").strip()
        raw_rows.append(raw_row)

    if not official_rows or not raw_fields_populated:
        return None

    official_df = pd.DataFrame(official_rows)
    ordered = [c for c in HELIX_OFFICIAL_EXCEL_COLUMNS if c in official_df.columns]
    extras = [c for c in official_df.columns if c not in ordered]
    official_df = official_df[ordered + extras].copy()

    raw_df = pd.DataFrame(raw_rows) if raw_rows else pd.DataFrame()
    if not raw_df.empty:
        # Keep incident id and link first for easier debugging.
        front = [c for c in ("ID de la Incidencia", "__item_url__") if c in raw_df.columns]
        rest = [c for c in raw_df.columns if c not in front]
        raw_df = raw_df[front + rest].copy()

    return official_df, raw_df
