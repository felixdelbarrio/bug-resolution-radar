from __future__ import annotations

import streamlit as st

from bug_resolution_radar.config import Settings, save_settings


def render(settings: Settings) -> None:
    st.subheader("Configuración (persistente en .env; NO guarda cookies)")

    c1, c2 = st.columns(2)

    with c1:
        jira_base = st.text_input("Jira Base URL", value=settings.JIRA_BASE_URL)
        jira_project = st.text_input("PROJECT_KEY", value=settings.JIRA_PROJECT_KEY)
        jira_jql = st.text_area("JQL (opcional)", value=settings.JIRA_JQL, height=80)

    with c2:
        jira_browser = st.selectbox(
            "Navegador (lectura cookie)",
            options=["chrome", "edge"],
            index=0 if settings.JIRA_BROWSER == "chrome" else 1,
        )

    k1, k2, k3 = st.columns(3)
    with k1:
        fort = st.number_input("Días quincena (rodante)", min_value=1, value=int(settings.KPI_FORTNIGHT_DAYS))
    with k2:
        month = st.number_input("Días mes (rodante)", min_value=1, value=int(settings.KPI_MONTH_DAYS))
    with k3:
        open_age = st.text_input("X días para '% abiertas > X' (coma)", value=settings.KPI_OPEN_AGE_X_DAYS)

    age_buckets = st.text_input("Buckets antigüedad (0-2,3-7,8-14,15-30,>30)", value=settings.KPI_AGE_BUCKETS)

    if st.button("💾 Guardar configuración"):
        new_settings = settings.model_copy(
            update=dict(
                JIRA_BASE_URL=jira_base.strip(),
                JIRA_PROJECT_KEY=jira_project.strip(),
                JIRA_JQL=jira_jql.strip(),
                JIRA_BROWSER=jira_browser,
                KPI_FORTNIGHT_DAYS=str(fort),
                KPI_MONTH_DAYS=str(month),
                KPI_OPEN_AGE_X_DAYS=open_age.strip(),
                KPI_AGE_BUCKETS=age_buckets.strip(),
            )
        )
        save_settings(new_settings)
        st.success("Configuración guardada en .env (cookies NO se guardan).")