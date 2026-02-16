from __future__ import annotations

import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.ui.common import load_issues_doc, save_issues_doc


def render(settings: Settings) -> None:
    st.subheader("Ingesta (solo Jira)")
    st.caption("Las llamadas se hacen directamente a Jira desde tu máquina. No hay backend.")
    st.info(
        "Consentimiento: Se leerán cookies locales del navegador solo para autenticar tu sesión personal hacia Jira. "
        "No se envían a terceros."
    )

    jira_cookie_manual = st.text_input(
        "Fallback: pegar cookie (header Cookie) manualmente (solo memoria, NO persistente)",
        value="",
        type="password",
        help="Ejemplo: atlassian.xsrf.token=...; cloud.session.token=... (solo si tu entorno lo requiere)",
    )

    colA, colB = st.columns([1, 1])
    with colA:
        test_jira = st.button("🔎 Test conexión Jira")
    with colB:
        run_jira = st.button("⬇️ Reingestar Jira ahora")

    doc = load_issues_doc(settings.DATA_PATH)

    if test_jira:
        with st.spinner("Probando Jira..."):
            ok, msg, _ = ingest_jira(settings=settings, cookie_manual=jira_cookie_manual or None, dry_run=True)
        (st.success if ok else st.error)(msg)

    if run_jira:
        with st.spinner("Ingestando Jira..."):
            ok, msg, new_doc = ingest_jira(
                settings=settings,
                cookie_manual=jira_cookie_manual or None,
                dry_run=False,
                existing_doc=doc,
            )
        if ok and new_doc is not None:
            save_issues_doc(settings.DATA_PATH, new_doc)
            st.success(f"{msg}. Guardado en {settings.DATA_PATH}")
        else:
            st.error(msg)

    st.markdown("---")
    st.markdown("### Última ingesta")
    st.json(
        {
            "schema_version": doc.schema_version,
            "ingested_at": doc.ingested_at,
            "jira_base_url": doc.jira_base_url,
            "project_key": doc.project_key,
            "query": doc.query,
            "issues_count": len(doc.issues),
        }
    )