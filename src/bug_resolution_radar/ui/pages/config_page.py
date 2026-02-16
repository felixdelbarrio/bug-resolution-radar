from __future__ import annotations

from typing import Any

import streamlit as st

from bug_resolution_radar.config import Settings, save_settings


def _boolish(value: Any, default: bool = True) -> bool:
    """Acepta bool o strings tipo: true/false, 1/0, yes/no, on/off."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


def render(settings: Settings) -> None:
    st.subheader("Configuración (persistente en .env; NO guarda cookies)")

    # Tabs like Ingest: Jira / Helix / KPIs
    t_jira, t_helix, t_kpis = st.tabs(["🟦 Jira", "🟩 Helix", "📊 KPIs"])

    # -------------------------
    # Jira tab
    # -------------------------
    with t_jira:
        st.markdown("### Jira")

        c1, c2 = st.columns(2)
        with c1:
            jira_base = st.text_input("Jira Base URL", value=settings.JIRA_BASE_URL, key="cfg_jira_base")
            jira_project = st.text_input("PROJECT_KEY", value=settings.JIRA_PROJECT_KEY, key="cfg_jira_project")
            jira_jql = st.text_area("JQL (opcional)", value=settings.JIRA_JQL, height=120, key="cfg_jira_jql")

        with c2:
            jira_browser = st.selectbox(
                "Navegador Jira (lectura cookie)",
                options=["chrome", "edge"],
                index=0 if settings.JIRA_BROWSER == "chrome" else 1,
                key="cfg_jira_browser",
            )

    # -------------------------
    # Helix tab
    # -------------------------
    with t_helix:
        st.markdown("### Helix")

        helix_base_default = getattr(settings, "HELIX_BASE_URL", "") or ""
        helix_org_default = getattr(settings, "HELIX_ORGANIZATION", "") or ""
        helix_path_default = getattr(settings, "HELIX_DATA_PATH", "") or ""
        helix_proxy_default = getattr(settings, "HELIX_PROXY", "") or ""
        helix_browser_default = getattr(settings, "HELIX_BROWSER", "chrome") or "chrome"
        helix_ssl_default = getattr(settings, "HELIX_SSL_VERIFY", True)

        c1, c2 = st.columns(2)
        with c1:
            helix_base = st.text_input(
                "Helix Base URL",
                value=helix_base_default,
                key="cfg_helix_base",
            )
            helix_org = st.text_input(
                "Helix Organization",
                value=helix_org_default,
                key="cfg_helix_org",
            )
            helix_data_path = st.text_input(
                "Helix Data Path",
                value=helix_path_default,
                help="Ruta local donde se guarda el dump JSON de Helix.",
                key="cfg_helix_data_path",
            )

        with c2:
            helix_browser = st.selectbox(
                "Navegador Helix (lectura cookie)",
                options=["chrome", "edge"],
                index=0 if helix_browser_default == "chrome" else 1,
                key="cfg_helix_browser",
            )
            helix_proxy = st.text_input(
                "Helix Proxy (opcional)",
                value=helix_proxy_default,
                help="Ej: http://127.0.0.1:8999 (si tu navegador usa proxy local para Helix)",
                key="cfg_helix_proxy",
            )
            helix_ssl_verify = st.selectbox(
                "Helix SSL verify",
                options=["true", "false"],
                index=0 if _boolish(helix_ssl_default, default=True) else 1,
                help="Pon false si estás detrás de inspección SSL corporativa o si tu proxy rompe el certificado.",
                key="cfg_helix_ssl_verify",
            )

    # -------------------------
    # KPI tab
    # -------------------------
    with t_kpis:
        st.markdown("### KPIs")

        k1, k2, k3 = st.columns(3)
        with k1:
            fort = st.number_input(
                "Días quincena (rodante)",
                min_value=1,
                value=int(settings.KPI_FORTNIGHT_DAYS),
                key="cfg_kpi_fortnight",
            )
        with k2:
            month = st.number_input(
                "Días mes (rodante)",
                min_value=1,
                value=int(settings.KPI_MONTH_DAYS),
                key="cfg_kpi_month",
            )
        with k3:
            open_age = st.text_input(
                "X días para '% abiertas > X' (coma)",
                value=settings.KPI_OPEN_AGE_X_DAYS,
                key="cfg_kpi_open_age",
            )

        age_buckets = st.text_input(
            "Buckets antigüedad (0-2,3-7,8-14,15-30,>30)",
            value=settings.KPI_AGE_BUCKETS,
            key="cfg_kpi_age_buckets",
        )

    st.markdown("---")

    # -------------------------
    # Save (single button applies all tabs)
    # -------------------------
    if st.button("💾 Guardar configuración", key="cfg_save_btn"):
        new_settings = settings.model_copy(
            update=dict(
                # Jira
                JIRA_BASE_URL=jira_base.strip(),
                JIRA_PROJECT_KEY=jira_project.strip(),
                JIRA_JQL=jira_jql.strip(),
                JIRA_BROWSER=jira_browser,
                # KPIs
                KPI_FORTNIGHT_DAYS=str(fort),
                KPI_MONTH_DAYS=str(month),
                KPI_OPEN_AGE_X_DAYS=open_age.strip(),
                KPI_AGE_BUCKETS=age_buckets.strip(),
                # Helix
                HELIX_BASE_URL=str(helix_base).strip(),
                HELIX_ORGANIZATION=str(helix_org).strip(),
                HELIX_BROWSER=str(helix_browser).strip(),
                HELIX_DATA_PATH=str(helix_data_path).strip(),
                HELIX_PROXY=str(helix_proxy).strip(),
                HELIX_SSL_VERIFY=str(helix_ssl_verify).strip().lower(),
            )
        )
        save_settings(new_settings)
        st.success("Configuración guardada en .env (cookies NO se guardan).")