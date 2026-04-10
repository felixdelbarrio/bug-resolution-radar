"""Duplicate detection views by exact title and heuristic similarity."""

from __future__ import annotations

from typing import Any, Callable, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.duplicates import (
    ExactTitleDuplicateStats,
    exact_title_duplicate_stats,
)
from bug_resolution_radar.analytics.duplicate_insights import (
    _dedupe_heuristic_clusters as _dedupe_heuristic_clusters_backend,
    prepare_duplicates_payload as _prepare_duplicates_payload_backend,
)
from bug_resolution_radar.analytics.insights import SimilarityCluster
from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.cache import cached_by_signature, dataframe_signature
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.exports.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.insights.chips import inject_insights_chip_css, render_issue_bullet
from bug_resolution_radar.ui.insights.engine import build_duplicates_brief
from bug_resolution_radar.ui.insights.header_actions import render_insights_header_row
from bug_resolution_radar.ui.insights.helpers import (
    build_issue_lookup,
    col_exists,
    open_only,
    safe_df,
)


def _set_duplicates_view(view_key: str, value: str) -> None:
    st.session_state[view_key] = value


def _inject_duplicates_view_toggle_css(*, scope_key: str) -> None:
    st.markdown(
        f"""
        <style>
          .st-key-{scope_key} .stButton > button {{
            min-height: 2.15rem !important;
            padding: 0.35rem 0.78rem !important;
            border-radius: 10px !important;
            font-weight: 700 !important;
            border: 1px solid var(--bbva-tab-soft-border) !important;
            background: var(--bbva-tab-soft-bg) !important;
            color: var(--bbva-tab-soft-text) !important;
          }}
          .st-key-{scope_key} .stButton > button[kind="primary"] {{
            border-color: var(--bbva-tab-active-border) !important;
            background: var(--bbva-tab-active-bg) !important;
            color: var(--bbva-tab-active-text) !important;
          }}
          .st-key-{scope_key} .stButton > button * {{
            color: inherit !important;
            fill: currentColor !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _dedupe_heuristic_clusters(
    *,
    clusters: list[SimilarityCluster],
    exact_title_groups: dict[str, list[str]],
) -> list[SimilarityCluster]:
    return _dedupe_heuristic_clusters_backend(
        clusters=clusters,
        exact_title_groups_payload=exact_title_groups,
    )


def _prepare_duplicates_payload(df2: pd.DataFrame) -> dict[str, Any]:
    return _prepare_duplicates_payload_backend(df2)


def render_duplicates_tab(
    *,
    settings: Settings,
    dff_filtered: pd.DataFrame,
    header_left_render: Callable[[], None] | None = None,
) -> None:
    """
    Tab: Incidencias similares (posibles duplicados)
    - Por título: agrupación exacta por summary (repeticiones directas)
    - Por heurística: similitud textual (Jaccard de tokens)
    """
    inject_insights_chip_css()

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    # Normaliza para que status/priority siempre existan como strings (si están)
    df2 = open_only(dff).copy()
    if df2.empty:
        st.info("No hay incidencias abiertas con los filtros actuales.")
        return

    if col_exists(df2, "status"):
        df2["status"] = normalize_text_col(df2["status"], "(sin estado)")
    if col_exists(df2, "priority"):
        df2["priority"] = normalize_text_col(df2["priority"], "(sin priority)")
    if col_exists(df2, "summary"):
        df2["summary"] = df2["summary"].fillna("").astype(str)

    today = pd.Timestamp.utcnow().tz_localize(None).strftime("%Y-%m-%d")
    sig = dataframe_signature(
        df2,
        columns=("key", "summary", "status", "priority", "assignee", "created", "updated"),
        salt=f"insights.duplicates.v1:{today}",
    )
    payload, _ = cached_by_signature(
        "insights.duplicates",
        sig,
        lambda: _prepare_duplicates_payload(df2),
        max_entries=12,
    )

    key_to_url, key_to_meta = build_issue_lookup(df2, settings=settings)
    key_to_extra = payload.get("key_to_extra")
    if not isinstance(key_to_extra, dict):
        key_to_extra = {}

    top_titles = payload.get("top_titles")
    if not isinstance(top_titles, list):
        top_titles = []

    title_export = payload.get("title_export")
    if not isinstance(title_export, pd.DataFrame):
        title_export = pd.DataFrame(columns=["cluster_size", "summary", "keys"])

    clusters = payload.get("clusters")
    if not isinstance(clusters, list):
        clusters = []

    heur_export = payload.get("heur_export")
    if not isinstance(heur_export, pd.DataFrame):
        heur_export = pd.DataFrame(
            columns=["cluster_size", "summary", "keys", "status_dominante", "priority_dominante"]
        )

    duplicate_stats = payload.get("duplicate_stats")
    if not isinstance(duplicate_stats, ExactTitleDuplicateStats):
        duplicate_stats = exact_title_duplicate_stats(df2, summary_col="summary")
    duplicate_groups = int(duplicate_stats.groups)
    duplicate_issues = int(duplicate_stats.issues)
    st.caption(
        build_duplicates_brief(
            total_open=int(len(df2)),
            duplicate_groups=duplicate_groups,
            duplicate_issues=duplicate_issues,
            heuristic_clusters=int(len(clusters)),
        )
    )

    view_key = "insights_duplicates_view"
    if str(st.session_state.get(view_key) or "") not in {"Por título", "Por heurística"}:
        st.session_state[view_key] = "Por título"
    active_view = str(st.session_state.get(view_key) or "Por título")

    def _render_duplicates_export_actions() -> None:
        if active_view == "Por título":
            render_minimal_export_actions(
                key_prefix="insights::duplicates::title",
                filename_prefix="insights_duplicados",
                suffix="por_titulo",
                csv_df=title_export,
            )
            return
        render_minimal_export_actions(
            key_prefix="insights::duplicates::heur",
            filename_prefix="insights_duplicados",
            suffix="heuristica",
            csv_df=heur_export,
        )

    render_insights_header_row(
        left_render=header_left_render,
        right_render=_render_duplicates_export_actions,
    )
    toggle_scope = "insights_duplicates_view_toggle"
    _inject_duplicates_view_toggle_css(scope_key=toggle_scope)
    with st.container(key=toggle_scope):
        c_title, c_heur = st.columns(2, gap="small")
        c_title.button(
            "Por título",
            key=f"{view_key}::title_btn",
            type="primary" if active_view == "Por título" else "secondary",
            width="stretch",
            on_click=_set_duplicates_view,
            args=(view_key, "Por título"),
        )
        c_heur.button(
            "Por heurística",
            key=f"{view_key}::heur_btn",
            type="primary" if active_view == "Por heurística" else "secondary",
            width="stretch",
            on_click=_set_duplicates_view,
            args=(view_key, "Por heurística"),
        )
    active_view = str(st.session_state.get(view_key) or "Por título")

    if active_view == "Por título":
        st.caption("Repeticiones exactas por título de incidencia.")
        if not (col_exists(df2, "summary") and col_exists(df2, "key")):
            st.info("Faltan columnas `summary`/`key` para agrupar por título.")
        else:
            if not top_titles:
                st.info("No se detectaron títulos repetidos con los filtros actuales.")
            else:
                for title, title_keys in top_titles:
                    with st.expander(f"**{len(title_keys)}x** · {title}", expanded=False):
                        for k in title_keys:
                            status, prio, summ = key_to_meta.get(
                                k, ("(sin estado)", "(sin priority)", "")
                            )
                            url = key_to_url.get(k, "")
                            summ_txt = (summ or "").strip()
                            if len(summ_txt) > 140:
                                summ_txt = summ_txt[:137] + "..."
                            age_days, assignee = key_to_extra.get(k, (None, None))
                            render_issue_bullet(
                                key=k,
                                url=url,
                                status=status,
                                priority=prio,
                                summary=summ_txt,
                                age_days=age_days,
                                assignee=assignee,
                            )

    else:
        st.caption("Clusters por similitud de texto en el summary (heurístico).")

        if not clusters:
            st.info("No se encontraron clusters por heurística con los filtros actuales.")
        else:
            for c in clusters[:12]:
                with st.expander(f"**{c.size}x** · {c.summary}", expanded=False):
                    cluster_keys: List[str] = list(getattr(c, "keys", []) or [])
                    if not cluster_keys:
                        st.caption("(Sin keys)")
                        continue
                    for k in cluster_keys:
                        k = str(k).strip()
                        if not k:
                            continue
                        status, prio, summ = key_to_meta.get(
                            k, ("(sin estado)", "(sin priority)", "")
                        )
                        url = key_to_url.get(k, "")
                        summ_txt = (summ or "").strip()
                        if len(summ_txt) > 140:
                            summ_txt = summ_txt[:137] + "..."
                        age_days, assignee = key_to_extra.get(k, (None, None))
                        render_issue_bullet(
                            key=k,
                            url=url,
                            status=status,
                            priority=prio,
                            summary=summ_txt,
                            age_days=age_days,
                            assignee=assignee,
                        )
