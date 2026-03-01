from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from bug_resolution_radar import config as cfg
from bug_resolution_radar.common.security import mask_secret, safe_log_text
from bug_resolution_radar.common.utils import now_iso, parse_age_buckets, parse_int_list
from bug_resolution_radar.services.notes import NotesStore
from bug_resolution_radar.ui.common import (
    chip_style_from_color,
    flow_signal_color_map,
    open_issues_only,
    priority_color,
    priority_color_map,
    semantic_popover_css_rules,
    status_color,
)
from bug_resolution_radar.ui.dashboard.constants import canonical_status_order
from bug_resolution_radar.ui.style import inject_bbva_css


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
        (
            "APP_TITLE=Radar\n"
            'JIRA_SOURCES_JSON=[{"country":"México","alias":"Core","jql":"project = X\\\\nAND status = Open"}]\n'
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cfg, "ENV_PATH", env_path)
    monkeypatch.setattr(cfg, "ENV_EXAMPLE_PATH", env_example)

    cfg.ensure_env()
    assert env_path.exists()

    settings = cfg.load_settings()
    assert settings.APP_TITLE == "Radar"
    jira_cfg = cfg.jira_sources(settings)
    assert len(jira_cfg) == 1
    assert "\n" in jira_cfg[0]["jql"]

    settings.JIRA_SOURCES_JSON = '[{"country":"México","alias":"Core","jql":"linea 1\\nlinea 2"}]'
    cfg.save_settings(settings)
    saved = env_path.read_text(encoding="utf-8")
    assert "JIRA_SOURCES_JSON=" in saved
    assert "linea 1\\nlinea 2" in saved


