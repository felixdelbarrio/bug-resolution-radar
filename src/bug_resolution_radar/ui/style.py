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
    BBVA_FONT_HEADLINE,
    BBVA_FONT_SANS,
    BBVA_FONT_SANS_BOOK,
    BBVA_FONT_SANS_MEDIUM,
    BBVA_LIGHT,
    BBVA_RADIUS_INNER_PX,
    BBVA_RADIUS_OUTER_PX,
)
from bug_resolution_radar.ui.common import flow_signal_color_map


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


def inject_bbva_css(*, dark_mode: bool = False) -> None:
    """Inject global CSS tokens and components for light/dark runtime themes."""
    palette = BBVA_DARK if dark_mode else BBVA_LIGHT
    if dark_mode:
        text_rgb = "234,240,255"
        surface_soft = "rgba(10,46,103,0.78)"
        surface_elevated = "rgba(10,46,103,0.90)"
        border = "rgba(234,240,255,0.26)"
        border_strong = "rgba(234,240,255,0.40)"
        tab_soft_bg = "#0A2E67"
        tab_soft_border = "rgba(133,200,255,0.44)"
        tab_soft_text = "#D8E8FF"
        tab_nav_active_text = "#85C8FF"
        tab_active_bg = "#004481"
        tab_active_border = "#53A9EF"
        tab_active_text = "#FFFFFF"
        icon_filter = "brightness(0) invert(1)"
        action_link = "#85C8FF"
        action_link_hover = "#8BE1E9"
        scrollbar_track = "rgba(234,240,255,0.10)"
        scrollbar_thumb = "rgba(133,200,255,0.44)"
        scrollbar_thumb_hover = "rgba(133,200,255,0.62)"
    else:
        text_rgb = "17,25,45"
        surface_soft = "rgba(255,255,255,0.62)"
        surface_elevated = "rgba(255,255,255,0.82)"
        border = "rgba(17,25,45,0.12)"
        border_strong = "rgba(17,25,45,0.20)"
        tab_soft_bg = "#EEF3FB"
        tab_soft_border = "#C8D6E8"
        tab_soft_text = "#5C6C84"
        tab_nav_active_text = "#0051F1"
        tab_active_bg = "#004481"
        tab_active_border = "#53A9EF"
        tab_active_text = "#FFFFFF"
        icon_filter = "brightness(0) invert(1)"
        action_link = "#0051F1"
        action_link_hover = "#004481"
        scrollbar_track = "rgba(17,25,45,0.08)"
        scrollbar_thumb = "rgba(7,33,70,0.22)"
        scrollbar_thumb_hover = "rgba(7,33,70,0.34)"

    css_vars = f"""
      :root {{
        --bbva-primary: {palette.electric_blue};
        --bbva-midnight: {palette.midnight};
        --bbva-text: {palette.ink};
        --bbva-text-muted: rgba({text_rgb},0.74);
        --bbva-surface: {palette.white if not dark_mode else '#0A1F45'};
        --bbva-surface-2: {palette.bg_light};
        --bbva-surface-soft: {surface_soft};
        --bbva-surface-elevated: {surface_elevated};
        --bbva-border: {border};
        --bbva-border-strong: {border_strong};
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
        --primary-color: var(--bbva-primary);
        --text-color: var(--bbva-text);
        --background-color: var(--bbva-surface-2);
        --secondary-background-color: var(--bbva-surface);
        --bbva-font-sans: {BBVA_FONT_SANS};
        --bbva-font-body: {BBVA_FONT_SANS_BOOK};
        --bbva-font-ui: {BBVA_FONT_SANS_MEDIUM};
        --bbva-font-headline: {BBVA_FONT_HEADLINE};
        --bbva-font-label: {BBVA_FONT_SANS_MEDIUM};
      }}
    """

    icon_report = _svg_data_uri(
        file_name="digital-press.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<rect x="3" y="4" width="18" height="14" rx="2" fill="#000"/>'
            '<rect x="7" y="19" width="10" height="2" rx="1" fill="#000"/>'
            "</svg>"
        ),
    )
    icon_ingest = _svg_data_uri(
        file_name="exploration.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="11" cy="11" r="7" fill="none" stroke="#000" stroke-width="2"/>'
            '<path d="M21 21l-5-5" stroke="#000" stroke-width="2" stroke-linecap="round"/>'
            "</svg>"
        ),
    )
    icon_theme = _svg_data_uri(
        file_name="sun.svg" if dark_mode else "moon.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="5" fill="#000"/>'
            "</svg>"
        ),
    )
    icon_config = _svg_data_uri(
        file_name="settings.svg",
        fallback_svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
            '<circle cx="12" cy="12" r="3" fill="#000"/>'
            '<path d="M12 2l2 2 3-1 1 3 3 1-1 3 2 2-2 2 1 3-3 1-1 3-3-1-2 2-2-2-3 1-1-3-3-1 1-3-2-2 2-2-1-3 3-1 1-3 3 1z" fill="#000"/>'
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
          }
          h2, h3, h4,
          [data-testid="stMarkdownContainer"] h2,
          [data-testid="stMarkdownContainer"] h3,
          [data-testid="stMarkdownContainer"] h4 {
            font-family: var(--bbva-font-ui) !important;
            font-weight: 700 !important;
            letter-spacing: -0.005em;
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
            padding-top: 16px;
            padding-bottom: 24px;
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
            color: #ffffff;
            border: 1px solid rgba(255,255,255,0.08);
          }
          .bbva-hero-title {
            margin: 0;
            font-size: 34px;
            line-height: 1.02;
            font-weight: 700;
            color: #ffffff;
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
            margin-bottom: -0.34rem;
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
            margin-bottom: -0.76rem;
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
            margin-top: -0.24rem;
          }
          .st-key-workspace_dashboard_content_issues,
          .st-key-workspace_dashboard_content_kanban,
          .st-key-workspace_dashboard_content_trends,
          .st-key-workspace_dashboard_content_insights {
            margin-top: -0.72rem;
          }
          .st-key-dashboard_filters_panel {
            margin-top: -0.64rem;
            margin-bottom: -0.44rem;
          }
          .st-key-insights_shell {
            margin-top: -0.64rem;
          }
          .st-key-issues_tab_issues_shell,
          .st-key-kanban_shell,
          .st-key-trend_chart_shell {
            margin-top: -0.20rem;
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
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 92%, #8EB4FF 8%) !important;
            background: color-mix(in srgb, var(--bbva-surface-elevated) 90%, #0E234C 10%) !important;
            box-shadow: 0 12px 28px color-mix(in srgb, #02091D 48%, transparent),
                        inset 0 0 0 1px color-mix(in srgb, #9DC0FF 18%, transparent) !important;
          }
          [class*="st-key-overview_summary_chart_"] [data-testid="stVerticalBlockBorderWrapper"],
          [class*="st-key-trins_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid color-mix(in srgb, var(--bbva-border-strong) 88%, #97BCFF 12%) !important;
            background: color-mix(in srgb, var(--bbva-surface) 80%, #0F244B 20%) !important;
            box-shadow: 0 8px 22px color-mix(in srgb, #02091D 42%, transparent),
                        inset 0 0 0 1px color-mix(in srgb, #9DC0FF 16%, transparent) !important;
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
          div[data-baseweb="popover"] [role="listbox"],
          div[data-baseweb="popover"] [role="menu"],
          div[data-baseweb="popover"] ul {
            background: var(--bbva-surface) !important;
            border: 1px solid var(--bbva-border) !important;
            color: var(--bbva-text) !important;
            list-style: none !important;
            margin: 0 !important;
            padding-inline-start: 0 !important;
          }
          div[data-baseweb="popover"] [role="option"],
          div[data-baseweb="popover"] li {
            color: var(--bbva-text) !important;
            background: transparent !important;
            position: relative;
            padding-left: 0.66rem !important;
            --bbva-opt-dot: transparent;
            list-style: none !important;
          }
          div[data-baseweb="popover"] li::marker {
            content: "" !important;
          }
          div[data-baseweb="popover"] [role="option"]::before,
          div[data-baseweb="popover"] li::before {
            content: none;
            width: 0.54rem;
            height: 0.54rem;
            border-radius: 999px;
            background: var(--bbva-opt-dot);
            position: absolute;
            left: 0.66rem;
            top: 50%;
            transform: translateY(-50%);
            pointer-events: none;
          }
          div[data-baseweb="popover"] [role="option"]:hover,
          div[data-baseweb="popover"] li:hover {
            background: color-mix(in srgb, var(--bbva-primary) 14%, transparent) !important;
          }
          div[data-baseweb="popover"] [role="option"][aria-selected="true"] {
            background: color-mix(in srgb, var(--bbva-primary) 20%, transparent) !important;
            color: var(--bbva-text) !important;
          }
          /* Option semáforo en listados (status/priority); el chip seleccionado mantiene solo fondo/borde */
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="new" i], [title*="new" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="analysing" i], [title*="analysing" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="blocked" i], [title*="blocked" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="created" i], [title*="created" i]) {
            padding-left: 1.70rem !important;
            --bbva-opt-dot: #D24756;
            border-left: 2px solid rgba(210,71,86,0.72);
          }
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="en progreso" i], [title*="en progreso" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="in progress" i], [title*="in progress" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="to rework" i], [title*="to rework" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="test" i], [title*="test" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="ready to verify" i], [title*="ready to verify" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="open" i], [title*="open" i]) {
            padding-left: 1.70rem !important;
            --bbva-opt-dot: #E08A00;
            border-left: 2px solid rgba(224,138,0,0.72);
          }
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="deployed" i], [title*="deployed" i]) {
            padding-left: 1.70rem !important;
            --bbva-opt-dot: var(--bbva-goal-green);
            border-left: 2px solid color-mix(in srgb, var(--bbva-goal-green) 72%, transparent);
          }
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="accepted" i], [title*="accepted" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="ready to deploy" i], [title*="ready to deploy" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="closed" i], [title*="closed" i]) {
            padding-left: 1.70rem !important;
            --bbva-opt-dot: #1E9E53;
            border-left: 2px solid rgba(30,158,83,0.72);
          }
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="supone un impedimento" i], [title*="supone un impedimento" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="highest" i], [title*="highest" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="high" i], [title*="high" i]) {
            padding-left: 1.70rem !important;
            --bbva-opt-dot: #B4232A;
            border-left: 2px solid rgba(180,35,42,0.72);
          }
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="medium" i], [title*="medium" i]) {
            padding-left: 1.70rem !important;
            --bbva-opt-dot: #E08A00;
            border-left: 2px solid rgba(224,138,0,0.72);
          }
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="low" i], [title*="low" i]),
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="lowest" i], [title*="lowest" i]) {
            padding-left: 1.70rem !important;
            --bbva-opt-dot: #1E9E53;
            border-left: 2px solid rgba(30,158,83,0.72);
          }
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="new" i], [title*="new" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="analysing" i], [title*="analysing" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="blocked" i], [title*="blocked" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="created" i], [title*="created" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="en progreso" i], [title*="en progreso" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="in progress" i], [title*="in progress" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="to rework" i], [title*="to rework" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="test" i], [title*="test" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="ready to verify" i], [title*="ready to verify" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="open" i], [title*="open" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="deployed" i], [title*="deployed" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="accepted" i], [title*="accepted" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="ready to deploy" i], [title*="ready to deploy" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="closed" i], [title*="closed" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="supone un impedimento" i], [title*="supone un impedimento" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="highest" i], [title*="highest" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="high" i], [title*="high" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="medium" i], [title*="medium" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="low" i], [title*="low" i])::before,
          div[data-baseweb="popover"].bbva-semantic-popover [role="option"]:is([aria-label*="lowest" i], [title*="lowest" i])::before {
            content: "";
          }
          .stTextInput input::placeholder,
          .stTextArea textarea::placeholder {
            color: color-mix(in srgb, var(--bbva-text) 45%, transparent) !important;
          }
          .stTextInput input:focus,
          .stTextArea textarea:focus,
          .stNumberInput input:focus {
            border-color: rgba(0,81,241,0.65) !important;
            box-shadow: 0 0 0 3px rgba(0,81,241,0.18) !important;
            outline: none !important;
          }

          .stButton > button[kind="primary"] {
            background: var(--bbva-primary) !important;
            border-color: var(--bbva-primary) !important;
            color: #ffffff !important;
            font-weight: 700 !important;
          }

          .stButton > button[kind="secondary"] {
            background: var(--bbva-surface) !important;
            border-color: var(--bbva-border-strong) !important;
            color: color-mix(in srgb, var(--bbva-text) 88%, transparent) !important;
            font-weight: 700 !important;
          }
          .stButton > button[kind="secondary"]:hover {
            border-color: rgba(0,81,241,0.35) !important;
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
          .st-key-workspace_btn_slot_ingest button,
          .st-key-workspace_btn_slot_theme button,
          .st-key-workspace_btn_slot_config button,
          .st-key-workspace_btn_report button,
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
          .st-key-workspace_btn_slot_ingest button > *,
          .st-key-workspace_btn_slot_theme button > *,
          .st-key-workspace_btn_slot_config button > *,
          .st-key-workspace_btn_report button > *,
          .st-key-workspace_btn_ingest button > *,
          .st-key-workspace_btn_theme button > *,
          .st-key-workspace_btn_config button > * {
            opacity: 0 !important;
          }
          .st-key-workspace_btn_slot_report button::before,
          .st-key-workspace_btn_slot_ingest button::before,
          .st-key-workspace_btn_slot_theme button::before,
          .st-key-workspace_btn_slot_config button::before,
          .st-key-workspace_btn_report button::before,
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
          .st-key-workspace_btn_report button { --bbva-btn-icon: url("__ICON_REPORT__"); }
          .st-key-workspace_btn_slot_ingest button,
          .st-key-workspace_btn_ingest button { --bbva-btn-icon: url("__ICON_INGEST__"); }
          .st-key-workspace_btn_slot_theme button,
          .st-key-workspace_btn_theme button { --bbva-btn-icon: url("__ICON_THEME__"); }
          .st-key-workspace_btn_slot_config button,
          .st-key-workspace_btn_config button { --bbva-btn-icon: url("__ICON_CONFIG__"); }

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
            color: color-mix(in srgb, var(--bbva-primary) 72%, white) !important;
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
            background: rgba(0,81,241,0.10) !important;
            border-color: rgba(0,81,241,0.30) !important;
          }
          div[data-testid="stPills"] button:focus-visible {
            outline: none !important;
            box-shadow: 0 0 0 3px rgba(0,81,241,0.18) !important;
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
            box-shadow: 0 0 0 3px rgba(0,81,241,0.18) !important;
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
          .issue-top {
            display: flex;
            gap: 10px;
            align-items: baseline;
            justify-content: space-between;
          }
          .issue-key a {
            font-weight: 700;
            text-decoration: none;
          }
          .issue-summary {
            margin-top: 6px;
            font-size: 0.95rem;
            line-height: 1.25rem;
            color: color-mix(in srgb, var(--bbva-text) 95%, transparent);
          }
          .badges {
            margin-top: 8px;
            display: flex;
            gap: 6px;
            flex-wrap: wrap;
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
            border-color: rgba(0,81,241,0.35);
            background: rgba(0,81,241,0.10);
          }
          .badge-status {
            border-color: rgba(7,14,70,0.25);
            background: rgba(7,14,70,0.06);
          }
          .badge-age {
            border-color: rgba(0,81,241,0.20);
            background: rgba(0,81,241,0.06);
          }

          [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
            border: 1px solid var(--bbva-border-strong) !important;
            border-radius: 12px !important;
            overflow: hidden !important;
            background: var(--bbva-surface-elevated) !important;
            --gdg-accent-color: var(--bbva-primary) !important;
            --gdg-accent-fg: #ffffff !important;
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
            --gdg-link-color: var(--bbva-primary) !important;
          }
          [data-testid="stDataFrame"] *,
          [data-testid="stDataEditor"] * {
            --gdg-accent-color: var(--bbva-primary) !important;
            --gdg-accent-fg: #ffffff !important;
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
            --gdg-link-color: var(--bbva-primary) !important;
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
    st.markdown(
        css_template.replace("__CSS_VARS__", css_vars)
        .replace("__FONT_FACE_CSS__", _font_face_css())
        .replace("__ICON_REPORT__", icon_report)
        .replace("__ICON_INGEST__", icon_ingest)
        .replace("__ICON_THEME__", icon_theme)
        .replace("__ICON_CONFIG__", icon_config),
        unsafe_allow_html=True,
    )


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


def apply_plotly_bbva(fig: Any, *, showlegend: bool = False) -> Any:
    """Apply a consistent Plotly style aligned with app design tokens."""
    dark_mode = bool(st.session_state.get("workspace_dark_mode", False))
    palette = BBVA_DARK if dark_mode else BBVA_LIGHT
    text_color = palette.ink
    grid_color = "rgba(234,240,255,0.14)" if dark_mode else "rgba(17,25,45,0.10)"
    legend_bg = "rgba(21,30,53,0.72)" if dark_mode else "rgba(255,255,255,0.65)"
    legend_border = "rgba(234,240,255,0.20)" if dark_mode else "rgba(17,25,45,0.12)"
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
        template="plotly_dark" if dark_mode else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
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
