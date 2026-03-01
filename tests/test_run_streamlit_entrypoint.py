from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _load_run_streamlit_module():
    module_path = Path(__file__).resolve().parents[1] / "run_streamlit.py"
    spec = importlib.util.spec_from_file_location("run_streamlit_test_module", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"No se pudo cargar módulo desde {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_streamlit = _load_run_streamlit_module()


def test_choreographer_wrapper_passthrough_ignores_normal_invocation(
    monkeypatch,
) -> None:
    monkeypatch.setattr(run_streamlit.sys, "argv", ["bug-resolution-radar"])
    assert run_streamlit._maybe_run_choreographer_wrapper_passthrough() is None


def test_choreographer_wrapper_passthrough_executes_wrapper_script(
    monkeypatch,
    tmp_path: Path,
) -> None:
    wrapper = tmp_path / "_unix_pipe_chromium_wrapper.py"
    wrapper.write_text("print('noop')\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def _fake_run_path(path: str, *, run_name: str) -> dict[str, object]:
        captured["path"] = path
        captured["run_name"] = run_name
        captured["argv_seen"] = list(run_streamlit.sys.argv)
        return {}

    original_argv = [
        "/Applications/bug-resolution-radar.app/Contents/MacOS/bug-resolution-radar",
        str(wrapper),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless",
    ]
    monkeypatch.setattr(run_streamlit.runpy, "run_path", _fake_run_path)
    monkeypatch.setattr(run_streamlit.sys, "argv", list(original_argv))

    assert run_streamlit._maybe_run_choreographer_wrapper_passthrough() == 0
    assert captured["path"] == str(wrapper)
    assert captured["run_name"] == "__main__"
    assert captured["argv_seen"] == [str(wrapper), *original_argv[2:]]
    assert run_streamlit.sys.argv == original_argv


def test_binary_runtime_stability_config_binds_localhost(monkeypatch) -> None:
    monkeypatch.delenv("STREAMLIT_SERVER_ADDRESS", raising=False)
    monkeypatch.delenv("STREAMLIT_SERVER_FILE_WATCHER_TYPE", raising=False)
    monkeypatch.delenv("STREAMLIT_SERVER_RUN_ON_SAVE", raising=False)
    monkeypatch.delenv("STREAMLIT_GLOBAL_DEVELOPMENT_MODE", raising=False)

    run_streamlit._configure_streamlit_runtime_stability_for_binary()

    assert os.environ["STREAMLIT_SERVER_ADDRESS"] == "127.0.0.1"
    assert os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] == "none"
    assert os.environ["STREAMLIT_SERVER_RUN_ON_SAVE"] == "false"
    assert os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] == "false"


def test_ensure_streamlit_credentials_creates_default_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    credentials_path = tmp_path / ".streamlit" / "credentials.toml"
    monkeypatch.setattr(
        run_streamlit,
        "_streamlit_credentials_file_path",
        lambda: credentials_path,
    )

    run_streamlit._ensure_streamlit_credentials("bug-resolution-radar@gmail.com")

    assert credentials_path.exists()
    assert (
        credentials_path.read_text(encoding="utf-8")
        == '[general]\nemail = "bug-resolution-radar@gmail.com"\n'
    )


def test_ensure_streamlit_credentials_does_not_overwrite_existing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    credentials_path = tmp_path / ".streamlit" / "credentials.toml"
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    credentials_path.write_text(
        '[general]\nemail = "existing@example.com"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run_streamlit,
        "_streamlit_credentials_file_path",
        lambda: credentials_path,
    )

    run_streamlit._ensure_streamlit_credentials("bug-resolution-radar@gmail.com")

    assert (
        credentials_path.read_text(encoding="utf-8")
        == '[general]\nemail = "existing@example.com"\n'
    )


def test_configure_streamlit_first_run_noninteractive_defaults(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("STREAMLIT_SERVER_SHOW_EMAIL_PROMPT", raising=False)
    monkeypatch.delenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", raising=False)
    monkeypatch.delenv("BUG_RESOLUTION_RADAR_STREAMLIT_DEFAULT_EMAIL", raising=False)

    credentials_path = tmp_path / ".streamlit" / "credentials.toml"
    monkeypatch.setattr(
        run_streamlit,
        "_streamlit_credentials_file_path",
        lambda: credentials_path,
    )

    run_streamlit._configure_streamlit_first_run_noninteractive_defaults()

    assert os.environ["STREAMLIT_SERVER_SHOW_EMAIL_PROMPT"] == "false"
    assert os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] == "false"
    assert credentials_path.exists()


