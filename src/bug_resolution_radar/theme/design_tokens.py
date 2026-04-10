"""BBVA design tokens shared by UI and report layers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


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


BBVA_LIGHT = BbvPalette(
    midnight="#072146",
    core_blue="#004481",
    electric_blue="#0051F1",
    royal_blue="#0C6DFF",
    serene_dark_blue="#53A9EF",
    serene_blue="#85C8FF",
    aqua="#8BE1E9",
    white="#FFFFFF",
    bg_light="#F4F6F9",
    ink="#11192D",
    ink_muted="#5C6C84",
)

BBVA_DARK = BbvPalette(
    midnight="#072146",
    core_blue="#0A2E67",
    electric_blue="#53A9EF",
    royal_blue="#5BBEFF",
    serene_dark_blue="#53A9EF",
    serene_blue="#85C8FF",
    aqua="#8BE1E9",
    white="#FFFFFF",
    bg_light="#050B1A",
    ink="#EAF0FF",
    ink_muted="#C6D7EF",
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
BBVA_NEUTRAL_SOFT = "#E2E6EE"
BBVA_DARK_SURFACE = "#0A1F45"

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
    return {
        "light": {
            "--bbva-primary": BBVA_LIGHT.electric_blue,
            "--bbva-primary-strong": BBVA_LIGHT.core_blue,
            "--bbva-midnight": BBVA_LIGHT.midnight,
            "--bbva-surface": BBVA_LIGHT.white,
            "--bbva-surface-2": BBVA_LIGHT.bg_light,
            "--bbva-surface-elevated": hex_to_rgba(BBVA_LIGHT.white, 0.96),
            "--bbva-border": hex_to_rgba(BBVA_LIGHT.midnight, 0.12),
            "--bbva-border-strong": hex_to_rgba(BBVA_LIGHT.midnight, 0.18),
            "--bbva-text": BBVA_LIGHT.ink,
            "--bbva-text-muted": hex_to_rgba(BBVA_LIGHT.ink, 0.72),
            "--bbva-on-primary": BBVA_LIGHT.white,
            "--bbva-success": BBVA_SIGNAL_GREEN_1,
            "--bbva-warning": BBVA_SIGNAL_ORANGE_1,
            "--bbva-danger": BBVA_SIGNAL_RED_1,
            "--bbva-tab-active-bg": BBVA_LIGHT.core_blue,
            "--bbva-tab-active-text": BBVA_LIGHT.white,
            "--bbva-tab-active-border": BBVA_LIGHT.midnight,
        },
        "dark": {
            "--bbva-primary": BBVA_DARK.royal_blue,
            "--bbva-primary-strong": BBVA_DARK.serene_blue,
            "--bbva-midnight": BBVA_DARK.midnight,
            "--bbva-surface": BBVA_DARK.core_blue,
            "--bbva-surface-2": BBVA_DARK.bg_light,
            "--bbva-surface-elevated": hex_to_rgba(BBVA_DARK.core_blue, 0.96),
            "--bbva-border": hex_to_rgba(BBVA_DARK.white, 0.12),
            "--bbva-border-strong": hex_to_rgba(BBVA_DARK.white, 0.20),
            "--bbva-text": BBVA_DARK.ink,
            "--bbva-text-muted": hex_to_rgba(BBVA_DARK.ink, 0.76),
            "--bbva-on-primary": BBVA_DARK.white,
            "--bbva-success": BBVA_SIGNAL_GREEN_1,
            "--bbva-warning": BBVA_SIGNAL_ORANGE_1,
            "--bbva-danger": BBVA_SIGNAL_RED_1,
            "--bbva-tab-active-bg": BBVA_DARK.white,
            "--bbva-tab-active-text": BBVA_DARK.midnight,
            "--bbva-tab-active-border": BBVA_DARK.white,
        },
    }
