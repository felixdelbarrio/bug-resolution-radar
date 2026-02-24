"""PyInstaller entrypoint that runs the app through Streamlit CLI."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from streamlit.web import cli as stcli


@dataclass(frozen=True)
class _BrowserHint:
    token: str
    macos_apps: tuple[str, ...]


_BROWSER_HINTS: tuple[_BrowserHint, ...] = (
    _BrowserHint(token="chrome", macos_apps=("Google Chrome", "Google Chrome Canary", "Chromium")),
    _BrowserHint(token="edge", macos_apps=("Microsoft Edge",)),
)


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
    Load a minimal .env file before starting Streamlit.

    This is important for the PyInstaller bundle because Streamlit tries to open
    the UI browser before our app code runs (so Settings/.env aren't loaded yet).
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


def _configure_streamlit_browser_env() -> None:
    """
    Encourage Streamlit to open the UI in Chrome/Edge instead of the default browser.

    Streamlit uses Python's `webbrowser` module; on macOS, setting `BROWSER` to an
    `open -a "<App>"` command reliably opens the chosen app, while plain tokens
    like "chrome" often fall back to the system default browser (Safari).
    """
    current = str(os.environ.get("BROWSER") or "").strip()
    current_token = current.lower()

    prefer = (
        str(os.environ.get("BUG_RESOLUTION_RADAR_BROWSER") or "").strip()
        or str(os.environ.get("HELIX_BROWSER") or "").strip()
        or str(os.environ.get("JIRA_BROWSER") or "").strip()
        or ""
    ).lower()

    # Only override empty/ambiguous values that often make `webbrowser` fall back.
    if current and current_token not in {
        "chrome",
        "google-chrome",
        "google chrome",
        "edge",
        "msedge",
        "microsoft-edge",
        "microsoft edge",
    }:
        return

    token = prefer or current_token or "chrome"
    if token not in {"chrome", "edge"}:
        token = "chrome"

    if sys.platform == "darwin":
        for hint in _BROWSER_HINTS:
            if hint.token != token:
                continue
            chosen: str | None = None
            for app in hint.macos_apps:
                if _macos_has_app(app):
                    chosen = app
                    break
            if chosen is None:
                chosen = hint.macos_apps[0]
            os.environ["BROWSER"] = f'open -a "{chosen}"'
            return
        return

    if token == "edge":
        os.environ["BROWSER"] = "microsoft-edge"
        return
    os.environ["BROWSER"] = "google-chrome"


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
        _load_dotenv_if_present(runtime_home / ".env")
        _configure_streamlit_browser_env()
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
