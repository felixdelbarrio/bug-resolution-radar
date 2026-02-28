from __future__ import annotations

from typing import Any

from bug_resolution_radar.ingest import browser_runtime


def test_is_target_page_open_returns_none_when_app_control_disabled_on_macos(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL", "false")
    monkeypatch.setattr(browser_runtime, "platform_system", lambda: "Darwin")

    def _must_not_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("osascript should not run when app control is disabled")

    monkeypatch.setattr(browser_runtime.subprocess, "run", _must_not_run)

    out = browser_runtime.is_target_page_open_in_configured_browser(
        "https://example.com/path",
        "chrome",
    )
    assert out is None


def test_open_url_falls_back_to_default_browser_when_app_control_disabled_on_macos(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL", "false")
    monkeypatch.setattr(browser_runtime, "platform_system", lambda: "Darwin")

    captured: dict[str, Any] = {}

    def _fake_open(url: str, new: int = 0, autoraise: bool = True) -> bool:
        captured["url"] = url
        captured["new"] = new
        captured["autoraise"] = autoraise
        return True

    def _must_not_get(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("webbrowser.get should not be used when app control is disabled")

    def _must_not_popen(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("open -a should not be used when app control is disabled")

    monkeypatch.setattr(browser_runtime.webbrowser, "open", _fake_open)
    monkeypatch.setattr(browser_runtime.webbrowser, "get", _must_not_get)
    monkeypatch.setattr(browser_runtime.subprocess, "Popen", _must_not_popen)

    ok = browser_runtime.open_url_in_configured_browser("https://example.com/path", "chrome")
    assert ok is True
    assert captured["url"] == "https://example.com/path"
    assert captured["new"] == 2
    assert captured["autoraise"] is True


def test_open_url_prefers_configured_browser_when_app_control_enabled(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL", "true")
    monkeypatch.setattr(browser_runtime, "platform_system", lambda: "Darwin")

    captured: dict[str, Any] = {}

    class _Controller:
        def open(self, url: str, *, new: int, autoraise: bool) -> bool:
            captured["url"] = url
            captured["new"] = new
            captured["autoraise"] = autoraise
            return True

    def _fake_get(name: str) -> _Controller:
        captured["name"] = name
        return _Controller()

    monkeypatch.setattr(browser_runtime.webbrowser, "get", _fake_get)

    ok = browser_runtime.open_url_in_configured_browser("https://example.com/path", "chrome")
    assert ok is True
    assert captured["name"] == "chrome"
    assert captured["url"] == "https://example.com/path"
    assert captured["new"] == 2
    assert captured["autoraise"] is True
