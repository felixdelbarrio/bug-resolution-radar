from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel

ENV_PATH = Path(".env")
ENV_EXAMPLE_PATH = Path(".env.example")


def _decode_env_multiline(v: str) -> str:
    # Persistimos multilínea en .env como una sola línea usando "\n"
    return v.replace("\\n", "\n")


def _encode_env_multiline(v: str) -> str:
    # Normaliza y escapa saltos de línea
    return v.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


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
    JIRA_PROJECT_KEY: str = ""
    JIRA_JQL: str = ""
    JIRA_BROWSER: str = "chrome"

    # -------------------------
    # HELIX
    # -------------------------
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
