# src/bug_resolution_radar/ui/insights/duplicates.py
from __future__ import annotations

from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.insights import find_similar_issue_clusters
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.insights.chips import inject_insights_chip_css, render_issue_bullet
from bug_resolution_radar.ui.insights.helpers import build_issue_lookup, col_exists, safe_df


def render_duplicates_tab(*, settings: Settings, dff_filtered: pd.DataFrame) -> None:
    """
    Tab: Incidencias similares (posibles duplicados)
    - Expander por cluster
    - Dentro: bullets con key clickable + summary + status + priority
    """
    st.caption("Agrupado por similitud de texto en el summary (heurístico).")
    inject_insights_chip_css()

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    clusters = find_similar_issue_clusters(dff, only_open=True)
    if not clusters:
        st.info("No se encontraron clusters de incidencias similares (o hay pocos datos).")
        return

    cluster_export = pd.DataFrame(
        [
            {
                "cluster_size": int(getattr(c, "size", 0) or 0),
                "summary": str(getattr(c, "summary", "") or ""),
                "keys": ", ".join(
                    [str(k).strip() for k in list(getattr(c, "keys", []) or []) if str(k).strip()]
                ),
            }
            for c in clusters[:12]
        ]
    )
    render_minimal_export_actions(
        key_prefix="insights::duplicates",
        filename_prefix="insights_duplicados",
        suffix="clusters",
        csv_df=cluster_export,
    )

    # Normaliza para que status/priority siempre existan como strings (si están)
    df2 = dff.copy()
    if col_exists(df2, "status"):
        df2["status"] = normalize_text_col(df2["status"], "(sin estado)")
    if col_exists(df2, "priority"):
        df2["priority"] = normalize_text_col(df2["priority"], "(sin priority)")
    if col_exists(df2, "summary"):
        df2["summary"] = df2["summary"].fillna("").astype(str)

    key_to_url, key_to_meta = build_issue_lookup(df2, settings=settings)

    for c in clusters[:12]:
        with st.expander(f"**{c.size}x** · {c.summary}", expanded=False):
            keys: List[str] = list(getattr(c, "keys", []) or [])
            if not keys:
                st.caption("(Sin keys)")
                continue

            for k in keys:
                k = str(k).strip()
                if not k:
                    continue

                status, prio, summ = key_to_meta.get(k, ("(sin estado)", "(sin priority)", ""))
                url = key_to_url.get(k, "")

                summ_txt = (summ or "").strip()
                if len(summ_txt) > 140:
                    summ_txt = summ_txt[:137] + "..."

                render_issue_bullet(
                    key=k,
                    url=url,
                    status=status,
                    priority=prio,
                    summary=summ_txt,
                )
