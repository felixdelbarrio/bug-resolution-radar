from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_run_desktop_module():
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    module_path = repo_root / "run_desktop.py"
    spec = importlib.util.spec_from_file_location("run_desktop_test_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_desktop = _load_run_desktop_module()


def test_desktop_webview_env_flag_can_disable(monkeypatch) -> None:
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW", "false")
    assert run_desktop._desktop_webview_enabled() is False


def test_browser_fallback_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("BUG_RESOLUTION_RADAR_DESKTOP_ALLOW_BROWSER_FALLBACK", raising=False)
    assert run_desktop._browser_fallback_enabled() is False


def test_configure_webview_runtime_settings_enables_downloads() -> None:
    fake_webview = type("FakeWebview", (), {"settings": {"ALLOW_DOWNLOADS": False}})()
    run_desktop._configure_webview_runtime_settings(fake_webview)
    assert fake_webview.settings["ALLOW_DOWNLOADS"] is True


def test_icon_asset_path_prefers_expected_file_type(tmp_path, monkeypatch) -> None:
    icon_dir = tmp_path / "assets" / "app_icon"
    icon_dir.mkdir(parents=True)
    png_path = icon_dir / "bug-resolution-radar.png"
    icns_path = icon_dir / "bug-resolution-radar.icns"
    png_path.write_bytes(b"png")
    icns_path.write_bytes(b"icns")

    monkeypatch.setattr(run_desktop, "ROOT", tmp_path)

    assert run_desktop._icon_asset_path() == png_path.resolve()
    assert run_desktop._icon_asset_path(prefer_icns=True) == icns_path.resolve()


def test_internal_mode_delegates_to_run_api(monkeypatch) -> None:
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_INTERNAL_API_SERVER", "1")
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_INTERNAL_API_PORT", "9876")
    captured: dict[str, object] = {}

    def _fake_run_api_main(argv: list[str]) -> int:
        captured["argv"] = list(argv)
        return 17

    monkeypatch.setattr(run_desktop, "run_api_main", _fake_run_api_main)
    assert run_desktop.main() == 17
    assert captured["argv"] == ["--host", "127.0.0.1", "--port", "9876"]
