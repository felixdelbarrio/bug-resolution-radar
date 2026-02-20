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


def _runtime_home_for_binary() -> Path:
    exe_dir = Path(sys.executable).resolve().parent
    # macOS app bundle: <App>.app/Contents/MacOS/<exe>
    if (
        exe_dir.name == "MacOS"
        and exe_dir.parent.name == "Contents"
        and exe_dir.parent.parent.suffix.lower() == ".app"
    ):
        # Put config (.env, data/) next to the .app bundle, not inside it.
        return exe_dir.parent.parent.parent
    if exe_dir.name.lower() == "dist":
        return exe_dir.parent
    return exe_dir


def main() -> int:
    if getattr(sys, "frozen", False):
        runtime_home = _runtime_home_for_binary()
        os.environ.setdefault("BUG_RESOLUTION_RADAR_HOME", str(runtime_home))
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