def test_start_binary_auto_shutdown_monitor_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_AUTO_SHUTDOWN_ON_LAST_SESSION", "false")

    class _ThreadMustNotRun:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Thread should not be created when auto-shutdown is disabled")

    monkeypatch.setattr(run_streamlit.threading, "Thread", _ThreadMustNotRun)
    run_streamlit._start_binary_auto_shutdown_monitor()


def test_start_binary_auto_shutdown_monitor_starts_daemon_thread(monkeypatch) -> None:
    monkeypatch.delenv("BUG_RESOLUTION_RADAR_AUTO_SHUTDOWN_ON_LAST_SESSION", raising=False)
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_AUTO_SHUTDOWN_GRACE_S", "7")
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_AUTO_SHUTDOWN_POLL_S", "0.5")

    captured: dict[str, object] = {}

    class _FakeThread:
        def __init__(self, *, target, kwargs, daemon, name):
            captured["target"] = target
            captured["kwargs"] = kwargs
            captured["daemon"] = daemon
            captured["name"] = name

        def start(self) -> None:
            captured["started"] = True

    monkeypatch.setattr(run_streamlit.threading, "Thread", _FakeThread)
    run_streamlit._start_binary_auto_shutdown_monitor()

    assert captured["target"] is run_streamlit._binary_auto_shutdown_monitor_loop
    assert captured["kwargs"] == {"grace_s": 7.0, "poll_s": 0.5}
    assert captured["daemon"] is True
    assert captured["name"] == "brr-auto-shutdown-monitor"
    assert captured["started"] is True


def test_build_streamlit_argv_for_internal_server_headless() -> None:
    script = Path("/tmp/app.py")
    argv = run_streamlit._build_streamlit_argv(script, port=9876, headless=True)

    assert argv[0:3] == ["streamlit", "run", str(script)]
    assert "--server.address=127.0.0.1" in argv
    assert "--server.port=9876" in argv
    assert "--server.headless=true" in argv


def test_build_streamlit_argv_for_local_dev_browser_mode() -> None:
    script = Path("/tmp/app.py")
    argv = run_streamlit._build_streamlit_argv(script, port=None, headless=False)

    assert "--server.address=127.0.0.1" not in argv
    assert "--server.headless=true" not in argv


def test_is_internal_server_mode_respects_env_flag(monkeypatch) -> None:
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_INTERNAL_STREAMLIT_SERVER", "1")
    assert run_streamlit._is_internal_server_mode() is True

    monkeypatch.setenv("BUG_RESOLUTION_RADAR_INTERNAL_STREAMLIT_SERVER", "false")
    assert run_streamlit._is_internal_server_mode() is False


def test_desktop_webview_default_is_disabled_on_macos(monkeypatch) -> None:
    monkeypatch.delenv("BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW", raising=False)
    monkeypatch.setattr(run_streamlit.sys, "platform", "darwin", raising=False)
    assert run_streamlit._desktop_webview_enabled_for_frozen_binary() is False


def test_desktop_webview_can_be_force_enabled_on_macos(monkeypatch) -> None:
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW", "true")
    monkeypatch.setattr(run_streamlit.sys, "platform", "darwin", raising=False)
    assert run_streamlit._desktop_webview_enabled_for_frozen_binary() is True


def test_start_internal_streamlit_subprocess_passes_internal_env(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeProcess:
        def poll(self) -> None:
            return None

    def _fake_popen(cmd, *, env, cwd):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["cwd"] = cwd
        return _FakeProcess()

    monkeypatch.setattr(run_streamlit.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(run_streamlit.sys, "executable", "/tmp/brr-bin")
    monkeypatch.setenv("EXISTING_ENV", "keep-me")

    proc = run_streamlit._start_internal_streamlit_subprocess(9123)

    assert isinstance(proc, _FakeProcess)
    assert captured["cmd"] == ["/tmp/brr-bin"]
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["BUG_RESOLUTION_RADAR_INTERNAL_STREAMLIT_SERVER"] == "1"
    assert env["BUG_RESOLUTION_RADAR_INTERNAL_STREAMLIT_PORT"] == "9123"
    assert env["BROWSER"] == "none"
    assert env["EXISTING_ENV"] == "keep-me"
