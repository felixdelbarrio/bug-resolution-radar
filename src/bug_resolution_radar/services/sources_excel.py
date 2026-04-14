"""Excel import/export helpers for Jira/Helix source configuration rows."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pandas as pd

from bug_resolution_radar.config import (
    Settings,
    build_source_id,
    helix_sources,
    jira_sources,
    supported_countries,
)

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
_TRANSVERSAL_SHEET_NAME = "Valores transversales"
_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "jira": ["country", "alias", "jql"],
    "helix": ["country", "alias"],
}
_TRANSVERSAL_KEYS_BY_SOURCE: dict[str, list[str]] = {
    "jira": ["JIRA_BASE_URL", "JIRA_BROWSER"],
    "helix": ["HELIX_PROXY", "HELIX_BROWSER", "HELIX_SSL_VERIFY", "HELIX_DASHBOARD_URL"],
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
_TRANSVERSAL_HEADER_ALIASES: dict[str, str] = {
    "key": "key",
    "clave": "key",
    "parameter": "key",
    "parametro": "key",
    "parametro_configuracion": "key",
    "configuracion": "key",
    "setting": "key",
    "value": "value",
    "valor": "value",
    "valor_actual": "value",
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


def _country_lookup(countries: list[str]) -> dict[str, str]:
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


def _build_export_rows(settings: Settings, *, source_type: str) -> list[dict[str, str]]:
    normalized_type = _normalize_source_type(source_type)
    rows = jira_sources(settings) if normalized_type == "jira" else helix_sources(settings)
    out: list[dict[str, str]] = []
    for row in list(rows or []):
        payload: dict[str, str] = {
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


def _rows_frame_from_source_rows(
    source_rows: list[dict[str, Any]],
    *,
    source_type: str,
) -> pd.DataFrame:
    cols = _EXPORT_COLUMNS[source_type]
    out_rows: list[dict[str, str]] = []
    for row in list(source_rows or []):
        payload = {column: _as_text(row.get(column)) for column in cols}
        out_rows.append(payload)
    return pd.DataFrame(out_rows, columns=cols)


def _transversal_keys(source_type: str) -> list[str]:
    return list(_TRANSVERSAL_KEYS_BY_SOURCE[source_type])


def _build_transversal_rows(
    settings: Settings,
    *,
    source_type: str,
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    override_map = dict(overrides or {})
    for key in _transversal_keys(source_type):
        if key in override_map:
            raw_value = override_map.get(key)
        else:
            raw_value = getattr(settings, key, "")
        out.append({"key": key, "value": _as_text(raw_value)})
    return out


def build_sources_export_dataframe(settings: Settings, *, source_type: str) -> pd.DataFrame:
    normalized_type = _normalize_source_type(source_type)
    rows = _build_export_rows(settings, source_type=normalized_type)
    return pd.DataFrame(rows, columns=_EXPORT_COLUMNS[normalized_type])


def build_sources_export_excel_bytes(
    settings: Settings,
    *,
    source_type: str,
    source_rows: list[dict[str, Any]] | None = None,
    transversal_values: dict[str, Any] | None = None,
) -> bytes:
    normalized_type = _normalize_source_type(source_type)
    if source_rows is None:
        source_frame = build_sources_export_dataframe(settings, source_type=normalized_type)
    else:
        source_frame = _rows_frame_from_source_rows(source_rows, source_type=normalized_type)

    transversal_rows = _build_transversal_rows(
        settings,
        source_type=normalized_type,
        overrides=transversal_values,
    )
    transversal_frame = pd.DataFrame(transversal_rows, columns=["key", "value"])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        source_frame.to_excel(
            writer,
            index=False,
            sheet_name=str(_SHEET_NAMES[normalized_type])[:31],
        )
        transversal_frame.to_excel(
            writer,
            index=False,
            sheet_name=str(_TRANSVERSAL_SHEET_NAME)[:31],
        )
    return output.getvalue()


@dataclass(frozen=True)
class SourcesExcelImportResult:
    source_type: str
    rows: list[dict[str, str]]
    imported_rows: int
    skipped_rows: int
    warnings: list[str]
    settings_values: dict[str, str]


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


def _sheet_name_matches(sheet_name: str, candidates: set[str]) -> bool:
    token = _normalize_token(sheet_name)
    return token in candidates


def _pick_source_sheet_name(sheet_names: list[str], *, source_type: str) -> str:
    preferred = _SHEET_NAMES[source_type]
    for name in sheet_names:
        if str(name) == preferred:
            return name
    return sheet_names[0]


def _parse_source_rows_from_frame(
    frame: pd.DataFrame,
    *,
    source_type: str,
    countries: list[str] | None = None,
) -> tuple[list[dict[str, str]], int, list[str]]:
    normalized_type = _normalize_source_type(source_type)
    if frame is None or frame.empty:
        raise ValueError("El Excel no contiene filas de fuentes.")

    col_map = _canonical_column_mapping(frame, source_type=normalized_type)
    missing = [name for name in _REQUIRED_COLUMNS[normalized_type] if name not in col_map]
    if missing:
        raise ValueError(
            "El Excel no contiene las columnas obligatorias: " + ", ".join(sorted(missing)) + "."
        )

    source_columns = _EXPORT_COLUMNS[normalized_type]
    countries_list = list(countries or [])
    if not countries_list:
        countries_list = supported_countries(Settings())
    country_by_key = _country_lookup(countries_list)

    warnings: list[str] = []
    rows: list[dict[str, str]] = []
    skipped_rows = 0
    seen: set[tuple[str, str]] = set()

    for idx, raw in enumerate(frame.to_dict(orient="records"), start=1):
        row_data: dict[str, str] = {}
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
        clean: dict[str, str] = {
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
    return rows, int(skipped_rows), warnings


def _parse_transversal_rows_from_frame(
    frame: pd.DataFrame,
    *,
    allowed_keys: set[str],
) -> dict[str, str]:
    if frame is None or frame.empty:
        return {}

    mapping: dict[str, str] = {}
    for column in list(frame.columns):
        normalized = _normalize_token(column)
        canonical = _TRANSVERSAL_HEADER_ALIASES.get(normalized)
        if canonical and canonical not in mapping:
            mapping[canonical] = str(column)

    out: dict[str, str] = {}
    if "key" in mapping and "value" in mapping:
        key_col = mapping["key"]
        value_col = mapping["value"]
        for raw in frame.to_dict(orient="records"):
            key = _as_text(raw.get(key_col, "")).upper()
            if not key or key not in allowed_keys:
                continue
            out[key] = _as_text(raw.get(value_col, ""))
        if out:
            return out

    first_row = {}
    rows = frame.to_dict(orient="records")
    if rows:
        first_row = dict(rows[0])
    for column in list(frame.columns):
        key = _as_text(column).upper()
        if key not in allowed_keys:
            continue
        out[key] = _as_text(first_row.get(column, ""))
    return out


def _pick_transversal_sheet_names(sheet_names: list[str], *, source_sheet_name: str) -> list[str]:
    candidates = [name for name in sheet_names if str(name) != str(source_sheet_name)]
    if not candidates:
        return []

    preferred_tokens = {
        _normalize_token(_TRANSVERSAL_SHEET_NAME),
        "valores_transversales",
        "configuracion",
        "configuracion_transversal",
        "transversal",
        "settings",
        "parametros",
    }
    preferred = [name for name in candidates if _sheet_name_matches(name, preferred_tokens)]
    return preferred + [name for name in candidates if name not in preferred]


def import_sources_from_excel_bytes(
    payload: bytes,
    *,
    source_type: str,
    countries: list[str] | None = None,
) -> SourcesExcelImportResult:
    normalized_type = _normalize_source_type(source_type)
    if not payload:
        raise ValueError("El Excel recibido está vacío.")

    try:
        excel = pd.ExcelFile(BytesIO(payload), engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"No se pudo leer el Excel: {exc}") from exc

    if not excel.sheet_names:
        raise ValueError("El Excel no contiene pestañas.")

    source_sheet_name = _pick_source_sheet_name(excel.sheet_names, source_type=normalized_type)
    source_frame = excel.parse(sheet_name=source_sheet_name)
    rows, skipped_rows, warnings = _parse_source_rows_from_frame(
        source_frame,
        source_type=normalized_type,
        countries=countries,
    )

    settings_values: dict[str, str] = {}
    allowed_settings = {key.upper() for key in _transversal_keys(normalized_type)}
    for sheet_name in _pick_transversal_sheet_names(
        excel.sheet_names,
        source_sheet_name=source_sheet_name,
    ):
        frame = excel.parse(sheet_name=sheet_name)
        parsed = _parse_transversal_rows_from_frame(frame, allowed_keys=allowed_settings)
        if parsed:
            settings_values = parsed
            break

    return SourcesExcelImportResult(
        source_type=normalized_type,
        rows=rows,
        imported_rows=len(rows),
        skipped_rows=int(skipped_rows),
        warnings=warnings,
        settings_values=settings_values,
    )
