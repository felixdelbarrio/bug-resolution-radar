"""PyInstaller entrypoint that runs the app through Streamlit CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from streamlit.web import cli as stcli


def _resolve_app_script() -> Path:
    # In onefile mode, PyInstaller extracts bundled files into _MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    script = base / "app.py"
    if script.exists():
        return script
    raise FileNotFoundError(f"Could not find bundled Streamlit entrypoint: {script}")


def _candidate_streamlit_config_paths() -> list[Path]:
    out: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        out.append(Path(meipass) / ".streamlit" / "config.toml")

    try:
        exe = Path(sys.executable).resolve()
        exe_dir = exe.parent
        out.append(exe_dir / ".streamlit" / "config.toml")
        out.append(exe_dir.parent / ".streamlit" / "config.toml")

        if (
            sys.platform == "darwin"
            and exe_dir.name == "MacOS"
            and exe_dir.parent.name == "Contents"
            and exe_dir.parent.parent.suffix.lower() == ".app"
        ):
            bundle_dir = exe_dir.parent.parent  # <App>.app
            out.append(bundle_dir / ".streamlit" / "config.toml")
            out.append(bundle_dir.parent / ".streamlit" / "config.toml")  # dist/
            out.append(bundle_dir.parent.parent / ".streamlit" / "config.toml")  # bundle root
    except Exception:
        pass

    # De-dup preserving order.
    seen: set[str] = set()
    uniq: list[Path] = []
    for path in out:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(path)
    return uniq


def _ensure_streamlit_config(runtime_home: Path) -> None:
    target = runtime_home / ".streamlit" / "config.toml"
    if target.exists():
        return

    source = next((p for p in _candidate_streamlit_config_paths() if p.exists()), None)
    if source is None:
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        return


def _runtime_home_for_binary() -> Path:
    # Use an OS-appropriate, user-writable directory so the app can persist
    # config/data even when macOS applies App Translocation (read-only mount).
    if sys.platform == "darwin":
        base = Path("~/Library/Application Support").expanduser()
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return (base / "bug-resolution-radar").expanduser()


def main() -> int:
    if getattr(sys, "frozen", False):
        runtime_home = _runtime_home_for_binary()
        os.environ.setdefault("BUG_RESOLUTION_RADAR_HOME", str(runtime_home))
        runtime_home.mkdir(parents=True, exist_ok=True)
        _ensure_streamlit_config(runtime_home)
        os.chdir(runtime_home)
    script = _resolve_app_script()
    sys.argv = [
        "streamlit",
        "run",
        str(script),
        "--global.developmentMode=false",
    ]
    return int(stcli.main())


if __name__ == "__main__":
    raise SystemExit(main())
