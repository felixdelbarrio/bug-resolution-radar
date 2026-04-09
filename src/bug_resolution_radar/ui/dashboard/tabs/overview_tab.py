"""Overview tab rendering for executive summary, charts and actionable focus cards."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.duplicates import exact_title_duplicate_stats
from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.common import normalize_text_col
from bug_resolution_radar.ui.components.actionable_cards import (
    ActionableCardItem,
    render_actionable_card_grid,
)
from bug_resolution_radar.ui.components.executive_kpis import (
    ExecutiveKpiItem,
    render_executive_kpi_grid,
)
from bug_resolution_radar.ui.dashboard.exports.downloads import (
    figures_to_html_bytes,
    render_minimal_export_actions,
)
from bug_resolution_radar.ui.dashboard.performance import (
    elapsed_ms,
    render_perf_footer,
    resolve_budget,
)
from bug_resolution_radar.ui.dashboard.registry import ChartContext, build_trends_registry
from bug_resolution_radar.ui.insights.engine import top_non_other_theme

_OVERVIEW_PERF_BUDGETS_MS: dict[str, dict[str, float]] = {
    "KPIs": {
        "kpis": 280.0,
        "focus_cards": 220.0,
        "total": 520.0,
    },
    "Summary": {
        "summary_charts": 280.0,
        "summary_exports": 70.0,
        "total": 420.0,
    },
    "Overview": {
        "kpis": 280.0,
        "focus_cards": 220.0,
        "summary_charts": 280.0,
        "summary_exports": 70.0,
        "total": 880.0,
    },
}
_OVERVIEW_PERF_ORDERS: dict[str, list[str]] = {
    "KPIs": ["kpis", "focus_cards", "total"],
    "Summary": ["summary_charts", "summary_exports", "total"],
    "Overview": ["kpis", "focus_cards", "summary_charts", "summary_exports", "total"],
}


def _overview_perf_budget(view: str) -> dict[str, float]:
    return resolve_budget(
        view=view,
        budgets_by_view=_OVERVIEW_PERF_BUDGETS_MS,
        default_view="Overview",
    )


def _overview_perf_order(view: str) -> list[str]:
    return list(_OVERVIEW_PERF_ORDERS.get(str(view or ""), _OVERVIEW_PERF_ORDERS["Overview"]))


def _parse_summary_charts(settings: Settings, registry_ids: List[str]) -> List[str]:
    """Resolve up to three valid summary chart ids from canonical settings keys."""
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


def _exit_funnel_counts_from_filtered(status_df: pd.DataFrame) -> tuple[int, int, int]:
    """Return Accepted / Ready to Deploy / total counts from the filtered chart scope."""
    safe = status_df if isinstance(status_df, pd.DataFrame) else pd.DataFrame()
    if safe.empty or "status" not in safe.columns:
        return (0, 0, 0)
    stx = normalize_text_col(safe["status"], "(sin estado)").astype(str).str.strip().str.lower()
    accepted_count = int(stx.eq("accepted").sum())
    ready_deploy_count = int(stx.eq("ready to deploy").sum())
    return (accepted_count, ready_deploy_count, accepted_count + ready_deploy_count)


def _render_summary_charts(*, settings: Settings, ctx: ChartContext) -> dict[str, float]:
    """Render the three selected summary charts, export actions and perf timings."""
    perf_ms: dict[str, float] = {"summary_charts": 0.0, "summary_exports": 0.0}
    charts_build_start_ts = perf_counter()
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
    charts_build_ms = elapsed_ms(charts_build_start_ts)

    st.markdown(
        """
        <style>
          .st-key-overview_summary_shell [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--bbva-border-strong) !important;
            background: var(--bbva-surface-elevated) !important;
            box-shadow: 0 10px 24px color-mix(in srgb, var(--bbva-text) 10%, transparent) !important;
          }
          [class*="st-key-overview_summary_chart_"] [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--bbva-border-strong) !important;
            background: var(--bbva-surface) !important;
            background: color-mix(in srgb, var(--bbva-surface) 94%, var(--bbva-surface-2)) !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True, key="overview_summary_shell"):
        export_cols = ["key", "summary", "status", "priority", "assignee", "created", "resolved"]
        export_df = ctx.dff[[c for c in export_cols if c in ctx.dff.columns]].copy(deep=False)
        exports_start_ts = perf_counter()
        render_minimal_export_actions(
            key_prefix="overview::summary",
            filename_prefix="resumen_visual",
            suffix="completo",
            csv_df=export_df,
            figure=figures_for_export[0] if figures_for_export else None,
            html_bytes=figures_to_html_bytes(
                figures_for_export, title="Resumen visual", subtitles=titles_for_export
            ),
        )
        perf_ms["summary_exports"] = elapsed_ms(exports_start_ts)

        charts_render_start_ts = perf_counter()
        cols = st.columns(3, gap="medium")

        for idx, (col, (chart_id, chart_title, fig)) in enumerate(zip(cols, prepared)):
            with col:
                with st.container(border=True, key=f"overview_summary_chart_{idx}"):
                    if not chart_id:
                        st.caption("—")
                        st.info("No configurado")
                        continue

                    if fig is None:
                        st.caption(chart_title or chart_id)
                        st.info("Sin datos para este gráfico con los filtros actuales.")
                        continue

                    st.caption(chart_title or chart_id)
                    st.plotly_chart(fig, width="stretch")
        perf_ms["summary_charts"] = charts_build_ms + elapsed_ms(charts_render_start_ts)
    return perf_ms


