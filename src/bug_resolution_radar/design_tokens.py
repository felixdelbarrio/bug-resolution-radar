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
    '"Tiempos Headline", "TiemposText-Regular", "Tiempos Text", '
    '"Lato", "Arial", serif'
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
