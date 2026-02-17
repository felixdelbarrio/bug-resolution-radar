from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.dashboard.downloads import (
    figures_to_html_bytes,
    render_minimal_export_actions,
)
from bug_resolution_radar.ui.dashboard.registry import ChartContext, build_trends_registry


def _parse_summary_charts(settings: Settings, registry_ids: List[str]) -> List[str]:
    """
    Lee preferencias de charts desde varios campos legacy/actuales
    y devuelve hasta 3 ids válidos.
    Fallback robusto si falta el setting o hay ids inválidos.
    """
    picked: List[str] = []

    def _append_csv(raw: object) -> None:
        txt = str(raw or "").strip()
        if not txt:
            return
        for part in txt.split(","):
            v = part.strip()
            if v and v in registry_ids and v not in picked:
                picked.append(v)

    # Nuevos campos canónicos
    _append_csv(getattr(settings, "DASHBOARD_SUMMARY_CHARTS", ""))
    _append_csv(getattr(settings, "TREND_SELECTED_CHARTS", ""))

    # Compatibilidad con configuraciones antiguas
    for name in (
        "TREND_FAV_1",
        "TREND_FAVORITE_1",
        "TREND_FAV_2",
        "TREND_FAVORITE_2",
        "TREND_FAV_3",
        "TREND_FAVORITE_3",
    ):
        v = str(getattr(settings, name, "") or "").strip()
        if v and v in registry_ids and v not in picked:
            picked.append(v)

    # Fallback por orden recomendado
    fallback = [
        x
        for x in [
            "timeseries",
            "age_buckets",
            "open_status_bar",
            "open_priority_pie",
            "resolution_hist",
        ]
        if x in registry_ids
    ]

    out: List[str] = []
    for x in picked + fallback:
        if x not in out:
            out.append(x)
        if len(out) == 3:
            break

    return out


def _render_summary_charts(*, settings: Settings, ctx: ChartContext) -> None:
    """
    Contenedor superior: 3 gráficos seleccionados por el cliente,
    cada uno en su contenedor, en 3 columnas para que entren.
    """
    registry = build_trends_registry()
    registry_ids = list(registry.keys())
    chosen = _parse_summary_charts(settings, registry_ids)

    # Siempre intentamos pintar 3 “slots” para que la cabecera se vea estable
    slots: List[str] = (chosen + ["", "", ""])[:3]
    prepared: List[tuple[str, str, Optional[object]]] = []
    figures_for_export: List[object] = []
    titles_for_export: List[str] = []

    for chart_id in slots:
        if not chart_id:
            prepared.append(("", "", None))
            continue
        spec = registry.get(chart_id)
        if spec is None:
            prepared.append((chart_id, chart_id, None))
            continue
        fig = spec.render(ctx)
        if fig is not None:
            fig.update_layout(
                title_text="",
                margin=dict(l=10, r=10, t=35, b=10),
                height=320,
                showlegend=False,
            )
            figures_for_export.append(fig)
            titles_for_export.append(spec.title)
        prepared.append((chart_id, spec.title, fig))

    with st.container(border=True):
        st.markdown("### 📌 Resumen visual")
        export_cols = ["key", "summary", "status", "priority", "assignee", "created", "resolved"]
        export_df = ctx.dff[[c for c in export_cols if c in ctx.dff.columns]].copy(deep=False)
        render_minimal_export_actions(
            key_prefix="overview::summary",
            filename_prefix="resumen_visual",
            suffix="completo",
            csv_df=export_df,
            html_bytes=figures_to_html_bytes(
                figures_for_export, title="Resumen visual", subtitles=titles_for_export
            ),
        )

        cols = st.columns(3, gap="medium")

        for col, (chart_id, chart_title, fig) in zip(cols, prepared):
            with col:
                with st.container(border=True):
                    if not chart_id:
                        st.caption("—")
                        st.info("No configurado")
                        continue

                    if fig is None:
                        st.caption(chart_title or chart_id)
                        st.info("Sin datos para este gráfico con los filtros actuales.")
                        continue

                    st.caption(chart_title or chart_id)
                    st.plotly_chart(fig, use_container_width=True)


def render_overview_tab(
    *,
    settings: Settings,
    kpis: Dict[str, Any],
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
) -> None:
    """
    Overview:
      1) Resumen visual (3 charts del cliente)  ✅ PRIMERO
      2) El resto de tu overview (KPIs, nuevas, etc)
    """
    dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    open_df = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    kpis = kpis if isinstance(kpis, dict) else {}

    # 1) Summary charts arriba del todo
    ctx = ChartContext(dff=dff, open_df=open_df, kpis=kpis)
    _render_summary_charts(settings=settings, ctx=ctx)


def render_overview_kpis(
    *,
    kpis: Dict[str, Any],
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
) -> None:
    """Render KPI block in a compact bordered container."""
    dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    open_df = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    kpis = kpis if isinstance(kpis, dict) else {}

    total_issues = int(kpis.get("issues_total", len(dff)))
    open_issues = int(kpis.get("issues_open", len(open_df)))
    closed_issues = int(kpis.get("issues_closed", max(total_issues - open_issues, 0)))

    with st.container(border=True):
        st.markdown("### KPIs")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Issues filtradas", total_issues)
        with c2:
            st.metric("Abiertas filtradas", open_issues)
        with c3:
            st.metric("Cerradas filtradas", closed_issues)

    # 👉 Si tu Overview tenía secciones (“Nuevas”, “Top X”, etc),
    # pégalas aquí debajo tal cual y NO cambia nada más.
