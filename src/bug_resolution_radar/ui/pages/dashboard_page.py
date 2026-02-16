from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.insights import find_similar_issue_clusters
from bug_resolution_radar.kpis import compute_kpis
from bug_resolution_radar.notes import NotesStore
from bug_resolution_radar.ui.common import (
    df_from_issues_doc,
    load_issues_doc,
    normalize_text_col,
    priority_color_map,
    priority_rank,
)
from bug_resolution_radar.ui.components.filters import (
    FilterState,
    apply_filters,
    render_filters,
    render_status_priority_matrix,
)
from bug_resolution_radar.ui.components.issues import render_issue_cards, render_issue_table
from bug_resolution_radar.ui.style import apply_plotly_bbva


def _open_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["resolved"].isna()].copy() if "resolved" in df.columns else df.copy()


def _render_overview(kpis: dict, open_df: pd.DataFrame) -> None:
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
        st.metric("Tiempo medio resolución (días)", f"{kpis['mean_resolution_days']:.1f}")
        st.caption(kpis["mean_resolution_days_by_priority"])
    with kcol5:
        st.metric("% abiertas > X días", kpis["pct_open_gt_x_days"])
    with kcol6:
        st.metric("Top 10 abiertas", "ver pestaña Insights")

    if not open_df.empty and "priority" in open_df.columns and "status" in open_df.columns:
        st.markdown("### Distribuciones (abiertas)")
        g1, g2 = st.columns(2)
        with g1:
            fig = px.pie(
                open_df,
                names="priority",
                title="Abiertas por Priority",
                hole=0.55,
                color="priority",
                color_discrete_map=priority_color_map(),
            )
            fig.update_traces(sort=False)
            st.plotly_chart(apply_plotly_bbva(fig), use_container_width=True)
        with g2:
            stc = open_df["status"].value_counts().reset_index()
            stc.columns = ["status", "count"]
            fig = px.bar(stc, x="status", y="count", title="Abiertas por Estado")
            st.plotly_chart(apply_plotly_bbva(fig), use_container_width=True)


def _render_issues_section(dff: pd.DataFrame) -> None:
    st.markdown("### Issues")

    view = st.radio(
        "Vista",
        options=["Tabla", "Cards"],
        horizontal=True,
        index=0,
        label_visibility="collapsed",
        key="issues_view_mode",
    )

    max_possible = int(len(dff))
    if max_possible <= 1:
        max_issues = max_possible
    else:
        step = 10 if max_possible >= 50 else 1
        max_issues = st.slider(
            "Max issues a mostrar",
            1,
            max_possible,
            max_possible,
            step=step,
            key="issues_max_slider",
        )

    dff_show = (
        dff.sort_values(by="updated", ascending=False).head(max_issues)
        if "updated" in dff.columns
        else dff.head(max_issues)
    )

    if view == "Cards":
        render_issue_cards(dff_show, max_cards=max_issues, title="Open issues (prioridad + última actualización)")
    else:
        render_issue_table(dff_show)

    with st.expander("Vista Kanban (abiertas por Estado)", expanded=False):
        open_df = _open_only(dff)
        if open_df.empty:
            st.info("No hay incidencias abiertas para mostrar.")
            return

        kan = open_df.copy()
        kan["status"] = normalize_text_col(kan["status"], "(sin estado)")
        status_counts = kan["status"].value_counts()
        all_statuses = status_counts.index.tolist()

        if len(all_statuses) > 8:
            selected_statuses = st.multiselect(
                "Estados a mostrar (máx 8 recomendado)",
                options=all_statuses,
                default=all_statuses[:6],
                key="kanban_statuses",
            )
        else:
            selected_statuses = all_statuses

        selected_statuses = selected_statuses[:8]
        if not selected_statuses:
            st.info("Selecciona al menos un estado.")
            return

        per_col = st.slider(
            "Max issues por columna",
            min_value=5,
            max_value=30,
            value=12,
            step=1,
            key="kanban_per_col",
        )

        cols = st.columns(len(selected_statuses))
        for col, st_name in zip(cols, selected_statuses):
            sub = kan[kan["status"] == st_name].copy()
            sub["_prio_rank"] = sub["priority"].astype(str).map(priority_rank) if "priority" in sub.columns else 99
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


