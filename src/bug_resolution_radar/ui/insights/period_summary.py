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
from bug_resolution_radar.ui.components.actionable_cards import (
    ActionableCardItem,
    render_actionable_card_grid,
)
from bug_resolution_radar.ui.dashboard.state import (
    ISSUES_QUINCENAL_SCOPE_KEY,
    clear_issue_scope,
)
from bug_resolution_radar.ui.insights.chips import (
    inject_insights_chip_css,
    issue_cards_html_from_df,
    neutral_chip_html,
    priority_chip_html,
    status_chip_html,
)
from bug_resolution_radar.ui.insights.helpers import build_issue_lookup


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _inject_period_summary_layout_css() -> None:
    """Fine-tune spacing between KPI totals and expandable detail sections."""
    st.markdown(
        """
        <style>
          .st-key-period_summary_groups {
            margin-top: 0.78rem;
          }
          .st-key-period_summary_groups [data-testid="stExpander"] {
            margin-top: 0.46rem;
          }
          .st-key-period_summary_groups [data-testid="stExpander"]:first-of-type {
            margin-top: 0.18rem;
          }
          [class*="st-key-period_summary_group_open_"] div[data-testid="stButton"] > button {
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            color: var(--bbva-action-link) !important;
            font-weight: 700 !important;
            text-align: right !important;
            justify-content: flex-end !important;
            padding: 0.06rem 0.04rem !important;
            min-height: 1.72rem !important;
          }
          [class*="st-key-period_summary_group_open_"] div[data-testid="stButton"] > button:hover {
            color: var(--bbva-action-link-hover) !important;
            transform: translateX(1px);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def _fmt_delta_hint(value: float | None) -> str:
    delta = _fmt_delta(value)
    return (
        f"Δ {delta} vs quincena previa"
        if delta != "sin referencia"
        else "Sin referencia en quincena previa"
    )


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


def _issue_keys(df: pd.DataFrame | None) -> List[str]:
    safe = _safe_df(df)
    if safe.empty or "key" not in safe.columns:
        return []
    out: List[str] = []
    seen: set[str] = set()
    for raw in safe["key"].fillna("").astype(str).tolist():
        key = str(raw or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _slug_for_key(raw: object) -> str:
    txt = str(raw or "").strip().lower()
    if not txt:
        return "scope"
    out = []
    for ch in txt:
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_", "."}:
            out.append("_")
    slug = "".join(out).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "scope"


def _jump_to_issues_with_keys(*, label: str, keys: List[str]) -> None:
    scoped_keys = [str(k or "").strip().upper() for k in list(keys or []) if str(k or "").strip()]
    if not scoped_keys:
        st.info("No hay incidencias en este bloque para abrir en Issues.")
        return
    st.session_state[ISSUES_QUINCENAL_SCOPE_KEY] = str(label or "").strip() or "Todas"
    clear_issue_scope()
    st.session_state["__jump_to_tab"] = "issues"
    st.rerun()


def _jump_to_issues_with_scope(*, label: str, df: pd.DataFrame | None) -> None:
    _jump_to_issues_with_keys(label=label, keys=_issue_keys(df))


def _render_issue_group(
    title: str,
    count: int,
    df: pd.DataFrame,
    *,
    key_to_url: Dict[str, str],
    key_to_meta: Dict[str, tuple[str, str, str]],
    help_text: str = "",
    source_col: str | None = "source",
    zoom_label: str | None = None,
) -> None:
    suffix = f" ({help_text})" if help_text else ""
    with st.expander(f"{title}: {count}{suffix}", expanded=False):
        if df is None or df.empty:
            st.caption("Sin incidencias en este bloque.")
            return
        rows_total = int(len(df))
        top_status = (
            str(df["status"].fillna("").astype(str).value_counts().index[0]).strip()
            if "status" in df.columns and rows_total > 0
            else "(sin estado)"
        )
        top_priority = (
            str(df["priority"].fillna("").astype(str).value_counts().index[0]).strip()
            if "priority" in df.columns and rows_total > 0
            else "(sin priority)"
        )
        chips = [
            neutral_chip_html(f"{rows_total} incidencias"),
            status_chip_html(top_status),
            priority_chip_html(top_priority),
        ]
        if help_text:
            chips.insert(1, neutral_chip_html(help_text))
        meta_col, action_col = st.columns([4.25, 1.2], gap="small")
        with meta_col:
            st.markdown(f'<div class="ins-meta-row">{"".join(chips)}</div>', unsafe_allow_html=True)
        scope_label = str(zoom_label or title or "").strip() or title
        with action_col:
            with st.container(key=f"period_summary_group_open_{_slug_for_key(scope_label)}"):
                if st.button(
                    "Abrir en Issues ↗",
                    key=f"period_summary_group_open_btn::{_slug_for_key(scope_label)}",
                    width="stretch",
                ):
                    _jump_to_issues_with_scope(label=scope_label, df=df)

        cards_html = issue_cards_html_from_df(
            df,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            summary_col="summary",
            assignee_col="assignee",
            source_col=source_col,
            summary_max_chars=180,
            limit=60,
        )
        if cards_html:
            st.markdown(cards_html, unsafe_allow_html=True)
        else:
            st.dataframe(
                df.loc[:, _visible_columns(df)].copy(deep=False),
                hide_index=True,
                width="stretch",
            )
        if rows_total > 60:
            st.caption(f"Mostrando 60 de {rows_total} incidencias.")


def render_period_summary_tab(*, settings: Settings, dff_filtered: pd.DataFrame) -> None:
    inject_insights_chip_css()
    _inject_period_summary_layout_css()
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
            {sid for sid in dff["source_id"].fillna("").astype(str).str.strip().tolist() if sid}
        )

    labels = source_label_map(settings, country=selected_country, source_ids=source_ids)
    result = build_country_quincenal_result(
        df=dff,
        settings=settings,
        country=selected_country,
        source_ids=source_ids,
        source_label_by_id=labels,
    )
    key_to_url, key_to_meta = build_issue_lookup(dff, settings=settings)

    summary = result.aggregate.summary
    groups = result.aggregate.groups
    st.caption(f"{summary.scope_label or selected_country} · {format_window_label(summary.window)}")

    open_total_group = pd.concat(
        [groups.maestras_open, groups.others_open], axis=0, ignore_index=True
    ).copy(deep=False)
    render_actionable_card_grid(
        [
            ActionableCardItem(
                card_id="new_now",
                kicker="Insights · Nuevas",
                metric=f"{int(summary.new_now):,}",
                detail=_fmt_delta_hint(summary.new_delta_pct),
                link_label="Nuevas (quincena actual) ↗",
                tone="risk",
                on_click=_jump_to_issues_with_keys,
                click_kwargs={
                    "label": "Nuevas (quincena actual)",
                    "keys": _issue_keys(groups.new_now),
                },
            ),
            ActionableCardItem(
                card_id="closed_now",
                kicker="Insights · Cerradas",
                metric=f"{int(summary.closed_now):,}",
                detail=_fmt_delta_hint(summary.closed_delta_pct),
                link_label="Cerradas (quincena actual) ↗",
                tone="flow",
                on_click=_jump_to_issues_with_keys,
                click_kwargs={
                    "label": "Cerradas (quincena actual)",
                    "keys": _issue_keys(groups.closed_now),
                },
            ),
            ActionableCardItem(
                card_id="resolution_now",
                kicker="Insights · Resolución",
                metric=_fmt_days(summary.resolution_days_now),
                detail=_fmt_delta_hint(summary.resolution_delta_pct),
                link_label="Resolución (cerradas ahora) ↗",
                tone="flow",
                on_click=_jump_to_issues_with_keys,
                click_kwargs={
                    "label": "Resolución (cerradas ahora)",
                    "keys": _issue_keys(groups.resolved_now),
                },
            ),
            ActionableCardItem(
                card_id="open_total",
                kicker="Insights · Abiertas totales",
                metric=f"{int(summary.open_total):,}",
                detail="Backlog abierto en el scope actual",
                link_label="Abiertas totales ↗",
                tone="warning",
                on_click=_jump_to_issues_with_keys,
                click_kwargs={
                    "label": "Abiertas totales",
                    "keys": _issue_keys(open_total_group),
                },
            ),
            ActionableCardItem(
                card_id="maestras",
                kicker="Insights · Maestras",
                metric=f"{int(summary.maestras_total):,}",
                detail="Abiertas marcadas como maestras",
                link_label="Maestras abiertas ↗",
                tone="warning",
                on_click=_jump_to_issues_with_keys,
                click_kwargs={
                    "label": "Maestras abiertas",
                    "keys": _issue_keys(groups.maestras_open),
                },
            ),
            ActionableCardItem(
                card_id="others",
                kicker="Insights · Otras",
                metric=f"{int(summary.others_total):,}",
                detail="Abiertas no maestras",
                link_label="Otras abiertas ↗",
                tone="warning",
                on_click=_jump_to_issues_with_keys,
                click_kwargs={
                    "label": "Otras abiertas",
                    "keys": _issue_keys(groups.others_open),
                },
            ),
        ],
        columns=3,
        key_prefix="period_summary_kpi",
    )
    with st.container(key="period_summary_groups"):
        _render_issue_group(
            "Maestras abiertas",
            summary.maestras_total,
            groups.maestras_open,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            zoom_label="Maestras abiertas",
        )
        _render_issue_group(
            "Otras abiertas",
            summary.others_total,
            groups.others_open,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            zoom_label="Otras abiertas",
        )
        _render_issue_group(
            "Nuevas (antes)",
            summary.new_before,
            groups.new_before,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="quincena previa",
            zoom_label="Nuevas (quincena previa)",
        )
        _render_issue_group(
            "Nuevas (ahora)",
            summary.new_now,
            groups.new_now,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="quincena actual",
            zoom_label="Nuevas (quincena actual)",
        )
        _render_issue_group(
            "Nuevas acumulado",
            summary.new_accumulated,
            groups.new_accumulated,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="mes actual",
            zoom_label="Nuevas (acumulado)",
        )
        _render_issue_group(
            "Cerradas (ahora)",
            summary.closed_now,
            groups.closed_now,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="quincena actual",
            zoom_label="Cerradas (quincena actual)",
        )
        _render_issue_group(
            "Días de resolución (detalle)",
            len(groups.resolved_now),
            groups.resolved_now,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="cerradas quincena actual",
            source_col=None,
            zoom_label="Resolución (cerradas ahora)",
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
