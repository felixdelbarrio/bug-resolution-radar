from __future__ import annotations

from pathlib import Path

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.pages import report_page


def _patch_macos_home(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(report_page.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(report_page.Path, "home", classmethod(lambda cls: home))


def test_default_report_export_dir_avoids_protected_paths_on_macos(
    monkeypatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    cfg_home = tmp_path / "cfg"
    downloads = home / "Downloads"
    _patch_macos_home(monkeypatch, home)
    monkeypatch.delenv("BUG_RESOLUTION_RADAR_ALLOW_PROTECTED_EXPORT_DIRS", raising=False)
    monkeypatch.setattr(report_page, "config_home", lambda: cfg_home)

    settings = Settings(REPORT_PPT_DOWNLOAD_DIR=str(downloads))
    out = report_page._default_report_export_dir(settings)

    assert out == cfg_home / "exports"
    assert out.exists()


def test_default_report_export_dir_honors_protected_paths_with_explicit_opt_in(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    cfg_home = tmp_path / "cfg"
    downloads = home / "Downloads"
    _patch_macos_home(monkeypatch, home)
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_ALLOW_PROTECTED_EXPORT_DIRS", "true")
    monkeypatch.setattr(report_page, "config_home", lambda: cfg_home)

    settings = Settings(REPORT_PPT_DOWNLOAD_DIR=str(downloads))
    out = report_page._default_report_export_dir(settings)

    assert out == downloads
    assert out.exists()


def test_default_report_export_dir_uses_app_exports_dir_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    cfg_home = tmp_path / "cfg"
    _patch_macos_home(monkeypatch, home)
    monkeypatch.delenv("BUG_RESOLUTION_RADAR_ALLOW_PROTECTED_EXPORT_DIRS", raising=False)
    monkeypatch.setattr(report_page, "config_home", lambda: cfg_home)

    settings = Settings(REPORT_PPT_DOWNLOAD_DIR="")
    out = report_page._default_report_export_dir(settings)

    assert out == cfg_home / "exports"
    assert out.exists()
