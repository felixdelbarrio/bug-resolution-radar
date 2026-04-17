"""Shared helpers to resolve and persist user-facing download artifacts."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from bug_resolution_radar.config import Settings


@dataclass(frozen=True)
class DownloadTarget:
    directory: Path
    configured: bool
    source: str


def _configured_download_path(settings: Settings) -> Path | None:
    configured = str(getattr(settings, "REPORT_PPT_DOWNLOAD_DIR", "") or "").strip()
    if not configured:
        return None
    return Path(configured).expanduser()


def _expand_user_dir_token(raw: str, *, home: Path) -> Path | None:
    txt = str(raw or "").strip().strip('"').strip("'")
    if not txt:
        return None
    txt = txt.replace("$HOME", str(home))
    txt = os.path.expandvars(txt)
    return Path(txt).expanduser()


def _linux_downloads_dir(home: Path) -> Path | None:
    env_value = _expand_user_dir_token(os.environ.get("XDG_DOWNLOAD_DIR", ""), home=home)
    if env_value is not None:
        return env_value

    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or (home / ".config")).expanduser()
    user_dirs = config_home / "user-dirs.dirs"
    try:
        for raw_line in user_dirs.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() != "XDG_DOWNLOAD_DIR":
                continue
            expanded = _expand_user_dir_token(value, home=home)
            if expanded is not None:
                return expanded
    except Exception:
        return None
    return None


def detect_system_downloads_dir() -> Path | None:
    home = Path.home().expanduser()
    if sys.platform.startswith("win"):
        user_profile = os.environ.get("USERPROFILE") or str(home)
        return Path(user_profile).expanduser() / "Downloads"
    if sys.platform.startswith("linux"):
        return _linux_downloads_dir(home) or (home / "Downloads")
    if os.name == "posix":
        return home / "Downloads"
    return None


def resolve_download_target(settings: Settings) -> DownloadTarget:
    configured = _configured_download_path(settings)
    if configured is not None:
        return DownloadTarget(directory=configured, configured=True, source="configured")

    system_downloads = detect_system_downloads_dir()
    if system_downloads is not None:
        return DownloadTarget(directory=system_downloads, configured=False, source="system")

    return DownloadTarget(directory=Path.cwd(), configured=False, source="fallback")


def default_download_dir(settings: Settings) -> Path:
    """Resolve the preferred download directory without creating it."""
    return resolve_download_target(settings).directory


def ensure_download_dir(settings: Settings) -> Path:
    """Create the target directory only during an explicit save action."""
    download_dir = default_download_dir(settings)
    try:
        download_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if download_dir.is_dir():
        return download_dir
    return Path.cwd()


def unique_download_path(download_dir: Path, *, file_name: str) -> Path:
    name = str(file_name or "").strip() or "radar-export.bin"
    target = download_dir / name
    if not target.exists():
        return target
    stem = target.stem or "radar-export"
    suffix = target.suffix or ".bin"
    for idx in range(1, 1000):
        candidate = download_dir / f"{stem}_{idx}{suffix}"
        if not candidate.exists():
            return candidate
    return download_dir / f"{stem}_{os.getpid()}{suffix}"


def save_download_content(
    settings: Settings,
    *,
    file_name: str,
    content: bytes,
) -> Path:
    download_dir = ensure_download_dir(settings)
    export_path = unique_download_path(download_dir, file_name=file_name)
    export_path.write_bytes(bytes(content or b""))
    return export_path
