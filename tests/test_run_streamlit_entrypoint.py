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
