"""PyInstaller entrypoint for desktop and CLI Streamlit runtimes."""

from __future__ import annotations

import multiprocessing as mp
import os
import runpy
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from traceback import format_exc

from streamlit.web import cli as stcli

_INTERNAL_SERVER_ENV = "BUG_RESOLUTION_RADAR_INTERNAL_STREAMLIT_SERVER"
_INTERNAL_SERVER_PORT_ENV = "BUG_RESOLUTION_RADAR_INTERNAL_STREAMLIT_PORT"
_LAUNCHER_LOG_FILE: Path | None = None


def _set_launcher_log_file(path: Path) -> None:
    global _LAUNCHER_LOG_FILE
    _LAUNCHER_LOG_FILE = path


def _launcher_log(message: str) -> None:
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    line = f"[{stamp}] {message}\n"
    try:
        if _LAUNCHER_LOG_FILE is not None:
            _LAUNCHER_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _LAUNCHER_LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:
        pass


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
    """Load a minimal `.env` file before starting Streamlit."""
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


def _corporate_mode_enabled() -> bool:
    return _bool_env("BUG_RESOLUTION_RADAR_CORPORATE_MODE", False)


def _float_env(name: str, default: float) -> float:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _ensure_localhost_no_proxy_env() -> None:
    tokens = ["localhost", "127.0.0.1", "::1"]
    for key in ("NO_PROXY", "no_proxy"):
        raw = str(os.environ.get(key) or "").strip()
        if not raw:
            os.environ[key] = ",".join(tokens)
            continue
        existing = [part.strip() for part in raw.split(",") if part.strip()]
        for token in tokens:
            if token not in existing:
                existing.append(token)
        os.environ[key] = ",".join(existing)


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
    """Prevent Streamlit's first-run email prompt in packaged builds."""
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
    changes in frozen apps and restart the report.
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
    Stop the Streamlit runtime after the last desktop session disconnects.

    We arm shutdown only after at least one active session has been observed, so
    startup races do not terminate the process too early.
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
    Start a background monitor that stops the server when the last session closes.

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


def _build_streamlit_argv(script: Path, *, port: int | None, headless: bool) -> list[str]:
    argv = [
        "streamlit",
        "run",
        str(script),
        "--global.developmentMode=false",
        "--server.fileWatcherType=none",
        "--server.runOnSave=false",
    ]
    if port is not None:
        argv.extend(
            [
                "--server.address=127.0.0.1",
                f"--server.port={int(port)}",
            ]
        )
    if headless:
        argv.append("--server.headless=true")
    return argv


def _run_streamlit_cli(script: Path, *, port: int | None, headless: bool) -> int:
    if headless:
        os.environ["BROWSER"] = "none"
    sys.argv = _build_streamlit_argv(script, port=port, headless=headless)
    return int(stcli.main())


def _desktop_candidate_ports() -> list[int]:
    first = max(1, _int_env("BUG_RESOLUTION_RADAR_DESKTOP_PORT", 8501))
    out: list[int] = [first]
    for offset in range(1, 6):
        candidate = first + offset
        if candidate > 65535:
            break
        out.append(candidate)
    return out


def _streamlit_base_url(port: int) -> str:
    return f"http://localhost:{int(port)}"


def _healthcheck_urls(port: int) -> list[str]:
    p = int(port)
    return [
        f"http://127.0.0.1:{p}/_stcore/health",
        f"http://localhost:{p}/_stcore/health",
    ]


