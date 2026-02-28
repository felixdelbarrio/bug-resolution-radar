"""Browser orchestration helpers for cookie-backed ingestion flows."""

from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from platform import system as platform_system
from typing import Iterable, List, Optional
from urllib.parse import urlparse


def _root_from_url(url: str) -> str:
    txt = str(url or "").strip()
    if not txt:
        return ""
    parsed = urlparse(txt)
    scheme = str(parsed.scheme or "").strip()
    host = str(parsed.hostname or "").strip()
    if not scheme or not host:
        return ""
    return f"{scheme}://{host}"


def _is_chrome_browser(browser: str) -> bool:
    return str(browser or "").strip().lower() == "chrome"


def _escape_applescript_text(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


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


def _browser_app_control_enabled(platform: str) -> bool:
    """
    Whether to use browser-app control primitives (AppleScript/open -a).

    On macOS this is disabled by default to avoid automation-style permission
    prompts when a simple URL open is enough.
    """
    if _corporate_mode_enabled():
        return False
    default = platform != "darwin"
    return _bool_env("BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL", default)


def _prefer_selected_browser_binary(platform: str) -> bool:
    """
    Prefer launching browser executables directly instead of app automation.

    This keeps automatic login bootstrap tabs working while avoiding AppleScript
    flows on restricted corporate macOS environments.
    """
    if _corporate_mode_enabled():
        return True
    default = platform in {"darwin", "linux"}
    return _bool_env("BUG_RESOLUTION_RADAR_PREFER_SELECTED_BROWSER_BINARY", default)


def _browser_binary_candidates(platform: str, *, use_chrome: bool) -> List[List[str]]:
    env_key = (
        "BUG_RESOLUTION_RADAR_CHROME_BINARY" if use_chrome else "BUG_RESOLUTION_RADAR_EDGE_BINARY"
    )
    explicit = str(os.environ.get(env_key) or "").strip()
    out: List[List[str]] = []
    if explicit:
        out.append([explicit])

    if platform == "darwin":
        if use_chrome:
            out.extend(
                [
                    ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
                    ["/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"],
                    ["google-chrome"],
                    ["chrome"],
                ]
            )
            return out
        out.extend(
            [
                ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
                ["microsoft-edge"],
                ["msedge"],
            ]
        )
        return out
    if platform == "linux":
        if use_chrome:
            out.extend([["google-chrome"], ["chrome"], ["chromium"]])
            return out
        out.extend([["microsoft-edge"], ["msedge"]])
        return out
    if platform == "windows":
        if use_chrome:
            out.extend(
                [
                    ["chrome"],
                    [r"C:\Program Files\Google\Chrome\Application\chrome.exe"],
                    [r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
                ]
            )
            return out
        out.extend(
            [
                ["msedge"],
                [r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
                [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"],
            ]
        )
        return out
    return out


def _resolve_base_command(base_cmd: List[str]) -> Optional[List[str]]:
    if not base_cmd:
        return None
    executable = str(base_cmd[0] or "").strip()
    if not executable:
        return None

    if os.path.isabs(executable):
        path = executable
        if not (os.path.exists(path) and os.path.isfile(path)):
            return None
        return [path, *base_cmd[1:]]

    resolved = shutil.which(executable)
    if not resolved:
        return None
    return [resolved, *base_cmd[1:]]


def _launch_url_with_selected_browser_binary(
    url: str,
    *,
    platform: str,
    use_chrome: bool,
) -> bool:
    for candidate in _browser_binary_candidates(platform, use_chrome=use_chrome):
        base_cmd = _resolve_base_command(candidate)
        if not base_cmd:
            continue
        cmd = [*base_cmd, url]
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            continue
    return False


def _launch_url_with_macos_selected_app(url: str, *, use_chrome: bool) -> bool:
    """Best-effort macOS fallback that still honors selected browser."""
    app_name = "Google Chrome" if use_chrome else "Microsoft Edge"
    try:
        subprocess.Popen(
            ["open", "-a", app_name, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def open_url_in_configured_browser(url: str, browser: str) -> bool:
    """Open URL in the configured browser with platform-specific fallbacks."""
    if not _root_from_url(url):
        return False

    use_chrome = _is_chrome_browser(browser)
    platform = platform_system().lower()
    allow_app_control = _browser_app_control_enabled(platform)
    prefer_browser_binary = _prefer_selected_browser_binary(platform)

    if prefer_browser_binary and _launch_url_with_selected_browser_binary(
        url,
        platform=platform,
        use_chrome=use_chrome,
    ):
        return True
    if platform == "darwin" and prefer_browser_binary:
        if _launch_url_with_macos_selected_app(url, use_chrome=use_chrome):
            return True

    browser_names = (
        ["chrome", "google-chrome", "google chrome"]
        if use_chrome
        else ["edge", "msedge", "microsoft-edge", "microsoft edge"]
    )
    if allow_app_control:
        for name in browser_names:
            try:
                ctl = webbrowser.get(name)
                if ctl.open(url, new=2, autoraise=True):
                    return True
            except Exception:
                continue

    if platform == "darwin" and allow_app_control:
        app_name = "Google Chrome" if use_chrome else "Microsoft Edge"
        try:
            subprocess.Popen(
                ["open", "-a", app_name, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            pass

    try:
        return bool(webbrowser.open(url, new=2, autoraise=True))
    except Exception:
        return False


def open_urls_in_configured_browser(
    urls: Iterable[str],
    browser: str,
    *,
    max_urls: Optional[int] = None,
) -> int:
    """
    Open multiple valid URLs in the configured browser (best effort).

    Returns the number of successful launches. URLs are de-duplicated while
    preserving order.
    """
    cap = max_urls
    if cap is None:
        cap_raw = str(
            os.environ.get("BUG_RESOLUTION_RADAR_BROWSER_BOOTSTRAP_MAX_TABS") or ""
        ).strip()
        if cap_raw:
            try:
                cap = int(cap_raw)
            except Exception:
                cap = 3
        else:
            cap = 3
    cap = max(1, int(cap or 1))

    normalized: List[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = str(raw or "").strip()
        if not url:
            continue
        if not _root_from_url(url):
            continue
        if url in seen:
            continue
        normalized.append(url)
        seen.add(url)
        if len(normalized) >= cap:
            break

    opened = 0
    for url in normalized:
        if open_url_in_configured_browser(url, browser):
            opened += 1
    return opened


def is_target_page_open_in_configured_browser(url: str, browser: str) -> Optional[bool]:
    """
    Return whether the target URL/root appears open in the configured browser.

    - `True`: at least one tab for URL/root is open.
    - `False`: browser is available and tab is not open.
    - `None`: status cannot be determined on this environment.
    """
    root = _root_from_url(url)
    if not root:
        return False

    platform = platform_system().lower()
    if platform != "darwin":
        return None
    if not _browser_app_control_enabled(platform):
        return None

    app_name = "Google Chrome" if _is_chrome_browser(browser) else "Microsoft Edge"
    script_lines = [
        f'set targetUrl to "{_escape_applescript_text(url)}"',
        f'set targetRoot to "{_escape_applescript_text(root)}"',
        f'set appName to "{app_name}"',
        "if application appName is not running then",
        '  return "0"',
        "end if",
        "try",
        "  tell application appName",
        "    repeat with w in windows",
        "      repeat with t in tabs of w",
        "        set tabUrl to URL of t",
        "        if tabUrl is missing value then",
        "        else if tabUrl starts with targetUrl then",
        '          return "1"',
        '        else if targetRoot is not "" and tabUrl starts with targetRoot then',
        '          return "1"',
        "        end if",
        "      end repeat",
        "    end repeat",
        "  end tell",
        "on error",
        '  return ""',
        "end try",
        'return "0"',
    ]
    cmd = ["osascript"]
    for line in script_lines:
        cmd.extend(["-e", line])

    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=2.5,
        )
    except Exception:
        return None

    value = str(result.stdout or "").strip()
    if value == "1":
        return True
    if value == "0":
        return False
    return None
