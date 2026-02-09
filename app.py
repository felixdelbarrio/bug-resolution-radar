from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings, ensure_env, load_settings, save_settings
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.kpis import compute_kpis
from bug_resolution_radar.notes import NotesStore
from bug_resolution_radar.schema import IssuesDocument
from bug_resolution_radar.security import consent_banner


def _load_doc(path: str) -> IssuesDocument:
    p = Path(path)
    if not p.exists():
        return IssuesDocument.empty()
    return IssuesDocument.model_validate_json(p.read_text(encoding="utf-8"))


def _save_doc(path: str, doc: IssuesDocument) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")


def _df_from_doc(doc: IssuesDocument) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = [i.model_dump() for i in doc.issues]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ["created", "updated", "resolved"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")
    return df


def main() -> None:
    ensure_env()
    settings: Settings = load_settings()

    st.set_page_config(page_title=settings.APP_TITLE, layout="wide")
    st.title(settings.APP_TITLE)
    consent_banner()

    tabs = st.tabs(["⚙️ Configuración", "⬇️ Ingesta", "📊 Dashboard"])

    with tabs[0]:
        st.subheader("Configuración (persistente en .env; NO guarda cookies)")
        c1, c2 = st.columns(2)

        with c1:
            jira_base = st.text_input("Jira Base URL", value=settings.JIRA_BASE_URL)
            jira_project = st.text_input("PROJECT_KEY", value=settings.JIRA_PROJECT_KEY)
            jira_jql = st.text_area("JQL (opcional)", value=settings.JIRA_JQL, height=80)

        with c2:
            jira_domain = st.text_input("Dominio cookie Jira", value=settings.JIRA_COOKIE_DOMAIN)
            jira_browser = st.selectbox(
                "Navegador (lectura cookie)",
                options=["chrome", "edge"],
                index=0 if settings.JIRA_BROWSER == "chrome" else 1,
            )
            crit_map = st.text_area(
                "CRITICALITY_MAP (formato: JiraPriority:Crit; separa por comas)",
                value=settings.CRITICALITY_MAP,
                height=80,
            )
            master_label = st.text_input("Label 'maestra'", value=settings.MASTER_LABEL)
            master_thr = st.number_input(
                "Threshold affected_clients_count para 'maestra'",
                min_value=0,
                value=int(settings.MASTER_AFFECTED_CLIENTS_THRESHOLD),
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
                    JIRA_COOKIE_DOMAIN=jira_domain.strip(),
                    JIRA_BROWSER=jira_browser,
                    CRITICALITY_MAP=crit_map.strip(),
                    MASTER_LABEL=master_label.strip(),
                    MASTER_AFFECTED_CLIENTS_THRESHOLD=str(master_thr),
                    KPI_FORTNIGHT_DAYS=str(fort),
                    KPI_MONTH_DAYS=str(month),
                    KPI_OPEN_AGE_X_DAYS=open_age.strip(),
                    KPI_AGE_BUCKETS=age_buckets.strip(),
                )
            )
            save_settings(new_settings)
            st.success("Configuración guardada en .env (cookies NO se guardan).")

    with tabs[1]:
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

        doc = _load_doc(settings.DATA_PATH)

        if test_jira:
            with st.spinner("Probando Jira..."):
                ok, msg = ingest_jira(settings=settings, cookie_manual=jira_cookie_manual or None, dry_run=True)
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
                _save_doc(settings.DATA_PATH, new_doc)
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

    with tabs[2]:
        st.subheader("Dashboard")
        doc = _load_doc(settings.DATA_PATH)
        df = _df_from_doc(doc)

        notes = NotesStore(Path(settings.NOTES_PATH))
        notes.load()

        if df.empty:
            st.warning("No hay datos todavía. Ve a la pestaña de Ingesta y ejecuta una ingesta.")
            return

        st.markdown("### Filtros")
        f1, f2, f3, f4, f5 = st.columns(5)
        with f1:
            status = st.multiselect("Estado", sorted(df["status"].dropna().unique().tolist()), default=None)
        with f2:
            crit = st.multiselect("Criticidad", sorted(df["criticality"].dropna().unique().tolist()), default=None)
        with f3:
            itype = st.multiselect("Tipo", sorted(df["type"].dropna().unique().tolist()), default=None)
        with f4:
            comp = st.multiselect(
                "Componente",
                sorted({c for lst in df["components"].dropna().tolist() for c in (lst or [])}),
                default=None,
            )
        with f5:
            assignee = st.multiselect("Asignado", sorted(df["assignee"].dropna().unique().tolist()), default=None)

        master_only = st.checkbox("Solo maestras", value=False)

        dff = df.copy()
        if status:
            dff = dff[dff["status"].isin(status)]
        if crit:
            dff = dff[dff["criticality"].isin(crit)]
        if itype:
            dff = dff[dff["type"].isin(itype)]
        if comp:
            dff = dff[dff["components"].apply(lambda xs: any(x in (xs or []) for x in comp))]
        if assignee:
            dff = dff[dff["assignee"].isin(assignee)]
        if master_only:
            dff = dff[dff["is_master"] == True]  # noqa: E712

        kpis = compute_kpis(dff, settings=settings)
        st.markdown("### KPIs")
        kcol1, kcol2, kcol3 = st.columns(3)
        with kcol1:
            st.metric("Abiertas actuales", int(kpis["open_now_total"]))
            st.caption(kpis["open_now_by_criticality"])
        with kcol2:
            st.metric("Nuevas (quincena)", int(kpis["new_fortnight_total"]))
            st.caption(kpis["new_fortnight_by_criticality"])
        with kcol3:
            st.metric("Cerradas (quincena)", int(kpis["closed_fortnight_total"]))
            st.caption(kpis["closed_fortnight_by_resolution_type"])

        kcol4, kcol5, kcol6 = st.columns(3)
        with kcol4:
            st.metric("Tiempo medio resolución (días)", f'{kpis["mean_resolution_days"]:.1f}')
            st.caption(kpis["mean_resolution_days_by_criticality"])
        with kcol5:
            st.metric("% abiertas > X días", kpis["pct_open_gt_x_days"])
        with kcol6:
            st.metric("Top 10 abiertas", "ver tabla")

        st.markdown("### Evolución (últimos 90 días)")
        st.plotly_chart(kpis["timeseries_chart"], use_container_width=True)

        st.markdown("### Distribución antigüedad (abiertas)")
        st.plotly_chart(kpis["age_buckets_chart"], use_container_width=True)

        st.markdown("### Top 10 problemas/funcionalidades (abiertas)")
        st.dataframe(kpis["top_open_table"], use_container_width=True, hide_index=True)

        st.markdown("### Listado (drill-down) + notas locales")
        show_cols = [
            "key","summary","status","criticality","type","priority",
            "created","updated","resolved","assignee","components","labels","is_master","affected_clients_count","url"
        ]
        show_cols = [c for c in show_cols if c in dff.columns]
        st.dataframe(dff[show_cols].sort_values(by="updated", ascending=False), use_container_width=True)

        st.markdown("#### Editar nota local")
        issue_key = st.selectbox("Issue", dff["key"].tolist())
        current = notes.get(issue_key) or ""
        new_note = st.text_area("Nota (local)", value=current, height=120)
        if st.button("💾 Guardar nota"):
            notes.set(issue_key, new_note)
            notes.save()
            st.success("Nota guardada localmente.")


if __name__ == "__main__":
    main()