def _render_trends(kpis: dict, dff: pd.DataFrame) -> None:
    st.markdown("### Evolución (últimos 90 días)")
    st.plotly_chart(apply_plotly_bbva(kpis["timeseries_chart"]), use_container_width=True)

    st.markdown("### Distribución antigüedad (abiertas)")
    st.plotly_chart(apply_plotly_bbva(kpis["age_buckets_chart"]), use_container_width=True)

    with st.expander("Distribución de tiempos de resolución", expanded=False):
        if "resolved" not in dff.columns or "created" not in dff.columns:
            st.info("No hay incidencias cerradas con fechas suficientes para calcular resolución.")
            return

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
            st.plotly_chart(apply_plotly_bbva(fig), use_container_width=True)
        else:
            st.info("No hay incidencias cerradas con fechas suficientes para calcular resolución.")


def _render_insights(kpis: dict, dff: pd.DataFrame) -> None:
    st.markdown("### Top 10 problemas/funcionalidades (abiertas)")
    st.dataframe(kpis["top_open_table"], use_container_width=True, hide_index=True)

    with st.expander("Incidencias similares (posibles duplicados)", expanded=False):
        clusters = find_similar_issue_clusters(dff, only_open=True)
        if not clusters:
            st.info("No se encontraron clusters de incidencias similares (o hay pocos datos).")
        else:
            st.caption("Agrupado por similitud de texto en el summary (heurístico).")
            for c in clusters[:12]:
                st.markdown(f"**{c.size}x** · {c.summary}")
                st.write(", ".join(c.keys))


def _render_notes(dff: pd.DataFrame, notes: NotesStore) -> None:
    st.markdown("#### Editar nota local")

    if "key" not in dff.columns or dff.empty:
        st.info("No hay issues disponibles para notas.")
        return

    issue_key = st.selectbox("Issue", dff["key"].tolist(), key="notes_issue_key")
    current = notes.get(issue_key) or ""
    new_note = st.text_area("Nota (local)", value=current, height=120, key="notes_text")
    if st.button("💾 Guardar nota", key="notes_save_btn"):
        notes.set(issue_key, new_note)
        notes.save()
        st.success("Nota guardada localmente.")


def render(settings: Settings) -> None:
    st.subheader("Dashboard")

    doc = load_issues_doc(settings.DATA_PATH)
    df = df_from_issues_doc(doc)

    if df.empty:
        st.warning("No hay datos todavía. Ve a la pestaña de Ingesta y ejecuta una ingesta.")
        return

    notes = NotesStore(Path(settings.NOTES_PATH))
    notes.load()

    fs: FilterState = render_filters(df)
    dff = apply_filters(df, fs)
    open_df = _open_only(dff)

    # Compute KPIs once (expensive). Used across tabs.
    kpis = compute_kpis(dff, settings=settings)

    # Sub-tabs inside Dashboard
    t_overview, t_issues, t_trends, t_insights, t_notes = st.tabs(
        ["📌 Resumen", "🧾 Issues", "📈 Tendencias", "🧠 Insights", "🗒️ Notas"]
    )

    with t_overview:
        # IMPORTANT: unique key_prefix to avoid DuplicateElementId when matrix appears in multiple tabs
        render_status_priority_matrix(open_df, fs, key_prefix="mx_overview")
        _render_overview(kpis, open_df)

    with t_issues:
        # IMPORTANT: unique key_prefix to avoid DuplicateElementId when matrix appears in multiple tabs
        render_status_priority_matrix(open_df, fs, key_prefix="mx_issues")
        _render_issues_section(dff)

    with t_trends:
        _render_trends(kpis, dff)

    with t_insights:
        _render_insights(kpis, dff)

    with t_notes:
        _render_notes(dff, notes)