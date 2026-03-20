"""Shared visual styling helpers for Streamlit and Plotly rendering."""

from __future__ import annotations

import base64
import html
import importlib.resources
from functools import lru_cache
from typing import Any

import streamlit as st

from bug_resolution_radar.theme.design_tokens import (
    BBVA_DARK,
    BBVA_DARK_SURFACE,
    BBVA_FONT_HEADLINE,
    BBVA_FONT_SANS,
    BBVA_FONT_SANS_BOOK,
    BBVA_FONT_SANS_MEDIUM,
    BBVA_LIGHT,
    BBVA_NEUTRAL_SOFT,
    BBVA_RADIUS_INNER_PX,
    BBVA_RADIUS_OUTER_PX,
    BBVA_SIGNAL_GREEN_2,
    BBVA_SIGNAL_ORANGE_1,
    BBVA_SIGNAL_ORANGE_2,
    BBVA_SIGNAL_RED_1,
    BBVA_SIGNAL_RED_2,
    BBVA_SIGNAL_RED_3,
    BBVA_SIGNAL_YELLOW_1,
    hex_to_rgba,
)
from bug_resolution_radar.ui.common import flow_signal_color_map, semantic_popover_css_rules


@lru_cache(maxsize=64)
def _svg_data_uri(*, file_name: str, fallback_svg: str) -> str:
    try:
        icon_ref = (
            importlib.resources.files("bug_resolution_radar.ui")
            / "assets"
            / "icons"
            / "bbva"
            / file_name
        )
        raw = icon_ref.read_bytes()
    except Exception:
        raw = fallback_svg.encode("utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")


def _font_data_uri(*, file_name: str, mime: str) -> str:
    try:
        font_ref = (
            importlib.resources.files("bug_resolution_radar.ui")
            / "assets"
            / "fonts"
            / "bbva"
            / file_name
        )
        raw = font_ref.read_bytes()
    except Exception:
        return ""
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


@lru_cache(maxsize=1)
def _font_face_css() -> str:
    specs = [
        ("BentonSansBBVA-Book", "BentonSansBBVA-Book.ttf", "font/ttf", "400", "normal"),
        ("Benton Sans BBVA Book", "BentonSansBBVA-Book.ttf", "font/ttf", "400", "normal"),
        ("BentonSansBBVA", "BentonSansBBVA-Book.ttf", "font/ttf", "400", "normal"),
        ("Benton Sans BBVA", "BentonSansBBVA-Book.ttf", "font/ttf", "400", "normal"),
        (
            "BentonSansBBVA-Medium",
            "BentonSansBBVA-Medium.ttf",
            "font/ttf",
            "500",
            "normal",
        ),
        (
            "Benton Sans BBVA Medium",
            "BentonSansBBVA-Medium.ttf",
            "font/ttf",
            "500",
            "normal",
        ),
        ("BentonSansBBVA-Bold", "BentonSansBBVA-Bold.ttf", "font/ttf", "700", "normal"),
        ("Benton Sans BBVA Bold", "BentonSansBBVA-Bold.ttf", "font/ttf", "700", "normal"),
        (
            "Tiempos Headline",
            "tiempos-headline-bold.woff2",
            "font/woff2",
            "700",
            "normal",
        ),
        (
            "Tiempos Headline Bold",
            "tiempos-headline-bold.woff2",
            "font/woff2",
            "700",
            "normal",
        ),
        (
            "TiemposText-Regular",
            "TiemposTextWeb-Regular.woff2",
            "font/woff2",
            "400",
            "normal",
        ),
        ("Tiempos Text", "TiemposTextWeb-Regular.woff2", "font/woff2", "400", "normal"),
    ]

    blocks: list[str] = []
    for family, file_name, mime, weight, style in specs:
        uri = _font_data_uri(file_name=file_name, mime=mime)
        if not uri:
            continue
        fmt = "woff2" if mime.endswith("woff2") else "truetype"
        blocks.append(
            f"""
            @font-face {{
              font-family: "{family}";
              src: url("{uri}") format("{fmt}");
              font-weight: {weight};
              font-style: {style};
              font-display: swap;
            }}
            """
        )
    return "\n".join(blocks)


