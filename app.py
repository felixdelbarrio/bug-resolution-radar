from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import streamlit as st

from bug_resolution_radar.config import Settings, ensure_env, load_settings, save_settings
from bug_resolution_radar.ingest.jira_ingest import ingest_jira
from bug_resolution_radar.insights import find_similar_issue_clusters
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


def _inject_card_css() -> None:
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

            /* Streamlit theme variables (force consistency; avoids odd red/black defaults). */
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

          /* Use serif only for headline-like elements; keep most UI in Benton Sans style */
          .bbva-hero-title {
            font-family: "Tiempos Headline", "Tiempos Headline Bold", Georgia, "Times New Roman", serif;
            letter-spacing: -0.01em;
          }

          /* App page background + content surface */
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

          /* BBVA Experience-like top band */
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

          /* Make the native Streamlit header blend in (avoid dark gradient mismatch) */
          header[data-testid="stHeader"] {
            background: transparent;
          }
          header[data-testid="stHeader"] * { color: inherit !important; }

          /* Sidebar like BBVA Experience left nav */
          section[data-testid="stSidebar"] {
            background: var(--bbva-surface);
            border-right: 1px solid var(--bbva-border);
          }
          section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] * {
            font-size: 14px;
          }

          /* Make widget corners consistent */
          .stButton > button,
          .stDownloadButton > button,
          .stTextInput input,
          .stTextArea textarea,
          .stSelectbox [data-baseweb="select"] > div,
          .stMultiSelect [data-baseweb="select"] > div {
            border-radius: var(--bbva-radius-m) !important;
          }

          /* Labels: readable on light background */
          label, [data-testid="stWidgetLabel"] p {
            color: rgba(17,25,45,0.82) !important;
            font-weight: 600 !important;
          }

          /* Inputs: force BBVA light surfaces even if Streamlit theme drifts */
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

          /* Pills (Streamlit 1.50): ensure readable in light mode */
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

          /* Tabs: accent must be BBVA primary (avoid red underline) */
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

          /* Links use BBVA primary */
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
    # Common Jira names, fallback to stable alphabetical.
    order = ["highest", "high", "medium", "low", "lowest"]
    pl = (p or "").strip().lower()
    if pl in order:
        return order.index(pl)
    return 99


def _priority_color_map() -> Dict[str, str]:
    # Traffic-light palette for charts only (requested):
    # - Red 2 (Tertiary):   #FF5252
    # - Orange 2 (Secondary): #FFB56B
    # - Green 6 (Secondary):  #88E783
    # Rest: coherent from the same BBVA palettes.
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
    # Callback: runs before the next rerun, so it can safely update widget state.
    st.session_state["filter_status"] = [st_name]
    st.session_state["filter_priority"] = [prio]


