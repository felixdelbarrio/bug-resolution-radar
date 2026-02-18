"""PyInstaller entrypoint that runs the app through Streamlit CLI."""

from __future__ import annotations

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


def main() -> int:
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
