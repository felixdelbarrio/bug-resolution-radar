from __future__ import annotations

import html
from typing import Any

import streamlit as st


def inject_bbva_css() -> None:
    """Inject BBVA-like CSS styling into Streamlit app."""
    st.markdown(
        """
        <style>
          :root {
            --bbva-primary: #0051F1;   /* Electric Blue */
            --bbva-midnight: #070E46;  /* Midnight Blue */
            --bbva-text: #11192D;      /* Grey 900 */
            --bbva-surface: #FFFFFF;
            --bbva-surface-2: #F4F6F9; /* Light neutral */
            --bbva-border: rgba(17,25,45,0.12);
            --bbva-border-strong: rgba(17,25,45,0.18);
            --bbva-radius-s: 4px;
            --bbva-radius-m: 8px;
            --bbva-radius-l: 12px;
            --bbva-radius-xl: 16px;

            /* Streamlit theme variables (force consistency; avoids odd defaults). */
            --primary-color: var(--bbva-primary);
            --text-color: var(--bbva-text);
            --background-color: var(--bbva-surface-2);
            --secondary-background-color: var(--bbva-surface);
          }

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
            padding-top: 0.75rem;
            padding-bottom: 2.0rem;
            max-width: 1200px;
          }

          /* Hero band */
          .bbva-hero {
            background: var(--bbva-midnight);
            border-radius: var(--bbva-radius-xl);
            padding: 22px 22px;
            margin: 10px 0 18px 0;
            color: #ffffff;
            border: 1px solid rgba(255,255,255,0.08);
          }
          .bbva-hero-title {
            margin: 0;
            font-size: 44px;
            line-height: 1.08;
            font-weight: 700;
            color: #ffffff;
          }
          .bbva-hero-sub {
            margin-top: 8px;
            opacity: 0.82;
            font-size: 14px;
          }

          /* Native Streamlit header: blend in */
          header[data-testid="stHeader"] {
            background: transparent;
          }
          header[data-testid="stHeader"] * { color: inherit !important; }

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
            color: rgba(17,25,45,0.82) !important;
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
          .stTextInput input::placeholder,
          .stTextArea textarea::placeholder {
            color: rgba(17,25,45,0.45) !important;
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
            color: rgba(17,25,45,0.88) !important;
            font-weight: 700 !important;
          }
          .stButton > button[kind="secondary"]:hover {
            border-color: rgba(0,81,241,0.35) !important;
            background: rgba(0,81,241,0.06) !important;
          }
          .stButton > button:disabled {
            opacity: 0.45 !important;
            cursor: not-allowed !important;
          }

          /* Pills */
          div[data-testid="stPills"] button {
            background: var(--bbva-surface) !important;
            border: 1px solid var(--bbva-border) !important;
            color: rgba(17,25,45,0.88) !important;
            border-radius: 999px !important;
          }
          div[data-testid="stPills"] button span,
          div[data-testid="stPills"] button p {
            color: rgba(17,25,45,0.88) !important;
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
          div[data-baseweb="tab"] button {
            color: rgba(17,25,45,0.72) !important;
            font-weight: 700 !important;
          }
          div[data-baseweb="tab"] button[aria-selected="true"] {
            color: var(--bbva-primary) !important;
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

          /* Links */
          a, a:visited { color: var(--bbva-primary); }

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
            opacity: 0.95;
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(app_title: str) -> None:
    """Render a top hero section."""
    st.markdown(
        f"""
        <div class="bbva-hero">
          <div class="bbva-hero-title">{html.escape(app_title)}</div>
          <div class="bbva-hero-sub">Análisis y seguimiento de incidencias basado en Jira</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_plotly_bbva(fig: Any) -> Any:
    """Apply a consistent Plotly style aligned with BBVA Experience."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family='"BBVA Benton Sans","Benton Sans","Inter",system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif',
            color="#11192D",
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
        legend=dict(bgcolor="rgba(255,255,255,0.65)"),
        margin=dict(l=16, r=16, t=48, b=16),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(17,25,45,0.10)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(17,25,45,0.10)", zeroline=False)
    return fig
