"""PyInstaller entrypoint that runs the app through Streamlit CLI."""

from __future__ import annotations

import multiprocessing as mp
import os
import runpy
import sys
import threading
import time
from pathlib import Path

from streamlit.web import cli as stcli


def _maybe_run_choreographer_wrapper_passthrough() -> int | None:
    """
    Execute choreographer's Chromium pipe wrapper when the frozen app is invoked as a Python executable.

    Kaleido/choreographer launches a helper on POSIX as:
      [sys.executable, _unix_pipe_chromium_wrapper.py, <chrome>, ...]
    In a PyInstaller app, ``sys.executable`` points to this bundled app binary, so
    without this passthrough we accidentally relaunch Streamlit and open extra tabs.
    """
    if len(sys.argv) < 2:
        return None

    wrapper_path = Path(str(sys.argv[1] or ""))
    if wrapper_path.name != "_unix_pipe_chromium_wrapper.py":
        return None
    if not wrapper_path.exists() or not wrapper_path.is_file():
        return None

    original_argv = list(sys.argv)
    try:
        # Emulate regular `python wrapper.py ...` argv semantics.
        sys.argv = [str(wrapper_path), *original_argv[2:]]
        runpy.run_path(str(wrapper_path), run_name="__main__")
        return 0
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return int(code)
        return 0
    finally:
        sys.argv = original_argv


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


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _float_env(name: str, default: float) -> float:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


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


def _streamlit_credentials_file_path() -> Path:
    return Path.home() / ".streamlit" / "credentials.toml"


def _ensure_streamlit_credentials(email: str) -> None:
    """
    Pre-seed Streamlit activation credentials to avoid first-run CLI prompts.

    Streamlit stores this file in the user's HOME (`~/.streamlit/credentials.toml`),
    not in the app runtime directory.
    """
    normalized_email = str(email or "").strip()
    if not normalized_email:
        return

    target = _streamlit_credentials_file_path()
    try:
        if target.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        escaped_email = normalized_email.replace("\\", "\\\\").replace('"', '\\"')
        target.write_text(
            f'[general]\nemail = "{escaped_email}"\n',
            encoding="utf-8",
        )
    except Exception:
        return


def _configure_streamlit_first_run_noninteractive_defaults() -> None:
    """
    Prevent Streamlit's first-run email prompt in packaged builds.

    We intentionally avoid forcing `server.headless=true` so the binary can keep
    auto-opening the browser for non-technical users.
    """
    os.environ.setdefault("STREAMLIT_SERVER_SHOW_EMAIL_PROMPT", "false")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    default_email = str(
        os.environ.get("BUG_RESOLUTION_RADAR_STREAMLIT_DEFAULT_EMAIL")
        or "bug-resolution-radar@gmail.com"
    ).strip()
    _ensure_streamlit_credentials(default_email)


def _configure_streamlit_runtime_stability_for_binary() -> None:
    """
    Reduce unexpected server restarts and network exposure in packaged builds.

    Long-running operations (e.g. PPT generation with Plotly/Kaleido) may create
    temp files. Streamlit's file watcher can interpret those changes as source
    changes in frozen apps and restart the report, which looks like "spinner
    eterno" and may reopen browser tabs.
    """
    os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
    os.environ.setdefault("STREAMLIT_SERVER_RUN_ON_SAVE", "false")
    os.environ.setdefault("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", "false")
    os.environ.setdefault("STREAMLIT_SERVER_ADDRESS", "127.0.0.1")


def _binary_active_session_count(runtime_obj: object) -> int:
    """Best-effort count of active Streamlit sessions across versions."""
    try:
        session_mgr = getattr(runtime_obj, "_session_mgr", None)
        if session_mgr is not None and hasattr(session_mgr, "num_active_sessions"):
            return int(session_mgr.num_active_sessions())
    except Exception:
        pass
    return 0


def _binary_auto_shutdown_monitor_loop(*, grace_s: float, poll_s: float) -> None:
    """
    Stop the Streamlit runtime after the last browser session disconnects.

    We arm shutdown only after at least one active session has been observed, so
    the binary can stay open while the user takes time to open the first tab.
    """
    seen_active_session = False
    no_session_since: float | None = None

    while True:
        try:
            from streamlit import runtime as st_runtime
            from streamlit.runtime.runtime import RuntimeState

            if not st_runtime.exists():
                time.sleep(poll_s)
                continue

            runtime = st_runtime.get_instance()
            state = getattr(runtime, "state", None)
            if state in (RuntimeState.STOPPING, RuntimeState.STOPPED):
                return

            active_count = _binary_active_session_count(runtime)
            if active_count > 0:
                seen_active_session = True
                no_session_since = None
            elif seen_active_session:
                if no_session_since is None:
                    no_session_since = time.monotonic()
                elif (time.monotonic() - no_session_since) >= grace_s:
                    runtime.stop()
                    return
        except Exception:
            # Keep this monitor fail-safe: never block app startup or usage.
            pass

        time.sleep(poll_s)


def _start_binary_auto_shutdown_monitor() -> None:
    """
    Start a background monitor that stops the server when the last tab closes.

    Defaults are conservative and only apply to packaged binaries.
    """
    enabled = _bool_env("BUG_RESOLUTION_RADAR_AUTO_SHUTDOWN_ON_LAST_SESSION", True)
    if not enabled:
        return

    grace_s = max(3.0, _float_env("BUG_RESOLUTION_RADAR_AUTO_SHUTDOWN_GRACE_S", 20.0))
    poll_s = max(0.2, _float_env("BUG_RESOLUTION_RADAR_AUTO_SHUTDOWN_POLL_S", 1.0))

    thread = threading.Thread(
        target=_binary_auto_shutdown_monitor_loop,
        kwargs={"grace_s": grace_s, "poll_s": poll_s},
        daemon=True,
        name="brr-auto-shutdown-monitor",
    )
    thread.start()


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
        _configure_streamlit_first_run_noninteractive_defaults()
        os.chdir(runtime_home)
        _load_dotenv_if_present(runtime_home / ".env")
        _configure_streamlit_ui_browser_env()
        _configure_streamlit_runtime_stability_for_binary()
        _start_binary_auto_shutdown_monitor()
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
    wrapper_exit = _maybe_run_choreographer_wrapper_passthrough()
    if wrapper_exit is not None:
        raise SystemExit(wrapper_exit)
    mp.freeze_support()
    raise SystemExit(main())
