"""Shared visual styling helpers for Streamlit and Plotly rendering."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from bug_resolution_radar.ui.common import flow_signal_color_map


def inject_bbva_css(*, dark_mode: bool = False) -> None:
    """Inject global CSS tokens and components for light/dark runtime themes."""
    if dark_mode:
        css_vars = """
          :root {
            --bbva-primary: #5F9FFF;
            --bbva-midnight: #070E46;
            --bbva-text: #EAF0FF;
            --bbva-text-muted: rgba(234,240,255,0.90);
            --bbva-surface: #1A2B47;
            --bbva-surface-2: #0A1228;
            --bbva-surface-soft: rgba(26,43,71,0.82);
            --bbva-surface-elevated: rgba(34,54,89,0.92);
            --bbva-border: rgba(234,240,255,0.28);
            --bbva-border-strong: rgba(234,240,255,0.42);
            --bbva-radius-s: 4px;
            --bbva-radius-m: 8px;
            --bbva-radius-l: 12px;
            --bbva-radius-xl: 16px;
            --bbva-tab-soft-bg: #1D2F4D;
            --bbva-tab-soft-border: #4A6290;
            --bbva-tab-soft-text: #E6EFFF;
            --bbva-tab-active-bg: #284A73;
            --bbva-tab-active-border: #6793C7;
            --bbva-tab-active-text: #F3F8FF;
            --primary-color: var(--bbva-primary);
            --text-color: var(--bbva-text);
            --background-color: var(--bbva-surface-2);
            --secondary-background-color: var(--bbva-surface);
          }
        """
    else:
        css_vars = """
          :root {
            --bbva-primary: #0051F1;
            --bbva-midnight: #070E46;
            --bbva-text: #11192D;
            --bbva-text-muted: rgba(17,25,45,0.72);
            --bbva-surface: #FFFFFF;
            --bbva-surface-2: #F4F6F9;
            --bbva-surface-soft: rgba(255,255,255,0.58);
            --bbva-surface-elevated: rgba(255,255,255,0.72);
            --bbva-border: rgba(17,25,45,0.12);
            --bbva-border-strong: rgba(17,25,45,0.18);
            --bbva-radius-s: 4px;
            --bbva-radius-m: 8px;
            --bbva-radius-l: 12px;
            --bbva-radius-xl: 16px;
            --bbva-tab-soft-bg: #E9EEF4;
            --bbva-tab-soft-border: #C7D2DF;
            --bbva-tab-soft-text: #44546B;
            --bbva-tab-active-bg: #6F839E;
            --bbva-tab-active-border: #657A94;
            --bbva-tab-active-text: #F8FBFF;
            --primary-color: var(--bbva-primary);
            --text-color: var(--bbva-text);
            --background-color: var(--bbva-surface-2);
            --secondary-background-color: var(--bbva-surface);
          }
        """

    css_template = """
        <style>
          __CSS_VARS__

          html, body, [class*="stApp"] {
            color: var(--bbva-text);
            font-family: "BBVA Benton Sans", "Benton Sans", "Inter", system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 16px;
            line-height: 1.5;
          }

          /* Use serif only for headline-like elements */
          .bbva-hero-title {
            font-family: "Tiempos Headline", "Tiempos Headline Bold", Georgia, "Times New Roman", serif;
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
            padding-top: 0.30rem;
            padding-bottom: 1.15rem;
            max-width: 1200px;
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
          div[data-testid="stSegmentedControl"] {
            margin-top: 0.02rem;
            margin-bottom: 0.08rem !important;
          }
          div[data-testid="stSegmentedControl"] [role="radiogroup"] {
            gap: 0.22rem !important;
          }
          div[data-testid="stSegmentedControl"] label,
          div[data-testid="stSegmentedControl"] button,
          div[data-testid="stSegmentedControl"] [role="radio"] {
            min-height: 2.15rem !important;
            padding: 0.35rem 0.78rem !important;
            border-radius: 10px !important;
            font-weight: 700 !important;
            border: 1px solid var(--bbva-tab-soft-border) !important;
            background: var(--bbva-tab-soft-bg) !important;
            color: var(--bbva-tab-soft-text) !important;
          }
          div[data-testid="stSegmentedControl"] label *,
          div[data-testid="stSegmentedControl"] button *,
          div[data-testid="stSegmentedControl"] [role="radio"] * {
            color: inherit !important;
            fill: currentColor !important;
          }
          div[data-testid="stSegmentedControl"] label:has(input:checked),
          div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
          div[data-testid="stSegmentedControl"] [role="radio"][aria-checked="true"] {
            border-color: var(--bbva-tab-active-border) !important;
            background: var(--bbva-tab-active-bg) !important;
            color: var(--bbva-tab-active-text) !important;
          }
          div[data-testid="stSegmentedControl"] label:hover,
          div[data-testid="stSegmentedControl"] button:hover,
          div[data-testid="stSegmentedControl"] [role="radio"]:hover {
            filter: brightness(0.99);
          }
          div[data-testid="stSegmentedControl"] [aria-disabled="true"] {
            opacity: 0.72 !important;
          }
          div[data-testid="stButton"] > button[aria-label="🛰️"],
          div[data-testid="stButton"] > button[aria-label="◐"],
          div[data-testid="stButton"] > button[aria-label="⚙️"] {
            min-height: 2.2rem !important;
            padding: 0.25rem 0.25rem !important;
            border-radius: 11px !important;
            font-size: 1.05rem !important;
          }
          /* Tighten the vertical gap between top tabs and dashboard filters/content */
          .st-key-workspace_nav_bar {
            margin-top: -0.04rem;
            margin-bottom: -0.76rem;
            border: 1px solid var(--bbva-border-strong);
            border-radius: 14px;
            background: color-mix(in srgb, var(--bbva-surface) 84%, transparent);
            padding: 0.32rem 0.42rem 0.26rem 0.42rem;
            box-shadow: 0 8px 22px color-mix(in srgb, var(--bbva-text) 16%, transparent);
          }
          .st-key-workspace_nav_bar div[data-testid="stHorizontalBlock"] {
            margin-bottom: 0 !important;
            row-gap: 0 !important;
            align-items: center !important;
          }
          .st-key-workspace_nav_bar div[data-testid="stSegmentedControl"] {
            margin-bottom: 0 !important;
          }
          .st-key-workspace_nav_bar div[data-testid="stSegmentedControl"] button,
          .st-key-workspace_nav_bar div[data-testid="stSegmentedControl"] label,
          .st-key-workspace_nav_bar div[data-testid="stSegmentedControl"] [role="radio"] {
            background: var(--bbva-tab-soft-bg) !important;
            border-color: var(--bbva-tab-soft-border) !important;
            color: var(--bbva-tab-soft-text) !important;
          }
          .st-key-workspace_nav_bar div[data-testid="stSegmentedControl"] button[aria-pressed="true"],
          .st-key-workspace_nav_bar
            div[data-testid="stSegmentedControl"]
            [role="radio"][aria-checked="true"],
          .st-key-workspace_nav_bar div[data-testid="stSegmentedControl"] label:has(input:checked) {
            background: var(--bbva-tab-active-bg) !important;
            border-color: var(--bbva-tab-active-border) !important;
            color: var(--bbva-tab-active-text) !important;
          }
          .st-key-workspace_dashboard_content {
            margin-top: -0.24rem;
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
          }
          div[data-baseweb="popover"] [role="option"],
          div[data-baseweb="popover"] li {
            color: var(--bbva-text) !important;
            background: transparent !important;
          }
          div[data-baseweb="popover"] [role="option"]:hover,
          div[data-baseweb="popover"] li:hover {
            background: color-mix(in srgb, var(--bbva-primary) 14%, transparent) !important;
          }
          div[data-baseweb="popover"] [role="option"][aria-selected="true"] {
            background: color-mix(in srgb, var(--bbva-primary) 20%, transparent) !important;
            color: var(--bbva-text) !important;
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

          /* Download button: same quiet language as segmented controls */
          .stDownloadButton > button {
            min-height: 2.15rem !important;
            padding: 0.35rem 0.78rem !important;
            border-radius: 10px !important;
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

          /* Tabs: underline accent color */
          div[data-baseweb="tab-list"] {
            gap: 8px;
          }
          [role="tablist"] button[role="tab"] {
            color: var(--bbva-tab-soft-text) !important;
            background: var(--bbva-tab-soft-bg) !important;
            border: 1px solid var(--bbva-tab-soft-border) !important;
            border-radius: 10px !important;
            min-height: 2.08rem !important;
            padding: 0.28rem 0.80rem !important;
            font-weight: 700 !important;
          }
          [role="tablist"] button[role="tab"] * {
            color: inherit !important;
          }
          [role="tablist"] button[role="tab"][aria-selected="true"] {
            color: var(--bbva-tab-active-text) !important;
            background: var(--bbva-tab-active-bg) !important;
            border-color: var(--bbva-tab-active-border) !important;
          }
          div[data-baseweb="tab-highlight"] {
            background-color: transparent !important;
          }
          [role="tablist"] button[role="tab"]:focus-visible {
            outline: none !important;
            box-shadow: 0 0 0 3px rgba(0,81,241,0.18) !important;
            border-radius: var(--bbva-radius-m) !important;
          }
          div[data-baseweb="tab-list"] button,
          div[data-testid="stTabs"] [role="tablist"] button {
            color: var(--bbva-tab-soft-text) !important;
            background: var(--bbva-tab-soft-bg) !important;
            border: 1px solid var(--bbva-tab-soft-border) !important;
            border-radius: 10px !important;
          }
          div[data-baseweb="tab-list"] button[aria-selected="true"],
          div[data-testid="stTabs"] [role="tablist"] button[aria-selected="true"] {
            color: var(--bbva-tab-active-text) !important;
            background: var(--bbva-tab-active-bg) !important;
            border-color: var(--bbva-tab-active-border) !important;
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
          [data-testid="stExpander"] summary * {
            color: var(--bbva-text) !important;
            opacity: 1 !important;
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
        </style>
        """
    st.markdown(
        css_template.replace("__CSS_VARS__", css_vars),
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
    text_color = "#EAF0FF" if dark_mode else "#11192D"
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
        "resolution_days": "Dias de resolucion",
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
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family='"BBVA Benton Sans","Benton Sans","Inter",system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif',
            color=text_color,
        ),
        colorway=[
            "#0051F1",  # Electric Blue (primary)
            "#2165CA",  # Royal Blue Dark
            "#0C6DFF",  # Royal Blue
            "#53A9EF",  # Serene Dark Blue
            "#85C8FF",  # Serene Blue
            "#D6E9FF",  # Light Blue
            "#070E46",  # Midnight Blue
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
            title=dict(font=dict(color=text_color)),
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
            trace.showlegend = bool(showlegend and trace.name)
            if hasattr(trace, "textfont"):
                trace.textfont = dict(color=text_color)
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
