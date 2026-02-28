"""Visual component renderers for cards, chips and formatted metric blocks."""

from __future__ import annotations

import html
from typing import Dict, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import (
    normalize_text_col,
    priority_rank,
)
from bug_resolution_radar.ui.components.filters import render_filters
from bug_resolution_radar.ui.components.issues import render_issue_cards, render_issue_table
from bug_resolution_radar.ui.dashboard.exports.downloads import df_to_excel_bytes
from bug_resolution_radar.ui.dashboard.registry import (
    ChartContext,
    ChartSpec,
    build_trends_registry,
    list_trend_chart_options,
    render_chart_with_insights,
)
from bug_resolution_radar.ui.dashboard.state import FILTER_STATUS_KEY


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------
def _parse_csv_list(value: object) -> List[str]:
    if value is None:
        return []
    s = str(value).strip()
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]


def _panel(title: str, subtitle: str | None = None) -> st.delta_generator.DeltaGenerator:
    """Elegant container (keeps current Streamlit/BBVA vibe without hardcoding colors)."""
    st.markdown(
        """
        <style>
          .bbva-panel {
            border: 1px solid var(--bbva-border);
            background: var(--bbva-surface-soft);
            border-radius: 16px;
            padding: 18px 18px 14px 18px;
            margin: 10px 0 16px 0;
            box-shadow: 0 8px 24px color-mix(in srgb, var(--bbva-text) 12%, transparent);
          }
          .bbva-panel h3 {
            margin: 0 0 2px 0;
            font-size: 1.05rem;
            font-weight: 750;
            letter-spacing: 0.2px;
          }
          .bbva-panel .sub {
            margin: 0 0 12px 0;
            opacity: 0.75;
            font-size: 0.92rem;
            line-height: 1.1rem;
          }
          .bbva-insights {
            border-top: 1px dashed var(--bbva-border);
            margin-top: 12px;
            padding-top: 10px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    subtitle_html = f'<div class="sub">{html.escape(subtitle)}</div>' if subtitle else ""
    st.markdown(
        f"""
        <div class="bbva-panel">
          <h3>{html.escape(title)}</h3>
          {subtitle_html}
        """,
        unsafe_allow_html=True,
    )
    c = st.container()
    st.markdown("</div>", unsafe_allow_html=True)
    return c


# ---------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------
def render_overview_kpis(kpis: dict) -> None:
    """Resumen = solo KPIs (los gráficos se ven en Tendencias)."""
    box = _panel("KPIs", "Indicadores operativos del backlog (según filtros actuales)")
    with box:
        kcol1, kcol2, kcol3 = st.columns(3)
        with kcol1:
            st.metric("Abiertas actuales", int(kpis.get("open_now_total", 0)))
            st.caption(kpis.get("open_now_by_priority", {}))
        with kcol2:
            st.metric("Issues filtradas", int(kpis.get("issues_total", 0)))
            st.caption(kpis.get("issues_closed", 0))
        with kcol3:
            st.metric("Cerradas", int(kpis.get("issues_closed", 0)))
            st.caption("Según filtros actuales")

        kcol4, kcol5, kcol6 = st.columns(3)
        with kcol4:
            st.metric(
                "Tiempo medio resolución (días)",
                f"{float(kpis.get('mean_resolution_days', 0.0)):.1f}",
            )
            st.caption(kpis.get("mean_resolution_days_by_priority", {}))
        with kcol5:
            st.metric("Serie temporal", "Últimos 90 días")
        with kcol6:
            st.metric("Top 10 abiertas", "ver pestaña Insights")


# ---------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------
def render_issues_section(dff: pd.DataFrame) -> None:
    """Issues with Cards (default) + Table. CSV download ALWAYS visible and exports table-format."""
    st.markdown("### Issues")

    # Keep stable sort
    dff_show = (
        dff.sort_values(by="updated", ascending=False) if "updated" in dff.columns else dff.copy()
    )

    # Download CSV (always visible; independent of view)
    top = _panel(
        "Exportación", "Descarga el dataset filtrado (formato tabla) para análisis externo"
    )
    with top:
        c1, c2 = st.columns([1, 2])
        with c1:
            csv_bytes = df_to_excel_bytes(dff_show, include_index=False, sheet_name="Issues")
            st.download_button(
                "Descargar Excel",
                data=csv_bytes,
                file_name="issues_filtradas.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="issues_download_csv",
                width="stretch",
            )
        with c2:
            st.caption(f"{len(dff_show)} issues (según filtros actuales)")

    view = st.radio(
        "Vista",
        options=["Cards", "Tabla"],
        horizontal=True,
        index=0,  # default Cards
        label_visibility="collapsed",
        key="issues_view_mode",
    )

    if view == "Cards":
        box = _panel("Vista Cards", "Lectura rápida: prioridad + última actualización")
        with box:
            render_issue_cards(
                dff_show,
                max_cards=int(len(dff_show)),
                title="Open issues (prioridad + última actualización)",
            )
        return

    box = _panel("Vista Tabla", "Ideal para ordenar, filtrar visualmente y exportar")
    with box:
        render_issue_table(dff_show)


# ---------------------------------------------------------------------
# Kanban
# ---------------------------------------------------------------------
def render_kanban(
    open_df: pd.DataFrame,
    *,
    header_click_sets_status: bool = True,
    max_status_cols: int = 8,
    default_cols: int = 6,
) -> None:
    """Kanban always expanded. If filter_status active -> show those statuses.
    Column headers can be clickable to set filter_status = [status].
    """
    st.markdown("### Kanban (abiertas por Estado)")

    if open_df is None or open_df.empty:
        st.info("No hay incidencias abiertas para mostrar.")
        return

    kan = open_df.copy(deep=False)
    kan["status"] = normalize_text_col(kan["status"], "(sin estado)")

    status_counts = kan["status"].value_counts()
    all_statuses = status_counts.index.tolist()
    grouped = kan.groupby("status", sort=False)
    status_groups: Dict[str, pd.DataFrame] = {str(name): frame for name, frame in grouped}

    # If user has status filter active, show exactly those statuses
    selected_statuses = list(st.session_state.get(FILTER_STATUS_KEY) or [])
    selected_statuses = [s for s in selected_statuses if s in all_statuses]

    if not selected_statuses:
        selected_statuses = all_statuses[:default_cols]
    selected_statuses = selected_statuses[:max_status_cols]

    if not selected_statuses:
        st.info("No hay estados disponibles para mostrar.")
        return

    per_col = st.slider(
        "Max issues por columna",
        min_value=5,
        max_value=30,
        value=int(st.session_state.get("kanban_per_col", 12) or 12),
        step=1,
        key="kanban_per_col",
    )

    cols = st.columns(len(selected_statuses))

    def _set_status_filter(st_name: str) -> None:
        st.session_state[FILTER_STATUS_KEY] = [st_name]

    for col, st_name in zip(cols, selected_statuses):
        sub = status_groups.get(st_name, pd.DataFrame()).copy(deep=False)
        if "priority" in sub.columns:
            sub["_prio_rank"] = sub["priority"].astype(str).map(priority_rank)
        else:
            sub["_prio_rank"] = 99

        sort_cols = ["_prio_rank"]
        sort_asc = [True]
        if "updated" in sub.columns:
            sort_cols.append("updated")
            sort_asc.append(False)

        sub = sub.sort_values(by=sort_cols, ascending=sort_asc).head(per_col)

        with col:
            if header_click_sets_status:
                st.button(
                    f"{st_name}",
                    key=f"kanban_hdr::{st_name}",
                    width="stretch",
                    on_click=_set_status_filter,
                    args=(st_name,),
                )
            else:
                st.markdown(f"**{st_name}**")

            st.caption(f"{int(status_counts.get(st_name, 0))} issues")

            display_rows = sub.reindex(columns=["key", "url", "summary"], fill_value="")
            for key_val, url_val, summary_val in display_rows.itertuples(index=False, name=None):
                key = html.escape(str(key_val or ""))
                url = html.escape(str(url_val or ""))
                summ = html.escape(str(summary_val or ""))
                if len(summ) > 80:
                    summ = summ[:77] + "..."
                st.markdown(
                    f'<div style="margin: 8px 0 10px 0;">'
                    f'<div><a href="{url}" target="_blank" rel="noopener noreferrer">{key}</a></div>'
                    f'<div style="opacity:0.85; font-size:0.85rem; line-height:1.1rem;">{summ}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------
# Trends (single chart per screen + intelligent insights)
# ---------------------------------------------------------------------
def render_trends(
    *,
    settings: Settings,
    df_all: pd.DataFrame,
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
    kpis: dict,
) -> None:
    """Tendencias:
    - Filtros se renderizan aquí (único sitio con widgets filter_*)
    - Se muestra como máximo 1 gráfico por pantalla (selector)
    - Cada gráfico va dentro de un panel + insights
    """
    # Filters ONLY here (keeps keys unique)
    render_filters(df_all)

    registry: Dict[str, ChartSpec] = build_trends_registry()
    options = list_trend_chart_options(registry)  # [(id, label), ...]
    ids = [cid for cid, _ in options]
    labels = {cid: label for cid, label in options}

    stored_selected = _parse_csv_list(getattr(settings, "TREND_SELECTED_CHARTS", "") or "")
    stored_selected = [c for c in stored_selected if c in ids]
    default_id = stored_selected[0] if stored_selected else (ids[0] if ids else "")

    # Single-chart selector
    sel = st.selectbox(
        "Gráfico",
        options=ids,
        index=ids.index(default_id) if default_id in ids else 0,
        format_func=lambda x: labels.get(x, x),
        key="trend_single_chart",
    )

    if not sel:
        st.info("No hay gráficos disponibles.")
        return

    ctx = ChartContext(dff=dff, open_df=open_df, kpis=kpis)
    spec = registry.get(sel)

    # Beautiful panel: one chart per “screen”
    panel_title = spec.title if spec else "Gráfico"
    panel_sub = spec.subtitle if spec else ""
    box = _panel(panel_title, panel_sub)

    with box:
        render_chart_with_insights(sel, ctx=ctx, registry=registry)