@lru_cache(maxsize=2)
def _compiled_bbva_css(*, dark_mode: bool = False) -> str:
    """Compile global CSS tokens/components for light/dark runtime themes."""
    palette = BBVA_DARK if dark_mode else BBVA_LIGHT
    if dark_mode:
        surface_base = BBVA_DARK_SURFACE
        surface_soft = hex_to_rgba(palette.core_blue, 0.78, fallback=BBVA_LIGHT.core_blue)
        surface_elevated = hex_to_rgba(palette.core_blue, 0.90, fallback=BBVA_LIGHT.core_blue)
        border = hex_to_rgba(palette.ink, 0.26, fallback=BBVA_LIGHT.ink)
        border_strong = hex_to_rgba(palette.ink, 0.40, fallback=BBVA_LIGHT.ink)
        tab_soft_bg = palette.core_blue
        tab_soft_border = hex_to_rgba(palette.serene_blue, 0.44, fallback=BBVA_LIGHT.serene_blue)
        tab_soft_text = hex_to_rgba(palette.ink, 0.92, fallback=BBVA_LIGHT.ink)
        tab_nav_active_text = palette.serene_blue
        tab_active_bg = BBVA_LIGHT.core_blue
        tab_active_border = BBVA_LIGHT.serene_dark_blue
        tab_active_text = palette.white
        icon_filter = "brightness(0) invert(1)"
        action_link = palette.serene_blue
        action_link_hover = palette.aqua
        scrollbar_track = hex_to_rgba(palette.ink, 0.10, fallback=BBVA_LIGHT.ink)
        scrollbar_thumb = hex_to_rgba(palette.serene_blue, 0.44, fallback=BBVA_LIGHT.serene_blue)
        scrollbar_thumb_hover = hex_to_rgba(
            palette.serene_blue, 0.62, fallback=BBVA_LIGHT.serene_blue
        )
        issue_card_border = hex_to_rgba(palette.serene_blue, 0.42, fallback=BBVA_LIGHT.serene_blue)
        issue_card_border_hover = hex_to_rgba(
            palette.electric_blue, 0.68, fallback=BBVA_LIGHT.electric_blue
        )
        issue_card_bg_start = hex_to_rgba(BBVA_DARK_SURFACE, 0.96, fallback=BBVA_LIGHT.core_blue)
        issue_card_bg_end = hex_to_rgba(palette.midnight, 0.96, fallback=BBVA_LIGHT.midnight)
        issue_card_shadow = (
            f"0 10px 26px {hex_to_rgba(palette.midnight, 0.42, fallback=BBVA_LIGHT.midnight)}"
        )
        issue_card_shadow_hover = (
            f"0 12px 30px {hex_to_rgba(palette.midnight, 0.48, fallback=BBVA_LIGHT.midnight)}"
        )
        issue_card_inset = hex_to_rgba(palette.serene_blue, 0.15, fallback=BBVA_LIGHT.serene_blue)
        issue_card_inset_hover = hex_to_rgba(
            palette.serene_blue, 0.26, fallback=BBVA_LIGHT.serene_blue
        )
        # Next Best Action is an alert container: orange in dark mode for semantic separation from cards.
        nba_banner_bg = (
            "color-mix(in srgb, var(--bbva-signal-orange) 20%, var(--bbva-surface-elevated) 80%)"
        )
        nba_banner_border = (
            "color-mix(in srgb, var(--bbva-signal-orange) 70%, var(--bbva-border) 30%)"
        )
        nba_banner_shadow = "var(--bbva-shadow-strong)"
        nba_ink_primary = "var(--bbva-text)"
        nba_ink_muted = "color-mix(in srgb, var(--bbva-text) 78%, var(--bbva-midnight) 22%)"
        nba_accent_a = hex_to_rgba(BBVA_SIGNAL_ORANGE_2, 0.98, fallback=BBVA_SIGNAL_ORANGE_2)
        nba_accent_b = hex_to_rgba(BBVA_SIGNAL_ORANGE_1, 0.90, fallback=BBVA_SIGNAL_ORANGE_1)
        nba_kicker_border = hex_to_rgba(BBVA_SIGNAL_ORANGE_2, 0.74, fallback=BBVA_SIGNAL_ORANGE_2)
        nba_kicker_bg = hex_to_rgba(BBVA_SIGNAL_ORANGE_1, 0.24, fallback=BBVA_SIGNAL_ORANGE_1)
        nba_kicker_text = hex_to_rgba(BBVA_SIGNAL_ORANGE_2, 0.98, fallback=BBVA_SIGNAL_ORANGE_2)
    else:
        surface_base = palette.white
        surface_soft = hex_to_rgba(palette.white, 0.62, fallback=BBVA_LIGHT.white)
        surface_elevated = hex_to_rgba(palette.white, 0.82, fallback=BBVA_LIGHT.white)
        border = hex_to_rgba(palette.ink, 0.12, fallback=BBVA_LIGHT.ink)
        border_strong = hex_to_rgba(palette.ink, 0.20, fallback=BBVA_LIGHT.ink)
        tab_soft_bg = "color-mix(in srgb, var(--bbva-surface) 74%, var(--bbva-surface-2))"
        tab_soft_border = hex_to_rgba(palette.midnight, 0.22, fallback=BBVA_LIGHT.midnight)
        tab_soft_text = palette.ink_muted
        tab_nav_active_text = palette.electric_blue
        tab_active_bg = palette.core_blue
        tab_active_border = palette.serene_dark_blue
        tab_active_text = palette.white
        icon_filter = "brightness(0) invert(1)"
        action_link = palette.electric_blue
        action_link_hover = palette.core_blue
        scrollbar_track = hex_to_rgba(palette.ink, 0.08, fallback=BBVA_LIGHT.ink)
        scrollbar_thumb = hex_to_rgba(palette.midnight, 0.22, fallback=BBVA_LIGHT.midnight)
        scrollbar_thumb_hover = hex_to_rgba(palette.midnight, 0.34, fallback=BBVA_LIGHT.midnight)
        issue_card_border = hex_to_rgba(palette.ink, 0.16, fallback=BBVA_LIGHT.ink)
        issue_card_border_hover = hex_to_rgba(
            palette.electric_blue, 0.36, fallback=BBVA_LIGHT.electric_blue
        )
        issue_card_bg_start = hex_to_rgba(palette.white, 0.98, fallback=BBVA_LIGHT.white)
        issue_card_bg_end = hex_to_rgba(palette.bg_light, 0.98, fallback=BBVA_LIGHT.bg_light)
        issue_card_shadow = (
            f"0 8px 22px {hex_to_rgba(palette.midnight, 0.12, fallback=BBVA_LIGHT.midnight)}"
        )
        issue_card_shadow_hover = (
            f"0 10px 26px {hex_to_rgba(palette.midnight, 0.18, fallback=BBVA_LIGHT.midnight)}"
        )
        issue_card_inset = hex_to_rgba(
            palette.electric_blue, 0.08, fallback=BBVA_LIGHT.electric_blue
        )
        issue_card_inset_hover = hex_to_rgba(
            palette.electric_blue, 0.14, fallback=BBVA_LIGHT.electric_blue
        )
        # Next Best Action is an alert container: yellow in light mode for semantic separation from cards.
        nba_banner_bg = (
            "color-mix(in srgb, var(--bbva-signal-yellow) 22%, var(--bbva-surface-elevated) 78%)"
        )
        nba_banner_border = (
            "color-mix(in srgb, var(--bbva-signal-orange) 58%, var(--bbva-border) 42%)"
        )
        nba_banner_shadow = "var(--bbva-shadow-soft)"
        nba_ink_primary = "var(--bbva-text)"
        nba_ink_muted = "color-mix(in srgb, var(--bbva-text) 74%, transparent)"
        nba_accent_a = hex_to_rgba(BBVA_SIGNAL_YELLOW_1, 0.98, fallback=BBVA_SIGNAL_YELLOW_1)
        nba_accent_b = hex_to_rgba(BBVA_SIGNAL_ORANGE_2, 0.90, fallback=BBVA_SIGNAL_ORANGE_2)
        nba_kicker_border = hex_to_rgba(BBVA_SIGNAL_ORANGE_1, 0.76, fallback=BBVA_SIGNAL_ORANGE_1)
        nba_kicker_bg = hex_to_rgba(BBVA_SIGNAL_YELLOW_1, 0.24, fallback=BBVA_SIGNAL_YELLOW_1)
        nba_kicker_text = hex_to_rgba(BBVA_SIGNAL_ORANGE_1, 0.96, fallback=BBVA_SIGNAL_ORANGE_1)

    css_vars = f"""
      :root {{
        --bbva-primary: {palette.electric_blue};
        --bbva-midnight: {palette.midnight};
        --bbva-text: {palette.ink};
        --bbva-white: {BBVA_LIGHT.white};
        --bbva-text-muted: {hex_to_rgba(palette.ink, 0.74, fallback=BBVA_LIGHT.ink)};
        --bbva-surface: {surface_base};
        --bbva-surface-2: {palette.bg_light};
        --bbva-surface-soft: {surface_soft};
        --bbva-surface-elevated: {surface_elevated};
        --bbva-border: {border};
        --bbva-border-strong: {border_strong};
        --bbva-on-primary: {palette.white};
        --bbva-focus-border: {hex_to_rgba(palette.electric_blue, 0.65, fallback=BBVA_LIGHT.electric_blue)};
        --bbva-focus-ring: {hex_to_rgba(palette.electric_blue, 0.18, fallback=BBVA_LIGHT.electric_blue)};
        --bbva-accent-border-soft: {hex_to_rgba(palette.electric_blue, 0.35, fallback=BBVA_LIGHT.electric_blue)};
        --bbva-accent-border-subtle: {hex_to_rgba(palette.electric_blue, 0.20, fallback=BBVA_LIGHT.electric_blue)};
        --bbva-accent-bg-soft: {hex_to_rgba(palette.electric_blue, 0.10, fallback=BBVA_LIGHT.electric_blue)};
        --bbva-accent-bg-subtle: {hex_to_rgba(palette.electric_blue, 0.06, fallback=BBVA_LIGHT.electric_blue)};
        --bbva-status-neutral: {BBVA_NEUTRAL_SOFT};
        --bbva-signal-red-strong: {BBVA_SIGNAL_RED_1};
        --bbva-signal-red: {BBVA_SIGNAL_RED_2};
        --bbva-signal-red-soft: {BBVA_SIGNAL_RED_3};
        --bbva-signal-orange: {BBVA_SIGNAL_ORANGE_2};
        --bbva-signal-yellow: {BBVA_SIGNAL_YELLOW_1};
        --bbva-signal-green: {BBVA_SIGNAL_GREEN_2};
        --bbva-focus-tone-risk: var(--bbva-signal-red);
        --bbva-focus-tone-warning: color-mix(in srgb, var(--bbva-signal-orange) 82%, var(--bbva-midnight) 18%);
        --bbva-focus-tone-flow: color-mix(in srgb, var(--bbva-signal-green) 78%, var(--bbva-midnight) 22%);
        --bbva-focus-tone-quality: color-mix(in srgb, var(--bbva-primary) 84%, var(--bbva-midnight) 16%);
        --bbva-focus-tone-opportunity: var(--bbva-signal-green);
        --bbva-nba-banner-bg: {nba_banner_bg};
        --bbva-nba-banner-border: {nba_banner_border};
        --bbva-nba-banner-shadow: {nba_banner_shadow};
        --bbva-nba-ink-primary: {nba_ink_primary};
        --bbva-nba-ink-muted: {nba_ink_muted};
        --bbva-nba-accent-a: {nba_accent_a};
        --bbva-nba-accent-b: {nba_accent_b};
        --bbva-nba-kicker-border: {nba_kicker_border};
        --bbva-nba-kicker-bg: {nba_kicker_bg};
        --bbva-nba-kicker-text: {nba_kicker_text};
        --bbva-shadow-deep: {hex_to_rgba(palette.midnight, 0.48, fallback=BBVA_LIGHT.midnight)};
        --bbva-shadow-strong: {hex_to_rgba(palette.midnight, 0.42, fallback=BBVA_LIGHT.midnight)};
        --bbva-shadow-soft: {hex_to_rgba(palette.midnight, 0.22, fallback=BBVA_LIGHT.midnight)};
        --bbva-glow-soft: {hex_to_rgba(palette.serene_blue, 0.18, fallback=BBVA_LIGHT.serene_blue)};
        --bbva-radius-s: 4px;
        --bbva-radius-m: {BBVA_RADIUS_INNER_PX}px;
        --bbva-radius-l: {BBVA_RADIUS_INNER_PX}px;
        --bbva-radius-xl: {BBVA_RADIUS_OUTER_PX}px;
        --bbva-tab-soft-bg: {tab_soft_bg};
        --bbva-tab-soft-border: {tab_soft_border};
        --bbva-tab-soft-text: {tab_soft_text};
        --bbva-tab-nav-active: {tab_nav_active_text};
        --bbva-tab-active-bg: {tab_active_bg};
        --bbva-tab-active-border: {tab_active_border};
        --bbva-tab-active-text: {tab_active_text};
        --bbva-icon-filter: {icon_filter};
        --bbva-goal-green: {palette.serene_dark_blue};
        --bbva-goal-green-bg: {palette.serene_blue};
        --bbva-action-link: {action_link};
        --bbva-action-link-hover: {action_link_hover};
        --bbva-scrollbar-track: {scrollbar_track};
        --bbva-scrollbar-thumb: {scrollbar_thumb};
        --bbva-scrollbar-thumb-hover: {scrollbar_thumb_hover};
        --bbva-issue-card-border: {issue_card_border};
        --bbva-issue-card-border-hover: {issue_card_border_hover};
        --bbva-issue-card-bg-start: {issue_card_bg_start};
        --bbva-issue-card-bg-end: {issue_card_bg_end};
        --bbva-issue-card-shadow: {issue_card_shadow};
        --bbva-issue-card-shadow-hover: {issue_card_shadow_hover};
        --bbva-issue-card-inset: {issue_card_inset};
        --bbva-issue-card-inset-hover: {issue_card_inset_hover};
        --primary-color: var(--bbva-primary);
        --text-color: var(--bbva-text);
        --background-color: var(--bbva-surface-2);
        --secondary-background-color: var(--bbva-surface);
        --bbva-font-sans: {BBVA_FONT_SANS};
        --bbva-font-body: {BBVA_FONT_SANS_BOOK};
        --bbva-font-ui: {BBVA_FONT_SANS_MEDIUM};
        --bbva-font-headline: {BBVA_FONT_HEADLINE};
        --bbva-font-label: {BBVA_FONT_SANS_MEDIUM};
        --bbva-heading-gap: 0.88rem;
        --bbva-heading-gap-tight: 0.68rem;
        --bbva-section-gap: 0.34rem;
      }}
    """

    icon_report = _svg_data_uri(
        file_name="digital-press.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<rect x="3" y="4" width="18" height="14" rx="2" fill="currentColor"/>'
            '<rect x="7" y="19" width="10" height="2" rx="1" fill="currentColor"/>'
            "</svg>"
        ),
    )
    icon_report_period = _svg_data_uri(
        file_name="presentation.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<rect x="4" y="4" width="16" height="11" rx="2" fill="none" '
            'stroke="currentColor" stroke-width="2"/>'
            '<path d="M12 15v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            '<path d="M8 20h8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            "</svg>"
        ),
    )
    icon_ingest = _svg_data_uri(
        file_name="spherica-down-cloud.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path d="M7 17h10a4 4 0 0 0 0-8h-.3A5.5 5.5 0 0 0 6.4 10.6 3.5 3.5 0 0 0 7 17z" '
            'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="M12 11v5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            '<path d="M10 14l2 2 2-2" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round" fill="none"/>'
            "</svg>"
        ),
    )
    icon_search = _svg_data_uri(
        file_name="spherica-search.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/>'
            '<path d="M21 21l-5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            "</svg>"
        ),
    )
    icon_theme = _svg_data_uri(
        file_name="sun.svg" if dark_mode else "moon.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="5" fill="currentColor"/>'
            "</svg>"
        ),
    )
    icon_config = _svg_data_uri(
        file_name="spherica-simulator.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="3" fill="currentColor"/>'
            '<path d="M12 2l2 2 3-1 1 3 3 1-1 3 2 2-2 2 1 3-3 1-1 3-3-1-2 2-2-2-3 1-1-3-3-1 1-3-2-2 2-2-1-3 3-1 1-3 3 1z" fill="currentColor"/>'
            "</svg>"
        ),
    )
    icon_save = _svg_data_uri(
        file_name="spherica-checkmark.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path d="M6 12l4 4 8-8" fill="none" stroke="currentColor" stroke-width="2.4" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            "</svg>"
        ),
    )
    icon_no_draw = _svg_data_uri(
        file_name="spherica-no-draw.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/>'
            '<path d="M8 8l8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            "</svg>"
        ),
    )
    icon_reingest = _svg_data_uri(
        file_name="spherica-save-for-later.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path d="M12 4v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            '<path d="M8 10l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/>'
            '<path d="M5 19h14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>'
            "</svg>"
        ),
    )
    icon_recycle = _svg_data_uri(
        file_name="spherica-recycle.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path d="M8 6h6l-2-2" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/>'
            '<path d="M16 10l2 3-2 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/>'
            '<path d="M6 14l-2-3 2-3" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/>'
            "</svg>"
        ),
    )
    icon_xml = _svg_data_uri(
        file_name="spherica-xml.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<path d="M7 8l-3 4 3 4" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>'
            '<path d="M17 8l3 4-3 4" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>'
            '<path d="M13 6l-2 12" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>'
            "</svg>"
        ),
    )

    css_template = """
        <style>
          __FONT_FACE_CSS__

          __CSS_VARS__

          html, body, [class*="stApp"] {
            color: var(--bbva-text);
            font-family: var(--bbva-font-body);
            font-size: 16px;
            line-height: 1.5;
          }

          /* Scrollbars (avoid bright default thumb in dark mode) */
          * {
            scrollbar-width: thin;
            scrollbar-color: var(--bbva-scrollbar-thumb) var(--bbva-scrollbar-track);
          }
          ::-webkit-scrollbar {
            width: 12px;
            height: 12px;
          }
          ::-webkit-scrollbar-track {
            background: var(--bbva-scrollbar-track);
          }
          ::-webkit-scrollbar-thumb {
            background-color: var(--bbva-scrollbar-thumb);
            border-radius: 999px;
            border: 3px solid var(--bbva-scrollbar-track);
          }
          ::-webkit-scrollbar-thumb:hover {
            background-color: var(--bbva-scrollbar-thumb-hover);
          }

          /* Typographic hierarchy */
          h1, [data-testid="stMarkdownContainer"] h1 {
            font-family: var(--bbva-font-headline) !important;
            font-weight: 700 !important;
            font-size: 2.05rem !important;
            line-height: 1.12 !important;
            letter-spacing: -0.01em;
            margin-top: 0.16rem !important;
            margin-bottom: var(--bbva-heading-gap) !important;
          }
          h2, h3, h4,
          [data-testid="stMarkdownContainer"] h2,
          [data-testid="stMarkdownContainer"] h3,
          [data-testid="stMarkdownContainer"] h4 {
            font-family: var(--bbva-font-ui) !important;
            font-weight: 700 !important;
            letter-spacing: -0.005em;
            margin-top: 0.12rem !important;
            margin-bottom: var(--bbva-heading-gap-tight) !important;
          }
          h2, [data-testid="stMarkdownContainer"] h2 {
            font-size: 1.48rem !important;
            line-height: 1.2 !important;
          }
          h3, [data-testid="stMarkdownContainer"] h3 {
            font-size: 1.24rem !important;
            line-height: 1.24 !important;
          }
          h4, [data-testid="stMarkdownContainer"] h4 {
            font-size: 1.08rem !important;
            line-height: 1.3 !important;
          }
          p, li, small,
          [data-testid="stMarkdownContainer"] p,
          [data-testid="stMarkdownContainer"] li,
          [data-testid="stCaptionContainer"] * {
            font-family: var(--bbva-font-body) !important;
            font-weight: 400 !important;
            font-size: 1rem;
          }
          button, input, select, textarea,
          [data-testid="stWidgetLabel"] p,
          label {
            font-family: var(--bbva-font-ui) !important;
          }

          .bbva-hero-title {
            font-family: var(--bbva-font-headline);
            letter-spacing: -0.01em;
          }

          /* App background + content width */
          [data-testid="stAppViewContainer"] {
            background: var(--bbva-surface-2);
          }
          [data-testid="stAppViewContainer"] > .main {
            background: transparent;
          }
          [data-testid="stAppViewContainer"] .block-container {
            padding-top: 20px;
            padding-bottom: 28px;
            padding-left: 24px;
            padding-right: 24px;
            max-width: 1280px;
          }

          /* Hero band */
          .bbva-hero {
            background: var(--bbva-midnight);
            border-radius: var(--bbva-radius-xl);
            padding: 14px 18px;
            margin: 4px 0 8px 0;
            color: var(--bbva-on-primary);
            border: 1px solid color-mix(in srgb, var(--bbva-on-primary) 8%, transparent);
          }
          .bbva-hero-title {
            margin: 0;
            font-size: 34px;
            line-height: 1.02;
            font-weight: 700;
            color: var(--bbva-on-primary);
          }
          .bbva-hero-sub {
            margin-top: 4px;
            opacity: 0.75;
            font-size: 12px;
          }

          /* Hide Streamlit chrome (deploy/status/toolbar) to keep a clean branded shell */
          header[data-testid="stHeader"],
          [data-testid="stToolbar"],
          [data-testid="stStatusWidget"],
          [data-testid="stDecoration"],
          [data-testid="stAppDeployButton"],
          [data-testid="stDeployButton"],
          button[title="Deploy"],
          button[aria-label="Deploy"],
          #MainMenu,
          footer {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
          }

          /* Top nav compact spacing */
          .st-key-workspace_scope_bar {
            margin-top: -0.02rem;
            margin-bottom: -0.12rem;
          }
          .st-key-workspace_scope_bar [data-testid="stHorizontalBlock"] {
            align-items: end !important;
          }
          .st-key-workspace_scope_bar [data-testid="stWidgetLabel"] p {
            font-size: 0.84rem !important;
            margin-bottom: 0.12rem !important;
          }
          .st-key-workspace_scope_bar [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            min-height: 2.1rem !important;
          }
          /* Segmented-control legacy styles removed intentionally:
             level-1 navigation now uses scoped button-tabs in workspace_nav_tabs. */
          /* Level-1 nav shell */
          .st-key-workspace_nav_bar,
          [class*="st-key-workspace_nav_bar_"] {
            margin-top: -0.04rem;
            margin-bottom: 0.04rem;
            border: 1px solid var(--bbva-border-strong);
            border-radius: 14px;
            background: var(--bbva-surface-elevated);
            padding: 0.22rem 0.38rem 0.16rem 0.38rem;
            box-shadow: 0 8px 22px color-mix(in srgb, var(--bbva-text) 16%, transparent);
          }
          .st-key-workspace_nav_bar div[data-testid="stHorizontalBlock"],
          [class*="st-key-workspace_nav_bar_"] div[data-testid="stHorizontalBlock"] {
            margin-bottom: 0 !important;
            row-gap: 0 !important;
            align-items: center !important;
          }

          /* Level-1 nav tabs (Resumen/Issues/Kanban/...) */
          .st-key-workspace_nav_tabs div[data-testid="stHorizontalBlock"] {
            align-items: center !important;
            gap: 0.30rem !important;
          }
          /* Top-right workspace actions (Informe, Ingesta, Tema, Configuración) */
          .st-key-workspace_nav_actions div[data-testid="stHorizontalBlock"] {
            justify-content: flex-end !important;
            align-items: center !important;
          }
          .st-key-workspace_dashboard_content_overview,
          .st-key-workspace_dashboard_content_notes {
            margin-top: 0.14rem;
          }
          .st-key-workspace_dashboard_content_issues,
          .st-key-workspace_dashboard_content_kanban,
          .st-key-workspace_dashboard_content_trends,
          .st-key-workspace_dashboard_content_insights {
            margin-top: -0.06rem;
          }
          .st-key-dashboard_filters_panel {
            margin-top: -0.12rem;
            margin-bottom: -0.04rem;
          }
          .st-key-insights_shell {
            margin-top: -0.10rem;
          }
          .st-key-issues_tab_issues_shell,
          .st-key-kanban_shell,
          .st-key-trend_chart_shell {
            margin-top: 0.12rem;
          }
          .st-key-dashboard_filters_panel [data-testid="stVerticalBlockBorderWrapper"],
          .st-key-issues_tab_issues_shell [data-testid="stVerticalBlockBorderWrapper"],
          .st-key-kanban_shell [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--bbva-border-strong) !important;
            background: var(--bbva-surface-elevated) !important;
            box-shadow: 0 10px 28px color-mix(in srgb, var(--bbva-text) 12%, transparent) !important;
          }
          .st-key-overview_summary_shell [data-testid="stVerticalBlockBorderWrapper"],
          .st-key-trend_chart_shell [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 92%, var(--bbva-glow-soft) 8%) !important;
            background: color-mix(in srgb, var(--bbva-surface-elevated) 90%, var(--bbva-midnight) 10%) !important;
            box-shadow: 0 12px 28px color-mix(in srgb, var(--bbva-shadow-deep) 100%, transparent),
                        inset 0 0 0 1px color-mix(in srgb, var(--bbva-glow-soft) 18%, transparent) !important;
          }
          [class*="st-key-overview_summary_chart_"] [data-testid="stVerticalBlockBorderWrapper"],
          [class*="st-key-trins_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 88%, var(--bbva-glow-soft) 12%) !important;
            background: color-mix(in srgb, var(--bbva-surface) 80%, var(--bbva-midnight) 20%) !important;
            box-shadow: 0 8px 22px color-mix(in srgb, var(--bbva-shadow-deep) 88%, transparent),
                        inset 0 0 0 1px color-mix(in srgb, var(--bbva-glow-soft) 16%, transparent) !important;
          }

          /* Sidebar */
          section[data-testid="stSidebar"] {
            background: var(--bbva-surface);
            border-right: 1px solid var(--bbva-border);
          }
          section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] * {
            font-size: 14px;
          }

          /* Widget corners */
          .stButton > button,
          .stDownloadButton > button,
          .stTextInput input,
          .stTextArea textarea,
          .stSelectbox [data-baseweb="select"] > div,
          .stMultiSelect [data-baseweb="select"] > div {
            border-radius: var(--bbva-radius-m) !important;
          }

          /* Labels */
          label, [data-testid="stWidgetLabel"] p {
            color: var(--bbva-text-muted) !important;
            font-weight: 600 !important;
          }

          /* Inputs */
          .stTextInput input,
          .stTextArea textarea,
          .stNumberInput input,
          .stSelectbox [data-baseweb="select"] > div,
          .stMultiSelect [data-baseweb="select"] > div,
          div[data-baseweb="select"] > div {
            background: var(--bbva-surface) !important;
            color: var(--bbva-text) !important;
            border: 1px solid var(--bbva-border) !important;
          }
          .stSelectbox [data-baseweb="select"] input,
          .stMultiSelect [data-baseweb="select"] input,
          div[data-baseweb="select"] input {
            color: var(--bbva-text) !important;
            -webkit-text-fill-color: var(--bbva-text) !important;
          }
          .stSelectbox [data-baseweb="select"] [aria-placeholder="true"],
          .stMultiSelect [data-baseweb="select"] [aria-placeholder="true"],
          div[data-baseweb="select"] [aria-placeholder="true"],
          .stSelectbox [data-baseweb="select"] [class*="placeholder"],
          .stMultiSelect [data-baseweb="select"] [class*="placeholder"],
          div[data-baseweb="select"] [class*="placeholder"] {
            color: color-mix(in srgb, var(--bbva-text) 76%, transparent) !important;
            -webkit-text-fill-color: color-mix(in srgb, var(--bbva-text) 76%, transparent) !important;
            opacity: 1 !important;
          }
          .stSelectbox [data-baseweb="select"] input::placeholder,
          .stMultiSelect [data-baseweb="select"] input::placeholder,
          div[data-baseweb="select"] input::placeholder {
            color: color-mix(in srgb, var(--bbva-text) 76%, transparent) !important;
            -webkit-text-fill-color: color-mix(in srgb, var(--bbva-text) 76%, transparent) !important;
            opacity: 1 !important;
          }
          .stSelectbox [data-baseweb="select"] svg,
          .stMultiSelect [data-baseweb="select"] svg,
          div[data-baseweb="select"] svg {
            color: var(--bbva-text-muted) !important;
            fill: var(--bbva-text-muted) !important;
          }
          div[data-baseweb="popover"] {
            max-height: min(21rem, 62vh) !important;
          }
          div[data-baseweb="popover"] [role="listbox"],
          div[data-baseweb="popover"] [role="menu"],
          div[data-baseweb="popover"] ul {
            background: var(--bbva-surface) !important;
            border: 1px solid var(--bbva-border) !important;
            color: var(--bbva-text) !important;
            list-style: none !important;
            margin: 0 !important;
            padding: 0.24rem 0 !important;
            padding-inline-start: 0 !important;
            gap: 0 !important;
            row-gap: 0 !important;
            column-gap: 0 !important;
            max-height: min(19.25rem, 56vh) !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            overscroll-behavior: contain !important;
          }
          /* Keep wrapper selectors present but avoid overriding virtualization heights. */
          div[data-baseweb="popover"] [role="listbox"] > *,
          div[data-baseweb="popover"] [role="menu"] > *,
          div[data-baseweb="popover"] ul > li,
          div[data-baseweb="popover"] ul > * {
            margin: 0 !important;
            padding: 0 !important;
            min-height: 0 !important;
            box-sizing: border-box !important;
          }
          /* Extra virtualized wrapper level used by BaseWeb in some Streamlit versions. */
          div[data-baseweb="popover"] [role="listbox"] > div > *,
          div[data-baseweb="popover"] [role="menu"] > div > * {
            margin: 0 !important;
            padding: 0 !important;
            min-height: 0 !important;
            box-sizing: border-box !important;
          }
          div[data-baseweb="popover"] ul > li {
            height: auto !important;
          }
          div[data-baseweb="popover"] li {
            list-style: none !important;
            margin: 0 !important;
            padding: 0 !important;
          }
          div[data-baseweb="popover"] li::marker {
            content: "" !important;
          }
          div[data-baseweb="popover"] [role="option"],
          div[data-baseweb="popover"] li[role="option"] {
            color: var(--bbva-text) !important;
            background: transparent !important;
            margin: 0 !important;
            min-height: 1.92rem !important;
            height: 1.92rem !important;
            max-height: 1.92rem !important;
            line-height: 1.18 !important;
            padding: 0.34rem 0.72rem !important;
            box-sizing: border-box !important;
            display: flex !important;
            align-items: center !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            --bbva-opt-dot: transparent;
          }
          div[data-baseweb="popover"] [role="option"] > div,
          div[data-baseweb="popover"] li[role="option"] > div {
            margin: 0 !important;
            padding: 0 !important;
            min-height: 0 !important;
            box-sizing: border-box !important;
            width: 100% !important;
            display: flex !important;
            align-items: center !important;
            gap: 0 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
          }
          __SEMANTIC_POPOVER_RULES__
          div[data-baseweb="popover"] [role="option"][data-bbva-semantic="1"],
          div[data-baseweb="popover"] li[role="option"][data-bbva-semantic="1"] {
            padding-left: 1.62rem !important;
            background-image: radial-gradient(
              circle at 0.80rem center,
              var(--bbva-opt-dot) 0.24rem,
              transparent 0.25rem
            ) !important;
            background-position: 0.80rem 50% !important;
            background-size: 0.50rem 0.50rem !important;
            background-repeat: no-repeat !important;
          }
          div[data-baseweb="popover"] [role="option"] > *,
          div[data-baseweb="popover"] li[role="option"] > * {
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            line-height: inherit !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
          }
          div[data-baseweb="popover"] [role="option"] span,
          div[data-baseweb="popover"] li[role="option"] span {
            margin: 0 !important;
            padding: 0 !important;
            line-height: 1.18 !important;
          }
          div[data-baseweb="popover"] [role="option"] p,
          div[data-baseweb="popover"] li[role="option"] p,
          div[data-baseweb="popover"] [role="option"] [data-testid="stMarkdownContainer"] p,
          div[data-baseweb="popover"] li[role="option"] [data-testid="stMarkdownContainer"] p {
            margin: 0 !important;
            padding: 0 !important;
            display: inline !important;
            line-height: 1.18 !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
          }
          div[data-baseweb="popover"] [role="option"]:hover,
          div[data-baseweb="popover"] li[role="option"]:hover {
            background-color: color-mix(in srgb, var(--bbva-primary) 14%, transparent) !important;
          }
          div[data-baseweb="popover"] [role="option"][aria-selected="true"] {
            background-color: color-mix(in srgb, var(--bbva-primary) 20%, transparent) !important;
            color: var(--bbva-text) !important;
          }
          .stTextInput input::placeholder,
          .stTextArea textarea::placeholder {
            color: color-mix(in srgb, var(--bbva-text) 45%, transparent) !important;
          }
          .stTextInput input:focus,
          .stTextArea textarea:focus,
          .stNumberInput input:focus {
            border-color: var(--bbva-focus-border) !important;
            box-shadow: 0 0 0 3px var(--bbva-focus-ring) !important;
            outline: none !important;
          }

          .stButton > button[kind="primary"] {
            background: var(--bbva-primary) !important;
            border-color: var(--bbva-primary) !important;
            color: var(--bbva-on-primary) !important;
            font-weight: 700 !important;
          }

          .stButton > button[kind="secondary"] {
            background: var(--bbva-surface) !important;
            border-color: var(--bbva-border-strong) !important;
            color: color-mix(in srgb, var(--bbva-text) 88%, transparent) !important;
            font-weight: 700 !important;
          }
          .stButton > button[kind="secondary"]:hover {
            border-color: var(--bbva-accent-border-soft) !important;
            background: color-mix(in srgb, var(--bbva-primary) 12%, transparent) !important;
          }
          .stButton > button:disabled {
            opacity: 0.45 !important;
            cursor: not-allowed !important;
          }

          /* Workspace nav: keep tab/action styling aligned with theme after global button rules */
          .st-key-workspace_nav_tabs .stButton > button,
          .st-key-workspace_nav_tabs [data-testid^="baseButton-"] {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            border-bottom: 2px solid transparent !important;
            border-radius: 0 !important;
            color: var(--bbva-tab-soft-text) !important;
            font-family: var(--bbva-font-label) !important;
            font-weight: 760 !important;
            letter-spacing: 0.01em !important;
            min-height: 2.02rem !important;
          }
          .st-key-workspace_nav_tabs .stButton > button[kind="primary"],
          .st-key-workspace_nav_tabs [data-testid="baseButton-primary"],
          .st-key-workspace_nav_tabs [data-testid="baseButton-primary"] > button {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            border-bottom: 2px solid var(--bbva-primary) !important;
            color: var(--bbva-tab-nav-active) !important;
          }
          .st-key-workspace_nav_tabs .stButton > button[kind="secondary"],
          .st-key-workspace_nav_tabs [data-testid="baseButton-secondary"],
          .st-key-workspace_nav_tabs [data-testid="baseButton-secondary"] > button {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            border-bottom: 2px solid transparent !important;
            color: var(--bbva-tab-soft-text) !important;
          }
          .st-key-workspace_nav_tabs .stButton > button:hover,
          .st-key-workspace_nav_tabs [data-testid^="baseButton-"]:hover,
          .st-key-workspace_nav_tabs [data-testid^="baseButton-"] > button:hover {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            border-bottom: 2px solid transparent !important;
            color: color-mix(in srgb, var(--bbva-primary) 82%, var(--bbva-tab-soft-text)) !important;
          }

          .st-key-workspace_nav_actions button,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"],
          .st-key-workspace_nav_actions [data-testid^="baseButton-"] > button {
            min-height: 2.02rem !important;
            min-width: 2.02rem !important;
            padding: 0.16rem !important;
            border-radius: 10px !important;
            font-size: 1.00rem !important;
            font-weight: 760 !important;
            border: 1px solid var(--bbva-tab-soft-border) !important;
            background: var(--bbva-tab-soft-bg) !important;
            background-color: var(--bbva-tab-soft-bg) !important;
            color: var(--bbva-tab-soft-text) !important;
            box-shadow: none !important;
            transition: background-color 120ms ease, border-color 120ms ease, color 120ms ease !important;
          }
          .st-key-workspace_nav_actions button[kind="primary"],
          .st-key-workspace_nav_actions [data-testid="baseButton-primary"],
          .st-key-workspace_nav_actions [data-testid="baseButton-primary"] > button {
            border-color: var(--bbva-tab-active-border) !important;
            background: var(--bbva-tab-active-bg) !important;
            background-color: var(--bbva-tab-active-bg) !important;
            color: var(--bbva-tab-active-text) !important;
          }
          .st-key-workspace_nav_actions button[kind="secondary"],
          .st-key-workspace_nav_actions [data-testid="baseButton-secondary"],
          .st-key-workspace_nav_actions [data-testid="baseButton-secondary"] > button {
            border-color: var(--bbva-tab-soft-border) !important;
            background: var(--bbva-tab-soft-bg) !important;
            background-color: var(--bbva-tab-soft-bg) !important;
            color: var(--bbva-tab-soft-text) !important;
          }
          .st-key-workspace_nav_actions button:hover,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"]:hover,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"] > button:hover {
            border-color: color-mix(in srgb, var(--bbva-primary) 42%, var(--bbva-tab-soft-border)) !important;
            background: color-mix(in srgb, var(--bbva-primary) 14%, var(--bbva-tab-soft-bg)) !important;
            background-color: color-mix(in srgb, var(--bbva-primary) 14%, var(--bbva-tab-soft-bg)) !important;
          }
          .st-key-workspace_nav_actions button:focus,
          .st-key-workspace_nav_actions button:focus-visible,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"]:focus,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"]:focus-visible,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"] > button:focus,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"] > button:focus-visible {
            outline: none !important;
            box-shadow: none !important;
          }
          .st-key-workspace_nav_actions button:active,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"]:active,
          .st-key-workspace_nav_actions [data-testid^="baseButton-"] > button:active {
            transform: none !important;
          }
          .st-key-workspace_nav_actions button[kind="secondary"]:focus,
          .st-key-workspace_nav_actions button[kind="secondary"]:active,
          .st-key-workspace_nav_actions [data-testid="baseButton-secondary"]:focus,
          .st-key-workspace_nav_actions [data-testid="baseButton-secondary"]:active,
          .st-key-workspace_nav_actions [data-testid="baseButton-secondary"] > button:focus,
          .st-key-workspace_nav_actions [data-testid="baseButton-secondary"] > button:active {
            border-color: var(--bbva-tab-soft-border) !important;
            background: var(--bbva-tab-soft-bg) !important;
            background-color: var(--bbva-tab-soft-bg) !important;
            color: var(--bbva-tab-soft-text) !important;
          }
          .st-key-workspace_nav_actions button[kind="primary"]:focus,
          .st-key-workspace_nav_actions button[kind="primary"]:active,
          .st-key-workspace_nav_actions [data-testid="baseButton-primary"]:focus,
          .st-key-workspace_nav_actions [data-testid="baseButton-primary"]:active,
          .st-key-workspace_nav_actions [data-testid="baseButton-primary"] > button:focus,
          .st-key-workspace_nav_actions [data-testid="baseButton-primary"] > button:active {
            border-color: var(--bbva-tab-active-border) !important;
            background: var(--bbva-tab-active-bg) !important;
            background-color: var(--bbva-tab-active-bg) !important;
            color: var(--bbva-tab-active-text) !important;
          }
          /* Keep top-right actions icon-only (avoid label text bleed/overlap). */
          .st-key-workspace_btn_slot_report button,
          .st-key-workspace_btn_slot_report_exec button,
          .st-key-workspace_btn_slot_report_period button,
          .st-key-workspace_btn_slot_ingest button,
          .st-key-workspace_btn_slot_theme button,
          .st-key-workspace_btn_slot_config button,
          .st-key-workspace_btn_report button,
          .st-key-workspace_btn_report_exec button,
          .st-key-workspace_btn_report_period button,
          .st-key-workspace_btn_ingest button,
          .st-key-workspace_btn_theme button,
          .st-key-workspace_btn_config button {
            font-size: 0 !important;
            line-height: 0 !important;
            letter-spacing: 0 !important;
            text-indent: 0 !important;
            overflow: hidden !important;
            position: relative !important;
            color: inherit !important;
          }
          .st-key-workspace_btn_slot_report button > *,
          .st-key-workspace_btn_slot_report_exec button > *,
          .st-key-workspace_btn_slot_report_period button > *,
          .st-key-workspace_btn_slot_ingest button > *,
          .st-key-workspace_btn_slot_theme button > *,
          .st-key-workspace_btn_slot_config button > *,
          .st-key-workspace_btn_report button > *,
          .st-key-workspace_btn_report_exec button > *,
          .st-key-workspace_btn_report_period button > *,
          .st-key-workspace_btn_ingest button > *,
          .st-key-workspace_btn_theme button > *,
          .st-key-workspace_btn_config button > * {
            opacity: 0 !important;
          }
          .st-key-workspace_btn_slot_report button::before,
          .st-key-workspace_btn_slot_report_exec button::before,
          .st-key-workspace_btn_slot_report_period button::before,
          .st-key-workspace_btn_slot_ingest button::before,
          .st-key-workspace_btn_slot_theme button::before,
          .st-key-workspace_btn_slot_config button::before,
          .st-key-workspace_btn_report button::before,
          .st-key-workspace_btn_report_exec button::before,
          .st-key-workspace_btn_report_period button::before,
          .st-key-workspace_btn_ingest button::before,
          .st-key-workspace_btn_theme button::before,
          .st-key-workspace_btn_config button::before {
            content: "" !important;
            display: block !important;
            width: 1.06rem !important;
            height: 1.06rem !important;
            background-color: currentColor !important;
            -webkit-mask-image: var(--bbva-btn-icon) !important;
            mask-image: var(--bbva-btn-icon) !important;
            -webkit-mask-repeat: no-repeat !important;
            mask-repeat: no-repeat !important;
            -webkit-mask-position: center !important;
            mask-position: center !important;
            -webkit-mask-size: contain !important;
            mask-size: contain !important;
            position: absolute !important;
            left: 50% !important;
            top: 50% !important;
            transform: translate(-50%, -50%) !important;
            text-indent: 0 !important;
            opacity: 1 !important;
          }
          .st-key-workspace_btn_slot_report button,
          .st-key-workspace_btn_slot_report_exec button,
          .st-key-workspace_btn_report button,
          .st-key-workspace_btn_report_exec button { --bbva-btn-icon: url("__ICON_REPORT__"); }
          .st-key-workspace_btn_slot_report_period button,
          .st-key-workspace_btn_report_period button {
            --bbva-btn-icon: url("__ICON_REPORT_PERIOD__");
          }
          .st-key-workspace_btn_slot_ingest button,
          .st-key-workspace_btn_ingest button { --bbva-btn-icon: url("__ICON_INGEST__"); }
          .st-key-workspace_btn_slot_theme button,
          .st-key-workspace_btn_theme button { --bbva-btn-icon: url("__ICON_THEME__"); }
          .st-key-workspace_btn_slot_config button,
          .st-key-workspace_btn_config button { --bbva-btn-icon: url("__ICON_CONFIG__"); }

          /* Save buttons: consistent checkmark icon (replaces legacy diskette emoji). */
          .st-key-cfg_save_jira_btn button,
          .st-key-cfg_save_helix_btn button,
          .st-key-cfg_save_prefs_btn button,
          .st-key-notes_save_btn button,
          [class*="st-key-btn_save_scope_ppt"] button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.4rem !important;
          }
          .st-key-cfg_save_jira_btn button::before,
          .st-key-cfg_save_helix_btn button::before,
          .st-key-cfg_save_prefs_btn button::before,
          .st-key-notes_save_btn button::before,
          [class*="st-key-btn_save_scope_ppt"] button::before {
            content: "" !important;
            display: inline-block !important;
            width: 0.98rem !important;
            height: 0.98rem !important;
            background-color: currentColor !important;
            -webkit-mask-image: url("__ICON_SAVE__") !important;
            mask-image: url("__ICON_SAVE__") !important;
            -webkit-mask-repeat: no-repeat !important;
            mask-repeat: no-repeat !important;
            -webkit-mask-position: center !important;
            mask-position: center !important;
            -webkit-mask-size: contain !important;
            mask-size: contain !important;
            flex: 0 0 0.98rem !important;
          }

          /* Reingest buttons: save-for-later icon (replaces legacy download emoji). */
          .st-key-btn_run_jira_all button,
          .st-key-btn_run_helix_all button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.4rem !important;
          }
          .st-key-btn_run_jira_all button::before,
          .st-key-btn_run_helix_all button::before {
            content: "" !important;
            display: inline-block !important;
            width: 0.98rem !important;
            height: 0.98rem !important;
            background-color: currentColor !important;
            -webkit-mask-image: url("__ICON_REINGEST__") !important;
            mask-image: url("__ICON_REINGEST__") !important;
            -webkit-mask-repeat: no-repeat !important;
            mask-repeat: no-repeat !important;
            -webkit-mask-position: center !important;
            mask-position: center !important;
            -webkit-mask-size: contain !important;
            mask-size: contain !important;
            flex: 0 0 0.98rem !important;
          }

          /* Ingest test buttons: search icon (replaces legacy magnifier emoji). */
          .st-key-btn_test_jira_all button,
          .st-key-btn_test_helix_all button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.4rem !important;
          }
          .st-key-btn_test_jira_all button::before,
          .st-key-btn_test_helix_all button::before {
            content: "" !important;
            display: inline-block !important;
            width: 0.98rem !important;
            height: 0.98rem !important;
            background-color: currentColor !important;
            -webkit-mask-image: url("__ICON_SEARCH__") !important;
            mask-image: url("__ICON_SEARCH__") !important;
            -webkit-mask-repeat: no-repeat !important;
            mask-repeat: no-repeat !important;
            -webkit-mask-position: center !important;
            mask-position: center !important;
            -webkit-mask-size: contain !important;
            mask-size: contain !important;
            flex: 0 0 0.98rem !important;
          }

          /* Cache reset button: recycle icon (replaces legacy recycle emoji). */
          .st-key-cfg_cache_reset_btn button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.4rem !important;
          }
          .st-key-cfg_cache_reset_btn button::before {
            content: "" !important;
            display: inline-block !important;
            width: 0.98rem !important;
            height: 0.98rem !important;
            background-color: currentColor !important;
            -webkit-mask-image: url("__ICON_RECYCLE__") !important;
            mask-image: url("__ICON_RECYCLE__") !important;
            -webkit-mask-repeat: no-repeat !important;
            mask-repeat: no-repeat !important;
            -webkit-mask-position: center !important;
            mask-position: center !important;
            -webkit-mask-size: contain !important;
            mask-size: contain !important;
            flex: 0 0 0.98rem !important;
          }

          /* Cache reset title: recycle icon. */
          .bbva-icon-recycle-title {
            display: flex !important;
            align-items: center !important;
            gap: 0.42rem !important;
            margin: 0.2rem 0 0.48rem !important;
            font-family: var(--bbva-font-ui) !important;
            font-size: 1.06rem !important;
            font-weight: 700 !important;
            line-height: 1.25 !important;
            color: var(--bbva-text) !important;
          }
          .bbva-icon-recycle-title::before {
            content: "" !important;
            display: inline-block !important;
            width: 1rem !important;
            height: 1rem !important;
            background-color: currentColor !important;
            -webkit-mask-image: url("__ICON_RECYCLE__") !important;
            mask-image: url("__ICON_RECYCLE__") !important;
            -webkit-mask-repeat: no-repeat !important;
            mask-repeat: no-repeat !important;
            -webkit-mask-position: center !important;
            mask-position: center !important;
            -webkit-mask-size: contain !important;
            mask-size: contain !important;
            flex: 0 0 1rem !important;
          }

          /* Excel downloads: XML icon (replaces legacy download glyphs). */
          [class*="st-key-cfg_export_jira_sources_xlsx"] button,
          [class*="st-key-cfg_export_helix_sources_xlsx"] button,
          [class*="st-key-issues_download_csv"] button,
          [class*="st-key-"][class*="download_csv"] button,
          [class*="st-key-"][class*="dl_csv_min"] button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.38rem !important;
          }
          [class*="st-key-cfg_export_jira_sources_xlsx"] button::before,
          [class*="st-key-cfg_export_helix_sources_xlsx"] button::before,
          [class*="st-key-issues_download_csv"] button::before,
          [class*="st-key-"][class*="download_csv"] button::before,
          [class*="st-key-"][class*="dl_csv_min"] button::before {
            content: "" !important;
            display: inline-block !important;
            width: 0.98rem !important;
            height: 0.98rem !important;
            background-color: currentColor !important;
            -webkit-mask-image: url("__ICON_XML__") !important;
            mask-image: url("__ICON_XML__") !important;
            -webkit-mask-repeat: no-repeat !important;
            mask-repeat: no-repeat !important;
            -webkit-mask-position: center !important;
            mask-position: center !important;
            -webkit-mask-size: contain !important;
            mask-size: contain !important;
            flex: 0 0 0.98rem !important;
          }

          /* Safe delete section titles: use no-draw icon instead of emoji broom. */
          .bbva-icon-no-draw-title {
            display: flex !important;
            align-items: center !important;
            gap: 0.42rem !important;
            margin: 0.2rem 0 0.48rem !important;
            font-family: var(--bbva-font-ui) !important;
            font-size: 1.06rem !important;
            font-weight: 700 !important;
            line-height: 1.25 !important;
            color: var(--bbva-text) !important;
          }
          .bbva-icon-no-draw-title::before {
            content: "" !important;
            display: inline-block !important;
            width: 1rem !important;
            height: 1rem !important;
            background-color: currentColor !important;
            -webkit-mask-image: url("__ICON_NO_DRAW__") !important;
            mask-image: url("__ICON_NO_DRAW__") !important;
            -webkit-mask-repeat: no-repeat !important;
            mask-repeat: no-repeat !important;
            -webkit-mask-position: center !important;
            mask-position: center !important;
            -webkit-mask-size: contain !important;
            mask-size: contain !important;
            flex: 0 0 1rem !important;
          }

          /* Download button: unified pill style across CSV/HTML exports */
          .stDownloadButton {
            width: auto !important;
          }
          .stDownloadButton > button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.32rem !important;
            min-height: 1.96rem !important;
            min-width: 4.86rem !important; /* keeps "HTML" fully inside */
            width: auto !important;
            padding: 0.24rem 0.74rem !important;
            border-radius: 999px !important;
            box-sizing: border-box !important;
            white-space: nowrap !important;
            line-height: 1.05 !important;
            font-weight: 700 !important;
            border: 1px solid var(--bbva-tab-soft-border) !important;
            background: var(--bbva-tab-soft-bg) !important;
            color: var(--bbva-tab-soft-text) !important;
          }
          .stDownloadButton > button:hover {
            background: color-mix(in srgb, var(--bbva-primary) 12%, var(--bbva-tab-soft-bg)) !important;
            border-color: color-mix(in srgb, var(--bbva-primary) 40%, var(--bbva-tab-soft-border)) !important;
          }
          .stDownloadButton > button:disabled {
            opacity: 0.45 !important;
          }

          /* Report saved path: link-like control */
          .st-key-workspace_report_saved_path_link button,
          .st-key-workspace_report_saved_path_link [data-testid^="baseButton-"],
          .st-key-workspace_report_saved_path_link [data-testid^="baseButton-"] > button {
            padding: 0 !important;
            border: none !important;
            background: transparent !important;
            background-color: transparent !important;
            box-shadow: none !important;
            min-height: auto !important;
            color: var(--bbva-primary) !important;
            font-weight: 700 !important;
            text-decoration: underline !important;
            text-align: left !important;
            white-space: normal !important;
            cursor: pointer !important;
          }
          .st-key-workspace_report_saved_path_link button:hover,
          .st-key-workspace_report_saved_path_link [data-testid^="baseButton-"]:hover,
          .st-key-workspace_report_saved_path_link [data-testid^="baseButton-"] > button:hover {
            background: transparent !important;
            background-color: transparent !important;
            color: color-mix(in srgb, var(--bbva-primary) 72%, var(--bbva-white)) !important;
          }
          .st-key-workspace_report_saved_path_link button:focus,
          .st-key-workspace_report_saved_path_link button:focus-visible,
          .st-key-workspace_report_saved_path_link [data-testid^="baseButton-"]:focus,
          .st-key-workspace_report_saved_path_link [data-testid^="baseButton-"]:focus-visible,
          .st-key-workspace_report_saved_path_link [data-testid^="baseButton-"] > button:focus,
          .st-key-workspace_report_saved_path_link [data-testid^="baseButton-"] > button:focus-visible {
            outline: none !important;
            box-shadow: none !important;
          }

          /* Pills */
          div[data-testid="stPills"] button {
            background: var(--bbva-surface) !important;
            border: 1px solid var(--bbva-border) !important;
            color: color-mix(in srgb, var(--bbva-text) 88%, transparent) !important;
            border-radius: 999px !important;
          }
          div[data-testid="stPills"] button span,
          div[data-testid="stPills"] button p {
            color: color-mix(in srgb, var(--bbva-text) 88%, transparent) !important;
            font-weight: 700 !important;
          }
          div[data-testid="stPills"] button[aria-pressed="true"],
          div[data-testid="stPills"] button[kind="primary"] {
            background: var(--bbva-accent-bg-soft) !important;
            border-color: color-mix(in srgb, var(--bbva-primary) 30%, transparent) !important;
          }
          div[data-testid="stPills"] button:focus-visible {
            outline: none !important;
            box-shadow: 0 0 0 3px var(--bbva-focus-ring) !important;
          }

          /* Action labels: denser, executive tone without altering status/priority chips */
          .flt-action-chip,
          .flt-action-chip-lbl,
          .nba-kicker {
            font-family: var(--bbva-font-sans) !important;
            font-weight: 790 !important;
            letter-spacing: 0.01em;
            font-kerning: normal;
          }
          [class*="st-key-nba_pending_slot_"] div[data-testid="stButton"] > button,
          [class*="st-key-nba_review_slot_"] div[data-testid="stButton"] > button,
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button,
          [class*="st-key-trins_"] div[data-testid="stButton"] > button,
          [class*="st-key-exec_focus_link_"] div[data-testid="stButton"] > button {
            font-family: var(--bbva-font-sans) !important;
            color: var(--bbva-action-link) !important;
          }
          [class*="st-key-nba_pending_slot_"] div[data-testid="stButton"] > button:hover,
          [class*="st-key-nba_review_slot_"] div[data-testid="stButton"] > button:hover,
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button:hover,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button:hover,
          [class*="st-key-trins_"] div[data-testid="stButton"] > button:hover,
          [class*="st-key-exec_focus_link_"] div[data-testid="stButton"] > button:hover {
            color: var(--bbva-action-link-hover) !important;
          }

          /* Tabs: underline accent color */
          div[data-baseweb="tab-list"] {
            gap: 8px;
          }
          div[data-testid="stTabs"] div[data-baseweb="tab-panel"] {
            padding-top: 0.08rem !important;
            margin-top: 0 !important;
          }
          div[data-testid="stTabs"] div[data-baseweb="tab-panel"] > div[data-testid="stVerticalBlock"] {
            row-gap: 0.3rem !important;
          }
          div[data-baseweb="tab"] button {
            color: var(--bbva-tab-soft-text) !important;
            font-weight: 700 !important;
            background: transparent !important;
            border: 0 !important;
            border-radius: 0 !important;
            opacity: 1 !important;
          }
          div[data-baseweb="tab"] button *,
          [role="tablist"] button[role="tab"] * {
            color: inherit !important;
            opacity: 1 !important;
          }
          div[data-baseweb="tab"] button[aria-selected="true"] {
            color: var(--bbva-primary) !important;
            opacity: 1 !important;
          }
          div[data-baseweb="tab"] button[aria-selected="false"],
          [role="tablist"] button[role="tab"][aria-selected="false"] {
            color: var(--bbva-text-muted) !important;
            opacity: 1 !important;
          }
          div[data-baseweb="tab-highlight"] {
            background-color: var(--bbva-primary) !important;
          }
          [role="tablist"] button[role="tab"][aria-selected="true"] {
            color: var(--bbva-primary) !important;
          }
          [role="tablist"] button[role="tab"]:focus-visible {
            outline: none !important;
            box-shadow: 0 0 0 3px var(--bbva-focus-ring) !important;
            border-radius: var(--bbva-radius-m) !important;
          }
          /* Hide all horizontal dividers and tab borders */
          hr,
          [data-testid="stDivider"],
          div[data-testid="stTabs"] div[data-baseweb="tab-border"] {
            display: none !important;
            height: 0 !important;
            border: 0 !important;
            margin: 0 !important;
          }

          /* Links */
          a, a:visited { color: var(--bbva-primary); }

          /* Plotly text hardening for dark mode/readability */
          .js-plotly-plot .legend text,
          .js-plotly-plot .legendtitletext,
          .js-plotly-plot .gtitle text,
          .js-plotly-plot .xtitle text,
          .js-plotly-plot .ytitle text,
          .js-plotly-plot .annotation text {
            fill: var(--bbva-text) !important;
          }
          .js-plotly-plot .xtick text,
          .js-plotly-plot .ytick text {
            fill: var(--bbva-text-muted) !important;
          }

          /* Issue cards */
          .issue-card {
            border: 1px solid var(--bbva-border);
            border-radius: var(--bbva-radius-xl);
            padding: 12px 14px;
            background: var(--bbva-surface);
          }
          [class*="st-key-issue_card_shell_"] {
            border: 1px solid var(--bbva-border-strong) !important;
            border-radius: var(--bbva-radius-xl) !important;
            padding: 12px 14px 10px 14px !important;
            margin: 0 0 10px 0 !important;
            background: var(--bbva-surface-elevated) !important;
            box-shadow: none !important;
            overflow: hidden !important;
          }
          [class*="st-key-issue_card_shell_"]:hover {
            border-color: var(--bbva-accent-border-soft) !important;
            box-shadow: none !important;
          }
          [class*="st-key-issue_card_shell_"] [data-testid="stVerticalBlock"] {
            gap: 0 !important;
          }
          [class*="st-key-issue_card_shell_"] [data-testid="stHorizontalBlock"] {
            align-items: baseline !important;
          }
          [class*="st-key-issue_card_shell_"] [data-testid="stVerticalBlock"] > [data-testid="element-container"] {
            margin-bottom: 0.22rem !important;
          }
          [class*="st-key-issue_card_shell_"] [data-testid="stVerticalBlock"] > [data-testid="element-container"]:last-child {
            margin-bottom: 0 !important;
          }
          .issue-key-anchor {
            display: inline-block;
            color: var(--bbva-action-link) !important;
            text-decoration: underline !important;
            font-weight: 800 !important;
            line-height: 1.08 !important;
            white-space: nowrap !important;
          }
          .issue-key-anchor:hover {
            color: var(--bbva-action-link-hover) !important;
          }
          .issue-key-anchor-disabled,
          .issue-key-anchor-disabled:hover {
            color: var(--bbva-text-muted) !important;
            text-decoration: none !important;
            font-weight: 700 !important;
            cursor: default !important;
          }
          .issue-title-inline {
            font-weight: 700;
            color: var(--bbva-text);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-top: 1px;
          }
          .issue-top {
            display: flex;
            gap: 10px;
            align-items: baseline;
            justify-content: flex-start;
            min-width: 0;
          }
          .issue-headline {
            display: inline-flex;
            align-items: baseline;
            gap: 8px;
            min-width: 0;
            max-width: 100%;
          }
          .issue-key a {
            font-weight: 700;
            text-decoration: none;
            white-space: nowrap;
          }
          .issue-title {
            font-weight: 700;
            color: color-mix(in srgb, var(--bbva-text) 96%, transparent);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            min-width: 0;
          }
          .issue-description {
            margin-top: 6px;
            font-size: 0.93rem;
            line-height: 1.24rem;
            color: color-mix(in srgb, var(--bbva-text) 90%, transparent);
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
            word-break: break-word;
          }
          .issue-description h1,
          .issue-description h2,
          .issue-description h3,
          .issue-description h4,
          .issue-description p,
          .issue-description li,
          .issue-description div,
          .issue-description span,
          .issue-description strong,
          .issue-description em {
            margin: 0 !important;
            padding: 0 !important;
            font-size: inherit !important;
            line-height: inherit !important;
            font-family: inherit !important;
            font-weight: inherit !important;
            letter-spacing: normal !important;
            text-transform: none !important;
            display: inline !important;
          }
          .issue-description li::marker {
            content: "" !important;
          }
          .badges {
            margin-top: 8px;
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
          }
          .issue-card-badges {
            margin-top: 11px !important;
            margin-bottom: 2px !important;
            padding-bottom: 8px !important;
            row-gap: 8px !important;
          }
          .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 999px;
            font-size: 0.80rem;
            border: 1px solid var(--bbva-border);
            background: var(--bbva-surface-2);
            white-space: nowrap;
          }
          .badge-priority {
            border-color: var(--bbva-accent-border-soft);
            background: var(--bbva-accent-bg-soft);
          }
          .badge-status {
            border-color: color-mix(in srgb, var(--bbva-midnight) 25%, transparent);
            background: color-mix(in srgb, var(--bbva-midnight) 6%, transparent);
          }
          .badge-age {
            border-color: var(--bbva-accent-border-subtle);
            background: var(--bbva-accent-bg-subtle);
          }

          [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
            border: 1px solid var(--bbva-border-strong) !important;
            border-radius: 12px !important;
            overflow: hidden !important;
            background: var(--bbva-surface-elevated) !important;
            --gdg-accent-color: var(--bbva-primary) !important;
            --gdg-accent-fg: var(--bbva-on-primary) !important;
            --gdg-accent-light: color-mix(in srgb, var(--bbva-primary) 22%, transparent) !important;
            --gdg-text-dark: var(--bbva-text) !important;
            --gdg-text-medium: color-mix(in srgb, var(--bbva-text) 78%, transparent) !important;
            --gdg-text-light: color-mix(in srgb, var(--bbva-text) 60%, transparent) !important;
            --gdg-text-header: color-mix(in srgb, var(--bbva-text) 86%, transparent) !important;
            --gdg-text-group-header: color-mix(in srgb, var(--bbva-text) 86%, transparent) !important;
            --gdg-bg-cell: color-mix(in srgb, var(--bbva-surface) 95%, var(--bbva-surface-2)) !important;
            --gdg-bg-cell-medium: color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2)) !important;
            --gdg-bg-header: color-mix(in srgb, var(--bbva-surface) 72%, var(--bbva-surface-2)) !important;
            --gdg-bg-header-has-focus: color-mix(in srgb, var(--bbva-primary) 16%, var(--bbva-surface)) !important;
            --gdg-bg-header-hovered: color-mix(in srgb, var(--bbva-primary) 10%, var(--bbva-surface)) !important;
            --gdg-bg-search-result: color-mix(in srgb, var(--bbva-primary) 14%, var(--bbva-surface)) !important;
            --gdg-border-color: var(--bbva-border) !important;
            --gdg-horizontal-border-color: var(--bbva-border) !important;
            --gdg-link-color: {action_link} !important;
          }
          [data-testid="stDataFrame"] [role="grid"],
          [data-testid="stDataEditor"] [role="grid"] {
            background: var(--bbva-surface) !important;
            color: var(--bbva-text) !important;
          }
          [data-testid="stDataFrame"] [role="columnheader"],
          [data-testid="stDataEditor"] [role="columnheader"] {
            background: color-mix(in srgb, var(--bbva-surface) 70%, var(--bbva-surface-2)) !important;
            color: var(--bbva-text) !important;
            border-color: var(--bbva-border) !important;
          }
          [data-testid="stDataEditor"] [role="gridcell"],
          [data-testid="stDataFrame"] [role="gridcell"] {
            border-color: var(--bbva-border) !important;
            color: var(--bbva-text) !important;
          }
          [data-testid="stDataEditor"] input {
            color: var(--bbva-text) !important;
            background: color-mix(in srgb, var(--bbva-surface) 88%, var(--bbva-surface-2)) !important;
          }
          [data-testid="stDataEditor"] input[type="checkbox"] {
            accent-color: var(--bbva-primary) !important;
            background-color: color-mix(in srgb, var(--bbva-surface) 88%, var(--bbva-surface-2)) !important;
            border-color: var(--bbva-border-strong) !important;
          }

          /* Metrics and expanders for dark/light readability */
          [data-testid="stMetric"] [data-testid="stMetricLabel"] * {
            color: var(--bbva-text-muted) !important;
          }
          [data-testid="stMetric"] [data-testid="stMetricValue"] * {
            color: var(--bbva-text) !important;
          }
          [data-testid="stMetric"] [data-testid="stMetricDelta"] * {
            color: var(--bbva-text-muted) !important;
          }
          [data-testid="stExpander"] {
            border: 1px solid var(--bbva-border) !important;
            border-radius: 14px !important;
            background: var(--bbva-surface-soft) !important;
          }
          [data-testid="stExpander"] > details {
            background: var(--bbva-surface-soft) !important;
            border-radius: 14px !important;
          }
          [data-testid="stExpander"] summary {
            color: var(--bbva-text) !important;
            background: color-mix(in srgb, var(--bbva-surface) 78%, transparent) !important;
            border-radius: 14px !important;
          }
          [data-testid="stExpander"] summary .material-symbols-rounded {
            font-size: 0 !important;
            line-height: 1 !important;
            width: 0.9rem;
            min-width: 0.9rem;
            display: inline-flex !important;
            align-items: center;
            justify-content: center;
          }
          [data-testid="stExpander"] summary .material-symbols-rounded::before {
            content: "▸";
            font-size: 0.92rem;
            line-height: 1;
            color: var(--bbva-text-muted);
          }
          [data-testid="stExpander"] details[open] summary .material-symbols-rounded::before {
            content: "▾";
          }
          [data-testid="stExpander"] summary * {
            color: var(--bbva-text) !important;
          }
          [data-testid="stExpander"] details[open] summary {
            border-bottom: 1px solid var(--bbva-border) !important;
            border-bottom-left-radius: 0 !important;
            border-bottom-right-radius: 0 !important;
          }
          [data-testid="stExpander"] summary:hover {
            background: color-mix(in srgb, var(--bbva-primary) 8%, transparent) !important;
          }
          [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--bbva-border-strong) !important;
            background: var(--bbva-surface-elevated) !important;
            box-shadow: 0 8px 24px color-mix(in srgb, var(--bbva-text) 10%, transparent) !important;
          }
          [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] p,
          [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] li,
          [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] h1,
          [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] h2,
          [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] h3,
          [data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] h4 {
            color: var(--bbva-text) !important;
          }
          [data-testid="stCaptionContainer"] * {
            color: var(--bbva-text-muted) !important;
          }
        </style>
        """
    return (
        css_template.replace("__CSS_VARS__", css_vars)
        .replace("__SEMANTIC_POPOVER_RULES__", semantic_popover_css_rules())
        .replace("__FONT_FACE_CSS__", _font_face_css())
        .replace("__ICON_REPORT__", icon_report)
        .replace("__ICON_REPORT_PERIOD__", icon_report_period)
        .replace("__ICON_INGEST__", icon_ingest)
        .replace("__ICON_THEME__", icon_theme)
        .replace("__ICON_CONFIG__", icon_config)
        .replace("__ICON_SAVE__", icon_save)
        .replace("__ICON_NO_DRAW__", icon_no_draw)
        .replace("__ICON_REINGEST__", icon_reingest)
        .replace("__ICON_RECYCLE__", icon_recycle)
        .replace("__ICON_SEARCH__", icon_search)
        .replace("__ICON_XML__", icon_xml)
    )


