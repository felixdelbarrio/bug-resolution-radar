from __future__ import annotations

from pathlib import Path

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.pages import report_page


def _patch_macos_home(monkeypatch, home: Path) -> None:
    monkeypatch.setattr(report_page.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(report_page.Path, "home", classmethod(lambda cls: home))


def test_default_report_export_dir_uses_configured_downloads_path_on_macos(
    monkeypatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    downloads = home / "Downloads"
    _patch_macos_home(monkeypatch, home)

    settings = Settings(REPORT_PPT_DOWNLOAD_DIR=str(downloads))
    out = report_page._default_report_export_dir(settings)

    assert out == downloads
    assert not out.exists()


def test_default_report_export_dir_uses_non_protected_configured_path_on_macos(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    safe_dir = home / "safe-exports"
    _patch_macos_home(monkeypatch, home)

    settings = Settings(REPORT_PPT_DOWNLOAD_DIR=str(safe_dir))
    out = report_page._default_report_export_dir(settings)

    assert out == safe_dir
    assert not out.exists()


def test_default_report_export_dir_uses_system_downloads_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    _patch_macos_home(monkeypatch, home)

    settings = Settings(REPORT_PPT_DOWNLOAD_DIR="")
    out = report_page._default_report_export_dir(settings)

    assert out == home / "Downloads"
    assert not out.exists()
