from __future__ import annotations

from pathlib import Path
from typing import Dict

from dotenv import dotenv_values
from pydantic import BaseModel

ENV_PATH = Path(".env")
ENV_EXAMPLE_PATH = Path(".env.example")


def _decode_env_multiline(v: str) -> str:
    # We persist multi-line values in .env as a single line using "\n".
    return v.replace("\\n", "\n")


def _encode_env_multiline(v: str) -> str:
    # Normalize and escape newlines so each KEY=VALUE stays on one physical line.
    return v.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


class Settings(BaseModel):
    APP_TITLE: str = "Bug Resolution Radar"
    THEME: str = "auto"
    DATA_PATH: str = "data/issues.json"
    NOTES_PATH: str = "data/notes.json"
    LOG_LEVEL: str = "INFO"

    JIRA_BASE_URL: str = ""
    JIRA_PROJECT_KEY: str = ""
    JIRA_JQL: str = ""
    JIRA_BROWSER: str = "chrome"

    KPI_FORTNIGHT_DAYS: str = "15"
    KPI_MONTH_DAYS: str = "30"
    KPI_OPEN_AGE_X_DAYS: str = "7,14,30"
    KPI_AGE_BUCKETS: str = "0-2,3-7,8-14,15-30,>30"

def ensure_env() -> None:
    if not ENV_PATH.exists():
        if ENV_EXAMPLE_PATH.exists():
            ENV_PATH.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            ENV_PATH.write_text("", encoding="utf-8")

def load_settings() -> Settings:
    vals: Dict[str, str] = {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}
    if "JIRA_JQL" in vals:
        vals["JIRA_JQL"] = _decode_env_multiline(vals["JIRA_JQL"])
    return Settings(**vals)

def save_settings(settings: Settings) -> None:
    lines = []
    data = settings.model_dump()
    for k, v in data.items():
        if isinstance(v, str):
            v = _encode_env_multiline(v)
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
