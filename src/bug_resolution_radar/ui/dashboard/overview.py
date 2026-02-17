from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.dashboard.registry import ChartContext, build_trends_registry
from bug_resolution_radar.ui.style import apply_plotly_bbva


def _parse_summary_charts(settings: Settings, registry_ids: List[str]) -> List[str]:
    """
    Lee settings.DASHBOARD_SUMMARY_CHARTS (CSV) y devuelve hasta 3 ids válidos.
    Fallback robusto si falta el setting o hay ids inválidos.
    """
    raw = (getattr(settings, "DASHBOARD_SUMMARY_CHARTS", "") or "").strip()
    picked = [x.strip() for x in raw.split(",") if x.strip()] if raw else []

    # Filtrar a los que existan
    picked = [x for x in picked if x in registry_ids]

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

    with st.container(border=True):
        st.markdown("### 📌 Resumen visual")

        cols = st.columns(3, gap="medium")

        for col, chart_id in zip(cols, slots):
            with col:
                with st.container(border=True):
                    if not chart_id:
                        st.caption("—")
                        st.info("No configurado")
                        continue

                    spec = registry.get(chart_id)
                    if spec is None:
                        st.caption(chart_id)
                        st.info("Gráfico no disponible.")
                        continue

                    st.caption(spec.title)

                    fig = spec.render(ctx)
                    if fig is None:
                        st.info("Sin datos para este gráfico con los filtros actuales.")
                        continue

                    # Ajuste “compacto” (sin tocar estilos globales)
                    fig = apply_plotly_bbva(fig)
                    fig.update_layout(
                        margin=dict(l=10, r=10, t=35, b=10),
                        height=320,
                        legend=dict(
                            orientation="h", yanchor="bottom", y=-0.25, xanchor="left", x=0
                        ),
                    )
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

    st.markdown("---")

    # 2) KPI básicos (fallback robusto a len(df))
    total_issues = int(kpis.get("issues_total", len(dff)))
    open_issues = int(kpis.get("issues_open", len(open_df)))
    closed_issues = int(kpis.get("issues_closed", max(total_issues - open_issues, 0)))

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
