"""Configuration loading, validation and source normalization helpers."""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List

from dotenv import dotenv_values
from pydantic import BaseModel


def _default_user_config_home() -> Path:
    """
    Return an OS-appropriate, user-writable config directory.

    We intentionally avoid writing next to the binary / .app bundle because:
    - macOS App Translocation can mount the app read-only
    - /Applications (and other install dirs) are often not writable
    """
    if sys.platform == "darwin":
        base = Path("~/Library/Application Support").expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return (base / "bug-resolution-radar").expanduser()


def _runtime_home() -> Path:
    override = str(os.getenv("BUG_RESOLUTION_RADAR_HOME", "") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        # In frozen builds, always use a user-writable location (not inside the app bundle).
        return _default_user_config_home().resolve()
    return Path(__file__).resolve().parents[2]


DEFAULT_CONFIG_HOME = _runtime_home()
ENV_PATH = DEFAULT_CONFIG_HOME / ".env"
ENV_EXAMPLE_PATH = DEFAULT_CONFIG_HOME / ".env.example"


def _candidate_env_example_paths() -> List[Path]:
    out: List[Path] = []
    out.append(ENV_EXAMPLE_PATH)

    # Useful for local/dev runs (in case working dir differs).
    try:
        out.append(Path.cwd() / ".env.example")
    except Exception:
        pass

    if getattr(sys, "frozen", False):
        try:
            exe = Path(sys.executable).resolve()
            exe_dir = exe.parent
            out.append(exe_dir / ".env.example")
            out.append(exe_dir.parent / ".env.example")

            # macOS app bundle: <App>.app/Contents/MacOS/<exe>
            if (
                sys.platform == "darwin"
                and exe_dir.name == "MacOS"
                and exe_dir.parent.name == "Contents"
                and exe_dir.parent.parent.suffix.lower() == ".app"
            ):
                bundle_dir = exe_dir.parent.parent  # <App>.app
                out.append(bundle_dir.parent / ".env.example")  # alongside .app
                out.append(
                    bundle_dir.parent.parent / ".env.example"
                )  # bundle root (e.g. .../dist/..)
        except Exception:
            pass

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            try:
                out.append(Path(meipass) / ".env.example")
            except Exception:
                pass

    # De-dup preserving order.
    seen: set[str] = set()
    uniq: List[Path] = []
    for path in out:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(path)
    return uniq


DEFAULT_SUPPORTED_COUNTRIES: List[str] = [
    "México",
    "España",
    "Peru",
    "Colombia",
    "Argentina",
]
DEFAULT_SUPPORTED_COUNTRIES_CSV = ",".join(DEFAULT_SUPPORTED_COUNTRIES)
_PATH_SETTING_KEYS = {
    "DATA_PATH",
    "NOTES_PATH",
    "INSIGHTS_LEARNING_PATH",
    "HELIX_DATA_PATH",
    "HELIX_CA_BUNDLE",
}


def _decode_env_multiline(v: str) -> str:
    # Persistimos multilínea en .env como una sola línea usando "\n"
    return v.replace("\\n", "\n")


def _encode_env_multiline(v: str) -> str:
    # Normaliza y escapa saltos de línea
    return v.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def _strip_legacy_inline_comment(value: object) -> str:
    """
    Backwards-compatibility: older .env.example used inline comments like:
      THEME=light  # light|dark

    python-dotenv may treat the comment as part of the value, so we strip it
    for specific enum-like keys.
    """
    txt = str(value or "").strip()
    if " #" in txt:
        txt = txt.split(" #", 1)[0].strip()
    return txt


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def config_home() -> Path:
    return ENV_PATH.expanduser().resolve().parent


def _resolve_runtime_path(raw: str) -> str:
    txt = _coerce_str(raw)
    if not txt:
        return ""
    path = Path(txt).expanduser()
    if not path.is_absolute():
        path = config_home() / path
    return str(path.resolve())


def _to_storable_path(raw: str) -> str:
    txt = _coerce_str(raw)
    if not txt:
        return ""
    path = Path(txt).expanduser()
    if not path.is_absolute():
        return str(path)
    try:
        rel = path.resolve().relative_to(config_home())
        return str(rel)
    except Exception:
        return str(path.resolve())


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
    APP_TITLE: str = "Cuadro de mando de incidencias"
    THEME: str = "auto"
    DATA_PATH: str = "data/issues.json"
    NOTES_PATH: str = "data/notes.json"
    INSIGHTS_LEARNING_PATH: str = "data/insights_learning.json"
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
    JIRA_BROWSER_LOGIN_URL: str = ""
    JIRA_BROWSER_LOGIN_WAIT_SECONDS: int = 90
    JIRA_BROWSER_LOGIN_POLL_SECONDS: float = 2.0

    # -------------------------
    # HELIX
    # -------------------------
    HELIX_SOURCES_JSON: str = "[]"
    # legacy fallback (solo compatibilidad si no hay HELIX_SOURCES_JSON)
    HELIX_BASE_URL: str = ""
    HELIX_ORGANIZATION: str = ""
    HELIX_BROWSER: str = "chrome"
    HELIX_DATA_PATH: str = "data/helix_dump.json"
    HELIX_DASHBOARD_URL: str = (
        "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console"
    )

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
    HELIX_QUERY_MODE: str = "arsql"  # person_workitems|arsql|auto
    HELIX_ARSQL_BASE_URL: str = ""
    HELIX_ARSQL_DATASOURCE_UID: str = ""
    HELIX_ARSQL_SOURCE_SERVICE_N1: str = "ENTERPRISE WEB"
    HELIX_ARSQL_LIMIT: int = 500
    HELIX_ARSQL_DS_AUTH: str = "IMS-JWT JWT PLACEHOLDER"
    HELIX_ARSQL_CLIENT_TYPE: str = "4021"
    HELIX_ARSQL_GRAFANA_ORG_ID: str = ""
    HELIX_ARSQL_GRAFANA_DEVICE_ID: str = ""
    HELIX_ARSQL_DASHBOARD_URL: str = ""
    HELIX_BROWSER_LOGIN_WAIT_SECONDS: int = 90
    HELIX_BROWSER_LOGIN_POLL_SECONDS: float = 2.0

    # -------------------------
    # Dashboard preferences
    # -------------------------
    DASHBOARD_SUMMARY_CHARTS: str = "timeseries,open_priority_pie,resolution_hist"
    TREND_SELECTED_CHARTS: str = "timeseries,open_priority_pie,resolution_hist"
    DASHBOARD_FILTER_STATUS_JSON: str = "[]"
    DASHBOARD_FILTER_PRIORITY_JSON: str = "[]"
    DASHBOARD_FILTER_ASSIGNEE_JSON: str = "[]"
    KEEP_CACHE_ON_SOURCE_DELETE: str = "false"
    # 0 = auto (máxima antigüedad disponible en backlog)
    ANALYSIS_LOOKBACK_MONTHS: int = 0
    # 0 = auto (máxima antigüedad disponible en backlog)
    # Legacy fallback (mantenido por compatibilidad)
    ANALYSIS_LOOKBACK_DAYS: int = 0


def ensure_env() -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        example_path = next((p for p in _candidate_env_example_paths() if p.exists()), None)
        if example_path is not None:
            ENV_PATH.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
            return
        ENV_PATH.write_text("", encoding="utf-8")


def load_settings() -> Settings:
    vals = {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}

    for key in ("THEME", "JIRA_BROWSER"):
        if key in vals:
            vals[key] = _strip_legacy_inline_comment(vals[key])

    # Decodificar multilínea
    if "JIRA_JQL" in vals:
        vals["JIRA_JQL"] = _decode_env_multiline(vals["JIRA_JQL"])
    settings = Settings.model_validate(vals)

    payload = settings.model_dump()
    for key in _PATH_SETTING_KEYS:
        payload[key] = _resolve_runtime_path(str(payload.get(key) or ""))
    return Settings.model_validate(payload)


def save_settings(settings: Settings) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    data = settings.model_dump()

    for k, v in data.items():
        if isinstance(v, str):
            if k in _PATH_SETTING_KEYS:
                v = _to_storable_path(v)
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