def inject_bbva_css(*, dark_mode: bool = False) -> None:
    """Inject global CSS tokens and components for light/dark runtime themes."""
    st.markdown(_compiled_bbva_css(dark_mode=bool(dark_mode)), unsafe_allow_html=True)


def render_hero(app_title: str) -> None:
    """Render a top hero section."""
    st.markdown(
        f"""
        <div class="bbva-hero">
          <div class="bbva-hero-title">{html.escape(app_title)}</div>
          <div class="bbva-hero-sub">Análisis y seguimiento de incidencias</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@lru_cache(maxsize=2)
def _plotly_template_without_scattermapbox(*, dark_mode: bool) -> Any:
    """
    Return a Plotly base template with deprecated `scattermapbox` defaults removed.

    Plotly keeps `scattermapbox` in built-in template data for backward compatibility,
    but newer versions emit a DeprecationWarning for that trace type. We strip only
    that entry and preserve the rest of the template.
    """
    template_name = "plotly_dark" if dark_mode else "plotly_white"
    try:
        import plotly.io as pio

        template_payload: dict[str, Any] = dict(pio.templates[template_name].to_plotly_json())
    except Exception:
        return template_name

    data_payload = template_payload.get("data")
    if not isinstance(data_payload, dict):
        return template_payload

    if "scattermapbox" not in data_payload:
        return template_payload

    cleaned_data = dict(data_payload)
    cleaned_data.pop("scattermapbox", None)
    template_payload["data"] = cleaned_data
    return template_payload


def apply_plotly_bbva(fig: Any, *, showlegend: bool = False) -> Any:
    """Apply a consistent Plotly style aligned with app design tokens."""
    dark_mode = bool(st.session_state.get("workspace_dark_mode", False))
    palette = BBVA_DARK if dark_mode else BBVA_LIGHT
    text_color = palette.ink
    grid_color = hex_to_rgba(
        palette.ink,
        0.14 if dark_mode else 0.10,
        fallback=BBVA_LIGHT.ink,
    )
    legend_bg = hex_to_rgba(
        palette.midnight if dark_mode else palette.white,
        0.72 if dark_mode else 0.65,
        fallback=BBVA_LIGHT.midnight,
    )
    legend_border = hex_to_rgba(
        palette.ink,
        0.20 if dark_mode else 0.12,
        fallback=BBVA_LIGHT.ink,
    )
    transparent_bg = hex_to_rgba(palette.ink, 0.0, fallback=BBVA_LIGHT.ink)
    legend_bottom_space = 92 if showlegend else 16
    undefined_tokens = {"undefined", "none", "nan", "null"}
    es_label_map = {
        "count": "Incidencias",
        "value": "Valor",
        "date": "Fecha",
        "status": "Estado",
        "priority": "Prioridad",
        "bucket": "Rango",
        "created": "Creadas",
        "closed": "Cerradas",
        "open_backlog_proxy": "Backlog abierto",
        "resolution_days": "Días de resolución",
    }

    def _clean_txt(v: object) -> str:
        txt = str(v or "").strip()
        return "" if txt.lower() in undefined_tokens else txt

    def _localize(txt: object) -> str:
        clean = _clean_txt(txt)
        if not clean:
            return ""
        return es_label_map.get(clean.strip().lower(), clean)

    fig.update_layout(
        template=_plotly_template_without_scattermapbox(dark_mode=dark_mode),
        paper_bgcolor=transparent_bg,
        plot_bgcolor=transparent_bg,
        font=dict(
            family=BBVA_FONT_SANS,
            color=text_color,
        ),
        colorway=[
            palette.electric_blue,
            palette.core_blue,
            palette.royal_blue,
            palette.serene_dark_blue,
            palette.serene_blue,
            palette.aqua,
            palette.midnight,
        ],
        showlegend=showlegend,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.22,
            xanchor="right",
            x=1.0,
            bgcolor=legend_bg,
            bordercolor=legend_border,
            borderwidth=1,
            font=dict(size=11, color=text_color),
            title=dict(font=dict(color=text_color), text=""),
        ),
        hoverlabel=dict(
            bgcolor=legend_bg,
            bordercolor=legend_border,
            font=dict(color=text_color),
        ),
        margin=dict(l=16, r=16, t=48, b=legend_bottom_space),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=grid_color,
        zeroline=False,
        tickfont=dict(color=text_color),
        title_font=dict(color=text_color),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=grid_color,
        zeroline=False,
        tickfont=dict(color=text_color),
        title_font=dict(color=text_color),
    )
    for series_name, color in flow_signal_color_map().items():
        fig.update_traces(
            line=dict(color=color),
            marker=dict(color=color),
            selector={"name": series_name},
        )

    # Remove "undefined" from layout-level labels/titles.
    try:
        title_obj = getattr(fig.layout, "title", None)
        title_text = _localize(getattr(title_obj, "text", ""))
        fig.update_layout(title_text=title_text)
    except Exception:
        pass

    try:
        x_axis = getattr(fig.layout, "xaxis", None)
        y_axis = getattr(fig.layout, "yaxis", None)
        x_title = _localize(getattr(getattr(x_axis, "title", None), "text", ""))
        y_title = _localize(getattr(getattr(y_axis, "title", None), "text", ""))
        fig.update_xaxes(title_text=x_title)
        fig.update_yaxes(title_text=y_title)
    except Exception:
        pass

    try:
        for ann in list(getattr(fig.layout, "annotations", []) or []):
            ann.text = _localize(getattr(ann, "text", ""))
            ann.font = dict(color=text_color)
    except Exception:
        pass

    # Defensive cleanup to avoid "undefined" noise in hover/labels.
    for trace in getattr(fig, "data", []):
        try:
            trace.name = _localize(getattr(trace, "name", ""))
            trace_type = str(getattr(trace, "type", "") or "").strip().lower()
            if trace_type == "pie":
                trace.showlegend = bool(showlegend)
            else:
                trace.showlegend = bool(showlegend and trace.name)
            if hasattr(trace, "textfont"):
                trace.textfont = dict(color=text_color)
            if hasattr(trace, "legendgrouptitle"):
                trace.legendgrouptitle = dict(font=dict(color=text_color))
        except Exception:
            pass

        try:
            hovertemplate = getattr(trace, "hovertemplate", None)
            if isinstance(hovertemplate, str):
                cleaned = hovertemplate
                cleaned = cleaned.replace("%{fullData.name}", "")
                cleaned = cleaned.replace("undefined", "")
                cleaned = cleaned.replace("Undefined", "")
                trace.hovertemplate = cleaned
        except Exception:
            pass
    return fig
