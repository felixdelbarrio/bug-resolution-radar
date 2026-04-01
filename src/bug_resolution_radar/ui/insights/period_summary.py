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
    tone_color_css,
)
from bug_resolution_radar.ui.dashboard.quincenal_scope import (
    QUINCENAL_SCOPE_CLOSED_CURRENT,
    QUINCENAL_SCOPE_CREATED_CURRENT,
    QUINCENAL_SCOPE_CREATED_MONTH,
    QUINCENAL_SCOPE_CREATED_PREVIOUS,
    QUINCENAL_SCOPE_OPEN_TOTAL,
    QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
    normalize_quincenal_scope_label,
    should_show_open_split,
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


def _inject_period_group_signal_css(*, container_key: str, color_css: str) -> None:
    tint = f"color-mix(in srgb, {color_css} 28%, transparent)"
    st.markdown(
        f"""
        <style>
          .st-key-{container_key} div[data-testid="stExpander"] {{
            box-shadow:
              inset 4px 0 0 {color_css},
              inset 0 0 0 1px {tint};
          }}
          .st-key-{container_key} div[data-testid="stExpander"] summary p {{
            color: {color_css} !important;
            font-weight: 760 !important;
          }}
          .st-key-{container_key} div[data-testid="stExpander"] summary svg {{
            color: {color_css} !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _period_group_signal_color(label: str) -> str:
    token = str(label or "").strip().lower()
    if token == QUINCENAL_SCOPE_CREATED_CURRENT.lower():
        return tone_color_css("risk")
    if token in {
        QUINCENAL_SCOPE_CLOSED_CURRENT.lower(),
        QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT.lower(),
    }:
        return tone_color_css("flow")
    if token in {
        QUINCENAL_SCOPE_OPEN_TOTAL.lower(),
        QUINCENAL_SCOPE_CREATED_PREVIOUS.lower(),
    }:
        return tone_color_css("warning")
    if token == QUINCENAL_SCOPE_CREATED_MONTH.lower():
        return tone_color_css("quality")
    if "quincena actual" in token and "creadas" in token:
        return tone_color_css("risk")
    if "cerradas en la quincena" in token or "resolución" in token:
        return tone_color_css("flow")
    if (
        "abiertas" in token
        or "maestras" in token
        or "criticidad alta" in token
        or "otras incidencias" in token
        or "quincena previa" in token
    ):
        return tone_color_css("warning")
    if "mes actual" in token:
        return tone_color_css("quality")
    return tone_color_css("quality")


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
    st.session_state[ISSUES_QUINCENAL_SCOPE_KEY] = normalize_quincenal_scope_label(label)
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
    age_days_col: str | None = None,
    sort_by_col: str | None = None,
    sort_desc: bool = False,
) -> None:
    scope_label = str(zoom_label or title or "").strip() or title
    scope_slug = _slug_for_key(scope_label)
    signal_color = _period_group_signal_color(scope_label)
    container_key = f"period_summary_group_signal_{scope_slug}"
    with st.container(key=container_key):
        _inject_period_group_signal_css(container_key=container_key, color_css=signal_color)
        with st.expander(f"{title}: {count}", expanded=False):
            if df is None or df.empty:
                st.caption("Sin incidencias en este bloque.")
                return
            view_df = df
            if sort_by_col and sort_by_col in df.columns:
                view_df = df.sort_values(
                    by=sort_by_col,
                    ascending=not sort_desc,
                    na_position="last",
                    kind="mergesort",
                    key=lambda col: pd.to_numeric(col, errors="coerce"),
                )
            rows_total = int(len(view_df))
            top_status = (
                str(view_df["status"].fillna("").astype(str).value_counts().index[0]).strip()
                if "status" in view_df.columns and rows_total > 0
                else "(sin estado)"
            )
            top_priority = (
                str(view_df["priority"].fillna("").astype(str).value_counts().index[0]).strip()
                if "priority" in view_df.columns and rows_total > 0
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
                st.markdown(
                    f'<div class="ins-meta-row">{"".join(chips)}</div>',
                    unsafe_allow_html=True,
                )
            with action_col:
                with st.container(key=f"period_summary_group_open_{scope_slug}"):
                    if st.button(
                        "Abrir en Issues ↗",
                        key=f"period_summary_group_open_btn::{scope_slug}",
                        width="stretch",
                    ):
                        _jump_to_issues_with_scope(label=scope_label, df=view_df)

            cards_html = issue_cards_html_from_df(
                view_df,
                key_to_url=key_to_url,
                key_to_meta=key_to_meta,
                summary_col="summary",
                assignee_col="assignee",
                age_days_col=age_days_col,
                source_col=source_col,
                summary_max_chars=180,
                limit=60,
            )
            if cards_html:
                st.markdown(cards_html, unsafe_allow_html=True)
            else:
                st.dataframe(
                    view_df.loc[:, _visible_columns(view_df)].copy(deep=False),
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

    open_total_group = pd.concat([groups.open_focus, groups.open_other], axis=0, ignore_index=True).copy(
        deep=False
    )
    show_open_split = should_show_open_split(
        maestras_total=int(summary.open_focus_total),
        others_total=int(summary.open_other_total),
        open_total=int(summary.open_total),
    )

    cards: List[ActionableCardItem] = [
        ActionableCardItem(
            card_id="new_now",
            kicker="Insights · Creadas",
            metric=f"{int(summary.new_now):,}",
            detail=_fmt_delta_hint(summary.new_delta_pct),
            link_label=f"{QUINCENAL_SCOPE_CREATED_CURRENT} ↗",
            tone="risk",
            on_click=_jump_to_issues_with_keys,
            click_kwargs={
                "label": QUINCENAL_SCOPE_CREATED_CURRENT,
                "keys": _issue_keys(groups.new_now),
            },
        ),
        ActionableCardItem(
            card_id="closed_now",
            kicker="Insights · Cerradas",
            metric=f"{int(summary.closed_now):,}",
            detail=_fmt_delta_hint(summary.closed_delta_pct),
            link_label=f"{QUINCENAL_SCOPE_CLOSED_CURRENT} ↗",
            tone="flow",
            on_click=_jump_to_issues_with_keys,
            click_kwargs={
                "label": QUINCENAL_SCOPE_CLOSED_CURRENT,
                "keys": _issue_keys(groups.closed_now),
            },
        ),
        ActionableCardItem(
            card_id="resolution_now",
            kicker="Insights · Resolución",
            metric=_fmt_days(summary.resolution_days_now),
            detail=_fmt_delta_hint(summary.resolution_delta_pct),
            link_label=f"{QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT} ↗",
            tone="flow",
            on_click=_jump_to_issues_with_keys,
            click_kwargs={
                "label": QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
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
                "label": QUINCENAL_SCOPE_OPEN_TOTAL,
                "keys": _issue_keys(open_total_group),
            },
        ),
    ]
    if show_open_split:
        cards.extend(
            [
                ActionableCardItem(
                    card_id="open_focus",
                    kicker=str(summary.open_focus_card_kicker),
                    metric=f"{int(summary.open_focus_total):,}",
                    detail=str(summary.open_focus_card_detail),
                    link_label=f"{summary.open_focus_label} ↗",
                    tone="warning",
                    on_click=_jump_to_issues_with_keys,
                    click_kwargs={
                        "label": str(summary.open_focus_label),
                        "keys": _issue_keys(groups.open_focus),
                    },
                ),
                ActionableCardItem(
                    card_id="others",
                    kicker=str(summary.open_other_card_kicker),
                    metric=f"{int(summary.open_other_total):,}",
                    detail=str(summary.open_other_card_detail),
                    link_label=f"{summary.open_other_label} ↗",
                    tone="warning",
                    on_click=_jump_to_issues_with_keys,
                    click_kwargs={
                        "label": str(summary.open_other_label),
                        "keys": _issue_keys(groups.open_other),
                    },
                ),
            ]
        )

    render_actionable_card_grid(
        cards,
        columns=3 if show_open_split else 4,
        key_prefix="period_summary_kpi",
    )
    with st.container(key="period_summary_groups"):
        if show_open_split:
            _render_issue_group(
                str(summary.open_focus_label),
                summary.open_focus_total,
                groups.open_focus,
                key_to_url=key_to_url,
                key_to_meta=key_to_meta,
                zoom_label=str(summary.open_focus_label),
            )
            _render_issue_group(
                str(summary.open_other_label),
                summary.open_other_total,
                groups.open_other,
                key_to_url=key_to_url,
                key_to_meta=key_to_meta,
                zoom_label=str(summary.open_other_label),
            )
        _render_issue_group(
            "Creadas en la quincena previa",
            summary.new_before,
            groups.new_before,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="quincena previa",
            zoom_label=QUINCENAL_SCOPE_CREATED_PREVIOUS,
        )
        _render_issue_group(
            "Creadas en la quincena actual",
            summary.new_now,
            groups.new_now,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="quincena actual",
            zoom_label=QUINCENAL_SCOPE_CREATED_CURRENT,
        )
        _render_issue_group(
            "Creadas en el mes actual",
            summary.new_accumulated,
            groups.new_accumulated,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="mes actual",
            zoom_label=QUINCENAL_SCOPE_CREATED_MONTH,
        )
        _render_issue_group(
            "Cerradas en la quincena",
            summary.closed_now,
            groups.closed_now,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="quincena actual",
            zoom_label=QUINCENAL_SCOPE_CLOSED_CURRENT,
        )
        _render_issue_group(
            "Días de resolución incidencias cerradas en la quincena actual",
            len(groups.resolved_now),
            groups.resolved_now,
            key_to_url=key_to_url,
            key_to_meta=key_to_meta,
            help_text="cerradas quincena actual",
            source_col=None,
            zoom_label=QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
            age_days_col="resolution_days",
            sort_by_col="resolution_days",
            sort_desc=True,
        )

    if scope_mode == "country" and result.by_source:
        st.markdown("##### Corte por origen seleccionado")
        focus_col_label = str(summary.open_focus_label or "foco abierto")
        other_col_label = str(summary.open_other_label or "otras incidencias")
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
                    focus_col_label: int(source_summary.open_focus_total),
                    other_col_label: int(source_summary.open_other_total),
                    "nuevas_ahora": int(source_summary.new_now),
                    "cerradas_ahora": int(source_summary.closed_now),
                    "resolucion_dias_ahora": _fmt_days(source_summary.resolution_days_now),
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
