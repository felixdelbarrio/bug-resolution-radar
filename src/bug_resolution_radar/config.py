from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

from dotenv import dotenv_values
from pydantic import BaseModel

ENV_PATH = Path(".env")
ENV_EXAMPLE_PATH = Path(".env.example")
DEFAULT_SUPPORTED_COUNTRIES: List[str] = [
    "México",
    "España",
    "Peru",
    "Colombia",
    "Argentina",
]
DEFAULT_SUPPORTED_COUNTRIES_CSV = ",".join(DEFAULT_SUPPORTED_COUNTRIES)


def _decode_env_multiline(v: str) -> str:
    # Persistimos multilínea en .env como una sola línea usando "\n"
    return v.replace("\\n", "\n")


def _encode_env_multiline(v: str) -> str:
    # Normaliza y escapa saltos de línea
    return v.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _ascii_fold(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    return folded.encode("ascii", "ignore").decode("ascii")


def _slug_token(value: str) -> str:
    txt = _ascii_fold(value).lower().strip()
    txt = re.sub(r"[^a-z0-9]+", "-", txt).strip("-")
    return txt or "default"


def _normalize_country(value: str, *, supported: List[str]) -> str:
    raw = _coerce_str(value)
    if not raw:
        return ""
    raw_key = _slug_token(raw)
    for country in supported:
        if _slug_token(country) == raw_key:
            return country
    return ""


def _parse_json_list(raw: str) -> List[Dict[str, Any]]:
    txt = _coerce_str(raw)
    if not txt:
        return []
    try:
        payload = json.loads(txt)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in payload:
        if isinstance(row, dict):
            out.append(dict(row))
    return out


def build_source_id(source_type: str, country: str, alias: str) -> str:
    return f"{_slug_token(source_type)}:{_slug_token(country)}:{_slug_token(alias)}"


class Settings(BaseModel):
    APP_TITLE: str = "Bug Resolution Radar"
    THEME: str = "auto"
    DATA_PATH: str = "data/issues.json"
    NOTES_PATH: str = "data/notes.json"
    LOG_LEVEL: str = "INFO"

    # -------------------------
    # JIRA
    # -------------------------
    JIRA_BASE_URL: str = ""
    SUPPORTED_COUNTRIES: str = DEFAULT_SUPPORTED_COUNTRIES_CSV
    JIRA_SOURCES_JSON: str = "[]"
    # legacy fallback (solo compatibilidad si no hay JIRA_SOURCES_JSON)
    JIRA_JQL: str = ""
    JIRA_BROWSER: str = "chrome"

    # -------------------------
    # HELIX
    # -------------------------
    HELIX_SOURCES_JSON: str = "[]"
    # legacy fallback (solo compatibilidad si no hay HELIX_SOURCES_JSON)
    HELIX_BASE_URL: str = ""
    HELIX_ORGANIZATION: str = ""
    HELIX_BROWSER: str = "chrome"
    HELIX_DATA_PATH: str = "data/helix_dump.json"

    # Proxy y SS
    HELIX_PROXY: str = ""
    HELIX_SSL_VERIFY: str = ""  # "true" o "false"
    HELIX_CA_BUNDLE: str = ""
    HELIX_CONNECT_TIMEOUT: int = 10
    HELIX_READ_TIMEOUT: int = 30
    HELIX_MAX_READ_TIMEOUT: int = 120
    HELIX_PROXY_MIN_READ_TIMEOUT: int = 30
    HELIX_DRYRUN_CONNECT_TIMEOUT: int = 10
    HELIX_DRYRUN_READ_TIMEOUT: int = 60
    HELIX_MIN_CHUNK_SIZE: int = 10
    HELIX_MAX_PAGES: int = 200
    HELIX_MAX_INGEST_SECONDS: int = 900

    # -------------------------
    # KPIs
    # -------------------------
    KPI_FORTNIGHT_DAYS: str = "15"
    KPI_MONTH_DAYS: str = "30"
    KPI_OPEN_AGE_X_DAYS: str = "7,14,30"
    KPI_AGE_BUCKETS: str = "0-2,3-7,8-14,15-30,>30"

    # -------------------------
    # Dashboard preferences
    # -------------------------
    DASHBOARD_SUMMARY_CHARTS: str = "timeseries,open_priority_pie,resolution_hist"
    TREND_SELECTED_CHARTS: str = "timeseries,open_priority_pie,resolution_hist"


def ensure_env() -> None:
    if not ENV_PATH.exists():
        if ENV_EXAMPLE_PATH.exists():
            ENV_PATH.write_text(
                ENV_EXAMPLE_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            ENV_PATH.write_text("", encoding="utf-8")


def load_settings() -> Settings:
    vals = {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}

    # Decodificar multilínea
    if "JIRA_JQL" in vals:
        vals["JIRA_JQL"] = _decode_env_multiline(vals["JIRA_JQL"])

    return Settings.model_validate(vals)


def save_settings(settings: Settings) -> None:
    lines = []
    data = settings.model_dump()

    for k, v in data.items():
        if isinstance(v, str):
            v = _encode_env_multiline(v)
        lines.append(f"{k}={v}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def supported_countries(settings: Settings) -> List[str]:
    raw = _coerce_str(getattr(settings, "SUPPORTED_COUNTRIES", ""))
    if not raw:
        return list(DEFAULT_SUPPORTED_COUNTRIES)

    out: List[str] = []
    for part in raw.split(","):
        country = _normalize_country(part, supported=DEFAULT_SUPPORTED_COUNTRIES)
        if country and country not in out:
            out.append(country)
    return out or list(DEFAULT_SUPPORTED_COUNTRIES)


def jira_sources(settings: Settings) -> List[Dict[str, str]]:
    countries = supported_countries(settings)
    rows = _parse_json_list(getattr(settings, "JIRA_SOURCES_JSON", ""))

    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        country = _normalize_country(_coerce_str(row.get("country")), supported=countries)
        alias = _coerce_str(row.get("alias"))
        jql = _decode_env_multiline(_coerce_str(row.get("jql")))
        if not country or not alias or not jql:
            continue
        sid = build_source_id("jira", country, alias)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(
            {
                "source_type": "jira",
                "source_id": sid,
                "country": country,
                "alias": alias,
                "jql": jql,
            }
        )

    if out:
        return out

    # Compatibilidad con configuraciones previas sin JIRA_SOURCES_JSON.
    legacy_jql = _decode_env_multiline(_coerce_str(getattr(settings, "JIRA_JQL", "")))
    if legacy_jql:
        country = countries[0] if countries else DEFAULT_SUPPORTED_COUNTRIES[0]
        alias = "Jira principal"
        return [
            {
                "source_type": "jira",
                "source_id": build_source_id("jira", country, alias),
                "country": country,
                "alias": alias,
                "jql": legacy_jql,
            }
        ]
    return []


def helix_sources(settings: Settings) -> List[Dict[str, str]]:
    countries = supported_countries(settings)
    rows = _parse_json_list(getattr(settings, "HELIX_SOURCES_JSON", ""))

    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        country = _normalize_country(_coerce_str(row.get("country")), supported=countries)
        alias = _coerce_str(row.get("alias"))
        base_url = _coerce_str(row.get("base_url"))
        organization = _coerce_str(row.get("organization"))
        browser = _coerce_str(row.get("browser")) or _coerce_str(settings.HELIX_BROWSER) or "chrome"
        proxy = _coerce_str(row.get("proxy")) or _coerce_str(settings.HELIX_PROXY)
        ssl_verify = (
            _coerce_str(row.get("ssl_verify")) or _coerce_str(settings.HELIX_SSL_VERIFY) or "true"
        )
        if not country or not alias or not base_url or not organization:
            continue
        sid = build_source_id("helix", country, alias)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(
            {
                "source_type": "helix",
                "source_id": sid,
                "country": country,
                "alias": alias,
                "base_url": base_url,
                "organization": organization,
                "browser": browser,
                "proxy": proxy,
                "ssl_verify": ssl_verify,
            }
        )

    if out:
        return out

    # Compatibilidad con configuración Helix histórica.
    base_url = _coerce_str(getattr(settings, "HELIX_BASE_URL", ""))
    organization = _coerce_str(getattr(settings, "HELIX_ORGANIZATION", ""))
    if base_url and organization:
        country = countries[0] if countries else DEFAULT_SUPPORTED_COUNTRIES[0]
        alias = "Helix principal"
        return [
            {
                "source_type": "helix",
                "source_id": build_source_id("helix", country, alias),
                "country": country,
                "alias": alias,
                "base_url": base_url,
                "organization": organization,
                "browser": _coerce_str(settings.HELIX_BROWSER) or "chrome",
                "proxy": _coerce_str(settings.HELIX_PROXY),
                "ssl_verify": _coerce_str(settings.HELIX_SSL_VERIFY) or "true",
            }
        ]
    return []


def all_configured_sources(
    settings: Settings, *, country: str | None = None
) -> List[Dict[str, str]]:
    country_norm = _coerce_str(country)
    out: List[Dict[str, str]] = []
    for src in jira_sources(settings) + helix_sources(settings):
        if country_norm and _coerce_str(src.get("country")) != country_norm:
            continue
        out.append(src)
    return out


def to_env_json(rows: List[Dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
