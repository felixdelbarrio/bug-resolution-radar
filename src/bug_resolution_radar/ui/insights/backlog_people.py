# src/bug_resolution_radar/ui/insights/backlog_people.py
from __future__ import annotations

import html
from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.insights.chips import (
    inject_insights_chip_css,
    neutral_chip_html,
    render_issue_bullet,
    status_chip_html,
)
from bug_resolution_radar.ui.insights.helpers import (
    as_naive_utc,
    build_issue_lookup,
    col_exists,
    open_only,
    pct,
    priority_weight,
    risk_label,
    safe_df,
    status_bucket,
)


# -------------------------
# Layout CSS
# -------------------------
def _inject_backlog_people_css() -> None:
    st.markdown(
        """
        <style>
          .people-state-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.45rem 0.5rem;
            margin: 0.35rem 0 0.2rem 0;
          }
          .people-state-item {
            display: inline-flex;
            align-items: center;
            gap: 0.34rem;
            min-height: 1.75rem;
          }
          .people-kpi-card {
            border: 1px solid rgba(17,25,45,0.12);
            border-radius: 12px;
            background: rgba(255,255,255,0.58);
            padding: 0.55rem 0.68rem 0.56rem 0.68rem;
            min-height: 94px;
          }
          .people-kpi-title {
            color: rgba(17,25,45,0.68);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.01em;
            text-transform: uppercase;
          }
          .people-kpi-value {
            color: #11192D;
            font-size: 1.85rem;
            font-weight: 800;
            line-height: 1.05;
            margin-top: 0.14rem;
          }
          .people-kpi-sub {
            color: rgba(17,25,45,0.66);
            font-size: 0.8rem;
            margin-top: 0.12rem;
          }
          .people-plan {
            border: 1px solid rgba(17,25,45,0.10);
            border-radius: 12px;
            background: rgba(255,255,255,0.48);
            padding: 0.7rem 0.8rem;
            margin-top: 0.2rem;
          }
          .people-plan-title {
            font-weight: 800;
            color: #11192D;
            margin-bottom: 0.36rem;
          }
          .people-plan-item {
            color: rgba(17,25,45,0.92);
            line-height: 1.38;
            margin: 0.28rem 0;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -------------------------
# Render
# -------------------------
def render_backlog_people_tab(*, settings: Settings, dff_filtered: pd.DataFrame) -> None:
    """
    Tab: Concentración de backlog por asignado (abiertas)
    - Expander por persona
    - Dentro: desglose por estado + KPIs
    - Extra: Top 3 más antiguas (si hay created)
    """
    inject_insights_chip_css()
    _inject_backlog_people_css()

    dff = safe_df(dff_filtered)
    if dff.empty:
        st.info("No hay datos con los filtros actuales.")
        return

    open_df = open_only(dff)
    if open_df.empty or not col_exists(open_df, "assignee"):
        st.info(
            "No hay incidencias abiertas (o no hay columna `assignee`) con los filtros actuales."
        )
        return

    df2 = open_df.copy()
    df2["assignee"] = df2["assignee"].fillna("(sin asignar)").astype(str)

    if col_exists(df2, "status"):
        df2["status"] = normalize_text_col(df2["status"], "(sin estado)")
    else:
        df2["status"] = "(sin estado)"

    if col_exists(df2, "priority"):
        df2["priority"] = normalize_text_col(df2["priority"], "(sin priority)")
    else:
        df2["priority"] = "(sin priority)"

    export_cols = ["key", "summary", "assignee", "status", "priority", "created", "updated", "url"]
    render_minimal_export_actions(
        key_prefix="insights::personas",
        filename_prefix="insights_personas",
        suffix="backlog",
        csv_df=df2[[c for c in export_cols if c in df2.columns]].copy(deep=False),
    )

    has_created = col_exists(df2, "created") and pd.api.types.is_datetime64_any_dtype(
        df2["created"]
    )
    if has_created:
        now = pd.Timestamp.utcnow().tz_localize(None)
        created_naive = as_naive_utc(df2["created"])
        df2["age_days"] = (now - created_naive).dt.total_seconds() / 86400.0
        df2["age_days"] = df2["age_days"].clip(lower=0.0)
    else:
        df2["age_days"] = pd.NA

    total_open = int(len(df2))
    counts = df2.groupby("assignee").size().sort_values(ascending=False).head(12)
    by_assignee = {str(k): g for k, g in df2.groupby("assignee", sort=False)}

    key_to_url, key_to_meta = build_issue_lookup(df2, settings=settings)

    if counts.empty:
        st.info("No hay personas con incidencias abiertas para mostrar.")
        return

    for assignee, n in counts.items():
        n_int = int(n)
        hdr = f"**{assignee}** · **{n_int}** abiertas · **{pct(n_int, total_open):.1f}%**"

        with st.expander(hdr, expanded=False):
            sub = by_assignee.get(str(assignee), pd.DataFrame()).copy(deep=False)

            st_counts = sub["status"].value_counts()
            state_items: List[str] = []
            for st_name, c in st_counts.items():
                state_items.append(
                    (
                        '<div class="people-state-item">'
                        f"{status_chip_html(st_name)}"
                        f"{neutral_chip_html(int(c))}"
                        "</div>"
                    )
                )
            st.markdown(
                (
                    '<div class="people-plan" style="margin-top:0.1rem;">'
                    '<div class="people-plan-title">Backlog por estado</div>'
                    f'<div class="people-state-grid">{"".join(state_items)}</div>'
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

            sub["__bucket"] = sub["status"].astype(str).map(status_bucket)
            bcounts = sub["__bucket"].value_counts()
            b_entrada = int(bcounts.get("entrada", 0))
            b_curso = int(bcounts.get("en_curso", 0))
            b_salida = int(bcounts.get("salida", 0))
            b_bloq = int(bcounts.get("bloqueado", 0))

            flow_risk_pct = pct(b_entrada + b_bloq, n_int)

            sub["__w"] = sub["priority"].astype(str).map(priority_weight)
            w_total = float(sub["__w"].sum()) if n_int else 0.0
            w_bad = (
                float(sub.loc[sub["__bucket"].isin(["entrada", "bloqueado"]), "__w"].sum())
                if n_int
                else 0.0
            )
            crit_risk_pct = (w_bad / w_total * 100.0) if w_total > 0 else 0.0

            risk_score = 0.6 * flow_risk_pct + 0.4 * crit_risk_pct
            risk_txt = risk_label(risk_score)

            push_pct = pct(b_salida, n_int)
            if has_created and sub["age_days"].notna().any():
                p90 = float(sub["age_days"].quantile(0.90))
                aging_value = f"{p90:.0f}d"
                aging_caption = "Casos más lentos"
            else:
                aging_value = "—"
                aging_caption = "Sin fecha de creación"

            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.markdown(
                    (
                        '<div class="people-kpi-card">'
                        '<div class="people-kpi-title">Riesgo operativo</div>'
                        f'<div class="people-kpi-value">{html.escape(str(risk_txt))}</div>'
                        f'<div class="people-kpi-sub">Flujo {flow_risk_pct:.0f}% · Criticidad {crit_risk_pct:.0f}%</div>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            with k2:
                st.markdown(
                    (
                        '<div class="people-kpi-card">'
                        '<div class="people-kpi-title">Empuje a salida</div>'
                        f'<div class="people-kpi-value">{push_pct:.0f}%</div>'
                        '<div class="people-kpi-sub">Cuanto más alto, mejor ritmo de avance</div>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            with k3:
                st.markdown(
                    (
                        '<div class="people-kpi-card">'
                        '<div class="people-kpi-title">Bloqueadas</div>'
                        f'<div class="people-kpi-value">{b_bloq}</div>'
                        '<div class="people-kpi-sub">Prioridad alta para desbloqueo</div>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            with k4:
                st.markdown(
                    (
                        '<div class="people-kpi-card">'
                        '<div class="people-kpi-title">Antigüedad crítica</div>'
                        f'<div class="people-kpi-value">{html.escape(aging_value)}</div>'
                        f'<div class="people-kpi-sub">{html.escape(aging_caption)}</div>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )

            st.markdown(
                '<div class="people-plan-title" style="margin-top:0.55rem;">Plan recomendado</div>',
                unsafe_allow_html=True,
            )
            recs: List[str] = []
            if b_bloq > 0:
                recs.append("Ataca bloqueadas primero: desbloquear 1–3 items suele liberar flujo.")
            if crit_risk_pct >= 55.0:
                recs.append(
                    "Criticidad atrapada en Entrada/Bloqueado: fija dueños/fechas y prioriza Highest/High."
                )
            if flow_risk_pct >= 60.0:
                recs.append(
                    "Entrada saturada: triage agresivo (duplicados/out-of-scope) y limita WIP nuevo."
                )
            if b_curso > 0 and b_salida == 0:
                recs.append(
                    "Crea ‘push’ hacia salida: objetivo semanal de mover X items a Verify/Deploy."
                )
            if not recs:
                recs.append("Buen equilibrio: mantén WIP limitado y revisa aging semanalmente.")
            st.markdown(
                (
                    '<div class="people-plan">'
                    + "".join(
                        f'<div class="people-plan-item">• {html.escape(rr)}</div>'
                        for rr in recs[:4]
                    )
                    + "</div>"
                ),
                unsafe_allow_html=True,
            )

            if has_created and col_exists(sub, "key") and sub["age_days"].notna().any():
                st.markdown("**Top 3 más antiguas (limpieza quirúrgica)**")
                oldest = (
                    sub.dropna(subset=["age_days"]).sort_values("age_days", ascending=False).head(3)
                )

                for _, rr in oldest.iterrows():
                    k = str(rr.get("key", "") or "").strip()
                    if not k:
                        continue
                    age = float(rr.get("age_days", 0.0) or 0.0)

                    status, prio, summ = key_to_meta.get(k, ("(sin estado)", "(sin priority)", ""))
                    summ_txt = (summ or "").strip()
                    if len(summ_txt) > 90:
                        summ_txt = summ_txt[:87] + "..."

                    url = key_to_url.get(k, "")
                    render_issue_bullet(
                        key=k,
                        url=url,
                        status=status,
                        priority=prio,
                        summary=summ_txt,
                        age_days=age,
                    )

    st.caption(
        "Tip: el riesgo combina ‘atasco de flujo’ (Entrada/Bloqueadas) + ‘criticidad atrapada’ (Highest/High sin avanzar)."
    )
