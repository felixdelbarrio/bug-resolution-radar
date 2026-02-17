# src/bug_resolution_radar/ui/insights/top_topics.py
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.insights.chips import (
    inject_insights_chip_css,
    issue_card_html,
    neutral_chip_html,
    priority_chip_html,
    status_chip_html,
)
from bug_resolution_radar.ui.insights.helpers import (
    as_naive_utc,
    build_issue_lookup,
    col_exists,
    open_only,
    safe_df,
)


def render_top_topics_tab(
    *, settings: Settings, dff_filtered: pd.DataFrame, kpis: Dict[str, Any]
) -> None:
    """
    Tab: Top temas funcionales (abiertas)
    - Agrupa por macro-tema (Softoken, Crédito, Monetarias, Tareas, ...)
    - Muestra expander por tema con lista de issues (key clickable) + estado + prioridad
    """
    _ = kpis  # maintained in signature for compatibility with caller
    inject_insights_chip_css()

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    open_df = open_only(dff)
    total_open = int(len(open_df)) if open_df is not None else 0
    if total_open == 0:
        st.info("No hay incidencias abiertas para analizar temas.")
        return

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
    tmp_open["assignee"] = (
        normalize_text_col(tmp_open["assignee"], "(sin asignar)")
        if col_exists(tmp_open, "assignee")
        else "(sin asignar)"
    )
    if col_exists(tmp_open, "created"):
        created_dt = pd.to_datetime(tmp_open["created"], errors="coerce", utc=True)
        created_naive = as_naive_utc(created_dt)
        now = pd.Timestamp.utcnow().tz_localize(None)
        tmp_open["__age_days"] = ((now - created_naive).dt.total_seconds() / 86400.0).clip(
            lower=0.0
        )
    else:
        tmp_open["__age_days"] = pd.NA

    if not col_exists(tmp_open, "summary"):
        st.info("No hay columna `summary` para construir temas.")
        return

    theme_rules: list[tuple[str, list[str]]] = [
        ("Softoken", ["softoken", "token", "firma", "otp"]),
        ("Crédito", ["credito", "crédito", "cvv", "tarjeta", "tdc"]),
        ("Monetarias", ["monetarias", "saldo", "nomina", "nómina"]),
        ("Tareas", ["tareas", "task", "acciones", "dashboard"]),
        ("Pagos", ["pago", "pagos", "tpv", "cobranza"]),
        ("Transferencias", ["transferencia", "spei", "swift", "divisas"]),
        ("Login y acceso", ["login", "acceso", "face id", "biometr", "password", "tokenbnc"]),
        ("Notificaciones", ["notificacion", "notificación", "push", "mensaje"]),
    ]

    def _norm(s: object) -> str:
        txt = str(s or "").strip().lower()
        txt = unicodedata.normalize("NFKD", txt)
        return "".join(ch for ch in txt if not unicodedata.combining(ch))

    def _theme_for_summary(summary: str) -> str:
        s = _norm(summary)
        for theme, keys in theme_rules:
            for kw in keys:
                if re.search(rf"\b{re.escape(_norm(kw))}\b", s):
                    return theme
        return "Otros"

    tmp_open["__theme"] = tmp_open["summary"].map(_theme_for_summary)
    theme_counts = tmp_open["__theme"].value_counts().sort_values(ascending=False)
    non_otros = [t for t in theme_counts.index.tolist() if str(t) != "Otros"]
    has_otros = "Otros" in theme_counts.index
    if has_otros:
        # "Otros" siempre al final, aunque tenga mayor volumen.
        if len(non_otros) >= 9:
            top_themes = non_otros[:9] + ["Otros"]
        else:
            top_themes = non_otros + ["Otros"]
    else:
        top_themes = non_otros[:10]
    top_tbl = pd.DataFrame(
        {
            "tema": top_themes,
            "open_count": [int(theme_counts[t]) for t in top_themes],
            "pct_open": [
                (float(theme_counts[t]) / float(total_open) * 100.0 if total_open else 0.0)
                for t in top_themes
            ],
        }
    )
    render_minimal_export_actions(
        key_prefix="insights::top_topics",
        filename_prefix="insights_temas",
        suffix="top_temas",
        csv_df=top_tbl.copy(deep=False),
    )

    for _, r in top_tbl.iterrows():
        topic = str(r.get("tema", "") or "").strip()
        cnt = int(r.get("open_count", 0) or 0)
        pct_txt = f"{float(r.get('pct_open', 0.0) or 0.0):.1f}%"
        sub = tmp_open[tmp_open["__theme"] == topic].copy(deep=False)

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

        hdr = f"**{cnt} issues** · **{pct_txt}** · {topic}"

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
                st.caption("No se han podido mapear issues individuales para este tema.")
                continue

            sort_cols: list[str] = []
            sort_asc: list[bool] = []
            if col_exists(sub, "__age_days"):
                sort_cols.append("__age_days")
                sort_asc.append(False)
            if col_exists(sub, "updated"):
                sort_cols.append("updated")
                sort_asc.append(False)
            if sort_cols:
                sub = sub.sort_values(by=sort_cols, ascending=sort_asc)

            cards: list[str] = []
            for _, ir in sub.head(20).iterrows():
                k = str(ir.get("key", "") or "").strip()
                if not k:
                    continue

                status, prio, _ = key_to_meta.get(k, ("(sin estado)", "(sin priority)", ""))
                url = key_to_url.get(k, "")
                age_raw = ir.get("__age_days", pd.NA)
                age_days = float(age_raw) if pd.notna(age_raw) else None
                assignee = str(ir.get("assignee", "") or "").strip() or "(sin asignar)"
                summ_txt = str(ir.get("summary", "") or "").strip()
                if len(summ_txt) > 160:
                    summ_txt = summ_txt[:157] + "..."
                card = issue_card_html(
                    key=k,
                    url=url,
                    status=status,
                    priority=prio,
                    age_days=age_days,
                    assignee=assignee,
                    summary=summ_txt,
                )
                if card:
                    cards.append(card)
            if cards:
                st.markdown("".join(cards), unsafe_allow_html=True)

    st.caption("Tip: el % te dice el peso real de cada tema en el backlog abierto filtrado.")