def render_overview_tab(
    *,
    settings: Settings,
    kpis: Dict[str, Any],
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
) -> None:
    """Render overview chart section using filtered context data."""
    section_start_ts = perf_counter()
    dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    open_df = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    kpis = kpis if isinstance(kpis, dict) else {}

    ctx = ChartContext(dff=dff, open_df=open_df, kpis=kpis)
    perf_ms = _render_summary_charts(settings=settings, ctx=ctx)
    perf_ms["total"] = elapsed_ms(section_start_ts)

    summary_view = "Summary"
    render_perf_footer(
        snapshot_key="overview::summary::perf_snapshot",
        view=summary_view,
        ordered_blocks=_overview_perf_order(summary_view),
        metrics_ms=perf_ms,
        budgets_ms=_overview_perf_budget(summary_view),
        emit_captions=False,
    )

    # End-to-end snapshot aggregates KPI + Summary timings for overview tab control.
    kpi_snapshot = st.session_state.get("overview::kpis::perf_snapshot")
    if isinstance(kpi_snapshot, dict):
        kpi_metrics = kpi_snapshot.get("metrics_ms")
        if isinstance(kpi_metrics, dict):
            overview_metrics: dict[str, float] = {
                "kpis": float(kpi_metrics.get("kpis", 0.0) or 0.0),
                "focus_cards": float(kpi_metrics.get("focus_cards", 0.0) or 0.0),
                "summary_charts": float(perf_ms.get("summary_charts", 0.0) or 0.0),
                "summary_exports": float(perf_ms.get("summary_exports", 0.0) or 0.0),
            }
            overview_metrics["total"] = sum(
                float(overview_metrics.get(block, 0.0) or 0.0)
                for block in ("kpis", "focus_cards", "summary_charts", "summary_exports")
            )
            overview_view = "Overview"
            render_perf_footer(
                snapshot_key="overview::perf_snapshot",
                view=overview_view,
                ordered_blocks=_overview_perf_order(overview_view),
                metrics_ms=overview_metrics,
                budgets_ms=_overview_perf_budget(overview_view),
                caption_prefix="Perf E2E",
                emit_captions=False,
            )


