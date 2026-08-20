"""BBVA design tokens shared by UI and report layers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final


@dataclass(frozen=True)
class BbvPalette:
    midnight: str
    core_blue: str
    electric_blue: str
    royal_blue: str
    serene_dark_blue: str
    serene_blue: str
    aqua: str
    white: str
    bg_light: str
    ink: str
    ink_muted: str


# BBVA Experience core palette. These constants are the canonical source for
# desktop UI, Plotly and report-layer brand colors.
BBVA_MIDNIGHT = "#070E46"
BBVA_ELECTRIC = "#001391"
BBVA_ROYAL_DARK = "#2165CA"
BBVA_ROYAL = "#0C6DFF"
BBVA_SERENE_DARK = "#53A9EF"
BBVA_SERENE = "#85C8FF"
BBVA_BLUE_LIGHT = "#D6E9F8"
BBVA_BLACK = "#000519"
BBVA_GREY_900 = "#11192D"
BBVA_GREY_800 = "#222C42"
BBVA_GREY_700 = "#334056"
BBVA_GREY_600 = "#46536D"
BBVA_GREY_500 = "#ADB8C2"
BBVA_GREY_400 = "#CAD1D8"
BBVA_GREY_300 = "#E2E6EA"
BBVA_GREY_200 = "#F7F8F8"
BBVA_WHITE = "#FFFFFF"


BBVA_LIGHT = BbvPalette(
    midnight=BBVA_MIDNIGHT,
    core_blue=BBVA_ELECTRIC,
    electric_blue=BBVA_ELECTRIC,
    royal_blue=BBVA_ROYAL,
    serene_dark_blue=BBVA_SERENE_DARK,
    serene_blue=BBVA_SERENE,
    aqua=BBVA_BLUE_LIGHT,
    white=BBVA_WHITE,
    bg_light=BBVA_GREY_200,
    ink=BBVA_GREY_900,
    ink_muted=BBVA_GREY_600,
)

BBVA_DARK = BbvPalette(
    midnight=BBVA_MIDNIGHT,
    core_blue=BBVA_GREY_900,
    electric_blue=BBVA_SERENE,
    royal_blue=BBVA_ROYAL,
    serene_dark_blue=BBVA_SERENE_DARK,
    serene_blue=BBVA_SERENE,
    aqua=BBVA_BLUE_LIGHT,
    white=BBVA_WHITE,
    bg_light=BBVA_BLACK,
    ink=BBVA_GREY_200,
    ink_muted=BBVA_GREY_500,
)

# Semantic signal tokens (status/priority chips and traffic-light cues).
BBVA_SIGNAL_RED_1 = "#B4232A"
BBVA_SIGNAL_RED_2 = "#D64550"
BBVA_SIGNAL_RED_3 = "#E85D63"
BBVA_SIGNAL_ORANGE_1 = "#D97706"
BBVA_SIGNAL_ORANGE_2 = "#F59E0B"
BBVA_SIGNAL_YELLOW_1 = "#FBBF24"
BBVA_SIGNAL_GREEN_1 = "#15803D"
BBVA_SIGNAL_GREEN_2 = "#22A447"
BBVA_SIGNAL_GREEN_3 = "#4CAF50"
BBVA_GOAL_ACCENT_7 = "#5B3FD0"
BBVA_GOAL_SURFACE_8 = "#ECE6FF"
BBVA_NEUTRAL_SOFT = BBVA_GREY_300
BBVA_DARK_SURFACE = "#0A1F45"
BBVA_DARK_RED = "#FF8585"
BBVA_DARK_ORANGE = "#FFC553"
BBVA_DARK_YELLOW = "#FFE761"
BBVA_DARK_GREEN = "#9CE67E"
BBVA_DARK_PURPLE = "#9694FF"

# Report semantic tones (PowerPoint/export layer) derived from approved theme palette.
BBVA_REPORT_GREEN = "#38761D"
BBVA_REPORT_AMBER = "#F5B942"
BBVA_REPORT_RED = BBVA_SIGNAL_RED_2
BBVA_REPORT_LINE = "#D3D8E1"
BBVA_REPORT_MIST = "#EEF3FB"
BBVA_REPORT_BLUE_BG = "#EAF2FF"
BBVA_REPORT_BLUE_BORDER = "#B8CCE8"
BBVA_REPORT_BLUE_TEXT = "#0B3A75"
BBVA_REPORT_SKY_BG = "#E8F7FF"
BBVA_REPORT_SKY_BORDER = "#9DDCFB"
BBVA_REPORT_SKY_TEXT = "#0B4A6F"
BBVA_REPORT_TEAL_BG = "#E6F9F7"
BBVA_REPORT_TEAL_BORDER = "#9EDFD9"
BBVA_REPORT_TEAL_TEXT = "#0E5C5C"
BBVA_REPORT_AMBER_BG = "#FFF4DE"
BBVA_REPORT_AMBER_BORDER = "#F3D89B"
BBVA_REPORT_AMBER_TEXT = "#7A5A12"
BBVA_REPORT_GREEN_BG = "#EAF6EC"
BBVA_REPORT_GREEN_BORDER = "#B8DDBF"
BBVA_REPORT_GREEN_TEXT = "#1F5B2E"
BBVA_REPORT_RED_BG = "#FDEBEC"
BBVA_REPORT_RED_BORDER = "#E3A5AA"
BBVA_REPORT_RED_TEXT = "#8B1D26"
BBVA_REPORT_NEUTRAL_BORDER = "#C8D6E8"
BBVA_REPORT_DARK_BG_1 = "#001B4A"
BBVA_REPORT_DARK_BG_2 = "#001C4A"
BBVA_REPORT_DARK_ACCENT_LINE = "#2A66B8"
BBVA_REPORT_DARK_TEXT_SOFT = "#BDD8FF"
BBVA_REPORT_DARK_TEXT_SUBTLE = "#CFE2FF"
BBVA_REPORT_DARK_TEXT_MID = "#DDEBFF"

BBVA_FONT_SANS_BOOK = (
    '"BentonSansBBVA-Book", "Benton Sans BBVA Book", "BentonSansBBVA", '
    '"Benton Sans BBVA", "BBVA Benton Sans", "Lato", "Arial", sans-serif'
)
BBVA_FONT_SANS_MEDIUM = (
    '"BentonSansBBVA-Medium", "Benton Sans BBVA Medium", "BentonSansBBVA", '
    '"Benton Sans BBVA", "BBVA Benton Sans", "Lato", "Arial", sans-serif'
)
BBVA_FONT_SANS = BBVA_FONT_SANS_BOOK
BBVA_FONT_HEADLINE = (
    '"Tiempos Headline", "TiemposText-Regular", "Tiempos Text", "Lato", "Arial", serif'
)


def _norm_font_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


@lru_cache(maxsize=1)
def _installed_font_hints() -> set[str]:
    hints: set[str] = set()

    # Common font dirs in macOS/Linux/Windows.
    roots = [
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library/Fonts",
        Path("/usr/share/fonts"),
        Path.home() / ".local/share/fonts",
        Path.home() / ".fonts",
    ]
    win_dir = os.environ.get("WINDIR")
    if win_dir:
        roots.append(Path(win_dir) / "Fonts")

    for root in roots:
        if not root.exists():
            continue
        try:
            for file_path in root.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                    continue
                hints.add(_norm_font_token(file_path.stem))
        except Exception:
            continue

    # Optional enrichment when matplotlib is available.
    try:
        from matplotlib import font_manager as fm  # type: ignore

        for font in list(getattr(fm.fontManager, "ttflist", []) or []):
            hints.add(_norm_font_token(getattr(font, "name", "")))
    except Exception:
        pass

    return hints


def _font_available(name: str, hints: set[str]) -> bool:
    token = _norm_font_token(name)
    if not token:
        return False
    return any(token in hint or hint in token for hint in hints)


def _resolve_ppt_font(preferred: list[str], *, fallback: str) -> str:
    hints = _installed_font_hints()
    for candidate in preferred:
        if _font_available(candidate, hints):
            return candidate
    return fallback


# PowerPoint supports one font name per run. Resolve locally with safe fallback.
BBVA_FONT_SANS_PPT = _resolve_ppt_font(
    [
        "Benton Sans BBVA",
        "BBVA Benton Sans",
        "Benton Sans",
        "Lato",
        "Arial",
    ],
    fallback="Arial",
)
BBVA_FONT_SANS_BOOK_PPT = _resolve_ppt_font(
    [
        "Benton Sans BBVA Book",
        "BBVA Benton Sans Book",
        "Benton Sans Book",
        "Lato",
        "Arial",
    ],
    fallback=BBVA_FONT_SANS_PPT,
)
BBVA_FONT_SANS_MEDIUM_PPT = _resolve_ppt_font(
    [
        "Benton Sans BBVA Medium",
        "BBVA Benton Sans Medium",
        "Benton Sans Medium",
        "Lato",
        "Arial",
    ],
    fallback=BBVA_FONT_SANS_PPT,
)
BBVA_FONT_HEADLINE_PPT = _resolve_ppt_font(
    [
        "Tiempos Headline",
        "Tiempos Headline Bold",
        "Lato",
        "Arial",
    ],
    fallback=BBVA_FONT_SANS_PPT,
)

BBVA_RADIUS_OUTER_PX = 16
BBVA_RADIUS_INNER_PX = 8
BBVA_GRID_BASE_PX = 8
BBVA_GRID_MARGIN_PX = 24
BBVA_GRID_GUTTER_PX = 24
BBVA_CONTENT_MAX_PX = 1296

# Executive PPT chart export tokens. Plotly interprets font sizes as pixels in
# exported raster output; keep the names stable for the report layer.
EXEC_CHART_AXIS_FONT_PT: Final[int] = 30
EXEC_CHART_AXIS_TITLE_FONT_PT: Final[int] = 31
EXEC_CHART_INSIDE_VALUE_FONT_PT: Final[int] = 30
EXEC_CHART_TOTAL_FONT_PT: Final[int] = 40
EXEC_CHART_LEGEND_FONT_PT: Final[int] = 28
EXEC_CHART_MARGIN: Final[dict[str, int]] = {"l": 72, "r": 48, "t": 78, "b": 142}
EXEC_CHART_EXPORT_WIDTH: Final[int] = 1700
EXEC_CHART_EXPORT_HEIGHT: Final[int] = 420
EXEC_CHART_TREND_EXPORT_HEIGHT: Final[int] = 773


def _safe_hex(hex_color: str, *, fallback: str) -> str:
    token = str(hex_color or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", token):
        return token
    return str(fallback or "").strip().lstrip("#")


def hex_to_rgb(hex_color: str, *, fallback: str = BBVA_LIGHT.ink) -> tuple[int, int, int]:
    token = _safe_hex(hex_color, fallback=fallback)
    return (int(token[0:2], 16), int(token[2:4], 16), int(token[4:6], 16))


def hex_to_rgb_csv(hex_color: str, *, fallback: str = BBVA_LIGHT.ink) -> str:
    r, g, b = hex_to_rgb(hex_color, fallback=fallback)
    return f"{r},{g},{b}"


def hex_to_rgba(hex_color: str, alpha: float, *, fallback: str = BBVA_LIGHT.ink) -> str:
    r, g, b = hex_to_rgb(hex_color, fallback=fallback)
    return f"rgba({r},{g},{b},{float(alpha):.3f})"


def hex_with_alpha(hex_color: str, alpha: int, *, fallback: str = BBVA_LIGHT.ink) -> str:
    """Return an 8-digit hex color (#RRGGBBAA) with bounded alpha."""
    token = _safe_hex(hex_color, fallback=fallback)
    alpha_i = max(0, min(255, int(alpha)))
    return f"#{token}{alpha_i:02X}"


def frontend_theme_tokens() -> dict[str, dict[str, str]]:
    """Return frontend CSS variables derived from the shared backend palette."""
    shared = {
        # Brand primitives never change meaning between themes. Components
        # consume semantic roles below instead of inverting this palette.
        "--bbva-midnight": BBVA_MIDNIGHT,
        "--bbva-electric": BBVA_ELECTRIC,
        "--bbva-royal-dark": BBVA_ROYAL_DARK,
        "--bbva-royal": BBVA_ROYAL,
        "--bbva-serene-dark": BBVA_SERENE_DARK,
        "--bbva-serene": BBVA_SERENE,
        "--bbva-blue-light": BBVA_BLUE_LIGHT,
        "--bbva-black": BBVA_BLACK,
        "--bbva-grey-900": BBVA_GREY_900,
        "--bbva-grey-800": BBVA_GREY_800,
        "--bbva-grey-700": BBVA_GREY_700,
        "--bbva-grey-600": BBVA_GREY_600,
        "--bbva-grey-500": BBVA_GREY_500,
        "--bbva-grey-400": BBVA_GREY_400,
        "--bbva-grey-300": BBVA_GREY_300,
        "--bbva-grey-200": BBVA_GREY_200,
        "--bbva-white": BBVA_WHITE,
        "--bbva-brand-midnight": BBVA_MIDNIGHT,
        "--bbva-brand-electric": BBVA_ELECTRIC,
        "--bbva-brand-on-hero": BBVA_WHITE,
        "--bbva-brand-on-hero-muted": BBVA_BLUE_LIGHT,
        "--bbva-radius-container": f"{BBVA_RADIUS_OUTER_PX}px",
        "--bbva-radius-component": f"{BBVA_RADIUS_INNER_PX}px",
        "--bbva-radius-xl": f"{BBVA_RADIUS_OUTER_PX}px",
        "--bbva-radius-lg": f"{BBVA_RADIUS_OUTER_PX}px",
        "--bbva-radius-md": f"{BBVA_RADIUS_INNER_PX}px",
        "--bbva-radius-sm": f"{BBVA_RADIUS_INNER_PX}px",
        "--bbva-grid-base": f"{BBVA_GRID_BASE_PX}px",
        "--bbva-grid-margin": f"{BBVA_GRID_MARGIN_PX}px",
        "--bbva-grid-gutter": f"{BBVA_GRID_GUTTER_PX}px",
        "--bbva-content-max": f"{BBVA_CONTENT_MAX_PX}px",
        "--bbva-status-intake": BBVA_SIGNAL_RED_3,
        "--bbva-status-progress": BBVA_SIGNAL_ORANGE_2,
        "--bbva-status-accepted": BBVA_SIGNAL_GREEN_3,
        "--bbva-status-deployed": BBVA_GOAL_ACCENT_7,
        "--bbva-status-open": BBVA_SIGNAL_YELLOW_1,
        "--bbva-priority-highest": BBVA_SIGNAL_RED_1,
        "--bbva-priority-high": BBVA_SIGNAL_RED_2,
        "--bbva-priority-medium": BBVA_SIGNAL_ORANGE_2,
        "--bbva-priority-low": BBVA_SIGNAL_GREEN_2,
        "--bbva-priority-lowest": BBVA_SIGNAL_GREEN_1,
        "--bbva-neutral": BBVA_NEUTRAL_SOFT,
        "--bbva-goal-accent": BBVA_GOAL_ACCENT_7,
        "--bbva-goal-surface": BBVA_GOAL_SURFACE_8,
    }
    return {
        "light": {
            **shared,
            "--bbva-primary": BBVA_LIGHT.electric_blue,
            "--bbva-primary-strong": BBVA_LIGHT.midnight,
            "--bbva-surface": BBVA_LIGHT.white,
            "--bbva-surface-2": BBVA_LIGHT.bg_light,
            "--bbva-surface-elevated": BBVA_LIGHT.white,
            "--bbva-border": BBVA_GREY_300,
            "--bbva-border-strong": BBVA_GREY_400,
            "--bbva-text": BBVA_LIGHT.midnight,
            "--bbva-text-muted": BBVA_GREY_600,
            "--bbva-on-primary": BBVA_LIGHT.white,
            "--bbva-success": BBVA_SIGNAL_GREEN_1,
            "--bbva-warning": BBVA_SIGNAL_ORANGE_1,
            "--bbva-danger": BBVA_SIGNAL_RED_1,
            "--bbva-accent-bg": BBVA_BLUE_LIGHT,
            "--bbva-action-bg": BBVA_WHITE,
            "--bbva-action-border": BBVA_GREY_400,
            "--bbva-tab-soft-text": BBVA_GREY_600,
            "--bbva-tab-active-bg": BBVA_ELECTRIC,
            "--bbva-tab-active-text": BBVA_LIGHT.white,
            "--bbva-tab-active-border": BBVA_ELECTRIC,
            "--bbva-inverse-surface": BBVA_MIDNIGHT,
            "--bbva-on-inverse": BBVA_WHITE,
            "--bbva-shadow": "0 8px 24px rgba(7,14,70,.10)",
            "--bbva-shadow-soft": "0 3px 12px rgba(7,14,70,.07)",
        },
        "dark": {
            **shared,
            "--bbva-primary": BBVA_SERENE,
            "--bbva-primary-strong": BBVA_BLUE_LIGHT,
            "--bbva-surface": BBVA_DARK.core_blue,
            "--bbva-surface-2": BBVA_DARK.bg_light,
            "--bbva-surface-elevated": BBVA_GREY_800,
            "--bbva-border": BBVA_GREY_700,
            "--bbva-border-strong": BBVA_GREY_600,
            "--bbva-text": BBVA_DARK.ink,
            "--bbva-text-muted": BBVA_GREY_400,
            "--bbva-on-primary": BBVA_MIDNIGHT,
            "--bbva-success": BBVA_DARK_GREEN,
            "--bbva-warning": BBVA_DARK_ORANGE,
            "--bbva-danger": BBVA_DARK_RED,
            "--bbva-accent-bg": BBVA_GREY_700,
            "--bbva-action-bg": BBVA_GREY_800,
            "--bbva-action-border": BBVA_GREY_600,
            "--bbva-tab-soft-text": BBVA_GREY_400,
            "--bbva-tab-active-bg": BBVA_SERENE,
            "--bbva-tab-active-text": BBVA_MIDNIGHT,
            "--bbva-tab-active-border": BBVA_SERENE,
            "--bbva-inverse-surface": BBVA_GREY_700,
            "--bbva-on-inverse": BBVA_WHITE,
            "--bbva-shadow": "0 8px 24px rgba(0,0,0,.32)",
            "--bbva-shadow-soft": "0 3px 12px rgba(0,0,0,.22)",
            "--bbva-status-intake": BBVA_DARK_RED,
            "--bbva-status-progress": BBVA_DARK_ORANGE,
            "--bbva-status-accepted": BBVA_DARK_GREEN,
            "--bbva-status-deployed": BBVA_DARK_PURPLE,
            "--bbva-status-open": BBVA_DARK_YELLOW,
            "--bbva-priority-highest": BBVA_DARK_RED,
            "--bbva-priority-high": BBVA_DARK_RED,
            "--bbva-priority-medium": BBVA_DARK_ORANGE,
            "--bbva-priority-low": BBVA_DARK_GREEN,
            "--bbva-priority-lowest": BBVA_DARK_GREEN,
            "--bbva-neutral": BBVA_GREY_600,
            "--bbva-goal-accent": BBVA_DARK_PURPLE,
            "--bbva-goal-surface": BBVA_GREY_700,
        },
    }
