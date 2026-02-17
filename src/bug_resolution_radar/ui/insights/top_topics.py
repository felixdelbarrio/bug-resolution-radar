# src/bug_resolution_radar/ui/insights/top_topics.py
from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.insights.chips import (
    inject_insights_chip_css,
    neutral_chip_html,
    priority_chip_html,
    render_issue_bullet,
    status_chip_html,
)
from bug_resolution_radar.ui.insights.helpers import (
    build_issue_lookup,
    col_exists,
    open_only,
    safe_df,
)


def render_top_topics_tab(
    *, settings: Settings, dff_filtered: pd.DataFrame, kpis: Dict[str, Any]
) -> None:
    """
    Tab: Top 10 problemas/funcionalidades (abiertas)
    - Usa kpis["top_open_table"]
    - Muestra expander por tópico con lista de issues (key clickable) + estado + prioridad
    - Dentro del expander NO repite summary (redundante), solo status/criticidad
    """
    inject_insights_chip_css()

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    top_tbl = kpis.get("top_open_table")
    if not isinstance(top_tbl, pd.DataFrame) or top_tbl.empty:
        st.info("No hay tabla de Top 10 disponible (kpis['top_open_table']).")
        return

    cols = list(top_tbl.columns)
    summary_col = "summary" if "summary" in cols else (cols[0] if cols else None)
    count_col = "open_count" if "open_count" in cols else ("count" if "count" in cols else None)

    if not summary_col:
        st.info("Top 10 no tiene columnas esperadas.")
        return

    render_minimal_export_actions(
        key_prefix="insights::top_topics",
        filename_prefix="insights_topicos",
        suffix="top10",
        csv_df=top_tbl.head(10).copy(deep=False),
    )

    open_df = open_only(dff)
    total_open = int(len(open_df)) if open_df is not None else 0

    key_to_url, key_to_meta = build_issue_lookup(open_df, settings=settings)

    tmp_open = open_df.copy(deep=False)
    tmp_open["status"] = (
        normalize_text_col(tmp_open["status"], "(sin estado)")
        if col_exists(tmp_open, "status")
        else "(sin estado)"
    )
    tmp_open["priority"] = (
        normalize_text_col(tmp_open["priority"], "(sin priority)")
        if col_exists(tmp_open, "priority")
        else "(sin priority)"
    )
    tmp_open["summary"] = (
        tmp_open["summary"].fillna("").astype(str) if col_exists(tmp_open, "summary") else ""
    )
    by_summary = (
        {str(k): g for k, g in tmp_open.groupby("summary", sort=False)}
        if col_exists(tmp_open, "summary")
        else {}
    )

    for _, r in top_tbl.head(10).iterrows():
        topic = str(r.get(summary_col, "") or "").strip()
        cnt_val = r.get(count_col, None)

        try:
            cnt = int(cnt_val) if pd.notna(cnt_val) else 0
        except Exception:
            cnt = 0

        pct = (cnt / total_open * 100.0) if total_open > 0 else 0.0
        pct_txt = f"{pct:.1f}%"

        sub = by_summary.get(topic, pd.DataFrame()) if topic else pd.DataFrame()

        st_dom = (
            sub["status"].value_counts().index[0]
            if (not sub.empty and "status" in sub.columns)
            else "-"
        )
        pr_dom = (
            sub["priority"].value_counts().index[0]
            if (not sub.empty and "priority" in sub.columns)
            else "-"
        )

        topic_txt = topic
        if len(topic_txt) > 180:
            topic_txt = topic_txt[:177] + "..."

        hdr = f"**{cnt} issues** · **{pct_txt}** · {topic_txt}"

        with st.expander(hdr, expanded=False):
            st.markdown(
                (
                    '<div class="ins-meta-row">'
                    f"{neutral_chip_html(f'{cnt} issues')}"
                    f"{neutral_chip_html(pct_txt)}"
                    f"{status_chip_html(st_dom)}"
                    f"{priority_chip_html(pr_dom)}"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
            if sub.empty or not col_exists(sub, "key"):
                st.caption(
                    "No se han podido mapear issues individuales para este tópico (matching por summary)."
                )
                continue

            for _, ir in sub.iterrows():
                k = str(ir.get("key", "") or "").strip()
                if not k:
                    continue

                status, prio, _ = key_to_meta.get(k, ("(sin estado)", "(sin priority)", ""))
                url = key_to_url.get(k, "")

                # 👇 sin summary (redundante), solo estado y criticidad
                render_issue_bullet(
                    key=k,
                    url=url,
                    status=status,
                    priority=prio,
                )

    st.caption("Tip: el % te dice el ‘peso real’ del tópico en el backlog abierto filtrado.")