def _wait_for_streamlit_ready(
    *, port: int, proc: subprocess.Popen[bytes], timeout_s: float
) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    _launcher_log(
        f"Esperando healthcheck de Streamlit en puerto {port} (timeout={timeout_s:.1f}s)."
    )
    deadline = time.monotonic() + max(1.0, float(timeout_s))
    while time.monotonic() < deadline:
        return_code = proc.poll()
        if return_code is not None:
            _launcher_log(
                f"Servidor interno terminó antes de estar listo. Exit code={return_code}."
            )
            raise RuntimeError(
                f"El servidor interno finalizó antes de iniciar (exit={return_code})."
            )
        for health_url in _healthcheck_urls(port):
            try:
                with opener.open(health_url, timeout=1.0) as response:
                    if int(getattr(response, "status", 200)) < 500:
                        return
            except (urllib.error.URLError, TimeoutError, OSError):
                continue
        time.sleep(0.2)
    raise TimeoutError(f"Timeout esperando Streamlit en {_streamlit_base_url(port)}.")


def _is_internal_server_mode() -> bool:
    return _bool_env(_INTERNAL_SERVER_ENV, False)


def _desktop_webview_enabled_for_frozen_binary() -> bool:
    """
    Return whether packaged binaries should use embedded pywebview.

    We run in container-first mode to keep UX consistent across environments and
    avoid forcing the system default browser for the main app shell.
    """
    default = True
    return _bool_env("BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW", default)


def _desktop_webview_browser_fallback_enabled() -> bool:
    """
    Allow automatic fallback to external browser if desktop container fails.

    This keeps the app usable even when pywebview backend initialization fails on
    a locked-down endpoint.
    """
    return _bool_env("BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW_FALLBACK_BROWSER", True)


def _start_internal_streamlit_subprocess(port: int) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env[_INTERNAL_SERVER_ENV] = "1"
    env[_INTERNAL_SERVER_PORT_ENV] = str(int(port))
    env["BROWSER"] = "none"
    for key in ("NO_PROXY", "no_proxy"):
        env[key] = str(os.environ.get(key) or "localhost,127.0.0.1,::1")
    _launcher_log(f"Iniciando servidor interno de Streamlit en puerto {port}.")
    return subprocess.Popen([sys.executable], env=env, cwd=os.getcwd())


