"""Browser orchestration helpers for cookie-backed ingestion flows."""

from __future__ import annotations

import subprocess
import webbrowser
from platform import system as platform_system
from typing import Optional
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


def open_url_in_configured_browser(url: str, browser: str) -> bool:
    """Open URL in the configured browser with platform-specific fallbacks."""
    if not _root_from_url(url):
        return False

    use_chrome = _is_chrome_browser(browser)
    browser_names = (
        ["chrome", "google-chrome", "google chrome"]
        if use_chrome
        else ["edge", "msedge", "microsoft-edge", "microsoft edge"]
    )
    for name in browser_names:
        try:
            ctl = webbrowser.get(name)
            if ctl.open(url, new=2, autoraise=True):
                return True
        except Exception:
            continue

    platform = platform_system().lower()
    if platform == "darwin":
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

    if platform == "linux":
        bins = (
            ["google-chrome", "chrome", "chromium"] if use_chrome else ["microsoft-edge", "msedge"]
        )
        for bin_name in bins:
            try:
                subprocess.Popen(
                    [bin_name, url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                continue

    try:
        return bool(webbrowser.open(url, new=2, autoraise=True))
    except Exception:
        return False


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

    if platform_system().lower() != "darwin":
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
