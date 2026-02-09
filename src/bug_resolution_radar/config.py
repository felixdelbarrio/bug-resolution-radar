from __future__ import annotations

from pathlib import Path
from typing import Dict

from dotenv import dotenv_values
from pydantic import BaseModel

ENV_PATH = Path(".env")
ENV_EXAMPLE_PATH = Path(".env.example")

class Settings(BaseModel):
    APP_TITLE: str = "Bug Resolution Radar"
    THEME: str = "auto"
    DATA_PATH: str = "data/issues.json"
    NOTES_PATH: str = "data/notes.json"
    LOG_LEVEL: str = "INFO"

    JIRA_BASE_URL: str = ""
    JIRA_PROJECT_KEY: str = ""
    JIRA_JQL: str = ""
    JIRA_COOKIE_DOMAIN: str = ""
    JIRA_BROWSER: str = "chrome"

    CRITICALITY_MAP: str = "Highest:P0,High:P1,Medium:P2,Low:P3,Lowest:P4"
    MASTER_LABEL: str = "master"
    MASTER_AFFECTED_CLIENTS_THRESHOLD: str = "5"

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
    return Settings(**vals)

def save_settings(settings: Settings) -> None:
    lines = []
    data = settings.model_dump()
    for k, v in data.items():
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
