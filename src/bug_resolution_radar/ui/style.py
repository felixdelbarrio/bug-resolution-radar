from __future__ import annotations

import html
from typing import Any

import streamlit as st

from bug_resolution_radar.ui.common import flow_signal_color_map


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
            --bbva-tab-soft-bg: #E9EEF4;      /* cool grey-blue */
            --bbva-tab-soft-border: #C7D2DF;  /* muted border */
            --bbva-tab-soft-text: #44546B;    /* desaturated ink */
            --bbva-tab-active-bg: #6F839E;    /* muted steel blue */
            --bbva-tab-active-border: #657A94;
            --bbva-tab-active-text: #F8FBFF;

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
          div[data-testid="stSegmentedControl"] label {
            min-height: 2.15rem !important;
            padding: 0.35rem 0.78rem !important;
            border-radius: 10px !important;
            font-weight: 700 !important;
            border: 1px solid var(--bbva-tab-soft-border) !important;
            background: var(--bbva-tab-soft-bg) !important;
            color: var(--bbva-tab-soft-text) !important;
          }
          div[data-testid="stSegmentedControl"] label:has(input:checked) {
            border-color: var(--bbva-tab-active-border) !important;
            background: var(--bbva-tab-active-bg) !important;
            color: var(--bbva-tab-active-text) !important;
          }
          div[data-testid="stSegmentedControl"] label:hover {
            filter: brightness(0.99);
          }
          div[data-testid="stButton"] > button[aria-label="🛰️"],
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
            border: 1px solid var(--bbva-border);
            border-radius: 14px;
            background: rgba(255,255,255,0.56);
            padding: 0.32rem 0.42rem 0.26rem 0.42rem;
            box-shadow: 0 1px 6px rgba(17,25,45,0.035);
          }
          .st-key-workspace_nav_bar div[data-testid="stHorizontalBlock"] {
            margin-bottom: 0 !important;
            row-gap: 0 !important;
            align-items: center !important;
          }
          .st-key-workspace_nav_bar div[data-testid="stSegmentedControl"] {
            margin-bottom: 0 !important;
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
            background: #e2e8ef !important;
            border-color: #bcc8d6 !important;
          }
          .stDownloadButton > button:disabled {
            opacity: 0.45 !important;
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
          <div class="bbva-hero-sub">Análisis y seguimiento de incidencias</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_plotly_bbva(fig: Any, *, showlegend: bool = False) -> Any:
    """Apply a consistent Plotly style aligned with BBVA Experience."""
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
        showlegend=showlegend,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.22,
            xanchor="right",
            x=1.0,
            bgcolor="rgba(255,255,255,0.65)",
            bordercolor="rgba(17,25,45,0.12)",
            borderwidth=1,
            font=dict(size=11),
        ),
        margin=dict(l=16, r=16, t=48, b=legend_bottom_space),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(17,25,45,0.10)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(17,25,45,0.10)", zeroline=False)
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
    except Exception:
        pass

    # Defensive cleanup to avoid "undefined" noise in hover/labels.
    for trace in getattr(fig, "data", []):
        try:
            trace.name = _localize(getattr(trace, "name", ""))
            trace.showlegend = bool(showlegend and trace.name)
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
