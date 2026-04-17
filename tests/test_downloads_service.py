from __future__ import annotations

from pathlib import Path

from bug_resolution_radar.config import Settings
from bug_resolution_radar.services import downloads


def test_detect_system_downloads_dir_on_macos(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    monkeypatch.setattr(downloads.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(downloads.sys, "platform", "darwin", raising=False)

    out = downloads.detect_system_downloads_dir()

    assert out == home / "Downloads"


def test_detect_system_downloads_dir_on_windows(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    profile = home / "windows-user"
    monkeypatch.setattr(downloads.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(downloads.sys, "platform", "win32", raising=False)
    monkeypatch.setenv("USERPROFILE", str(profile))

    out = downloads.detect_system_downloads_dir()

    assert out == profile / "Downloads"


def test_detect_system_downloads_dir_uses_linux_xdg_config(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_home = home / ".config"
    config_home.mkdir(parents=True)
    (config_home / "user-dirs.dirs").write_text(
        'XDG_DOWNLOAD_DIR="$HOME/Descargas"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(downloads.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(downloads.sys, "platform", "linux", raising=False)
    monkeypatch.delenv("XDG_DOWNLOAD_DIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    out = downloads.detect_system_downloads_dir()

    assert out == home / "Descargas"


def test_resolve_download_target_prefers_configured_directory(tmp_path: Path) -> None:
    configured = tmp_path / "exports"

    target = downloads.resolve_download_target(Settings(REPORT_PPT_DOWNLOAD_DIR=str(configured)))

    assert target.directory == configured
    assert target.configured is True
    assert target.source == "configured"
