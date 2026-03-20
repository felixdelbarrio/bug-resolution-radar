"""Insights tab: fortnight summary with expandable issue detail."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.period_summary import (
    build_country_quincenal_result,
    format_window_label,
    source_label_map,
)
from bug_resolution_radar.config import Settings


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _fmt_delta(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "sin referencia"
    pct = float(value) * 100.0
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.1f}%"


def _fmt_days(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{max(0.0, float(value)):.1f} d"


def _visible_columns(df: pd.DataFrame) -> List[str]:
    preferred = [
        "key",
        "summary",
        "status",
        "priority",
        "assignee",
        "source",
        "created",
        "resolved",
        "resolution_days",
    ]
    return [c for c in preferred if c in df.columns]


def _render_issue_group(title: str, count: int, df: pd.DataFrame, *, help_text: str = "") -> None:
    suffix = f" ({help_text})" if help_text else ""
    with st.expander(f"{title}: {count}{suffix}", expanded=False):
        if df is None or df.empty:
            st.caption("Sin incidencias en este bloque.")
            return
        st.dataframe(
            df.loc[:, _visible_columns(df)].copy(deep=False),
            hide_index=True,
            width="stretch",
        )


def render_period_summary_tab(*, settings: Settings, dff_filtered: pd.DataFrame) -> None:
    dff = _safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos en el scope actual para resumen quincenal.")
        return

    selected_country = str(st.session_state.get("workspace_country") or "").strip()
    if not selected_country and "country" in dff.columns:
        selected_country = str(dff["country"].fillna("").astype(str).iloc[0]).strip()

    scope_mode = str(st.session_state.get("workspace_scope_mode") or "source").strip().lower()
    if scope_mode not in {"country", "source"}:
        scope_mode = "source"

    source_ids: List[str] = []
    if scope_mode == "source":
        selected_source = str(st.session_state.get("workspace_source_id") or "").strip()
        if selected_source:
            source_ids = [selected_source]
    if not source_ids and "source_id" in dff.columns:
        source_ids = sorted(
            {
                sid
                for sid in dff["source_id"].fillna("").astype(str).str.strip().tolist()
                if sid
            }
        )

    labels = source_label_map(settings, country=selected_country, source_ids=source_ids)
    result = build_country_quincenal_result(
        df=dff,
        settings=settings,
        country=selected_country,
        source_ids=source_ids,
        source_label_by_id=labels,
    )

    summary = result.aggregate.summary
    groups = result.aggregate.groups
    st.caption(
        f"{summary.scope_label or selected_country} · {format_window_label(summary.window)}"
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Nuevas (ahora)", summary.new_now, delta=_fmt_delta(summary.new_delta_pct))
    c2.metric("Cerradas (ahora)", summary.closed_now, delta=_fmt_delta(summary.closed_delta_pct))
    c3.metric(
        "Días resolución (ahora)",
        _fmt_days(summary.resolution_days_now),
        delta=_fmt_delta(summary.resolution_delta_pct),
    )

    c4, c5, c6 = st.columns(3)
    c4.metric("Abiertas totales", summary.open_total)
    c5.metric("Maestras", summary.maestras_total)
    c6.metric("Otras", summary.others_total)

    _render_issue_group("Maestras abiertas", summary.maestras_total, groups.maestras_open)
    _render_issue_group("Otras abiertas", summary.others_total, groups.others_open)
    _render_issue_group(
        "Nuevas (antes)",
        summary.new_before,
        groups.new_before,
        help_text="quincena previa",
    )
    _render_issue_group(
        "Nuevas (ahora)",
        summary.new_now,
        groups.new_now,
        help_text="quincena actual",
    )
    _render_issue_group(
        "Nuevas acumulado",
        summary.new_accumulated,
        groups.new_accumulated,
        help_text="mes actual",
    )
    _render_issue_group(
        "Cerradas (ahora)",
        summary.closed_now,
        groups.closed_now,
        help_text="quincena actual",
    )
    _render_issue_group(
        "Días de resolución (detalle)",
        len(groups.resolved_now),
        groups.resolved_now,
        help_text="cerradas quincena actual",
    )

    if scope_mode == "country" and result.by_source:
        st.markdown("##### Corte por origen seleccionado")
        rows: List[Dict[str, object]] = []
        for source_id in result.source_ids:
            source_scope = result.by_source.get(source_id)
            if source_scope is None:
                continue
            source_summary = source_scope.summary
            rows.append(
                {
                    "origen": labels.get(source_id, source_id),
                    "abiertas": int(source_summary.open_total),
                    "maestras": int(source_summary.maestras_total),
                    "otras": int(source_summary.others_total),
                    "nuevas_ahora": int(source_summary.new_now),
                    "cerradas_ahora": int(source_summary.closed_now),
                    "resolucion_dias_ahora": _fmt_days(source_summary.resolution_days_now),
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