def test_config_resolves_relative_data_paths_against_env_location(
    monkeypatch: Any, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        (
            "DATA_PATH=data/issues.json\n"
            "NOTES_PATH=data/notes.json\n"
            "INSIGHTS_LEARNING_PATH=data/insights_learning.json\n"
            "HELIX_DATA_PATH=data/helix_dump.json\n"
            "REPORT_PPT_DOWNLOAD_DIR=exports/ppt\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cfg, "ENV_PATH", env_path)
    monkeypatch.setattr(cfg, "ENV_EXAMPLE_PATH", tmp_path / ".env.example")

    settings = cfg.load_settings()
    assert settings.DATA_PATH == str((tmp_path / "data/issues.json").resolve())
    assert settings.NOTES_PATH == str((tmp_path / "data/notes.json").resolve())
    assert settings.INSIGHTS_LEARNING_PATH == str(
        (tmp_path / "data/insights_learning.json").resolve()
    )
    assert settings.HELIX_DATA_PATH == str((tmp_path / "data/helix_dump.json").resolve())
    assert settings.REPORT_PPT_DOWNLOAD_DIR == str((tmp_path / "exports/ppt").resolve())

    cfg.save_settings(settings)
    saved = env_path.read_text(encoding="utf-8")
    assert "DATA_PATH=data/issues.json" in saved
    assert "NOTES_PATH=data/notes.json" in saved
    assert "INSIGHTS_LEARNING_PATH=data/insights_learning.json" in saved
    assert "HELIX_DATA_PATH=data/helix_dump.json" in saved
    assert "REPORT_PPT_DOWNLOAD_DIR=exports/ppt" in saved


def test_config_save_settings_preserves_unknown_env_keys(monkeypatch: Any, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        ("APP_TITLE=Radar\nBUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=true\nCUSTOM_CORP_FLAG=keep-me\n"),
        encoding="utf-8",
    )

    monkeypatch.setattr(cfg, "ENV_PATH", env_path)
    monkeypatch.setattr(cfg, "ENV_EXAMPLE_PATH", tmp_path / ".env.example")

    settings = cfg.load_settings()
    settings.APP_TITLE = "Radar Pro"
    cfg.save_settings(settings)

    saved = env_path.read_text(encoding="utf-8")
    assert "APP_TITLE=Radar Pro" in saved
    assert "BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=true" in saved
    assert "CUSTOM_CORP_FLAG=keep-me" in saved


def test_config_save_settings_can_prune_legacy_keys(monkeypatch: Any, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        (
            "APP_TITLE=Radar\n"
            "BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=true\n"
            "ANALYSIS_LOOKBACK_DAYS=365\n"
            "BUG_RESOLUTION_RADAR_CORPORATE_MODE=true\n"
            "CUSTOM_CORP_FLAG=keep-me\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cfg, "ENV_PATH", env_path)
    monkeypatch.setattr(cfg, "ENV_EXAMPLE_PATH", tmp_path / ".env.example")

    settings = cfg.load_settings()
    settings.APP_TITLE = "Radar Pro"
    cfg.save_settings(settings, drop_keys=cfg.LEGACY_ENV_KEYS_TO_PRUNE)

    saved = env_path.read_text(encoding="utf-8")
    assert "APP_TITLE=Radar Pro" in saved
    assert "BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=true" in saved
    assert "CUSTOM_CORP_FLAG=keep-me" in saved
    assert "ANALYSIS_LOOKBACK_DAYS=" not in saved
    assert "BUG_RESOLUTION_RADAR_CORPORATE_MODE=" not in saved


def test_config_restore_env_from_example_overwrites_env(monkeypatch: Any, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("APP_TITLE=Old\n", encoding="utf-8")
    env_example = tmp_path / ".env.example"
    env_example.write_text("APP_TITLE=Recovered\n", encoding="utf-8")

    monkeypatch.setattr(cfg, "ENV_PATH", env_path)
    monkeypatch.setattr(cfg, "ENV_EXAMPLE_PATH", env_example)
    monkeypatch.setattr(cfg, "_candidate_env_example_paths", lambda: [env_example])

    restored_from = cfg.restore_env_from_example()

    assert restored_from == env_example
    assert env_path.read_text(encoding="utf-8") == "APP_TITLE=Recovered\n"


def test_config_restore_env_from_example_raises_when_example_missing(
    monkeypatch: Any, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    env_example = tmp_path / ".env.example"

    monkeypatch.setattr(cfg, "ENV_PATH", env_path)
    monkeypatch.setattr(cfg, "ENV_EXAMPLE_PATH", env_example)
    monkeypatch.setattr(cfg, "_candidate_env_example_paths", lambda: [env_example])

    try:
        cfg.restore_env_from_example()
    except FileNotFoundError as exc:
        assert "No se encontró `.env.example`" in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError when .env.example does not exist")


def test_normalize_analysis_lookback_months_defaults_for_non_positive_values() -> None:
    assert cfg.normalize_analysis_lookback_months("0") == 12
    assert cfg.normalize_analysis_lookback_months("-8") == 12
    assert cfg.normalize_analysis_lookback_months("abc") == 12
    assert cfg.normalize_analysis_lookback_months("6") == 6


def test_semantic_status_and_priority_colors() -> None:
    assert status_color("New") == "#E85D63"
    assert status_color("Ready") == "#E85D63"
    assert status_color("Analysing") == "#E85D63"
    assert status_color("Blocked") == "#E85D63"
    assert status_color("In Progress") == "#F59E0B"
    assert status_color("To Rework") == "#F59E0B"
    assert status_color("Test") == "#F59E0B"
    assert status_color("Ready To Verify") == "#F59E0B"
    assert status_color("Accepted") == "#4CAF50"
    assert status_color("Ready to Deploy") == "#4CAF50"
    assert status_color("Open") == "#FBBF24"
    assert status_color("Closed") == "#15803D"
    assert status_color("Deployed") == "#5B3FD0"

    assert priority_color("Supone un impedimento") == "#B4232A"
    assert priority_color("Highest") == "#B4232A"
    assert priority_color("High") == "#D64550"
    assert priority_color("Medium") == "#F59E0B"
    assert priority_color("Low") == "#22A447"
    assert priority_color("Lowest") == "#15803D"


def test_canonical_status_order_includes_ready_after_analysing() -> None:
    order = canonical_status_order()
    assert order.index("Analysing") < order.index("Ready") < order.index("Blocked")


def test_semantic_color_maps_include_flow_signals() -> None:
    pmap = priority_color_map()
    assert pmap["Supone un impedimento"] == "#B4232A"
    assert pmap["Medium"] == "#F59E0B"
    assert pmap["Lowest"] == "#15803D"

    smap = flow_signal_color_map()
    assert smap["created"] == "#E85D63"
    assert smap["open"] == "#FBBF24"
    assert smap["closed"] == "#22A447"
    assert smap["deployed"] == "#5B3FD0"


def test_goal_state_chip_uses_stronger_fill() -> None:
    deployed_style = chip_style_from_color(status_color("Deployed"))
    accepted_style = chip_style_from_color(status_color("Accepted"))
    ready_deploy_style = chip_style_from_color(status_color("Ready to Deploy"))
    assert "background:#ECE6FF" in deployed_style
    assert "color:#5B3FD0" in deployed_style
    assert "rgba(76,175,80,0.160)" in accepted_style
    assert accepted_style == ready_deploy_style


def test_semantic_popover_rules_are_built_from_shared_color_tokens() -> None:
    css = semantic_popover_css_rules()
    assert '[aria-label*="new" i]' in css
    assert '[aria-label*="analysing" i]' in css
    assert '[aria-label*="blocked" i]' in css
    assert "--bbva-opt-dot: #E85D63;" in css
    assert '[aria-label*="to rework" i]' in css
    assert '[aria-label*="test" i]' in css
    assert '[aria-label*="ready to verify" i]' in css
    assert "--bbva-opt-dot: #F59E0B;" in css
    assert '[aria-label*="accepted" i]' in css
    assert '[aria-label*="ready to deploy" i]' in css
    assert "--bbva-opt-dot: #4CAF50;" in css


def _captured_injected_css(*, dark_mode: bool) -> str:
    captured: list[str] = []
    original = st.markdown

    def _fake_markdown(body: str, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        captured.append(str(body))

    st.markdown = _fake_markdown  # type: ignore[assignment]
    try:
        inject_bbva_css(dark_mode=dark_mode)
    finally:
        st.markdown = original  # type: ignore[assignment]
    return "\n".join(captured)


def test_nba_banner_base_uses_alert_tokens_by_theme() -> None:
    css_dark = _captured_injected_css(dark_mode=True)
    css_light = _captured_injected_css(dark_mode=False)
    assert (
        "--bbva-nba-banner-bg: color-mix(in srgb, var(--bbva-signal-orange) 20%, "
        "var(--bbva-surface-elevated) 80%);" in css_dark
    )
    assert (
        "--bbva-nba-banner-border: color-mix(in srgb, var(--bbva-signal-orange) 70%, "
        "var(--bbva-border) 30%);" in css_dark
    )
    assert (
        "--bbva-nba-banner-bg: color-mix(in srgb, var(--bbva-signal-yellow) 22%, "
        "var(--bbva-surface-elevated) 78%);" in css_light
    )
    assert (
        "--bbva-nba-banner-border: color-mix(in srgb, var(--bbva-signal-orange) 58%, "
        "var(--bbva-border) 42%);" in css_light
    )
    for css in [css_dark, css_light]:
        assert "--bbva-signal-yellow: #FBBF24;" in css
        assert "--bbva-nba-ink-primary: var(--bbva-text);" in css


def test_open_issues_only_treats_accepted_without_resolved_as_closed() -> None:
    df = pd.DataFrame(
        {
            "key": ["A-1", "A-2", "A-3"],
            "status": ["New", "Accepted", "Blocked"],
            "resolved": [pd.NaT, pd.NaT, "2025-01-03T00:00:00+00:00"],
        }
    )
    out = open_issues_only(df)
    assert out["key"].astype(str).tolist() == ["A-1"]


def test_multi_country_sources_parsing_and_ids() -> None:
    settings = cfg.Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        JIRA_SOURCES_JSON='[{"country":"Mexico","alias":"Core MX","jql":"status = Open"}]',
        HELIX_SOURCES_JSON='[{"country":"España","alias":"SmartIT ES"}]',
        HELIX_BROWSER="edge",
        HELIX_SSL_VERIFY="true",
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
