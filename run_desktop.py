"""Desktop runtime for the packaged React + API application."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from run_api import main as run_api_main  # noqa: E402

_INTERNAL_SERVER_ENV = "BUG_RESOLUTION_RADAR_INTERNAL_API_SERVER"
_INTERNAL_SERVER_PORT_ENV = "BUG_RESOLUTION_RADAR_INTERNAL_API_PORT"
_BROWSER_FALLBACK_ENV = "BUG_RESOLUTION_RADAR_DESKTOP_ALLOW_BROWSER_FALLBACK"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _localhost_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}/"


def _health_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}/api/health"


def _ensure_localhost_no_proxy_env() -> None:
    current = str(os.environ.get("NO_PROXY", "") or os.environ.get("no_proxy", "") or "").strip()
    tokens = [token.strip() for token in current.split(",") if token.strip()]
    for token in ("127.0.0.1", "localhost"):
        if token not in tokens:
            tokens.append(token)
    value = ",".join(tokens)
    os.environ["NO_PROXY"] = value
    os.environ["no_proxy"] = value


def _desktop_webview_enabled() -> bool:
    token = str(os.environ.get("BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW", "true") or "true").strip().lower()
    return token not in {"0", "false", "no", "off"}


def _browser_fallback_enabled() -> bool:
    token = str(os.environ.get(_BROWSER_FALLBACK_ENV, "false") or "false").strip().lower()
    return token in {"1", "true", "yes", "on"}


def _configure_webview_runtime_settings(webview_module: object) -> None:
    settings = getattr(webview_module, "settings", None)
    if isinstance(settings, dict):
        settings["ALLOW_DOWNLOADS"] = True


def _wait_for_api_ready(port: int, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + float(timeout_seconds)
    last_error = "unknown"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(_health_url(port), timeout=2) as response:
                if int(getattr(response, "status", 0) or 0) == 200:
                    return
        except urllib.error.URLError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.2)
    raise TimeoutError(f"Timeout esperando la API local: {last_error}")


def _start_internal_api_subprocess(port: int) -> subprocess.Popen[bytes]:
    env = dict(os.environ)
    env[_INTERNAL_SERVER_ENV] = "1"
    env[_INTERNAL_SERVER_PORT_ENV] = str(port)
    env.setdefault("BUG_RESOLUTION_RADAR_FRONTEND_DEV_URL", "")

    if getattr(sys, "frozen", False):
        cmd = [sys.executable]
    else:
        cmd = [sys.executable, str(ROOT / "run_desktop.py")]

    return subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop_internal_api_subprocess(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
        return
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _run_desktop_container() -> int:
    _ensure_localhost_no_proxy_env()
    port = _find_free_port()
    proc = _start_internal_api_subprocess(port)
    try:
        _wait_for_api_ready(port)
        url = _localhost_url(port)
        if not _desktop_webview_enabled():
            webbrowser.open(url, new=1, autoraise=True)
            return 0

        try:
            import webview
        except Exception as exc:
            if _browser_fallback_enabled():
                webbrowser.open(url, new=1, autoraise=True)
                return 0
            raise RuntimeError(
                "No se pudo iniciar el contenedor desktop con pywebview. "
                "Instala la dependencia GUI o activa el fallback explícito si "
                "quieres abrir el navegador."
            ) from exc

        _configure_webview_runtime_settings(webview)
        webview.create_window(
            "Bug Resolution Radar",
            url=url,
            min_size=(1200, 820),
            text_select=True,
        )
        webview.start(debug=False)
        return 0
    finally:
        _stop_internal_api_subprocess(proc)


def main() -> int:
    if str(os.environ.get(_INTERNAL_SERVER_ENV, "") or "").strip() == "1":
        port = int(str(os.environ.get(_INTERNAL_SERVER_PORT_ENV, "8000") or "8000"))
        return run_api_main(["--host", "127.0.0.1", "--port", str(port)])
    return _run_desktop_container()


if __name__ == "__main__":
    raise SystemExit(main())