def _matrix_clear_filters() -> None:
    # Callback: runs before the next rerun.
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

    # Sort: priority (rough), then updated desc.
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
    # Keep visuals aligned with BBVA Experience (Color: Primary).
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
                ok, msg, _ = ingest_jira(
                    settings=settings, cookie_manual=jira_cookie_manual or None, dry_run=True
                )
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
        # Normalize empty values so filters + matrix can round-trip selections.
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

        # Open issues (used by matrix + several gadgets).
        open_df = dff[dff["resolved"].isna()].copy() if "resolved" in dff.columns else dff.copy()
        # Matrix stuck to filters. Matrix click syncs filters + table/cards.
        if not open_df.empty and "status" in open_df.columns and "priority" in open_df.columns:
            st.markdown("### Matriz Estado x Priority (abiertas)")

            mx = open_df.assign(
                status=open_df["status"].fillna("(sin estado)").replace("", "(sin estado)"),
                priority=open_df["priority"].fillna("(sin priority)").replace("", "(sin priority)"),
            )
            status_counts = mx["status"].value_counts()
            statuses = status_counts.index.tolist()
            priorities = sorted(
                mx["priority"].dropna().astype(str).unique().tolist(),
                key=lambda p: (_priority_rank(p), p),
            )

            selected_status = status[0] if isinstance(status, list) and len(status) == 1 else None
            selected_priority = priority[0] if isinstance(priority, list) and len(priority) == 1 else None
            has_matrix_sel = bool(selected_status and selected_priority)

            cA, cB = st.columns([3, 1])
            with cA:
                if has_matrix_sel:
                    st.caption(f"Seleccionado: Estado={selected_status} · Priority={selected_priority}")
                else:
                    st.caption("Click en una celda: sincroniza Estado/Priority y actualiza la tabla.")
            with cB:
                st.button(
                    "Limpiar selección",
                    disabled=not has_matrix_sel,
                    on_click=_matrix_clear_filters,
                )

            # Header row
            hdr = st.columns(len(priorities) + 1)
            hdr[0].markdown("**Estado**")
            for i, p in enumerate(priorities):
                if selected_priority == p:
                    hdr[i + 1].markdown(
                        f'<span style="color:var(--bbva-primary); font-weight:800;">{html.escape(p)}</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    hdr[i + 1].markdown(f"**{p}**")

            counts = pd.crosstab(mx["status"], mx["priority"])
            for st_name in statuses[:12]:  # keep it usable; top statuses by count
                row = st.columns(len(priorities) + 1)
                if selected_status == st_name:
                    row[0].markdown(
                        f'<span style="color:var(--bbva-primary); font-weight:800;">{html.escape(st_name)}</span>',
                        unsafe_allow_html=True,
                    )
                else:
                    row[0].markdown(st_name)
                for i, p in enumerate(priorities):
                    cnt = int(counts.at[st_name, p]) if (st_name in counts.index and p in counts.columns) else 0
                    is_selected = bool(selected_status == st_name and selected_priority == p)
                    row[i + 1].button(
                        str(cnt),
                        key=f"mx::{st_name}::{p}",
                        disabled=(cnt == 0),
                        type="primary" if is_selected else "secondary",
                        use_container_width=True,
                        on_click=_matrix_set_filters,
                        args=(st_name, p),
                    )

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
            # Show a clickable Jira link (opens in a new tab) using the stored issue URL.
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
                column_config["jira"] = st.column_config.LinkColumn(
                    "Jira",
                    display_text=r".*/browse/(.*)",
                )
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

        kcol4, kcol5, kcol6 = st.columns(3)
        with kcol4:
            st.metric("Tiempo medio resolución (días)", f'{kpis["mean_resolution_days"]:.1f}')
            st.caption(kpis["mean_resolution_days_by_priority"])
        with kcol5:
            st.metric("% abiertas > X días", kpis["pct_open_gt_x_days"])
        with kcol6:
            st.metric("Top 10 abiertas", "ver tabla")

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

        st.markdown("### Distribución antigüedad (abiertas)")
        st.plotly_chart(_apply_plotly_bbva(kpis["age_buckets_chart"]), use_container_width=True)

        with st.expander("Distribución de tiempos de resolución", expanded=False):
            closed = dff[dff["resolved"].notna() & dff["created"].notna()].copy()
            if not closed.empty:
                closed["resolution_days"] = (
                    (closed["resolved"] - closed["created"]).dt.total_seconds() / 86400.0
                ).clip(lower=0.0)
                fig = px.histogram(
                    closed,
                    x="resolution_days",
                    nbins=30,
                    title="Histograma: días hasta resolución (cerradas)",
                )
                st.plotly_chart(_apply_plotly_bbva(fig), use_container_width=True)
            else:
                st.info("No hay incidencias cerradas con fechas suficientes para calcular resolución.")

        st.markdown("### Top 10 problemas/funcionalidades (abiertas)")
        st.dataframe(kpis["top_open_table"], use_container_width=True, hide_index=True)

        with st.expander("Incidencias similares (posibles duplicados)", expanded=False):
            clusters = find_similar_issue_clusters(dff_show, only_open=True)
            if not clusters:
                st.info("No se encontraron clusters de incidencias similares (o hay pocos datos).")
            else:
                st.caption("Agrupado por similitud de texto en el summary (heurístico).")
                for c in clusters[:12]:
                    st.markdown(f"**{c.size}x** · {c.summary}")
                    st.write(", ".join(c.keys))

        with st.expander("Vista Kanban (abiertas por Estado)", expanded=False):
            kan = open_df.copy()
            kan["status"] = kan["status"].fillna("(sin estado)").replace("", "(sin estado)")
            status_counts = kan["status"].value_counts()
            all_statuses = status_counts.index.tolist()

            if len(all_statuses) > 8:
                selected_statuses = st.multiselect(
                    "Estados a mostrar (máx 8 recomendado)",
                    options=all_statuses,
                    default=all_statuses[:6],
                )
            else:
                selected_statuses = all_statuses

            selected_statuses = selected_statuses[:8]
            if not selected_statuses:
                st.info("Selecciona al menos un estado.")
            else:
                per_col = st.slider("Max issues por columna", min_value=5, max_value=30, value=12, step=1)
                cols = st.columns(len(selected_statuses))
                for col, st_name in zip(cols, selected_statuses):
                    sub = kan[kan["status"] == st_name].copy()
                    sub["_prio_rank"] = sub["priority"].astype(str).map(_priority_rank)
                    sub = sub.sort_values(by=["_prio_rank", "updated"], ascending=[True, False]).head(per_col)
                    with col:
                        st.markdown(f"**{st_name}**  \n{len(kan[kan['status']==st_name])} issues")
                        for _, r in sub.iterrows():
                            key = html.escape(str(r.get("key", "") or ""))
                            url = html.escape(str(r.get("url", "") or ""))
                            summ = html.escape(str(r.get("summary", "") or ""))
                            if len(summ) > 80:
                                summ = summ[:77] + "..."
                            st.markdown(
                                f'<div style="margin: 8px 0 10px 0;">'
                                f'<div><a href="{url}" target="_blank" rel="noopener noreferrer">{key}</a></div>'
                                f'<div style="opacity:0.85; font-size:0.85rem; line-height:1.1rem;">{summ}</div>'
                                f"</div>",
                                unsafe_allow_html=True,
                            )

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
