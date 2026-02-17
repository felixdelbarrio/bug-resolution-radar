"""Operational health insights tab with KPI snapshot and aged-open cases."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.insights.chips import (
    inject_insights_chip_css,
    issue_card_html,
    priority_chip_html,
)
from bug_resolution_radar.ui.insights.helpers import (
    as_naive_utc,
    build_issue_lookup,
    col_exists,
    open_only,
    safe_df,
)


def render_ops_health_tab(*, settings: Settings, dff_filtered: pd.DataFrame) -> None:
    """
    Tab: Salud operativa (operational quick insights)
      - KPIs resumen (issues filtradas, abiertas, prioridad dominante)
      - Top 10 abiertas más antiguas (bullets + key clickable + status/priority/summary)
    """
    inject_insights_chip_css()

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    open_df = open_only(dff)
    export_cols = ["key", "summary", "status", "priority", "assignee", "created", "updated", "url"]
    render_minimal_export_actions(
        key_prefix="insights::ops_health",
        filename_prefix="insights_salud",
        suffix="abiertas",
        csv_df=open_df[[c for c in export_cols if c in open_df.columns]].copy(deep=False),
    )

    # -------------------------
    # KPIs resumen
    # -------------------------
    st.markdown(
        """
        <style>
          .ops-kpi-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 0.2rem;
            margin-bottom: 0.65rem;
          }
          .ops-kpi-card {
            border: 1px solid var(--bbva-border);
            border-radius: 12px;
            background: var(--bbva-surface-soft);
            padding: 0.64rem 0.72rem;
            min-height: 6.3rem;
          }
          .ops-kpi-label {
            color: var(--bbva-text-muted);
            font-weight: 700;
            font-size: 0.98rem;
            line-height: 1.2;
          }
          .ops-kpi-value {
            margin-top: 0.26rem;
            color: var(--bbva-text);
            font-weight: 800;
            font-size: 2.10rem;
            line-height: 1.08;
            letter-spacing: -0.01em;
          }
          .ops-kpi-sub {
            margin-top: 0.34rem;
            color: var(--bbva-text-muted);
            font-size: 0.86rem;
            line-height: 1.2;
          }
          @media (max-width: 980px) {
            .ops-kpi-grid { grid-template-columns: 1fr; }
          }
          .st-key-ops_health_top10_shell [data-testid="stVerticalBlockBorderWrapper"] {
            margin-top: 0.34rem !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    total_issues = int(len(dff))
    open_issues = int(len(open_df))
    if col_exists(open_df, "priority") and not open_df.empty:
        pr = normalize_text_col(open_df["priority"], "(sin priority)")
        top = pr.value_counts().head(1)
        top_pr = str(top.index[0]) if not top.empty else "-"
        top_count = int(top.iloc[0]) if not top.empty else 0
    else:
        top_pr = "-"
        top_count = 0

    pr_chip = priority_chip_html(top_pr) if top_pr != "-" else '<span class="ins-chip">-</span>'
    st.markdown(
        (
            '<div class="ops-kpi-grid">'
            '<article class="ops-kpi-card">'
            '<div class="ops-kpi-label">Issues (filtradas)</div>'
            f'<div class="ops-kpi-value">{total_issues:,}</div>'
            "</article>"
            '<article class="ops-kpi-card">'
            '<div class="ops-kpi-label">Abiertas (filtradas)</div>'
            f'<div class="ops-kpi-value">{open_issues:,}</div>'
            "</article>"
            '<article class="ops-kpi-card">'
            '<div class="ops-kpi-label">Prioridad dominante</div>'
            f'<div class="ops-kpi-value">{top_count:,}</div>'
            f'<div class="ops-kpi-sub">{pr_chip}</div>'
            "</article>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    # -------------------------
    # Top 10 abiertas más antiguas
    # -------------------------
    if open_df.empty or not (
        col_exists(open_df, "created") and pd.api.types.is_datetime64_any_dtype(open_df["created"])
    ):
        st.caption(
            "Tip: si tu ingest incluye `created` como datetime, aquí verás las más antiguas."
        )
        return

    tmp = open_df[open_df["created"].notna()].copy()
    if tmp.empty:
        st.caption("No hay `created` válidas para calcular antigüedad.")
        return

    now = pd.Timestamp.utcnow().tz_localize(None)
    created_naive = as_naive_utc(tmp["created"])
    tmp["age_days"] = (now - created_naive).dt.total_seconds() / 86400.0
    tmp["age_days"] = tmp["age_days"].clip(lower=0.0)

    # Orden por antigüedad (desc)
    tmp = tmp.sort_values("age_days", ascending=False).head(10)

    # Lookup (links + meta)
    key_to_url, key_to_meta = build_issue_lookup(tmp, settings=settings)

    with st.container(border=True, key="ops_health_top10_shell"):
        st.markdown("#### Top 10 abiertas más antiguas (según filtros)")
        cards: list[str] = []
        for _, rr in tmp.iterrows():
            k = str(rr.get("key", "") or "").strip()
            if not k:
                continue

            age = float(rr.get("age_days", 0.0) or 0.0)
            status, prio, summ = key_to_meta.get(k, ("(sin estado)", "(sin priority)", ""))

            summ_txt = (summ or "").strip()
            if len(summ_txt) > 120:
                summ_txt = summ_txt[:117] + "..."

            url = key_to_url.get(k, "")
            card = issue_card_html(
                key=k, url=url, status=status, priority=prio, summary=summ_txt, age_days=age
            )
            if card:
                cards.append(card)
        if cards:
            st.markdown("".join(cards), unsafe_allow_html=True)