def render_overview_kpis(
    *,
    kpis: Dict[str, Any],
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
) -> None:
    """Render compact executive KPIs plus dynamic actionable focus cards."""
    section_start_ts = perf_counter()
    perf_ms: dict[str, float] = {}
    kpis_start_ts = perf_counter()
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
        metric: str
        detail: str
        score: float
        section: str
        trend_chart: str | None = None
        insights_tab: str | None = None
        tone: str = "neutral"

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

    # Exit funnel must match the same filtered scope shown in "Issues por Estado" chart.
    accepted_count, ready_deploy_count, exit_buffer = _exit_funnel_counts_from_filtered(dff)
    exit_state = "Accepted" if accepted_count >= ready_deploy_count else "Ready to deploy"
    exit_state_count = accepted_count if exit_state == "Accepted" else ready_deploy_count

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
    filtered_total = int(len(dff))
    exit_buffer_pct = (exit_buffer / filtered_total * 100.0) if filtered_total else 0.0
    exit_state_pct = (exit_state_count / filtered_total * 100.0) if filtered_total else 0.0
    dup_groups = 0
    dup_issues = 0
    top_theme = "-"
    top_theme_count = 0
    created_14 = 0
    resolved_14 = 0

    if not open_df.empty and "summary" in open_df.columns:
        duplicate_stats = exact_title_duplicate_stats(open_df, summary_col="summary")
        dup_groups = int(duplicate_stats.groups)
        dup_issues = int(duplicate_stats.issues)
        top_theme, top_theme_count = top_non_other_theme(open_df)

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
          .exec-focus-title {
            margin: 0.06rem 0 0.34rem 0;
            font-weight: 800;
            color: var(--bbva-text);
            font-size: 0.96rem;
            letter-spacing: -0.01em;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    render_executive_kpi_grid(
        [
            ExecutiveKpiItem(
                label="Issues filtradas",
                value=f"{total_issues:,}",
                hint="Base de análisis actual",
            ),
            ExecutiveKpiItem(
                label="Backlog abierto",
                value=f"{open_issues:,}",
                hint=f"{open_pct:.1f}% del total",
            ),
            ExecutiveKpiItem(
                label="En cola > 30 días",
                value=f"{aged_30_count:,}",
                hint=f"{aged_30_pct:.1f}% de abiertas",
            ),
            ExecutiveKpiItem(
                label="Prioridad dominante",
                value=dominant_priority,
                hint=f"{dominant_priority_count:,} incidencias",
            ),
        ],
        columns=4,
    )

    perf_ms["kpis"] = elapsed_ms(kpis_start_ts)
    focus_cards_start_ts = perf_counter()
    st.markdown('<div class="exec-focus-title">Focos accionables</div>', unsafe_allow_html=True)

    trend_target_labels = {
        "timeseries": "Evolución",
        "age_buckets": "Antigüedad",
        "open_status_bar": "Estado",
        "open_priority_pie": "Prioridad",
    }
    insights_target_labels = {
        "top_topics": "Por funcionalidad",
        "duplicates": "Duplicados",
        "people": "Personas",
        "ops_health": "Salud operativa",
    }

    def _focus_scope_label(focus: FocusCard) -> str:
        if focus.section == "trends":
            detail = trend_target_labels.get(str(focus.trend_chart or ""), "Detalle")
            return f"Tendencias · {detail}"
        if focus.section == "insights":
            detail = insights_target_labels.get(str(focus.insights_tab or ""), "Detalle")
            return f"Insights · {detail}"
        return "Operación"

    focus_candidates: list[FocusCard] = []
    if aged_30_count > 0:
        focus_candidates.append(
            FocusCard(
                card_id="age",
                title="Cola envejecida",
                metric=f"{aged_30_count:,}",
                detail=f"abiertas con más de 30 días ({aged_30_pct:.1f}% del backlog abierto).",
                score=float(aged_30_pct),
                section="trends",
                trend_chart="age_buckets",
                tone="risk",
            )
        )
    if exit_buffer > 0:
        focus_candidates.append(
            FocusCard(
                card_id="exit",
                title="Salida finalista",
                metric=f"{exit_state_count:,}",
                detail=(
                    f"Estado: {exit_state}={exit_state_count:,} "
                    f"({exit_state_pct:.1f}% del total filtrado)."
                ),
                score=float(exit_buffer_pct)
                + (8.0 if accepted_count > (ready_deploy_count * 1.5) else 0.0),
                section="trends",
                trend_chart="open_status_bar",
                tone="flow",
            )
        )
    if blocked_count > 0:
        focus_candidates.append(
            FocusCard(
                card_id="blocked",
                title="Bloqueos activos",
                metric=f"{blocked_count:,}",
                detail=f"incidencias bloqueadas ({blocked_pct:.1f}% del backlog abierto).",
                score=float(blocked_pct) + (10.0 if blocked_count >= 10 else 0.0),
                section="insights",
                insights_tab="people",
                tone="warning",
            )
        )
    if dup_issues > 0 or top_theme_count > 0:
        dup_pct = (dup_issues / open_issues * 100.0) if open_issues else 0.0
        focus_candidates.append(
            FocusCard(
                card_id="hygiene",
                title="Higiene de backlog",
                metric=f"{dup_issues:,}",
                detail=(
                    f"duplicadas en {dup_groups:,} grupos. "
                    f"Tema líder: {top_theme} ({top_theme_count:,})."
                ),
                score=float(dup_pct) + (6.0 if dup_groups >= 20 else 0.0),
                section="insights",
                insights_tab="top_topics",
                tone="quality",
            )
        )
    if dominant_priority.lower() in {"supone un impedimento", "highest", "high"}:
        dom_pct = (dominant_priority_count / open_issues * 100.0) if open_issues else 0.0
        focus_candidates.append(
            FocusCard(
                card_id="critical_mix",
                title="Presión de criticidad",
                metric=f"{dominant_priority_count:,}",
                detail=f"issues con prioridad dominante {dominant_priority} ({dom_pct:.1f}% de abiertas).",
                score=float(dom_pct) + 12.0,
                section="trends",
                trend_chart="open_priority_pie",
                tone="risk",
            )
        )
    if created_14 > 0 or resolved_14 > 0:
        if created_14 > resolved_14:
            ratio = ((created_14 - resolved_14) / max(created_14, 1)) * 100.0
            focus_candidates.append(
                FocusCard(
                    card_id="flow_pressure",
                    title="Entrada superior a salida",
                    metric=f"{created_14:,} vs {resolved_14:,}",
                    detail="creadas vs cerradas en los últimos 14 días.",
                    score=float(ratio) + 10.0,
                    section="trends",
                    trend_chart="timeseries",
                    tone="warning",
                )
            )
        else:
            ratio = ((resolved_14 - created_14) / max(resolved_14, 1)) * 100.0
            focus_candidates.append(
                FocusCard(
                    card_id="flow_opportunity",
                    title="Oportunidad de limpieza",
                    metric=f"{resolved_14:,} vs {created_14:,}",
                    detail="cerradas vs creadas en los últimos 14 días.",
                    score=float(ratio),
                    section="trends",
                    trend_chart="timeseries",
                    tone="opportunity",
                )
            )

    if not focus_candidates:
        focus_candidates = [
            FocusCard(
                card_id="baseline",
                title="Seguimiento operativo",
                metric=f"{open_issues:,}",
                detail="incidencias en el backlog abierto actual.",
                score=0.0,
                section="trends",
                trend_chart="timeseries",
                tone="neutral",
            )
        ]

    focus_cards = sorted(focus_candidates, key=lambda x: x.score, reverse=True)[:4]
    if len(focus_cards) < 4:
        fallback = [
            FocusCard(
                card_id="age_f",
                title="Cola envejecida",
                metric=f"{aged_30_count:,}",
                detail="abiertas con más de 30 días.",
                score=0.0,
                section="trends",
                trend_chart="age_buckets",
                tone="risk",
            ),
            FocusCard(
                card_id="exit_f",
                title="Salida finalista",
                metric=f"{exit_state_count:,}",
                detail=f"Estado: {exit_state}={exit_state_count:,}.",
                score=0.0,
                section="trends",
                trend_chart="open_status_bar",
                tone="flow",
            ),
            FocusCard(
                card_id="topic_f",
                title="Higiene de backlog",
                metric=f"{top_theme_count:,}",
                detail=f"issues del tema líder: {top_theme}.",
                score=0.0,
                section="insights",
                insights_tab="top_topics",
                tone="quality",
            ),
            FocusCard(
                card_id="block_f",
                title="Bloqueos activos",
                metric=f"{blocked_count:,}",
                detail="incidencias bloqueadas actualmente.",
                score=0.0,
                section="insights",
                insights_tab="people",
                tone="warning",
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

    render_actionable_card_grid(
        [
            ActionableCardItem(
                card_id=str(focus.card_id),
                kicker=_focus_scope_label(focus),
                metric=str(focus.metric),
                detail=str(focus.detail),
                link_label=f"{focus.title} ↗",
                tone=str(focus.tone or "neutral"),
                on_click=_jump_to,
                click_args=(focus.section,),
                click_kwargs={
                    "trend_chart": focus.trend_chart,
                    "insights_tab": focus.insights_tab,
                },
            )
            for focus in focus_cards
        ],
        columns=4,
        key_prefix="exec_focus",
    )
    perf_ms["focus_cards"] = elapsed_ms(focus_cards_start_ts)
    perf_ms["total"] = elapsed_ms(section_start_ts)
    kpis_view = "KPIs"
    render_perf_footer(
        snapshot_key="overview::kpis::perf_snapshot",
        view=kpis_view,
        ordered_blocks=_overview_perf_order(kpis_view),
        metrics_ms=perf_ms,
        budgets_ms=_overview_perf_budget(kpis_view),
        emit_captions=False,
    )
