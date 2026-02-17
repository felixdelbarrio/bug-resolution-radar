"""Overview tab rendering for executive summary, charts and actionable focus cards."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.dashboard.downloads import (
    figures_to_html_bytes,
    render_minimal_export_actions,
)
from bug_resolution_radar.ui.dashboard.registry import ChartContext, build_trends_registry


def _parse_summary_charts(settings: Settings, registry_ids: List[str]) -> List[str]:
    """Resolve up to three valid summary chart ids from settings and legacy keys."""
    picked: List[str] = []

    def _append_csv(raw: object) -> None:
        txt = str(raw or "").strip()
        if not txt:
            return
        for part in txt.split(","):
            v = part.strip()
            if v and v in registry_ids and v not in picked:
                picked.append(v)

    _append_csv(getattr(settings, "DASHBOARD_SUMMARY_CHARTS", ""))
    _append_csv(getattr(settings, "TREND_SELECTED_CHARTS", ""))

    for name in (
        "TREND_FAV_1",
        "TREND_FAVORITE_1",
        "TREND_FAV_2",
        "TREND_FAVORITE_2",
        "TREND_FAV_3",
        "TREND_FAVORITE_3",
    ):
        v = str(getattr(settings, name, "") or "").strip()
        if v and v in registry_ids and v not in picked:
            picked.append(v)

    fallback = [
        x
        for x in [
            "timeseries",
            "age_buckets",
            "open_status_bar",
            "open_priority_pie",
            "resolution_hist",
        ]
        if x in registry_ids
    ]

    out: List[str] = []
    for x in picked + fallback:
        if x not in out:
            out.append(x)
        if len(out) == 3:
            break

    return out


def _render_summary_charts(*, settings: Settings, ctx: ChartContext) -> None:
    """Render the three selected summary charts and compact export actions."""
    registry = build_trends_registry()
    registry_ids = list(registry.keys())
    chosen = _parse_summary_charts(settings, registry_ids)

    slots: List[str] = (chosen + ["", "", ""])[:3]
    prepared: List[tuple[str, str, Optional[object]]] = []
    figures_for_export: List[object] = []
    titles_for_export: List[str] = []

    for chart_id in slots:
        if not chart_id:
            prepared.append(("", "", None))
            continue
        spec = registry.get(chart_id)
        if spec is None:
            prepared.append((chart_id, chart_id, None))
            continue
        fig = spec.render(ctx)
        if fig is not None:
            fig.update_layout(
                title_text="",
                margin=dict(l=10, r=10, t=35, b=10),
                height=320,
                showlegend=False,
            )
            figures_for_export.append(fig)
            titles_for_export.append(spec.title)
        prepared.append((chart_id, spec.title, fig))

    with st.container(border=True):
        export_cols = ["key", "summary", "status", "priority", "assignee", "created", "resolved"]
        export_df = ctx.dff[[c for c in export_cols if c in ctx.dff.columns]].copy(deep=False)
        render_minimal_export_actions(
            key_prefix="overview::summary",
            filename_prefix="resumen_visual",
            suffix="completo",
            csv_df=export_df,
            html_bytes=figures_to_html_bytes(
                figures_for_export, title="Resumen visual", subtitles=titles_for_export
            ),
        )

        cols = st.columns(3, gap="medium")

        for col, (chart_id, chart_title, fig) in zip(cols, prepared):
            with col:
                with st.container(border=True):
                    if not chart_id:
                        st.caption("—")
                        st.info("No configurado")
                        continue

                    if fig is None:
                        st.caption(chart_title or chart_id)
                        st.info("Sin datos para este gráfico con los filtros actuales.")
                        continue

                    st.caption(chart_title or chart_id)
                    st.plotly_chart(fig, use_container_width=True)


def render_overview_tab(
    *,
    settings: Settings,
    kpis: Dict[str, Any],
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
) -> None:
    """Render overview chart section using filtered context data."""
    dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    open_df = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    kpis = kpis if isinstance(kpis, dict) else {}

    ctx = ChartContext(dff=dff, open_df=open_df, kpis=kpis)
    _render_summary_charts(settings=settings, ctx=ctx)


def render_overview_kpis(
    *,
    kpis: Dict[str, Any],
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
) -> None:
    """Render compact executive KPIs plus dynamic actionable focus cards."""
    dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    open_df = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    kpis = kpis if isinstance(kpis, dict) else {}

    total_issues = int(kpis.get("issues_total", len(dff)))
    open_issues = int(kpis.get("issues_open", len(open_df)))
    open_pct = (open_issues / total_issues * 100.0) if total_issues else 0.0

    @dataclass(frozen=True)
    class FocusCard:
        card_id: str
        title: str
        body: str
        score: float
        section: str
        trend_chart: str | None = None
        insights_tab: str | None = None

    def _jump_to(
        section: str,
        *,
        trend_chart: str | None = None,
        insights_tab: str | None = None,
    ) -> None:
        st.session_state["__jump_to_tab"] = section
        if trend_chart:
            st.session_state["trend_chart_single"] = trend_chart
        if insights_tab:
            st.session_state["__jump_to_insights_tab"] = insights_tab

    blocked_count = 0
    accepted_count = 0
    ready_deploy_count = 0
    aged_30_count = 0
    dominant_priority = "-"
    dominant_priority_count = 0

    if not open_df.empty and "status" in open_df.columns:
        stx = normalize_text_col(open_df["status"], "(sin estado)").str.strip().str.lower()
        blocked_count = int(stx.str.contains("blocked|bloque", regex=True).sum())
        accepted_count = int(stx.eq("accepted").sum())
        ready_deploy_count = int(stx.str.contains("ready to deploy", regex=False).sum())

    if not open_df.empty and "created" in open_df.columns:
        created = pd.to_datetime(open_df["created"], errors="coerce", utc=True)
        created_naive = created.dt.tz_localize(None)
        now = pd.Timestamp.utcnow().tz_localize(None)
        ages = ((now - created_naive).dt.total_seconds() / 86400.0).clip(lower=0.0)
        aged_30_count = int((ages > 30).sum())

    if not open_df.empty and "priority" in open_df.columns:
        pr = normalize_text_col(open_df["priority"], "(sin priority)")
        vc = pr.value_counts()
        if not vc.empty:
            dominant_priority = str(vc.index[0])
            dominant_priority_count = int(vc.iloc[0])

    aged_30_pct = (aged_30_count / open_issues * 100.0) if open_issues else 0.0
    blocked_pct = (blocked_count / open_issues * 100.0) if open_issues else 0.0
    exit_buffer = accepted_count + ready_deploy_count
    exit_buffer_pct = (exit_buffer / open_issues * 100.0) if open_issues else 0.0
    dup_groups = 0
    dup_issues = 0
    top_theme = "-"
    top_theme_count = 0
    created_14 = 0
    resolved_14 = 0

    if not open_df.empty and "summary" in open_df.columns:
        summaries = open_df["summary"].fillna("").astype(str).str.strip()
        summaries = summaries[summaries != ""]
        if not summaries.empty:
            vc = summaries.value_counts()
            dup_groups = int((vc > 1).sum())
            dup_issues = int(vc[vc > 1].sum())

            theme_rules: list[tuple[str, list[str]]] = [
                ("Softoken", ["softoken", "token", "firma", "otp"]),
                ("Crédito", ["credito", "credito", "cvv", "tarjeta", "tdc"]),
                ("Monetarias", ["monetarias", "saldo", "nomina", "nomina"]),
                ("Tareas", ["tareas", "task", "acciones", "dashboard"]),
                ("Pagos", ["pago", "pagos", "tpv", "cobranza"]),
                ("Transferencias", ["transferencia", "spei", "swift", "divisas"]),
                (
                    "Login y acceso",
                    ["login", "acceso", "face id", "biometr", "password", "tokenbnc"],
                ),
                ("Notificaciones", ["notificacion", "notificacion", "push", "mensaje"]),
            ]

            def _norm(s: object) -> str:
                txt = str(s or "").strip().lower()
                txt = unicodedata.normalize("NFKD", txt)
                return "".join(ch for ch in txt if not unicodedata.combining(ch))

            def _theme_for_summary(summary: str) -> str:
                s = _norm(summary)
                for theme_name, keys in theme_rules:
                    for kw in keys:
                        if re.search(rf"\b{re.escape(_norm(kw))}\b", s):
                            return theme_name
                return "Otros"

            theme_vc = summaries.map(_theme_for_summary).value_counts()
            if not theme_vc.empty:
                non_otros = theme_vc[theme_vc.index.astype(str) != "Otros"]
                if not non_otros.empty:
                    top_theme = str(non_otros.index[0])
                    top_theme_count = int(non_otros.iloc[0])
                else:
                    top_theme = "—"
                    top_theme_count = 0

    if not dff.empty and "created" in dff.columns:
        created_dt = pd.to_datetime(dff["created"], errors="coerce", utc=True).dt.tz_localize(None)
        now = pd.Timestamp.utcnow().tz_localize(None)
        w14 = now - pd.Timedelta(days=14)
        created_14 = int((created_dt >= w14).sum())
        if "resolved" in dff.columns:
            resolved_dt = pd.to_datetime(dff["resolved"], errors="coerce", utc=True).dt.tz_localize(
                None
            )
            resolved_14 = int((resolved_dt >= w14).sum())

    st.markdown(
        """
        <style>
          .exec-wrap {
            border: 1px solid var(--bbva-border);
            border-radius: 16px;
            background: color-mix(in srgb, var(--bbva-surface) 62%, transparent);
            padding: 0.46rem 0.62rem;
          }
          .exec-kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.42rem;
            margin-bottom: 0.40rem;
          }
          .exec-kpi {
            border: 1px solid var(--bbva-border);
            border-radius: 12px;
            background: color-mix(in srgb, var(--bbva-surface) 75%, transparent);
            padding: 0.40rem 0.52rem;
          }
          .exec-kpi-lbl {
            color: var(--bbva-text-muted);
            font-size: 0.76rem;
            font-weight: 700;
            line-height: 1.15;
          }
          .exec-kpi-val {
            margin-top: 0.08rem;
            color: var(--bbva-text);
            font-size: 1.44rem;
            font-weight: 800;
            line-height: 1.04;
          }
          .exec-kpi-hint {
            margin-top: 0.14rem;
            color: var(--bbva-text-muted);
            font-size: 0.72rem;
            line-height: 1.1;
          }
          .exec-focus-title {
            margin: 0.05rem 0 0.28rem 0;
            font-weight: 800;
            color: var(--bbva-text);
            font-size: 0.90rem;
          }
          [class*="st-key-exec_focus_"] div[data-testid="stButton"] > button {
            justify-content: flex-start !important;
            width: 100% !important;
            min-height: 1.80rem !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            color: var(--bbva-text) !important;
            font-size: 1.03rem !important;
            font-weight: 800 !important;
            letter-spacing: -0.01em !important;
            border-radius: 8px !important;
            text-align: left !important;
            box-shadow: none !important;
          }
          [class*="st-key-exec_focus_"] div[data-testid="stButton"] > button:hover {
            color: var(--bbva-primary) !important;
            transform: translateX(1px);
          }
          [class*="st-key-exec_focus_"] div[data-testid="stButton"] > button:focus-visible {
            outline: none !important;
            box-shadow: 0 0 0 2px rgba(0,81,241,0.16) !important;
          }
          @media (max-width: 1020px) {
            .exec-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          }
          @media (max-width: 680px) {
            .exec-kpi-grid { grid-template-columns: 1fr; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        (
            '<section class="exec-wrap">'
            '<div class="exec-kpi-grid">'
            '<article class="exec-kpi">'
            '<div class="exec-kpi-lbl">Issues filtradas</div>'
            f'<div class="exec-kpi-val">{total_issues:,}</div>'
            '<div class="exec-kpi-hint">Base de análisis actual</div>'
            "</article>"
            '<article class="exec-kpi">'
            '<div class="exec-kpi-lbl">Backlog abierto</div>'
            f'<div class="exec-kpi-val">{open_issues:,}</div>'
            f'<div class="exec-kpi-hint">{open_pct:.1f}% del total</div>'
            "</article>"
            '<article class="exec-kpi">'
            '<div class="exec-kpi-lbl">En cola > 30 días</div>'
            f'<div class="exec-kpi-val">{aged_30_count:,}</div>'
            f'<div class="exec-kpi-hint">{aged_30_pct:.1f}% de abiertas</div>'
            "</article>"
            '<article class="exec-kpi">'
            '<div class="exec-kpi-lbl">Prioridad dominante</div>'
            f'<div class="exec-kpi-val">{dominant_priority}</div>'
            f'<div class="exec-kpi-hint">{dominant_priority_count:,} incidencias</div>'
            "</article>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="exec-focus-title">Focos accionables</div>', unsafe_allow_html=True)

    focus_candidates: list[FocusCard] = []
    if aged_30_count > 0:
        focus_candidates.append(
            FocusCard(
                card_id="age",
                title="Cola envejecida ↗",
                body=f"**{aged_30_count:,}** abiertas >30d (**{aged_30_pct:.1f}%**).",
                score=float(aged_30_pct),
                section="trends",
                trend_chart="age_buckets",
            )
        )
    if exit_buffer > 0:
        focus_candidates.append(
            FocusCard(
                card_id="exit",
                title="Embudo de salida ↗",
                body=f"**{exit_buffer:,}** en salida (**{exit_buffer_pct:.1f}%**): Accepted + Ready.",
                score=float(exit_buffer_pct)
                + (8.0 if accepted_count > (ready_deploy_count * 1.5) else 0.0),
                section="trends",
                trend_chart="open_status_bar",
            )
        )
    if blocked_count > 0:
        focus_candidates.append(
            FocusCard(
                card_id="blocked",
                title="Bloqueos activos ↗",
                body=f"**{blocked_count:,}** bloqueadas (**{blocked_pct:.1f}%** de abiertas).",
                score=float(blocked_pct) + (10.0 if blocked_count >= 10 else 0.0),
                section="insights",
                insights_tab="people",
            )
        )
    if dup_issues > 0 or top_theme_count > 0:
        dup_pct = (dup_issues / open_issues * 100.0) if open_issues else 0.0
        focus_candidates.append(
            FocusCard(
                card_id="hygiene",
                title="Higiene de backlog ↗",
                body=(
                    f"Duplicadas: **{dup_issues:,}** en **{dup_groups:,}** grupos. "
                    f"Tema líder: **{top_theme} ({top_theme_count:,})**."
                ),
                score=float(dup_pct) + (6.0 if dup_groups >= 20 else 0.0),
                section="insights",
                insights_tab="top_topics",
            )
        )
    if dominant_priority.lower() in {"supone un impedimento", "highest", "high"}:
        dom_pct = (dominant_priority_count / open_issues * 100.0) if open_issues else 0.0
        focus_candidates.append(
            FocusCard(
                card_id="critical_mix",
                title="Presión de criticidad ↗",
                body=f"Predomina **{dominant_priority}** con **{dominant_priority_count:,}** issues (**{dom_pct:.1f}%**).",
                score=float(dom_pct) + 12.0,
                section="trends",
                trend_chart="open_priority_pie",
            )
        )
    if created_14 > 0 or resolved_14 > 0:
        if created_14 > resolved_14:
            ratio = ((created_14 - resolved_14) / max(created_14, 1)) * 100.0
            focus_candidates.append(
                FocusCard(
                    card_id="flow_pressure",
                    title="Entrada superior a salida ↗",
                    body=f"Últimos 14 días: creadas **{created_14:,}** vs cerradas **{resolved_14:,}**.",
                    score=float(ratio) + 10.0,
                    section="trends",
                    trend_chart="timeseries",
                )
            )
        else:
            ratio = ((resolved_14 - created_14) / max(resolved_14, 1)) * 100.0
            focus_candidates.append(
                FocusCard(
                    card_id="flow_opportunity",
                    title="Oportunidad de limpieza ↗",
                    body=f"Últimos 14 días: cerradas **{resolved_14:,}** vs creadas **{created_14:,}**.",
                    score=float(ratio),
                    section="trends",
                    trend_chart="timeseries",
                )
            )

    if not focus_candidates:
        focus_candidates = [
            FocusCard(
                card_id="baseline",
                title="Seguimiento operativo ↗",
                body=f"Backlog abierto actual: **{open_issues:,}** incidencias.",
                score=0.0,
                section="trends",
                trend_chart="timeseries",
            )
        ]

    focus_cards = sorted(focus_candidates, key=lambda x: x.score, reverse=True)[:4]
    if len(focus_cards) < 4:
        fallback = [
            FocusCard(
                "age_f",
                "Cola envejecida ↗",
                f"**{aged_30_count:,}** abiertas >30d.",
                0.0,
                "trends",
                "age_buckets",
            ),
            FocusCard(
                "exit_f",
                "Embudo de salida ↗",
                f"**{exit_buffer:,}** en salida.",
                0.0,
                "trends",
                "open_status_bar",
            ),
            FocusCard(
                "topic_f",
                "Higiene de backlog ↗",
                f"Tema líder: **{top_theme} ({top_theme_count:,})**.",
                0.0,
                "insights",
                insights_tab="top_topics",
            ),
            FocusCard(
                "block_f",
                "Bloqueos activos ↗",
                f"**{blocked_count:,}** bloqueadas.",
                0.0,
                "insights",
                insights_tab="people",
            ),
        ]
        used_ids = {c.card_id for c in focus_cards}
        for cand in fallback:
            if cand.card_id in used_ids:
                continue
            focus_cards.append(cand)
            used_ids.add(cand.card_id)
            if len(focus_cards) >= 4:
                break

    focus_cols = st.columns(4, gap="small")
    for col, focus in zip(focus_cols, focus_cards):
        with col:
            with st.container(border=True):
                with st.container(key=f"exec_focus_{focus.card_id}"):
                    st.button(
                        focus.title,
                        key=f"exec_focus_{focus.card_id}_title",
                        use_container_width=True,
                        on_click=_jump_to,
                        args=(focus.section,),
                        kwargs={
                            "trend_chart": focus.trend_chart,
                            "insights_tab": focus.insights_tab,
                        },
                    )
                st.markdown(focus.body)

    # 👉 Si tu Overview tenía secciones (“Nuevas”, “Top X”, etc),
    # pégalas aquí debajo tal cual y NO cambia nada más.
