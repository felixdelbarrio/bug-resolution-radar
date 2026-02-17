"""Duplicate detection views by exact title and heuristic similarity."""

from __future__ import annotations

from collections import Counter
from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.insights import find_similar_issue_clusters
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.insights.chips import inject_insights_chip_css, render_issue_bullet
from bug_resolution_radar.ui.insights.helpers import (
    as_naive_utc,
    build_issue_lookup,
    col_exists,
    open_only,
    safe_df,
)


def render_duplicates_tab(*, settings: Settings, dff_filtered: pd.DataFrame) -> None:
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

    key_to_url, key_to_meta = build_issue_lookup(df2, settings=settings)
    key_to_extra: dict[str, tuple[float | None, str | None]] = {}

    if col_exists(df2, "key"):
        extra_cols = ["key"]
        if col_exists(df2, "created"):
            extra_cols.append("created")
        if col_exists(df2, "assignee"):
            extra_cols.append("assignee")

        extra_df = df2.loc[:, extra_cols].copy(deep=False)
        extra_df["key"] = extra_df["key"].fillna("").astype(str).str.strip()
        extra_df = extra_df[extra_df["key"] != ""].drop_duplicates(subset=["key"], keep="first")

        age_series = pd.Series([pd.NA] * len(extra_df), index=extra_df.index)
        if "created" in extra_df.columns:
            created_dt = pd.to_datetime(extra_df["created"], errors="coerce", utc=True)
            created_naive = as_naive_utc(created_dt)
            now = pd.Timestamp.utcnow().tz_localize(None)
            age_series = ((now - created_naive).dt.total_seconds() / 86400.0).clip(lower=0.0)

        assignee_series = (
            extra_df["assignee"].fillna("").astype(str).str.strip()
            if "assignee" in extra_df.columns
            else pd.Series([""] * len(extra_df), index=extra_df.index, dtype=str)
        )

        key_to_extra = {
            k: (
                float(age) if pd.notna(age) else None,
                assg if assg else None,
            )
            for k, age, assg in zip(
                extra_df["key"].tolist(), age_series.tolist(), assignee_series.tolist()
            )
        }

    t_title, t_heur = st.tabs(["Por título", "Por heurística"])

    with t_title:
        st.caption("Repeticiones exactas por título de incidencia.")
        if not (col_exists(df2, "summary") and col_exists(df2, "key")):
            st.info("Faltan columnas `summary`/`key` para agrupar por título.")
        else:
            title_groups = (
                df2[df2["summary"].astype(str).str.strip() != ""]
                .groupby("summary", sort=False)["key"]
                .apply(lambda s: [str(k).strip() for k in s.tolist() if str(k).strip()])
                .to_dict()
            )
            top_titles = sorted(title_groups.items(), key=lambda x: len(x[1]), reverse=True)
            top_titles = [
                (title, title_keys) for title, title_keys in top_titles if len(title_keys) > 1
            ][:12]

            title_export = pd.DataFrame(
                [
                    {
                        "cluster_size": len(keys),
                        "summary": title,
                        "keys": ", ".join(keys),
                    }
                    for title, keys in top_titles
                ]
            )
            render_minimal_export_actions(
                key_prefix="insights::duplicates::title",
                filename_prefix="insights_duplicados",
                suffix="por_titulo",
                csv_df=title_export,
            )

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

    with t_heur:
        st.caption("Clusters por similitud de texto en el summary (heurístico).")
        clusters = find_similar_issue_clusters(df2, only_open=False)
        heur_export = pd.DataFrame(
            [
                {
                    "cluster_size": int(getattr(c, "size", 0) or 0),
                    "summary": str(getattr(c, "summary", "") or ""),
                    "keys": ", ".join(
                        [
                            str(k).strip()
                            for k in list(getattr(c, "keys", []) or [])
                            if str(k).strip()
                        ]
                    ),
                    "status_dominante": (
                        Counter([str(s or "") for s in getattr(c, "statuses", [])]).most_common(1)[
                            0
                        ][0]
                        if getattr(c, "statuses", [])
                        else ""
                    ),
                    "priority_dominante": (
                        Counter([str(p or "") for p in getattr(c, "priorities", [])]).most_common(
                            1
                        )[0][0]
                        if getattr(c, "priorities", [])
                        else ""
                    ),
                }
                for c in clusters[:12]
            ]
        )
        render_minimal_export_actions(
            key_prefix="insights::duplicates::heur",
            filename_prefix="insights_duplicados",
            suffix="heuristica",
            csv_df=heur_export,
        )

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
