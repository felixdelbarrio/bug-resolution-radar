from __future__ import annotations

from pathlib import Path
from typing import Any

from bug_resolution_radar import config as config_mod
from bug_resolution_radar.config import Settings


def test_resolve_period_ppt_template_path_returns_first_existing_candidate(
    tmp_path: Path, monkeypatch: Any
) -> None:
    existing = tmp_path / "corporate-template.pptx"
    existing.write_bytes(b"pptx")

    monkeypatch.setattr(
        config_mod,
        "period_ppt_template_candidates",
        lambda _settings, explicit_path=None: [tmp_path / "missing.pptx", existing],
    )

    out = config_mod.resolve_period_ppt_template_path(Settings())
    assert out == existing.resolve()


def test_resolve_period_ppt_template_path_raises_when_no_candidate_exists(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        config_mod,
        "period_ppt_template_candidates",
        lambda _settings, explicit_path=None: [tmp_path / "missing.pptx"],
    )

    try:
        config_mod.resolve_period_ppt_template_path(Settings())
        raise AssertionError("expected FileNotFoundError")
    except FileNotFoundError as exc:
        msg = str(exc)
        assert "plantilla del informe de seguimiento" in msg.lower()
        assert "corporativa integrada" in msg.lower()


def test_suggested_period_ppt_template_path_prefers_existing_candidate(
    tmp_path: Path, monkeypatch: Any
) -> None:
    existing = tmp_path / "candidate.pptx"
    existing.write_bytes(b"pptx")
    bundled = tmp_path / "bundled-default.pptx"

    monkeypatch.setattr(
        config_mod,
        "period_ppt_template_candidates",
        lambda _settings: [tmp_path / "missing.pptx", existing],
    )
    monkeypatch.setattr(config_mod, "bundled_period_ppt_template_path", lambda: bundled)

    out = config_mod.suggested_period_ppt_template_path(Settings())
    assert out == existing.resolve()


def test_suggested_period_ppt_template_path_falls_back_to_bundled_when_missing(
    tmp_path: Path, monkeypatch: Any
) -> None:
    bundled = tmp_path / "bundled-default.pptx"
    monkeypatch.setattr(config_mod, "period_ppt_template_candidates", lambda _settings: [])
    monkeypatch.setattr(config_mod, "bundled_period_ppt_template_path", lambda: bundled)

    out = config_mod.suggested_period_ppt_template_path(Settings())
    assert out == bundled
