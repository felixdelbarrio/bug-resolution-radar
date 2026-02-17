from __future__ import annotations

import streamlit as st

from bug_resolution_radar.config import ensure_env, load_settings
from bug_resolution_radar.security import consent_banner
from bug_resolution_radar.ui.pages import config_page, dashboard_page, ingest_page
from bug_resolution_radar.ui.style import inject_bbva_css, render_hero


def main() -> None:
    ensure_env()
    settings = load_settings()

    st.set_page_config(
        page_title=settings.APP_TITLE, layout="wide", page_icon="assets/bbva/favicon.png"
    )
    st.logo("assets/bbva/logo.png", size="medium")

    consent_banner()
    inject_bbva_css()
    render_hero(settings.APP_TITLE)

    tabs = st.tabs(["📊 Dashboard", "⬇️ Ingesta", "⚙️ Configuración"])

    with tabs[0]:
        dashboard_page.render(settings)

    with tabs[1]:
        ingest_page.render(settings)

    with tabs[2]:
        config_page.render(settings)
