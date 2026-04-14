"""Excel import/export helpers for Jira/Helix source configuration rows."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List

import pandas as pd

from bug_resolution_radar.config import (
    Settings,
    build_source_id,
    helix_sources,
    jira_sources,
    supported_countries,
)
from bug_resolution_radar.services.tabular_export import dataframe_to_xlsx_bytes

_SUPPORTED_SOURCE_TYPES = {"jira", "helix"}
_EXPORT_COLUMNS: dict[str, list[str]] = {
    "jira": ["source_id", "country", "alias", "jql"],
    "helix": [
        "source_id",
        "country",
        "alias",
        "service_origin_buug",
        "service_origin_n1",
        "service_origin_n2",
    ],
}
_SHEET_NAMES: dict[str, str] = {
    "jira": "Fuentes Jira",
    "helix": "Fuentes Helix",
}
_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "jira": ["country", "alias", "jql"],
    "helix": ["country", "alias"],
}
_HEADER_ALIASES: dict[str, dict[str, str]] = {
    "jira": {
        "source_id": "source_id",
        "sourceid": "source_id",
        "id_fuente": "source_id",
        "country": "country",
        "pais": "country",
        "alias": "alias",
        "jql": "jql",
        "query": "jql",
        "consulta": "jql",
    },
    "helix": {
        "source_id": "source_id",
        "sourceid": "source_id",
        "id_fuente": "source_id",
        "country": "country",
        "pais": "country",
        "alias": "alias",
        "service_origin_buug": "service_origin_buug",
        "serviceoriginbuug": "service_origin_buug",
        "service_origin_bu_ug": "service_origin_buug",
        "serviceoriginbuug_": "service_origin_buug",
        "servicio_origen_bu_ug": "service_origin_buug",
        "servicio_origen_buug": "service_origin_buug",
        "servicioorigenbuug": "service_origin_buug",
        "service_origin_n1": "service_origin_n1",
        "serviceoriginn1": "service_origin_n1",
        "servicio_origen_n1": "service_origin_n1",
        "servicioorigenn1": "service_origin_n1",
        "service_origin_n2": "service_origin_n2",
        "serviceoriginn2": "service_origin_n2",
        "servicio_origen_n2": "service_origin_n2",
        "servicioorigenn2": "service_origin_n2",
    },
}


def _normalize_source_type(source_type: str) -> str:
    token = str(source_type or "").strip().lower()
    if token not in _SUPPORTED_SOURCE_TYPES:
        raise ValueError(f"Tipo de fuente no soportado: {source_type}")
    return token


def _normalize_token(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = folded.encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return token


def _country_lookup(countries: List[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for country in list(countries or []):
        key = _normalize_token(country)
        if key and key not in out:
            out[key] = str(country)
    return out


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _build_export_rows(settings: Settings, *, source_type: str) -> List[Dict[str, str]]:
    normalized_type = _normalize_source_type(source_type)
    rows = jira_sources(settings) if normalized_type == "jira" else helix_sources(settings)
    out: List[Dict[str, str]] = []
    for row in list(rows or []):
        payload: Dict[str, str] = {
            "source_id": _as_text(row.get("source_id")),
            "country": _as_text(row.get("country")),
            "alias": _as_text(row.get("alias")),
        }
        if normalized_type == "jira":
            payload["jql"] = _as_text(row.get("jql"))
        else:
            payload["service_origin_buug"] = _as_text(row.get("service_origin_buug"))
            payload["service_origin_n1"] = _as_text(row.get("service_origin_n1"))
            payload["service_origin_n2"] = _as_text(row.get("service_origin_n2"))
        out.append(payload)
    return out


def build_sources_export_dataframe(settings: Settings, *, source_type: str) -> pd.DataFrame:
    normalized_type = _normalize_source_type(source_type)
    rows = _build_export_rows(settings, source_type=normalized_type)
    return pd.DataFrame(rows, columns=_EXPORT_COLUMNS[normalized_type])


def build_sources_export_excel_bytes(settings: Settings, *, source_type: str) -> bytes:
    normalized_type = _normalize_source_type(source_type)
    frame = build_sources_export_dataframe(settings, source_type=normalized_type)
    return dataframe_to_xlsx_bytes(
        frame,
        sheet_name=_SHEET_NAMES[normalized_type],
        include_index=False,
    )


@dataclass(frozen=True)
class SourcesExcelImportResult:
    source_type: str
    rows: List[Dict[str, str]]
    imported_rows: int
    skipped_rows: int
    warnings: List[str]


def _canonical_column_mapping(
    frame: pd.DataFrame,
    *,
    source_type: str,
) -> dict[str, str]:
    aliases = _HEADER_ALIASES[source_type]
    mapping: dict[str, str] = {}
    for column in list(frame.columns):
        normalized = _normalize_token(column)
        canonical = aliases.get(normalized)
        if not canonical:
            continue
        if canonical not in mapping:
            mapping[canonical] = str(column)
    return mapping


def import_sources_from_excel_bytes(
    payload: bytes,
    *,
    source_type: str,
    countries: List[str] | None = None,
) -> SourcesExcelImportResult:
    normalized_type = _normalize_source_type(source_type)
    if not payload:
        raise ValueError("El Excel recibido está vacío.")

    try:
        frame = pd.read_excel(BytesIO(payload), sheet_name=0, engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"No se pudo leer el Excel: {exc}") from exc

    if frame is None or frame.empty:
        raise ValueError("El Excel no contiene filas de fuentes.")

    col_map = _canonical_column_mapping(frame, source_type=normalized_type)
    missing = [name for name in _REQUIRED_COLUMNS[normalized_type] if name not in col_map]
    if missing:
        raise ValueError(
            "El Excel no contiene las columnas obligatorias: "
            + ", ".join(sorted(missing))
            + "."
        )

    source_columns = _EXPORT_COLUMNS[normalized_type]
    countries_list = list(countries or [])
    if not countries_list:
        countries_list = supported_countries(Settings())
    country_by_key = _country_lookup(countries_list)

    warnings: List[str] = []
    rows: List[Dict[str, str]] = []
    skipped_rows = 0
    seen: set[tuple[str, str]] = set()

    for idx, raw in enumerate(frame.to_dict(orient="records"), start=1):
        row_data: Dict[str, str] = {}
        for column in source_columns:
            excel_col = col_map.get(column)
            row_data[column] = _as_text(raw.get(excel_col, "")) if excel_col else ""

        non_empty_values = [_as_text(row_data.get(col, "")) for col in source_columns]
        if not any(non_empty_values):
            skipped_rows += 1
            continue

        country_raw = _as_text(row_data.get("country", ""))
        alias = _as_text(row_data.get("alias", ""))
        if not country_raw:
            warnings.append(f"Fila {idx}: país vacío. Se omite.")
            skipped_rows += 1
            continue
        country = country_by_key.get(_normalize_token(country_raw), "")
        if not country:
            warnings.append(f"Fila {idx}: país no soportado '{country_raw}'. Se omite.")
            skipped_rows += 1
            continue
        if not alias:
            warnings.append(f"Fila {idx}: alias vacío. Se omite.")
            skipped_rows += 1
            continue

        if normalized_type == "jira":
            jql = _as_text(row_data.get("jql", ""))
            if not jql:
                warnings.append(f"Fila {idx}: JQL vacío. Se omite.")
                skipped_rows += 1
                continue

        dedup_key = (country.lower(), alias.lower())
        if dedup_key in seen:
            warnings.append(
                f"Fila {idx}: fuente duplicada para {country} · {alias}. Se omite duplicado."
            )
            skipped_rows += 1
            continue
        seen.add(dedup_key)

        source_id = _as_text(row_data.get("source_id", "")) or build_source_id(
            normalized_type, country, alias
        )
        clean: Dict[str, str] = {
            "source_id": source_id,
            "country": country,
            "alias": alias,
        }
        if normalized_type == "jira":
            clean["jql"] = _as_text(row_data.get("jql", ""))
        else:
            for key in ("service_origin_buug", "service_origin_n1", "service_origin_n2"):
                val = _as_text(row_data.get(key, ""))
                if val:
                    clean[key] = val
        rows.append(clean)

    if not rows:
        raise ValueError("No se encontraron filas válidas en el Excel para importar.")

    return SourcesExcelImportResult(
        source_type=normalized_type,
        rows=rows,
        imported_rows=len(rows),
        skipped_rows=int(skipped_rows),
        warnings=warnings,
    )

