from __future__ import annotations

from pathlib import Path

import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ingest.helix_ingest import ingest_helix
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.schema_helix import HelixDocument
from bug_resolution_radar.ui.common import load_issues_doc, save_issues_doc


def _get_helix_path(settings: Settings) -> str:
    # Prefer config (HELIX_DATA_PATH). Fallback to a sensible default.
    p = (getattr(settings, "HELIX_DATA_PATH", "") or "").strip()
    return p or "data/helix.json"


def render(settings: Settings) -> None:
    # Sub-tabs inside ingestion page
    t_jira, t_helix = st.tabs(["🟦 Jira", "🟩 Helix"])

    # -----------------------------
    # Jira
    # -----------------------------
    with t_jira:
        colA, colB = st.columns([1, 1])
        with colA:
            test_jira = st.button("🔎 Test conexión Jira", key="btn_test_jira")
        with colB:
            run_jira = st.button("⬇️ Reingestar Jira ahora", key="btn_run_jira")

        doc = load_issues_doc(settings.DATA_PATH)

        if test_jira:
            with st.spinner("Probando Jira..."):
                ok, msg, _ = ingest_jira(
                    settings=settings,
                    dry_run=True,
                )
            (st.success if ok else st.error)(msg)

        if run_jira:
            with st.spinner("Ingestando Jira..."):
                ok, msg, new_jira_doc = ingest_jira(
                    settings=settings,
                    dry_run=False,
                    existing_doc=doc,
                )
            if ok and new_jira_doc is not None:
                save_issues_doc(settings.DATA_PATH, new_jira_doc)
                st.success(f"{msg}. Guardado en {settings.DATA_PATH}")
            else:
                st.error(msg)

        st.markdown("---")
        st.markdown("### Última ingesta (Jira)")
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

    # -----------------------------
    # Helix
    # -----------------------------
    with t_helix:
        helix_base_url = (getattr(settings, "HELIX_BASE_URL", "") or "").strip()
        helix_org = (getattr(settings, "HELIX_ORGANIZATION", "") or "").strip()
        helix_browser = (getattr(settings, "HELIX_BROWSER", "chrome") or "chrome").strip()
        helix_proxy = (getattr(settings, "HELIX_PROXY", "") or "").strip()
        helix_ssl_verify = (getattr(settings, "HELIX_SSL_VERIFY", "") or "").strip()

        helix_path = _get_helix_path(settings)
        helix_repo = HelixRepo(Path(helix_path))

        helix_doc = helix_repo.load() or HelixDocument.empty()

        colH1, colH2 = st.columns([1, 1])
        with colH1:
            test_helix = st.button("🔎 Test conexión Helix", key="btn_test_helix")
        with colH2:
            run_helix = st.button("⬇️ Reingestar Helix ahora", key="btn_run_helix")

        if test_helix:
            with st.spinner("Probando Helix..."):
                ok, msg, _ = ingest_helix(
                    helix_base_url=helix_base_url,
                    browser=helix_browser,
                    organization=helix_org,
                    proxy=helix_proxy,
                    ssl_verify=helix_ssl_verify,
                    dry_run=True,
                    existing_doc=helix_doc,
                )
            (st.success if ok else st.error)(msg)

        if run_helix:
            with st.spinner("Ingestando Helix... (puede tardar con proxy)"):
                ok, msg, new_helix_doc = ingest_helix(
                    helix_base_url=helix_base_url,
                    browser=helix_browser,
                    organization=helix_org,
                    proxy=helix_proxy,
                    ssl_verify=helix_ssl_verify,
                    dry_run=False,
                    existing_doc=helix_doc,
                )
            if ok and new_helix_doc is not None:
                helix_repo.save(new_helix_doc)
                st.success(f"{msg}. Guardado en {helix_path}")
                helix_doc = new_helix_doc
            else:
                st.error(msg)

        st.markdown("---")
        st.markdown("### Última ingesta (Helix)")
        st.json(
            {
                "schema_version": helix_doc.schema_version,
                "ingested_at": helix_doc.ingested_at,
                "helix_base_url": helix_doc.helix_base_url,
                "query": helix_doc.query,
                "items_count": len(helix_doc.items),
                "data_path": helix_path,
            }
        )
