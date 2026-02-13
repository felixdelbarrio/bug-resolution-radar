from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import streamlit as st

from bug_resolution_radar.config import Settings, ensure_env, load_settings, save_settings
from bug_resolution_radar.ingest.helix_ingest import ingest_helix
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.insights import find_similar_issue_clusters
from bug_resolution_radar.kpis import compute_kpis
from bug_resolution_radar.notes import NotesStore
from bug_resolution_radar.schema import IssuesDocument
from bug_resolution_radar.schema_helix import HelixDocument
from bug_resolution_radar.security import consent_banner


def _boolish(value: Any, default: bool = True) -> bool:
    """
    Acepta bool o strings tipo: true/false, 1/0, yes/no, on/off.
    """
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


def _load_doc(path: str) -> IssuesDocument:
    p = Path(path)
    if not p.exists():
        return IssuesDocument.empty()
    return IssuesDocument.model_validate_json(p.read_text(encoding="utf-8"))


def _save_doc(path: str, doc: IssuesDocument) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(doc.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")


def _load_helix_doc(path: str) -> HelixDocument:
    p = Path(path)
    if not p.exists():
        return HelixDocument.empty()
    return HelixDocument.model_validate_json(p.read_text(encoding="utf-8"))


def _save_helix_doc(path: str, doc: HelixDocument) -> None:
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


def _inject_card_css() -> None:
    st.markdown(
        """
        <style>
          :root {
            --bbva-primary: #0051F1;
            --bbva-midnight: #070E46;
            --bbva-text: #11192D;
            --bbva-surface: #FFFFFF;
            --bbva-surface-2: #F4F6F9;
            --bbva-border: rgba(17,25,45,0.12);
            --bbva-border-strong: rgba(17,25,45,0.18);
            --bbva-radius-s: 4px;
            --bbva-radius-m: 8px;
            --bbva-radius-l: 12px;
            --bbva-radius-xl: 16px;

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

          .bbva-hero-title {
            font-family: "Tiempos Headline", "Tiempos Headline Bold", Georgia, "Times New Roman", serif;
            letter-spacing: -0.01em;
          }

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

          header[data-testid="stHeader"] { background: transparent; }
          header[data-testid="stHeader"] * { color: inherit !important; }

          section[data-testid="stSidebar"] {
            background: var(--bbva-surface);
            border-right: 1px solid var(--bbva-border);
          }
          section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] * {
            font-size: 14px;
          }

          .stButton > button,
          .stDownloadButton > button,
          .stTextInput input,
          .stTextArea textarea,
          .stSelectbox [data-baseweb="select"] > div,
          .stMultiSelect [data-baseweb="select"] > div {
            border-radius: var(--bbva-radius-m) !important;
          }

          label, [data-testid="stWidgetLabel"] p {
            color: rgba(17,25,45,0.82) !important;
            font-weight: 600 !important;
          }

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

          a, a:visited { color: var(--bbva-primary); }

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


def _priority_rank(p: str) -> int:
    order = ["highest", "high", "medium", "low", "lowest"]
    pl = (p or "").strip().lower()
    if pl in order:
        return order.index(pl)
    return 99


def _priority_color_map() -> Dict[str, str]:
    return {
        "Highest": "#FF5252",
        "High": "#FFB56B",
        "Medium": "#FFE761",
        "Low": "#88E783",
        "Lowest": "#9CE67E",
        "(sin priority)": "#E2E6EE",
        "": "#E2E6EE",
    }


def _matrix_set_filters(st_name: str, prio: str) -> None:
    st.session_state["filter_status"] = [st_name]
    st.session_state["filter_priority"] = [prio]


def _matrix_clear_filters() -> None:
    st.session_state["filter_status"] = []
    st.session_state["filter_priority"] = []


def _render_issue_cards(dff: pd.DataFrame, *, max_cards: int, title: str) -> None:
    st.markdown(f"### {title}")
    if dff.empty:
        st.info("No hay issues para mostrar con los filtros actuales.")
        return

    cols = ["key", "summary", "status", "priority", "assignee", "created", "updated", "resolved", "url"]
    for c in cols:
        if c not in dff.columns:
            dff[c] = None

    now = pd.Timestamp.utcnow()
    open_df = dff[dff["resolved"].isna()].copy()
    if "created" in open_df.columns:
        open_df["open_age_days"] = ((now - open_df["created"]).dt.total_seconds() / 86400.0).fillna(0.0)
    else:
        open_df["open_age_days"] = 0.0

    open_df["_prio_rank"] = open_df["priority"].astype(str).map(_priority_rank)
    open_df = open_df.sort_values(by=["_prio_rank", "updated"], ascending=[True, False]).head(max_cards)

    for _, r in open_df.iterrows():
        key = html.escape(str(r.get("key", "") or ""))
        url = html.escape(str(r.get("url", "") or ""))
        summary = html.escape(str(r.get("summary", "") or ""))
        status = html.escape(str(r.get("status", "") or ""))
        prio = html.escape(str(r.get("priority", "") or ""))
        assignee = html.escape(str(r.get("assignee", "") or ""))
        age = float(r.get("open_age_days") or 0.0)

        badges = []
        if prio:
            badges.append(f'<span class="badge badge-priority">Priority: {prio}</span>')
        if status:
            badges.append(f'<span class="badge badge-status">Status: {status}</span>')
        if assignee:
            badges.append(f'<span class="badge">Assignee: {assignee}</span>')
        badges.append(f'<span class="badge badge-age">Open age: {age:.0f}d</span>')

        st.markdown(
            f"""
            <div class="issue-card">
              <div class="issue-top">
                <div class="issue-key"><a href="{url}" target="_blank" rel="noopener noreferrer">{key}</a></div>
              </div>
              <div class="issue-summary">{summary}</div>
              <div class="badges">{''.join(badges)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")


def _apply_plotly_bbva(fig: Any) -> Any:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(
            family='"BBVA Benton Sans","Benton Sans","Inter",system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif',
            color="#11192D",
        ),
        colorway=["#0051F1", "#2165CA", "#0C6DFF", "#53A9EF", "#85C8FF", "#D6E9FF", "#070E46"],
        legend=dict(bgcolor="rgba(255,255,255,0.65)"),
        margin=dict(l=16, r=16, t=48, b=16),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(17,25,45,0.10)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(17,25,45,0.10)", zeroline=False)
    return fig


def main() -> None:
    ensure_env()
    settings: Settings = load_settings()

    st.set_page_config(page_title=settings.APP_TITLE, layout="wide", page_icon="assets/bbva/favicon.png")
    st.logo("assets/bbva/logo.png", size="medium")
    consent_banner()

    _inject_card_css()
    st.markdown(
        f"""
        <div class="bbva-hero">
          <div class="bbva-hero-title">{html.escape(settings.APP_TITLE)}</div>
          <div class="bbva-hero-sub">Análisis y seguimiento de incidencias basado en Jira</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tabs = st.tabs(["⚙️ Configuración", "⬇️ Ingesta", "📊 Dashboard"])

    with tabs[0]:
        st.subheader("Configuración (persistente en .env; NO guarda cookies)")
        c1, c2 = st.columns(2)

        with c1:
            jira_base = st.text_input("Jira Base URL", value=settings.JIRA_BASE_URL)
            jira_project = st.text_input("PROJECT_KEY", value=settings.JIRA_PROJECT_KEY)
            jira_jql = st.text_area("JQL (opcional)", value=settings.JIRA_JQL, height=80)

            st.markdown("#### Helix")
            helix_base = st.text_input("Helix Base URL", value=settings.HELIX_BASE_URL)
            helix_org = st.text_input("Helix Organization", value=settings.HELIX_ORGANIZATION)
            helix_data_path = st.text_input(
                "Helix Data Path",
                value=settings.HELIX_DATA_PATH,
                help="Ruta local donde se guarda el dump JSON de Helix.",
            )
            helix_proxy = st.text_input(
                "Helix Proxy (opcional)",
                value=settings.HELIX_PROXY,
                help="Ej: http://127.0.0.1:8999 (si tu navegador usa proxy local para Helix)",
            )
            helix_ssl_verify = st.selectbox(
                "Helix SSL verify",
                options=["true", "false"],
                index=0 if _boolish(getattr(settings, "HELIX_SSL_VERIFY", True), default=True) else 1,
                help="Pon false si estás detrás de inspección SSL corporativa o si tu proxy rompe el certificado.",
            )

        with c2:
            jira_browser = st.selectbox(
                "Navegador Jira (lectura cookie)",
                options=["chrome", "edge"],
                index=0 if settings.JIRA_BROWSER == "chrome" else 1,
            )
            helix_browser = st.selectbox(
                "Navegador Helix (lectura cookie)",
                options=["chrome", "edge"],
                index=0 if settings.HELIX_BROWSER == "chrome" else 1,
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
                    HELIX_BASE_URL=helix_base.strip(),
                    HELIX_ORGANIZATION=helix_org.strip(),
                    HELIX_BROWSER=helix_browser,
                    HELIX_DATA_PATH=helix_data_path.strip(),
                    HELIX_PROXY=helix_proxy.strip(),
                    HELIX_SSL_VERIFY=str(helix_ssl_verify).strip().lower(),
                )
            )
            save_settings(new_settings)
            st.success("Configuración guardada en .env (cookies NO se guardan).")

    with tabs[1]:
        st.subheader("Ingesta (Jira y Helix)")
        st.caption("Las llamadas se hacen directamente desde tu máquina. No hay backend.")
        st.info(
            "Consentimiento: Se leerán cookies locales del navegador solo para autenticar tu sesión personal hacia Jira/Helix. "
            "No se envían a terceros."
        )

        # Jira
        st.markdown("### Jira")
        jira_cookie_manual = st.text_input(
            "Fallback Jira: pegar cookie (header Cookie) manualmente (solo memoria, NO persistente)",
            value="",
            type="password",
        )

        colA, colB = st.columns([1, 1])
        with colA:
            test_jira = st.button("🔎 Test conexión Jira")
        with colB:
            run_jira = st.button("⬇️ Reingestar Jira ahora")

        doc = _load_doc(settings.DATA_PATH)

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
                _save_doc(settings.DATA_PATH, new_doc)
                st.success(f"{msg}. Guardado en {settings.DATA_PATH}")
            else:
                st.error(msg)

        st.markdown("#### Última ingesta Jira")
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

        # Helix
        st.markdown("---")
        st.markdown("### Helix")

        helix_cookie_manual = st.text_input(
            "Fallback Helix: pegar cookie (header Cookie) manualmente (solo memoria, NO persistente)",
            value="",
            type="password",
        )

        hcolA, hcolB = st.columns([1, 1])
        with hcolA:
            test_helix = st.button("🔎 Test conexión Helix")
        with hcolB:
            run_helix = st.button("⬇️ Reingestar Helix ahora")

        helix_data_path = settings.HELIX_DATA_PATH
        helix_doc = _load_helix_doc(helix_data_path)

        if test_helix:
            with st.spinner("Probando Helix..."):
                ok, msg, _ = ingest_helix(
                    helix_base_url=settings.HELIX_BASE_URL,
                    browser=settings.HELIX_BROWSER,
                    organization=settings.HELIX_ORGANIZATION,
                    proxy=settings.HELIX_PROXY,
                    ssl_verify=settings.HELIX_SSL_VERIFY,
                    cookie_manual=helix_cookie_manual or None,
                    dry_run=True,
                )
            (st.success if ok else st.error)(msg)

        if run_helix:
            with st.spinner("Ingestando Helix..."):
                ok, msg, new_hdoc = ingest_helix(
                    helix_base_url=settings.HELIX_BASE_URL,
                    browser=settings.HELIX_BROWSER,
                    organization=settings.HELIX_ORGANIZATION,
                    proxy=settings.HELIX_PROXY,
                    ssl_verify=settings.HELIX_SSL_VERIFY,
                    cookie_manual=helix_cookie_manual or None,
                    dry_run=False,
                    existing_doc=helix_doc,
                )
            if ok and new_hdoc is not None:
                _save_helix_doc(helix_data_path, new_hdoc)
                st.success(f"{msg}. Guardado en {helix_data_path}")
            else:
                st.error(msg)

        st.markdown("#### Última ingesta Helix")
        st.json(
            {
                "schema_version": helix_doc.schema_version,
                "ingested_at": helix_doc.ingested_at,
                "helix_base_url": helix_doc.helix_base_url,
                "query": helix_doc.query,
                "items_count": len(helix_doc.items),
                "data_path": helix_data_path,
                "proxy": settings.HELIX_PROXY,
                "ssl_verify": settings.HELIX_SSL_VERIFY,
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
        status_col = (
            df["status"].fillna("(sin estado)").replace("", "(sin estado)")
            if "status" in df.columns
            else pd.Series([], dtype=str)
        )
        priority_col = (
            df["priority"].fillna("(sin priority)").replace("", "(sin priority)")
            if "priority" in df.columns
            else pd.Series([], dtype=str)
        )

        f1, f2, f3, f4 = st.columns(4)
        with f1:
            status_opts = sorted(status_col.astype(str).unique().tolist())
            status = st.pills("Estado", options=status_opts, selection_mode="multi", default=[], key="filter_status")
        with f2:
            priority = (
                st.multiselect(
                    "Priority",
                    sorted(priority_col.astype(str).unique().tolist(), key=lambda p: (_priority_rank(p), p)),
                    default=[],
                    key="filter_priority",
                )
                if "priority" in df.columns
                else None
            )
        with f3:
            itype = st.multiselect(
                "Tipo",
                sorted(df["type"].dropna().unique().tolist()),
                default=[],
                key="filter_type",
            )
        with f4:
            assignee = st.multiselect(
                "Asignado",
                sorted(df["assignee"].dropna().unique().tolist()),
                default=[],
                key="filter_assignee",
            )

        dff = df.copy()
        if "status" in dff.columns:
            dff["status"] = dff["status"].fillna("(sin estado)").replace("", "(sin estado)")
        if "priority" in dff.columns:
            dff["priority"] = dff["priority"].fillna("(sin priority)").replace("", "(sin priority)")
        if status:
            dff = dff[dff["status"].isin(status)]
        if priority:
            dff = dff[dff["priority"].isin(priority)]
        if itype:
            dff = dff[dff["type"].isin(itype)]
        if assignee:
            dff = dff[dff["assignee"].isin(assignee)]

        open_df = dff[dff["resolved"].isna()].copy() if "resolved" in dff.columns else dff.copy()

        st.markdown("### Issues")
        view = st.radio("Vista", options=["Tabla", "Cards"], horizontal=True, index=0, label_visibility="collapsed")
        max_possible = int(len(dff))
        if max_possible <= 1:
            max_issues = max_possible
        else:
            step = 10 if max_possible >= 50 else 1
            max_issues = st.slider("Max issues a mostrar", 1, max_possible, max_possible, step=step)
        dff_show = dff.sort_values(by="updated", ascending=False).head(max_issues)

        if view == "Cards":
            _render_issue_cards(dff_show, max_cards=max_issues, title="Open issues (prioridad + ultima actualizacion)")
        else:
            display_df = dff_show.copy()
            if "url" in display_df.columns:
                display_df["jira"] = display_df["url"]

            show_cols = [
                "jira",
                "summary",
                "status",
                "type",
                "priority",
                "created",
                "updated",
                "resolved",
                "assignee",
                "components",
                "labels",
            ]
            show_cols = [c for c in show_cols if c in display_df.columns]
            column_config = {}
            if "jira" in show_cols:
                column_config["jira"] = st.column_config.LinkColumn("Jira", display_text=r".*/browse/(.*)")
            st.dataframe(
                display_df[show_cols].sort_values(by="updated", ascending=False),
                use_container_width=True,
                column_config=column_config,
            )

        kpis = compute_kpis(dff, settings=settings)
        st.markdown("### KPIs")
        kcol1, kcol2, kcol3 = st.columns(3)
        with kcol1:
            st.metric("Abiertas actuales", int(kpis["open_now_total"]))
            st.caption(kpis["open_now_by_priority"])
        with kcol2:
            st.metric("Nuevas (quincena)", int(kpis["new_fortnight_total"]))
            st.caption(kpis["new_fortnight_by_priority"])
        with kcol3:
            st.metric("Cerradas (quincena)", int(kpis["closed_fortnight_total"]))
            st.caption(kpis["closed_fortnight_by_resolution_type"])

        if not open_df.empty:
            st.markdown("### Distribuciones (abiertas)")
            g1, g2 = st.columns(2)
            with g1:
                fig = px.pie(
                    open_df,
                    names="priority",
                    title="Abiertas por Priority",
                    hole=0.55,
                    color="priority",
                    color_discrete_map=_priority_color_map(),
                )
                fig.update_traces(sort=False)
                st.plotly_chart(_apply_plotly_bbva(fig), use_container_width=True)
            with g2:
                stc = open_df["status"].value_counts().reset_index()
                stc.columns = ["status", "count"]
                fig = px.bar(stc, x="status", y="count", title="Abiertas por Estado")
                st.plotly_chart(_apply_plotly_bbva(fig), use_container_width=True)

        st.markdown("### Evolución (últimos 90 días)")
        st.plotly_chart(_apply_plotly_bbva(kpis["timeseries_chart"]), use_container_width=True)

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
