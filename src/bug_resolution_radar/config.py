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
    "REPORT_PPT_DOWNLOAD_DIR",
}


def _decode_env_multiline(v: str) -> str:
    # Persistimos multilínea en .env como una sola línea usando "\n"
    return v.replace("\\n", "\n")


def _encode_env_multiline(v: str) -> str:
    # Normaliza y escapa saltos de línea
    return v.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


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
    BUG_RESOLUTION_RADAR_CORPORATE_MODE: str = "false"
    BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW: str = ""
    BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL: str = "false"
    BUG_RESOLUTION_RADAR_PREFER_SELECTED_BROWSER_BINARY: str = "true"
    BUG_RESOLUTION_RADAR_CHROME_BINARY: str = ""
    BUG_RESOLUTION_RADAR_EDGE_BINARY: str = ""
    BUG_RESOLUTION_RADAR_BROWSER_BOOTSTRAP_MAX_TABS: int = 3

    # -------------------------
    # JIRA
    # -------------------------
    JIRA_BASE_URL: str = ""
    SUPPORTED_COUNTRIES: str = DEFAULT_SUPPORTED_COUNTRIES_CSV
    JIRA_SOURCES_JSON: str = "[]"
    JIRA_INGEST_DISABLED_SOURCES_JSON: str = "[]"
    JIRA_BROWSER: str = "chrome"
    JIRA_BROWSER_LOGIN_URL: str = ""
    JIRA_BROWSER_LOGIN_WAIT_SECONDS: int = 90
    JIRA_BROWSER_LOGIN_POLL_SECONDS: float = 2.0

    # -------------------------
    # HELIX
    # -------------------------
    HELIX_SOURCES_JSON: str = "[]"
    HELIX_INGEST_DISABLED_SOURCES_JSON: str = "[]"
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
    REPORT_PPT_DOWNLOAD_DIR: str = ""
    # 0 = auto (máxima antigüedad disponible en backlog)
    ANALYSIS_LOOKBACK_MONTHS: int = 0


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
    settings = Settings.model_validate(vals)

    payload = settings.model_dump()
    for key in _PATH_SETTING_KEYS:
        payload[key] = _resolve_runtime_path(str(payload.get(key) or ""))
    return Settings.model_validate(payload)


def save_settings(settings: Settings) -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {k: v for k, v in dotenv_values(ENV_PATH).items() if k}
    data = settings.model_dump()
    serialized_data: Dict[str, str] = {}
    for k, v in data.items():
        value = v
        if isinstance(value, str):
            if k in _PATH_SETTING_KEYS:
                value = _to_storable_path(value)
            value = _encode_env_multiline(value)
        serialized_data[k] = str(value)

    ordered_keys: List[str] = []
    seen: set[str] = set()
    for key in list(existing.keys()) + list(serialized_data.keys()):
        if key in seen:
            continue
        seen.add(key)
        ordered_keys.append(key)

    lines: List[str] = []
    for key in ordered_keys:
        if key in serialized_data:
            lines.append(f"{key}={serialized_data[key]}")
            continue
        raw_existing = existing.get(key)
        if raw_existing is None:
            continue
        lines.append(f"{key}={_encode_env_multiline(str(raw_existing))}")

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

    return out


def helix_sources(settings: Settings) -> List[Dict[str, str]]:
    countries = supported_countries(settings)
    rows = _parse_json_list(getattr(settings, "HELIX_SOURCES_JSON", ""))

    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        country = _normalize_country(_coerce_str(row.get("country")), supported=countries)
        alias = _coerce_str(row.get("alias"))
        service_origin_buug = _coerce_str(row.get("service_origin_buug"))
        service_origin_n1 = _coerce_str(row.get("service_origin_n1"))
        service_origin_n2 = _coerce_str(row.get("service_origin_n2"))
        if not country or not alias:
            continue
        sid = build_source_id("helix", country, alias)
        if sid in seen:
            continue
        seen.add(sid)
        payload = {
            "source_type": "helix",
            "source_id": sid,
            "country": country,
            "alias": alias,
        }
        if service_origin_buug:
            payload["service_origin_buug"] = service_origin_buug
        if service_origin_n1:
            payload["service_origin_n1"] = service_origin_n1
        if service_origin_n2:
            payload["service_origin_n2"] = service_origin_n2
        out.append(payload)

    return out


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
