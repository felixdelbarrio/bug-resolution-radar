from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from bug_resolution_radar import config as cfg
from bug_resolution_radar.notes import NotesStore
from bug_resolution_radar.security import mask_secret, safe_log_text
from bug_resolution_radar.ui.common import (
    chip_style_from_color,
    flow_signal_color_map,
    priority_color,
    priority_color_map,
    status_color,
)
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


def test_semantic_status_and_priority_colors() -> None:
    assert status_color("New") == "#E85D63"
    assert status_color("Analysing") == "#D64550"
    assert status_color("Blocked") == "#B4232A"
    assert status_color("Open") == "#FBBF24"
    assert status_color("Closed") == "#15803D"
    assert status_color("Deployed") == "#008F2A"

    assert priority_color("Supone un impedimento") == "#B4232A"
    assert priority_color("Highest") == "#B4232A"
    assert priority_color("High") == "#D64550"
    assert priority_color("Medium") == "#F59E0B"
    assert priority_color("Low") == "#22A447"
    assert priority_color("Lowest") == "#15803D"


def test_semantic_color_maps_include_flow_signals() -> None:
    pmap = priority_color_map()
    assert pmap["Supone un impedimento"] == "#B4232A"
    assert pmap["Medium"] == "#F59E0B"
    assert pmap["Lowest"] == "#15803D"

    smap = flow_signal_color_map()
    assert smap["created"] == "#E85D63"
    assert smap["open"] == "#FBBF24"
    assert smap["closed"] == "#22A447"
    assert smap["deployed"] == "#008F2A"


def test_goal_state_chip_uses_stronger_fill() -> None:
    deployed_style = chip_style_from_color(status_color("Deployed"))
    accepted_style = chip_style_from_color(status_color("Accepted"))
    assert "rgba(0,143,42,0.260)" in deployed_style
    assert "rgba(76,175,80,0.160)" in accepted_style


def test_multi_country_sources_parsing_and_ids() -> None:
    settings = cfg.Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        JIRA_SOURCES_JSON='[{"country":"Mexico","alias":"Core MX","jql":"status = Open"}]',
        HELIX_SOURCES_JSON=(
            '[{"country":"España","alias":"SmartIT ES","base_url":"https://helix.example.com",'
            '"organization":"ORG-ES","browser":"edge","proxy":"","ssl_verify":"true"}]'
        ),
    )

    countries = cfg.supported_countries(settings)
    assert countries == ["México", "España", "Peru", "Colombia", "Argentina"]

    jira_cfg = cfg.jira_sources(settings)
    helix_cfg = cfg.helix_sources(settings)
    assert len(jira_cfg) == 1
    assert len(helix_cfg) == 1

    assert jira_cfg[0]["country"] == "México"
    assert jira_cfg[0]["source_id"] == "jira:mexico:core-mx"
    assert helix_cfg[0]["country"] == "España"
    assert helix_cfg[0]["source_id"] == "helix:espana:smartit-es"
