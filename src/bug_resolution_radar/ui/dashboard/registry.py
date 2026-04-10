"""Chart registry for trends and summary visualizations."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict

import plotly.graph_objects as go
import streamlit as st

from bug_resolution_radar.analytics.trend_charts import (
    ChartContext,
    ChartSpec,
    _render_age_buckets as _render_age_buckets_pure,
    _render_open_priority_pie as _render_open_priority_pie_pure,
    _render_open_status_bar as _render_open_status_bar_pure,
    _render_resolution_hist as _render_resolution_hist_pure,
    _render_timeseries as _render_timeseries_pure,
    build_trends_registry as _build_trends_registry,
    list_trend_chart_options,
)


def _workspace_dark_mode_enabled() -> bool:
    try:
        return bool(st.session_state.get("workspace_dark_mode", False))
    except Exception:
        return False


def _ui_ctx(ctx: ChartContext) -> ChartContext:
    return replace(ctx, dark_mode=_workspace_dark_mode_enabled())


def _render_timeseries(ctx: ChartContext) -> go.Figure | None:
    return _render_timeseries_pure(_ui_ctx(ctx))


def _render_age_buckets(ctx: ChartContext) -> go.Figure | None:
    return _render_age_buckets_pure(_ui_ctx(ctx))


def _render_resolution_hist(ctx: ChartContext) -> go.Figure | None:
    return _render_resolution_hist_pure(_ui_ctx(ctx))


def _render_open_priority_pie(ctx: ChartContext) -> go.Figure | None:
    return _render_open_priority_pie_pure(_ui_ctx(ctx))


def _render_open_status_bar(ctx: ChartContext) -> go.Figure | None:
    return _render_open_status_bar_pure(_ui_ctx(ctx))


def build_trends_registry() -> Dict[str, ChartSpec]:
    base = _build_trends_registry()
    render_overrides = {
        "timeseries": _render_timeseries,
        "age_buckets": _render_age_buckets,
        "resolution_hist": _render_resolution_hist,
        "open_priority_pie": _render_open_priority_pie,
        "open_status_bar": _render_open_status_bar,
    }
    return {
        chart_id: replace(spec, render=render_overrides.get(chart_id, spec.render))
        for chart_id, spec in base.items()
    }


def render_chart_with_insights(
    chart_id: str,
    *,
    ctx: ChartContext,
    registry: Dict[str, ChartSpec],
) -> None:
    """Render a chart + its insights (no layout container here; handled by layout.py)."""
    spec = registry.get(chart_id)
    if spec is None:
        st.info("Gráfico no disponible.")
        return

    fig = spec.render(ctx)
    if fig is None:
        st.info("No hay datos suficientes para este gráfico con los filtros actuales.")
        return

    st.plotly_chart(fig, width="stretch")

    bullets = spec.insights(ctx) or []
    if bullets:
        st.markdown("##### Insights")
        for bullet in bullets[:4]:
            st.markdown(f"- {bullet}")
