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


def _load_dotenv_if_present(dotenv_path: Path) -> None:
    """
    Load a minimal `.env` file before starting Streamlit.

    Streamlit opens the UI browser before `app.py` runs, so bundled builds need
    environment configuration in place ahead of time (paths, proxies, Helix/Jira
    settings, etc.).
    """
    try:
        path = Path(dotenv_path)
        if not path.exists() or not path.is_file():
            return
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            k = key.strip()
            if not k or k in os.environ:
                continue
            v = value.strip().strip("'").strip('"')
            os.environ[k] = v
    except Exception:
        return


def _macos_has_app(app_name: str) -> bool:
    for base in (Path("/Applications"), Path.home() / "Applications"):
        try:
            if (base / f"{app_name}.app").exists():
                return True
        except Exception:
            continue
    return False


def _configure_streamlit_ui_browser_env() -> None:
    """
    Keep Streamlit UI browser selection independent from Helix/Jira ingestion browsers.

    - Default: open the system default browser (Safari, etc.).
    - Optional: set `BUG_RESOLUTION_RADAR_UI_BROWSER=chrome|edge` to force.
    """
    ui_browser = str(os.environ.get("BUG_RESOLUTION_RADAR_UI_BROWSER") or "").strip().lower()

    # Avoid "bounce" behavior when BROWSER is set to ambiguous tokens (e.g. "chrome")
    # and the bundle cannot resolve it.
    if not ui_browser or ui_browser == "default":
        current = str(os.environ.get("BROWSER") or "").strip().lower()
        if current in {
            "chrome",
            "google-chrome",
            "google chrome",
            "edge",
            "msedge",
            "microsoft-edge",
            "microsoft edge",
        }:
            os.environ.pop("BROWSER", None)
        return

    if ui_browser not in {"chrome", "edge"}:
        return

    if sys.platform == "darwin":
        app = "Google Chrome" if ui_browser == "chrome" else "Microsoft Edge"
        os.environ["BROWSER"] = f'open -a "{app}"'
        return

    os.environ["BROWSER"] = "microsoft-edge" if ui_browser == "edge" else "google-chrome"


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


def _configure_streamlit_runtime_stability_for_binary() -> None:
    """
    Reduce unexpected server restarts in packaged builds.

    Long-running operations (e.g. PPT generation with Plotly/Kaleido) may create
    temp files. Streamlit's file watcher can interpret those changes as source
    changes in frozen apps and restart the report, which looks like "spinner
    eterno" and may reopen browser tabs.
    """
    os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
    os.environ.setdefault("STREAMLIT_SERVER_RUN_ON_SAVE", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")


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
        _load_dotenv_if_present(runtime_home / ".env")
        _configure_streamlit_ui_browser_env()
        _configure_streamlit_runtime_stability_for_binary()
    script = _resolve_app_script()
    sys.argv = [
        "streamlit",
        "run",
        str(script),
        "--global.developmentMode=false",
        "--server.fileWatcherType=none",
        "--server.runOnSave=false",
    ]
    return int(stcli.main())


if __name__ == "__main__":
    raise SystemExit(main())
