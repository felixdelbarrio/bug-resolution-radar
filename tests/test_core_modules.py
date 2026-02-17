from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from bug_resolution_radar import config as cfg
from bug_resolution_radar.notes import NotesStore
from bug_resolution_radar.security import mask_secret, safe_log_text
from bug_resolution_radar.utils import now_iso, parse_age_buckets, parse_int_list


def test_now_iso_is_valid_utc_timestamp() -> None:
    parsed = datetime.fromisoformat(now_iso())
    assert parsed.tzinfo is not None


def test_parse_helpers() -> None:
    assert parse_int_list("1, 2,3") == [1, 2, 3]
    assert parse_age_buckets("0-2,3-7,>30") == [(0, 2), (3, 7), (30, 10**9)]


def test_notes_store_roundtrip(tmp_path: Path) -> None:
    store_path = tmp_path / "notes.json"
    store = NotesStore(store_path)

    store.load()
    assert store.get("X-1") is None

    store.set("X-1", "nota local")
    store.save()

    reloaded = NotesStore(store_path)
    reloaded.load()
    assert reloaded.get("X-1") == "nota local"


def test_security_masking_helpers() -> None:
    assert mask_secret("abc") == "***"
    assert mask_secret("1234567890").startswith("123")
    masked = safe_log_text("Authorization: very-secret-token\ncookie: foo=bar\nmy token=abc123")
    assert "very-secret-token" not in masked
    assert "foo=bar" not in masked
    assert "abc123" not in masked


def test_config_ensure_env_from_example_and_load_save(monkeypatch: Any, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_example = tmp_path / ".env.example"
    env_example.write_text(
        "APP_TITLE=Radar\nJIRA_JQL=project = X\\\\nAND status = Open\n", encoding="utf-8"
    )

    monkeypatch.setattr(cfg, "ENV_PATH", env_path)
    monkeypatch.setattr(cfg, "ENV_EXAMPLE_PATH", env_example)

    cfg.ensure_env()
    assert env_path.exists()

    settings = cfg.load_settings()
    assert settings.APP_TITLE == "Radar"
    assert "\n" in settings.JIRA_JQL

    settings.JIRA_JQL = "linea 1\nlinea 2"
    cfg.save_settings(settings)
    saved = env_path.read_text(encoding="utf-8")
    assert "JIRA_JQL=linea 1\\nlinea 2" in saved