def _stop_internal_streamlit_subprocess(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        _launcher_log("Solicitado terminate() del servidor interno.")
    except Exception:
        pass
    try:
        proc.wait(timeout=10)
        return
    except Exception:
        pass
    try:
        proc.kill()
        _launcher_log("Ejecutado kill() del servidor interno tras timeout.")
    except Exception:
        pass


def _run_desktop_container() -> int:
    last_error: Exception | None = None
    chosen_port: int | None = None
    proc: subprocess.Popen[bytes] | None = None
    try:
        for port in _desktop_candidate_ports():
            candidate_proc = _start_internal_streamlit_subprocess(port)
            try:
                _wait_for_streamlit_ready(
                    port=port,
                    proc=candidate_proc,
                    timeout_s=_float_env("BUG_RESOLUTION_RADAR_SERVER_BOOT_TIMEOUT_S", 45.0),
                )
                proc = candidate_proc
                chosen_port = port
                _launcher_log(f"Servidor interno listo en puerto {chosen_port}.")
                break
            except Exception as exc:
                last_error = exc
                _launcher_log(
                    f"Fallo arrancando servidor interno en puerto {port}: {type(exc).__name__}: {exc}"
                )
                _stop_internal_streamlit_subprocess(candidate_proc)
                continue

        if proc is None or chosen_port is None:
            if last_error is not None:
                raise last_error
            raise RuntimeError("No se pudo iniciar el servidor interno de Streamlit.")

        try:
            import webview
        except Exception as exc:
            _launcher_log(
                "Error importando webview para contenedor de escritorio.\n" + format_exc()
            )
            raise RuntimeError(
                "No se pudo cargar pywebview para abrir el contenedor de escritorio."
            ) from exc

        title = str(os.environ.get("APP_TITLE") or "Bug Resolution Radar").strip() or (
            "Bug Resolution Radar"
        )
        width = max(960, _int_env("BUG_RESOLUTION_RADAR_WINDOW_WIDTH", 1480))
        height = max(700, _int_env("BUG_RESOLUTION_RADAR_WINDOW_HEIGHT", 940))
        min_width = max(800, _int_env("BUG_RESOLUTION_RADAR_WINDOW_MIN_WIDTH", 1024))
        min_height = max(600, _int_env("BUG_RESOLUTION_RADAR_WINDOW_MIN_HEIGHT", 700))

        webview.create_window(
            title=title,
            url=_streamlit_base_url(chosen_port),
            width=width,
            height=height,
            min_size=(min_width, min_height),
        )
        gui_backend = str(os.environ.get("BUG_RESOLUTION_RADAR_WEBVIEW_GUI") or "").strip()
        if gui_backend:
            _launcher_log(f"Abriendo contenedor desktop con GUI backend explícito: {gui_backend}")
            webview.start(gui=gui_backend, debug=False)
        else:
            _launcher_log("Abriendo contenedor desktop con GUI backend automático.")
            webview.start(debug=False)
        _launcher_log("Contenedor desktop finalizado correctamente.")
        return 0
    finally:
        if proc is not None:
            _stop_internal_streamlit_subprocess(proc)


def _prepare_frozen_runtime() -> None:
    runtime_home = _runtime_home_for_binary()
    os.environ.setdefault("BUG_RESOLUTION_RADAR_HOME", str(runtime_home))
    runtime_home.mkdir(parents=True, exist_ok=True)
    _set_launcher_log_file(runtime_home / "logs" / "desktop-launcher.log")
    _launcher_log("Inicializando runtime empaquetado.")
    _ensure_streamlit_config(runtime_home)
    _configure_streamlit_first_run_noninteractive_defaults()
    os.chdir(runtime_home)
    _load_dotenv_if_present(runtime_home / ".env")
    if _corporate_mode_enabled():
        # Conservative defaults for locked-down corporate endpoints.
        # Force container-first on corporate endpoints to avoid default-browser UX drift,
        # even if old .env templates left this value as false.
        os.environ["BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW"] = "true"
        os.environ.setdefault("BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW_FALLBACK_BROWSER", "true")
        os.environ.setdefault("BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL", "false")
        os.environ.setdefault("BUG_RESOLUTION_RADAR_PREFER_SELECTED_BROWSER_BINARY", "true")
        _launcher_log(
            "Corporate mode activo: contenedor embebido + mínimos permisos + browser bootstrap sin AppleScript."
        )
    _ensure_localhost_no_proxy_env()
    _configure_streamlit_runtime_stability_for_binary()


def main() -> int:
    script = _resolve_app_script()

    if not getattr(sys, "frozen", False):
        return _run_streamlit_cli(script, port=None, headless=False)

    _prepare_frozen_runtime()

    if _is_internal_server_mode():
        _start_binary_auto_shutdown_monitor()
        port = max(1, _int_env(_INTERNAL_SERVER_PORT_ENV, 8501))
        return _run_streamlit_cli(script, port=port, headless=True)

    if not _desktop_webview_enabled_for_frozen_binary():
        _launcher_log(
            "Modo desktop sin pywebview activado: usando navegador del sistema para minimizar permisos."
        )
        _start_binary_auto_shutdown_monitor()
        return _run_streamlit_cli(script, port=None, headless=False)

    try:
        return _run_desktop_container()
    except Exception as exc:
        _launcher_log("Error fatal iniciando contenedor desktop.\n" + format_exc())
        if _desktop_webview_browser_fallback_enabled():
            _launcher_log(
                "Fallback automático a navegador del sistema tras fallo de contenedor desktop."
            )
            _start_binary_auto_shutdown_monitor()
            return _run_streamlit_cli(script, port=None, headless=False)
        log_hint = f" Revisa: {_LAUNCHER_LOG_FILE}" if _LAUNCHER_LOG_FILE is not None else ""
        print(f"Error iniciando contenedor de escritorio: {exc}.{log_hint}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    wrapper_exit = _maybe_run_choreographer_wrapper_passthrough()
    if wrapper_exit is not None:
        raise SystemExit(wrapper_exit)
    mp.freeze_support()
    raise SystemExit(main())
