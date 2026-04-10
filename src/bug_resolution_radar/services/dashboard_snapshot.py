"""Backend snapshots for dashboard and intelligence views."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, cast

import pandas as pd
import plotly.graph_objects as go

from bug_resolution_radar.analytics.duplicates import exact_title_duplicate_stats
from bug_resolution_radar.analytics.analysis_window import apply_analysis_depth_filter
from bug_resolution_radar.analytics.duplicate_insights import prepare_duplicates_payload
from bug_resolution_radar.analytics.filtering import (
    FilterState,
    apply_dashboard_issue_scope,
    apply_filters,
    normalize_filter_tokens,
    open_only,
)
from bug_resolution_radar.analytics.issues import normalize_text_col, priority_rank
from bug_resolution_radar.analytics.insights import (
    build_theme_color_map,
    build_theme_daily_trend,
    build_theme_fortnight_trend,
    build_theme_render_order,
    order_theme_labels_by_volume,
    prepare_open_theme_payload,
    segment_text_color,
    top_non_other_theme,
)
from bug_resolution_radar.analytics.insights_scope import (
    INSIGHTS_VIEW_MODE_ACCUMULATED,
    INSIGHTS_VIEW_MODE_LABELS,
    INSIGHTS_VIEW_MODE_OPTIONS,
    build_insights_combo_context,
)
from bug_resolution_radar.analytics.kpis import compute_kpis
from bug_resolution_radar.analytics.period_summary import (
    build_country_quincenal_result,
    format_window_label,
    source_label_map,
)
from bug_resolution_radar.analytics.quincenal_scope import (
    QUINCENAL_SCOPE_CLOSED_CURRENT,
    QUINCENAL_SCOPE_CREATED_CURRENT,
    QUINCENAL_SCOPE_CREATED_MONTH,
    QUINCENAL_SCOPE_CREATED_PREVIOUS,
    QUINCENAL_SCOPE_OPEN_TOTAL,
    QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
    apply_issue_key_scope,
    quincenal_scope_options,
    should_show_open_split,
)
from bug_resolution_radar.analytics.topic_expandable_summary import (
    TopicExpandableSummary,
    build_topic_expandable_summaries,
)
from bug_resolution_radar.analytics.trend_charts import ChartContext, build_trends_registry
from bug_resolution_radar.analytics.trend_constants import (
    canonical_status_order,
    order_statuses_canonical,
)
from bug_resolution_radar.analytics.trend_insights import (
    build_trend_insight_pack,
    build_duplicates_brief,
    build_ops_health_brief,
    build_people_plan_recommendations,
    build_topic_brief,
)
from bug_resolution_radar.config import Settings
from bug_resolution_radar.repositories.issues_store import load_issues_df
from bug_resolution_radar.services.workspace import WorkspaceSelection, apply_workspace_source_scope
from bug_resolution_radar.theme.design_tokens import BBVA_LIGHT
from bug_resolution_radar.theme.plotly_style import apply_plotly_bbva


def _fig_payload(fig: Any) -> dict[str, Any] | None:
    if fig is None:
        return None
    try:
        import plotly.io as pio

        payload = json.loads(pio.to_json(fig, pretty=False))
        return cast(dict[str, Any], payload) if isinstance(payload, dict) else None
    except Exception:
        try:
            payload = fig.to_plotly_json()
            return cast(dict[str, Any], payload) if isinstance(payload, dict) else None
        except Exception:
            return None


def _fmt_days(value: object) -> str:
    if isinstance(value, bool):
        return f"{float(int(value)):.1f}d"
    if isinstance(value, (int, float)):
        return f"{float(value):.1f}d"
    token = str(value or "").strip()
    if not token:
        return "0.0d"
    try:
        return f"{float(token):.1f}d"
    except Exception:
        return "0.0d"


def _parse_settings_list(raw: object) -> list[str]:
    token = str(raw or "").strip()
    if not token:
        return []
    try:
        payload = json.loads(token)
    except Exception:
        payload = None
    if isinstance(payload, list):
        return normalize_filter_tokens([str(item).strip() for item in payload if str(item).strip()])
    return normalize_filter_tokens([part.strip() for part in token.split(",") if part.strip()])


def build_default_filters(settings: Settings) -> dict[str, list[str]]:
    return {
        "status": _parse_settings_list(getattr(settings, "DASHBOARD_FILTER_STATUS_JSON", "[]")),
        "priority": _parse_settings_list(getattr(settings, "DASHBOARD_FILTER_PRIORITY_JSON", "[]")),
        "assignee": _parse_settings_list(getattr(settings, "DASHBOARD_FILTER_ASSIGNEE_JSON", "[]")),
    }


def _parse_summary_chart_ids(settings: Settings, *, registry_ids: Sequence[str]) -> list[str]:
    picked: list[str] = []
    for raw in (
        getattr(settings, "DASHBOARD_SUMMARY_CHARTS", ""),
        getattr(settings, "TREND_SELECTED_CHARTS", ""),
    ):
        for token in str(raw or "").split(","):
            chart_id = str(token or "").strip()
            if chart_id and chart_id in registry_ids and chart_id not in picked:
                picked.append(chart_id)

    fallback = [
        chart_id
        for chart_id in (
            "timeseries",
            "age_buckets",
            "open_status_bar",
            "open_priority_pie",
            "resolution_hist",
        )
        if chart_id in registry_ids and chart_id not in picked
    ]
    return (picked + fallback)[:3]


def build_dashboard_defaults(settings: Settings) -> dict[str, Any]:
    registry = build_trends_registry()
    chart_ids = list(registry.keys())
    summary_ids = _parse_summary_chart_ids(settings, registry_ids=chart_ids)
    default_trend_chart = (
        "open_status_bar" if "open_status_bar" in chart_ids else (chart_ids[0] if chart_ids else "")
    )
    return {
        "summaryChartIds": summary_ids,
        "defaultTrendChartId": default_trend_chart,
    }


def _exit_funnel_counts_from_filtered(status_df: pd.DataFrame) -> tuple[int, int, int]:
    safe = status_df if isinstance(status_df, pd.DataFrame) else pd.DataFrame()
    if safe.empty or "status" not in safe.columns:
        return (0, 0, 0)
    stx = normalize_text_col(safe["status"], "(sin estado)").astype(str).str.strip().str.lower()
    accepted_count = int(stx.eq("accepted").sum())
    ready_deploy_count = int(stx.eq("ready to deploy").sum())
    return (accepted_count, ready_deploy_count, accepted_count + ready_deploy_count)


def build_overview_focus_cards(
    *,
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
    kpis: dict[str, Any],
) -> list[dict[str, Any]]:
    dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    open_df = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    total_issues = int(kpis.get("issues_total", len(dff)))
    open_issues = int(kpis.get("issues_open", len(open_df)))

    blocked_count = 0
    if not open_df.empty and "status" in open_df.columns:
        stx = normalize_text_col(open_df["status"], "(sin estado)").str.strip().str.lower()
        blocked_count = int(stx.str.contains("blocked|bloque", regex=True).sum())

    accepted_count, ready_deploy_count, exit_buffer = _exit_funnel_counts_from_filtered(dff)
    exit_state = "Accepted" if accepted_count >= ready_deploy_count else "Ready to deploy"
    exit_state_count = accepted_count if exit_state == "Accepted" else ready_deploy_count
    exit_state_pct = (exit_state_count / total_issues * 100.0) if total_issues else 0.0
    exit_buffer_pct = (exit_buffer / total_issues * 100.0) if total_issues else 0.0

    aged_30_count = 0
    if not open_df.empty and "created" in open_df.columns:
        created = pd.to_datetime(open_df["created"], errors="coerce", utc=True).dt.tz_localize(None)
        now = pd.Timestamp.utcnow().tz_localize(None)
        ages = ((now - created).dt.total_seconds() / 86400.0).clip(lower=0.0)
        aged_30_count = int((ages > 30).sum())

    dominant_priority = "-"
    dominant_priority_count = 0
    if not open_df.empty and "priority" in open_df.columns:
        priorities = normalize_text_col(open_df["priority"], "(sin priority)")
        value_counts = priorities.value_counts()
        if not value_counts.empty:
            dominant_priority = str(value_counts.index[0])
            dominant_priority_count = int(value_counts.iloc[0])

    dup_groups = 0
    dup_issues = 0
    if not open_df.empty:
        try:
            duplicate_stats = exact_title_duplicate_stats(open_df)
            dup_groups = int(getattr(duplicate_stats, "groups", 0) or 0)
            dup_issues = int(getattr(duplicate_stats, "issues", 0) or 0)
        except Exception:
            dup_groups = 0
            dup_issues = 0
    top_theme, top_theme_count = top_non_other_theme(open_df)

    created_14 = 0
    resolved_14 = 0
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

    aged_30_pct = (aged_30_count / open_issues * 100.0) if open_issues else 0.0
    blocked_pct = (blocked_count / open_issues * 100.0) if open_issues else 0.0

    focus_candidates: list[dict[str, Any]] = []
    if aged_30_count > 0:
        focus_candidates.append(
            {
                "cardId": "age",
                "title": "Cola envejecida",
                "metric": f"{aged_30_count:,}",
                "detail": f"abiertas con más de 30 días ({aged_30_pct:.1f}% del backlog abierto).",
                "score": float(aged_30_pct),
                "panel": "trends",
                "target": "age_buckets",
                "kicker": "Tendencias · Antigüedad",
                "tone": "risk",
            }
        )
    if exit_buffer > 0:
        focus_candidates.append(
            {
                "cardId": "exit",
                "title": "Salida finalista",
                "metric": f"{exit_state_count:,}",
                "detail": f"Estado: {exit_state}={exit_state_count:,} ({exit_state_pct:.1f}% del total filtrado).",
                "score": float(exit_buffer_pct)
                + (8.0 if accepted_count > (ready_deploy_count * 1.5) else 0.0),
                "panel": "trends",
                "target": "open_status_bar",
                "kicker": "Tendencias · Estado",
                "tone": "flow",
            }
        )
    if blocked_count > 0:
        focus_candidates.append(
            {
                "cardId": "blocked",
                "title": "Bloqueos activos",
                "metric": f"{blocked_count:,}",
                "detail": f"incidencias bloqueadas ({blocked_pct:.1f}% del backlog abierto).",
                "score": float(blocked_pct) + (10.0 if blocked_count >= 10 else 0.0),
                "panel": "insights",
                "target": "people",
                "kicker": "Insights · Personas",
                "tone": "warning",
            }
        )
    if dup_issues > 0 or top_theme_count > 0:
        dup_pct = (dup_issues / open_issues * 100.0) if open_issues else 0.0
        focus_candidates.append(
            {
                "cardId": "hygiene",
                "title": "Higiene de backlog",
                "metric": f"{dup_issues:,}",
                "detail": f"duplicadas en {dup_groups:,} grupos. Tema líder: {top_theme} ({top_theme_count:,}).",
                "score": float(dup_pct) + (6.0 if dup_groups >= 20 else 0.0),
                "panel": "insights",
                "target": "top_topics",
                "kicker": "Insights · Por funcionalidad",
                "tone": "quality",
            }
        )
    if dominant_priority.lower() in {"supone un impedimento", "highest", "high"}:
        dom_pct = (dominant_priority_count / open_issues * 100.0) if open_issues else 0.0
        focus_candidates.append(
            {
                "cardId": "critical_mix",
                "title": "Presión de criticidad",
                "metric": f"{dominant_priority_count:,}",
                "detail": f"issues con prioridad dominante {dominant_priority} ({dom_pct:.1f}% de abiertas).",
                "score": float(dom_pct) + 12.0,
                "panel": "trends",
                "target": "open_priority_pie",
                "kicker": "Tendencias · Prioridad",
                "tone": "risk",
            }
        )
    if created_14 > 0 or resolved_14 > 0:
        if created_14 > resolved_14:
            ratio = ((created_14 - resolved_14) / max(created_14, 1)) * 100.0
            focus_candidates.append(
                {
                    "cardId": "flow_pressure",
                    "title": "Entrada superior a salida",
                    "metric": f"{created_14:,} vs {resolved_14:,}",
                    "detail": "creadas vs cerradas en los últimos 14 días.",
                    "score": float(ratio) + 10.0,
                    "panel": "trends",
                    "target": "timeseries",
                    "kicker": "Tendencias · Evolución",
                    "tone": "warning",
                }
            )
        else:
            ratio = ((resolved_14 - created_14) / max(resolved_14, 1)) * 100.0
            focus_candidates.append(
                {
                    "cardId": "flow_opportunity",
                    "title": "Oportunidad de limpieza",
                    "metric": f"{resolved_14:,} vs {created_14:,}",
                    "detail": "cerradas vs creadas en los últimos 14 días.",
                    "score": float(ratio),
                    "panel": "trends",
                    "target": "timeseries",
                    "kicker": "Tendencias · Evolución",
                    "tone": "opportunity",
                }
            )

    if not focus_candidates:
        focus_candidates = [
            {
                "cardId": "baseline",
                "title": "Seguimiento operativo",
                "metric": f"{open_issues:,}",
                "detail": "incidencias en el backlog abierto actual.",
                "score": 0.0,
                "panel": "trends",
                "target": "timeseries",
                "kicker": "Tendencias · Evolución",
                "tone": "neutral",
            }
        ]

    fallback_cards = [
        {
            "cardId": "age_f",
            "title": "Cola envejecida",
            "metric": f"{aged_30_count:,}",
            "detail": "abiertas con más de 30 días.",
            "score": 0.0,
            "panel": "trends",
            "target": "age_buckets",
            "kicker": "Tendencias · Antigüedad",
            "tone": "risk",
        },
        {
            "cardId": "exit_f",
            "title": "Salida finalista",
            "metric": f"{exit_state_count:,}",
            "detail": f"Estado: {exit_state}={exit_state_count:,}.",
            "score": 0.0,
            "panel": "trends",
            "target": "open_status_bar",
            "kicker": "Tendencias · Estado",
            "tone": "flow",
        },
        {
            "cardId": "topic_f",
            "title": "Higiene de backlog",
            "metric": f"{top_theme_count:,}",
            "detail": f"issues del tema líder: {top_theme}.",
            "score": 0.0,
            "panel": "insights",
            "target": "top_topics",
            "kicker": "Insights · Por funcionalidad",
            "tone": "quality",
        },
        {
            "cardId": "block_f",
            "title": "Bloqueos activos",
            "metric": f"{blocked_count:,}",
            "detail": "incidencias bloqueadas actualmente.",
            "score": 0.0,
            "panel": "insights",
            "target": "people",
            "kicker": "Insights · Personas",
            "tone": "warning",
        },
    ]

    focus_cards = sorted(
        focus_candidates, key=lambda row: float(row.get("score", 0.0)), reverse=True
    )[:4]
    used_ids = {str(card.get("cardId") or "") for card in focus_cards}
    for fallback in fallback_cards:
        card_id = str(fallback.get("cardId") or "")
        if card_id in used_ids:
            continue
        focus_cards.append(fallback)
        used_ids.add(card_id)
        if len(focus_cards) >= 4:
            break
    return focus_cards[:4]


def build_overview_kpis_payload(
    *,
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
    kpis: dict[str, Any],
) -> list[dict[str, str]]:
    dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    open_df = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    kpis = kpis if isinstance(kpis, dict) else {}

    total_issues = int(kpis.get("issues_total", len(dff)))
    open_issues = int(kpis.get("issues_open", len(open_df)))
    open_pct = (open_issues / total_issues * 100.0) if total_issues else 0.0

    aged_30_count = 0
    if not open_df.empty and "created" in open_df.columns:
        created = pd.to_datetime(open_df["created"], errors="coerce", utc=True).dt.tz_localize(None)
        now = pd.Timestamp.utcnow().tz_localize(None)
        ages = ((now - created).dt.total_seconds() / 86400.0).clip(lower=0.0)
        aged_30_count = int((ages > 30).sum())
    aged_30_pct = (aged_30_count / open_issues * 100.0) if open_issues else 0.0

    dominant_priority = "-"
    dominant_priority_count = 0
    if not open_df.empty and "priority" in open_df.columns:
        priorities = normalize_text_col(open_df["priority"], "(sin priority)")
        value_counts = priorities.value_counts()
        if not value_counts.empty:
            dominant_priority = str(value_counts.index[0])
            dominant_priority_count = int(value_counts.iloc[0])
    dominant_priority_token = dominant_priority.strip().lower()
    if dominant_priority_token in {"supone un impedimento", "highest", "high"}:
        dominant_priority_tone = "risk"
    elif dominant_priority_token == "medium":
        dominant_priority_tone = "warning"
    elif dominant_priority_token in {"low", "lowest"}:
        dominant_priority_tone = "flow"
    else:
        dominant_priority_tone = "quality"

    return [
        {
            "label": "Issues filtradas",
            "value": f"{total_issues:,}",
            "hint": "Base de análisis actual",
            "tone": "quality",
        },
        {
            "label": "Backlog abierto",
            "value": f"{open_issues:,}",
            "hint": f"{open_pct:.1f}% del total",
            "tone": "warning",
        },
        {
            "label": "En cola > 30 días",
            "value": f"{aged_30_count:,}",
            "hint": f"{aged_30_pct:.1f}% de abiertas",
            "tone": "risk",
        },
        {
            "label": "Prioridad dominante",
            "value": dominant_priority,
            "hint": f"{dominant_priority_count:,} incidencias",
            "tone": dominant_priority_tone,
        },
    ]


def build_status_priority_matrix_payload(
    scoped_df: pd.DataFrame,
    *,
    active_filters: FilterState,
) -> dict[str, Any]:
    if (
        scoped_df is None
        or scoped_df.empty
        or "status" not in scoped_df.columns
        or "priority" not in scoped_df.columns
    ):
        return {
            "total": 0,
            "priorities": [],
            "rows": [],
            "selected": {"status": [], "priority": []},
        }

    mx = scoped_df.assign(
        status=normalize_text_col(scoped_df["status"], "(sin estado)"),
        priority=normalize_text_col(scoped_df["priority"], "(sin priority)"),
    )
    statuses = order_statuses_canonical(mx["status"].value_counts().index.tolist())
    priorities = sorted(
        mx["priority"].dropna().astype(str).unique().tolist(),
        key=lambda value: (priority_rank(value), value),
    )
    if "Supone un impedimento" in priorities:
        priorities = ["Supone un impedimento"] + [
            value for value in priorities if value != "Supone un impedimento"
        ]
    counts = pd.crosstab(mx["status"], mx["priority"])
    col_totals = {
        priority: int(counts[priority].sum()) if priority in counts.columns else 0
        for priority in priorities
    }
    row_totals = {
        status: int(counts.loc[status].sum()) if status in counts.index else 0
        for status in statuses
    }
    rows = []
    for status in statuses:
        rows.append(
            {
                "status": status,
                "count": row_totals.get(status, 0),
                "cells": [
                    {
                        "priority": priority,
                        "count": int(counts.at[status, priority])
                        if status in counts.index and priority in counts.columns
                        else 0,
                    }
                    for priority in priorities
                ],
            }
        )
    return {
        "title": "Matriz Estado x Priority (filtradas)",
        "total": int(sum(row_totals.values())),
        "priorities": [
            {"priority": priority, "count": col_totals.get(priority, 0)} for priority in priorities
        ],
        "rows": rows,
        "selected": {
            "status": list(active_filters.status or []),
            "priority": list(active_filters.priority or []),
        },
    }


def _norm_status_token(value: object) -> str:
    return str(value or "").strip().lower()


def _status_filter_has_terminal(status_filters: list[str]) -> bool:
    terminal_tokens = (
        "closed",
        "resolved",
        "done",
        "deployed",
        "accepted",
        "cancelled",
        "canceled",
    )
    return any(
        any(token in _norm_status_token(status_name) for token in terminal_tokens)
        for status_name in list(status_filters or [])
    )


def _effective_trends_open_scope(
    *,
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
    active_status_filters: list[str],
) -> tuple[pd.DataFrame, bool]:
    safe_open = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    safe_dff = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    chosen = [str(item).strip() for item in list(active_status_filters or []) if str(item).strip()]
    if not chosen or safe_dff.empty or "status" not in safe_dff.columns:
        return safe_open, False
    status_norm = normalize_text_col(safe_dff["status"], "(sin estado)")
    scoped = safe_dff.loc[status_norm.isin(chosen)].copy(deep=False)
    if scoped.empty:
        return safe_open, False
    if _status_filter_has_terminal(chosen):
        return scoped, True
    return safe_open, False


@dataclass(frozen=True)
class DashboardQuery:
    workspace: WorkspaceSelection
    filters: FilterState
    quincenal_scope: str = "Todas"
    issue_scope_keys: tuple[str, ...] = ()
    issue_sort_col: str = ""
    issue_like_query: str = ""
    chart_ids: tuple[str, ...] = ()
    dark_mode: bool = False


def load_workspace_dataframe(settings: Settings, *, query: DashboardQuery) -> pd.DataFrame:
    df = load_issues_df(settings.DATA_PATH)
    scoped_df = apply_workspace_source_scope(df, settings=settings, selection=query.workspace)
    return apply_analysis_depth_filter(scoped_df, settings=settings)


def build_dashboard_snapshot(
    settings: Settings,
    *,
    query: DashboardQuery,
) -> dict[str, Any]:
    scoped_df = load_workspace_dataframe(settings, query=query)
    dff = apply_filters(scoped_df, query.filters)
    source_ids = []
    if query.workspace.source_id:
        source_ids = [query.workspace.source_id]
    elif "source_id" in scoped_df.columns:
        source_ids = sorted(
            {sid for sid in scoped_df["source_id"].fillna("").astype(str).tolist() if sid}
        )
    dff = apply_dashboard_issue_scope(
        dff,
        settings=settings,
        country=query.workspace.country,
        source_ids=source_ids,
        quincenal_scope=query.quincenal_scope,
        issue_keys=query.issue_scope_keys,
        sort_col=query.issue_sort_col,
        like_query=query.issue_like_query,
    )
    open_df = open_only(dff)
    kpis = compute_kpis(dff, settings=settings, include_timeseries_chart=True)
    registry = build_trends_registry()
    requested_ids = (
        list(query.chart_ids)
        if query.chart_ids
        else [
            "timeseries",
            "age_buckets",
            "open_status_bar",
            "open_priority_pie",
            "resolution_hist",
        ]
    )
    ctx = ChartContext(dff=dff, open_df=open_df, kpis=kpis, dark_mode=query.dark_mode)
    charts: list[dict[str, Any]] = []
    for chart_id in requested_ids:
        spec = registry.get(chart_id)
        if spec is None:
            continue
        fig = spec.render(ctx)
        charts.append(
            {
                "id": chart_id,
                "title": spec.title,
                "subtitle": spec.subtitle,
                "group": spec.group,
                "figure": _fig_payload(fig),
                "insights": spec.insights(ctx),
            }
        )

    open_priority = kpis.get("open_now_by_priority") if isinstance(kpis, dict) else {}
    top_open_table = kpis.get("top_open_table") if isinstance(kpis, dict) else pd.DataFrame()
    if not isinstance(top_open_table, pd.DataFrame):
        top_open_table = pd.DataFrame(columns=["summary", "open_count"])

    return {
        "stats": {
            "issues_total": int(kpis.get("issues_total", len(dff))),
            "issues_open": int(kpis.get("issues_open", len(open_df))),
            "issues_closed": int(kpis.get("issues_closed", max(len(dff) - len(open_df), 0))),
            "mean_resolution_days": _fmt_days(kpis.get("mean_resolution_days", 0.0)),
        },
        "overviewKpis": build_overview_kpis_payload(dff=dff, open_df=open_df, kpis=kpis),
        "focusCards": build_overview_focus_cards(dff=dff, open_df=open_df, kpis=kpis),
        "statusPriorityMatrix": build_status_priority_matrix_payload(
            dff,
            active_filters=query.filters,
        ),
        "open_priority_breakdown": [
            {"priority": str(priority), "count": int(count)}
            for priority, count in dict(open_priority or {}).items()
        ],
        "top_open": top_open_table.fillna("").to_dict(orient="records"),
        "charts": charts,
        "row_count": int(len(dff)),
        "open_row_count": int(len(open_df)),
    }


def build_issue_rows(
    settings: Settings,
    *,
    query: DashboardQuery,
    offset: int = 0,
    limit: int = 100,
    sort_by: str = "updated",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    scoped_df = load_workspace_dataframe(settings, query=query)
    dff = apply_filters(scoped_df, query.filters)
    source_ids = [query.workspace.source_id] if query.workspace.source_id else []
    dff = apply_dashboard_issue_scope(
        dff,
        settings=settings,
        country=query.workspace.country,
        source_ids=source_ids,
        quincenal_scope=query.quincenal_scope,
        issue_keys=query.issue_scope_keys,
        sort_col=query.issue_sort_col,
        like_query=query.issue_like_query,
    )

    sort_column = (
        sort_by if sort_by in dff.columns else ("updated" if "updated" in dff.columns else "key")
    )
    ascending = str(sort_dir or "desc").strip().lower() == "asc"
    if sort_column in dff.columns:
        dff = dff.sort_values(sort_column, ascending=ascending, kind="mergesort")
    page = dff.iloc[max(offset, 0) : max(offset, 0) + max(limit, 1)].copy(deep=False)
    columns = [
        "key",
        "summary",
        "description",
        "status",
        "type",
        "priority",
        "assignee",
        "created",
        "updated",
        "resolved",
        "source_type",
        "source_alias",
        "source_id",
        "country",
        "url",
    ]
    for column in columns:
        if column not in page.columns:
            page[column] = ""
    for column in ("created", "updated", "resolved"):
        if column in page.columns:
            page[column] = page[column].astype(str).replace({"NaT": "", "nan": ""})
    for column in (
        "key",
        "summary",
        "description",
        "status",
        "type",
        "priority",
        "assignee",
        "source_type",
        "source_alias",
        "source_id",
        "country",
        "url",
    ):
        if column in page.columns:
            page[column] = page[column].fillna("").astype(str)
    return {
        "total": int(len(dff)),
        "rows": page.loc[:, columns].fillna("").to_dict(orient="records"),
    }


def build_kanban_columns(
    settings: Settings,
    *,
    query: DashboardQuery,
) -> list[dict[str, Any]]:
    scoped_df = load_workspace_dataframe(settings, query=query)
    dff = apply_filters(scoped_df, query.filters)
    source_ids = [query.workspace.source_id] if query.workspace.source_id else []
    dff = apply_dashboard_issue_scope(
        dff,
        settings=settings,
        country=query.workspace.country,
        source_ids=source_ids,
        quincenal_scope=query.quincenal_scope,
        issue_keys=query.issue_scope_keys,
        sort_col=query.issue_sort_col,
        like_query=query.issue_like_query,
    )
    open_df = open_only(dff)
    if open_df.empty or "status" not in open_df.columns:
        return []

    kan = open_df.copy(deep=False)
    kan["status"] = normalize_text_col(kan["status"], "(sin estado)")
    if "created" in kan.columns:
        created = pd.to_datetime(kan["created"], errors="coerce", utc=True).dt.tz_localize(None)
        now = pd.Timestamp.utcnow().tz_localize(None)
        kan["ageDays"] = ((now - created).dt.total_seconds() / 86400.0).clip(lower=0.0).fillna(0.0)
    else:
        kan["ageDays"] = 0.0
    status_counts = kan["status"].value_counts()
    if list(query.filters.status or []):
        selected_statuses = [
            status for status in query.filters.status if status in status_counts.index
        ]
        selected_statuses = order_statuses_canonical(selected_statuses)
    else:
        selected_statuses = order_statuses_canonical(status_counts.index.tolist()[:6])

    columns: list[dict[str, Any]] = []
    for status in selected_statuses[:8]:
        sub = kan.loc[kan["status"].eq(status)].copy(deep=False)
        if sub.empty:
            continue
        if "priority" in sub.columns:
            sub["__prio_rank"] = (
                sub["priority"].fillna("").astype(str).map(priority_rank).fillna(99)
            )
        else:
            sub["__prio_rank"] = 99
        sort_columns = ["__prio_rank"]
        ascending = [True]
        if "updated" in sub.columns:
            sort_columns.append("updated")
            ascending.append(False)
        sub = sub.sort_values(by=sort_columns, ascending=ascending, kind="mergesort")
        items = sub.head(220).copy(deep=False)
        for column in (
            "key",
            "summary",
            "status",
            "priority",
            "assignee",
            "updated",
            "source_alias",
            "source_type",
            "url",
        ):
            if column not in items.columns:
                items[column] = ""
        for column in ("updated",):
            if column in items.columns:
                items[column] = items[column].astype(str).replace({"NaT": "", "nan": ""})
        for column in (
            "key",
            "summary",
            "status",
            "priority",
            "assignee",
            "source_alias",
            "source_type",
            "url",
        ):
            if column in items.columns:
                items[column] = items[column].fillna("").astype(str)
        items["ageDays"] = (
            pd.to_numeric(items.get("ageDays", 0.0), errors="coerce").fillna(0.0).astype(float)
        )
        columns.append(
            {
                "status": status,
                "count": int(len(sub)),
                "items": items.loc[
                    :,
                    [
                        "key",
                        "summary",
                        "status",
                        "priority",
                        "assignee",
                        "updated",
                        "source_alias",
                        "source_type",
                        "url",
                        "ageDays",
                    ],
                ]
                .fillna("")
                .to_dict(orient="records"),
            }
        )
    return columns


def build_issue_keys(
    settings: Settings,
    *,
    query: DashboardQuery,
) -> dict[str, Any]:
    scoped_df = load_workspace_dataframe(settings, query=query)
    dff = apply_filters(scoped_df, query.filters)
    source_ids = [query.workspace.source_id] if query.workspace.source_id else []
    dff = apply_dashboard_issue_scope(
        dff,
        settings=settings,
        country=query.workspace.country,
        source_ids=source_ids,
        quincenal_scope=query.quincenal_scope,
        issue_keys=query.issue_scope_keys,
        sort_col=query.issue_sort_col,
        like_query=query.issue_like_query,
    )
    if dff.empty or "key" not in dff.columns:
        return {"total": 0, "keys": []}
    keys = sorted(
        {
            str(item).strip()
            for item in dff["key"].dropna().astype(str).tolist()
            if str(item).strip()
        }
    )
    return {"total": len(keys), "keys": keys}


def build_trend_detail(
    settings: Settings,
    *,
    query: DashboardQuery,
    chart_id: str,
) -> dict[str, Any]:
    scoped_df = load_workspace_dataframe(settings, query=query)
    dff = apply_filters(scoped_df, query.filters)
    source_ids = [query.workspace.source_id] if query.workspace.source_id else []
    dff = apply_dashboard_issue_scope(
        dff,
        settings=settings,
        country=query.workspace.country,
        source_ids=source_ids,
        quincenal_scope=query.quincenal_scope,
        issue_keys=query.issue_scope_keys,
        sort_col=query.issue_sort_col,
        like_query=query.issue_like_query,
    )
    open_df = open_only(dff)
    trend_open_df, adapted_for_terminal = _effective_trends_open_scope(
        dff=dff,
        open_df=open_df,
        active_status_filters=list(query.filters.status or []),
    )
    chart_context = ChartContext(
        dff=dff,
        open_df=trend_open_df,
        kpis=compute_kpis(dff, settings=settings, include_timeseries_chart=True),
        dark_mode=query.dark_mode,
    )
    registry = build_trends_registry()
    spec = registry.get(str(chart_id or "").strip())
    if spec is None:
        return {
            "chart": None,
            "metrics": [],
            "cards": [],
            "executiveTip": None,
            "adaptedForTerminal": adapted_for_terminal,
        }
    pack = build_trend_insight_pack(str(chart_id or "").strip(), dff=dff, open_df=trend_open_df)
    return {
        "chart": {
            "id": str(chart_id or "").strip(),
            "title": spec.title,
            "subtitle": spec.subtitle,
            "group": spec.group,
            "figure": _fig_payload(spec.render(chart_context)),
        },
        "metrics": [
            {"label": metric.label, "value": metric.value} for metric in list(pack.metrics or [])
        ],
        "cards": [
            {
                "title": card.title,
                "body": card.body,
                "score": float(card.score),
                "statusFilters": list(card.status_filters or []),
                "priorityFilters": list(card.priority_filters or []),
                "assigneeFilters": list(card.assignee_filters or []),
            }
            for card in list(pack.cards or [])
        ],
        "executiveTip": pack.executive_tip,
        "adaptedForTerminal": adapted_for_terminal,
    }


def _scope_reference_day(df: pd.DataFrame) -> pd.Timestamp | None:
    safe = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if safe.empty:
        return None
    max_candidates: list[pd.Timestamp] = []
    for column in ("updated", "resolved", "created"):
        if column not in safe.columns:
            continue
        ts = pd.to_datetime(safe[column], errors="coerce", utc=True)
        if not ts.notna().any():
            continue
        max_ts = ts.max()
        if pd.notna(max_ts):
            picked = pd.Timestamp(max_ts)
            try:
                picked = picked.tz_convert(None)
            except Exception:
                try:
                    picked = picked.tz_localize(None)
                except Exception:
                    pass
            max_candidates.append(picked)
    if not max_candidates:
        return None
    return max(max_candidates).normalize()


def _insights_quincenal_df(*, settings: Settings, dff: pd.DataFrame) -> pd.DataFrame:
    safe = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    if safe.empty:
        return safe
    options = quincenal_scope_options(
        safe,
        settings=settings,
        reference_day=_scope_reference_day(safe),
    )
    selected_keys: list[str] = []
    for label in (QUINCENAL_SCOPE_CREATED_CURRENT, QUINCENAL_SCOPE_CLOSED_CURRENT):
        selected_keys.extend(options.get(label, []))
    scoped = apply_issue_key_scope(safe, keys=selected_keys)
    if scoped.empty:
        return pd.DataFrame(columns=list(safe.columns))
    return scoped


def _issue_keys(df: pd.DataFrame | None) -> list[str]:
    safe = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if safe.empty or "key" not in safe.columns:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in safe["key"].fillna("").astype(str).tolist():
        key = str(raw).strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _pct(numerator: int, denominator: int) -> float:
    return (float(numerator) / float(denominator) * 100.0) if denominator else 0.0


def _risk_label(score_0_100: float) -> str:
    if score_0_100 >= 70.0:
        return "Alto"
    if score_0_100 >= 40.0:
        return "Medio"
    return "Bajo"


def _status_bucket(status: str) -> str:
    token = str(status or "").strip().lower()
    if "block" in token or "bloque" in token:
        return "bloqueado"
    if token in {"new", "nuevo"} or "analys" in token or "analis" in token or "accept" in token:
        return "entrada"
    if "progress" in token or "progreso" in token or "rework" in token or "wip" in token:
        return "en_curso"
    if (
        "verify" in token
        or "verif" in token
        or "deploy" in token
        or token == "test"
        or "qa" in token
        or "done" in token
        or "closed" in token
        or "resolved" in token
    ):
        return "salida"
    return "otro"


def _priority_weight(priority: str) -> float:
    token = str(priority or "").strip().lower()
    if "highest" in token or token == "p0":
        return 3.0
    if "high" in token or token == "p1":
        return 2.2
    if "medium" in token or token == "p2":
        return 1.4
    if "low" in token or token == "p3":
        return 1.0
    if "lowest" in token:
        return 0.8
    if "imped" in token:
        return 2.6
    return 1.1


def _issue_records_from_df(
    df: pd.DataFrame,
    *,
    limit: int = 20,
    age_days_col: str | None = None,
    sort_by_col: str | None = None,
    sort_desc: bool = False,
) -> list[dict[str, Any]]:
    safe = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if safe.empty:
        return []

    work = safe.copy(deep=False)
    if sort_by_col and sort_by_col in work.columns:
        try:
            work = work.sort_values(
                by=sort_by_col,
                ascending=not sort_desc,
                kind="mergesort",
                na_position="last",
                key=lambda col: pd.to_numeric(col, errors="coerce"),
            )
        except Exception:
            work = work.sort_values(
                by=sort_by_col,
                ascending=not sort_desc,
                kind="mergesort",
                na_position="last",
            )
    elif "updated" in work.columns:
        work = work.sort_values("updated", ascending=False, kind="mergesort", na_position="last")

    page = work.head(max(int(limit), 1)).copy(deep=False)
    for column in (
        "key",
        "summary",
        "description",
        "status",
        "priority",
        "assignee",
        "created",
        "updated",
        "resolved",
        "url",
        "source_alias",
        "source_type",
    ):
        if column not in page.columns:
            page[column] = ""

    if age_days_col and age_days_col in page.columns:
        page["ageDays"] = pd.to_numeric(page[age_days_col], errors="coerce").fillna(0.0)
    elif "created" in page.columns:
        created = pd.to_datetime(page["created"], errors="coerce", utc=True).dt.tz_localize(None)
        now = pd.Timestamp.utcnow().tz_localize(None)
        page["ageDays"] = ((now - created).dt.total_seconds() / 86400.0).clip(lower=0.0).fillna(0.0)
    else:
        page["ageDays"] = 0.0

    for column in ("created", "updated", "resolved"):
        if column not in page.columns:
            continue
        as_text = page[column].astype(str).replace({"NaT": "", "nan": ""})
        page[column] = as_text
    for column in (
        "key",
        "summary",
        "description",
        "status",
        "priority",
        "assignee",
        "url",
        "source_alias",
        "source_type",
    ):
        if column not in page.columns:
            continue
        page[column] = page[column].fillna("").astype(str)
    page["ageDays"] = pd.to_numeric(page["ageDays"], errors="coerce").fillna(0.0).astype(float)

    return cast(
        list[dict[str, Any]],
        page.loc[
            :,
            [
                "key",
                "summary",
                "description",
                "status",
                "priority",
                "assignee",
                "created",
                "updated",
                "resolved",
                "url",
                "source_alias",
                "source_type",
                "ageDays",
            ],
        ]
        .fillna("")
        .to_dict(orient="records"),
    )


def _build_theme_trend_figure(
    trend_df: pd.DataFrame,
    *,
    theme_order: Sequence[str],
    use_accumulated_scope: bool,
    dark_mode: bool,
) -> dict[str, Any] | None:
    safe = trend_df if isinstance(trend_df, pd.DataFrame) else pd.DataFrame()
    if safe.empty:
        return None

    x_col = "quincena_label" if use_accumulated_scope else "date_label"
    x_title = "Quincena" if use_accumulated_scope else "Día"
    y_title = "Incidencias abiertas acumuladas" if use_accumulated_scope else "Incidencias abiertas"
    axis_labels = safe[x_col].dropna().astype(str).drop_duplicates().tolist()
    if not axis_labels:
        return None

    present_themes = {
        str(theme).strip()
        for theme in safe.get("tema", pd.Series([], dtype=str)).astype(str).tolist()
        if str(theme).strip()
    }
    ordered_themes = [
        str(theme).strip()
        for theme in list(theme_order or [])
        if str(theme).strip() in present_themes
    ]
    theme_totals = (
        safe.groupby("tema", dropna=False)["issues_value"].sum().sort_values(ascending=False)
    )
    if not ordered_themes:
        ordered_themes = order_theme_labels_by_volume(
            theme_totals.index.tolist(),
            counts_by_label=theme_totals,
            others_last=True,
        )
    ordering = build_theme_render_order(
        ordered_themes,
        counts_by_label=theme_totals,
        others_last=True,
        others_at_x_axis=True,
    )
    legend_order = list(ordering.display_order)
    stacked_order = list(ordering.stack_order_bottom_to_top)
    if not legend_order or not stacked_order:
        return None

    legend_rank = {theme: idx for idx, theme in enumerate(legend_order)}
    theme_color_map = build_theme_color_map(theme_order=legend_order, dark_mode=dark_mode)
    fig = go.Figure()
    totals = (
        safe.groupby(x_col, dropna=False)["issues_value"]
        .sum()
        .reindex(axis_labels)
        .fillna(0)
        .astype(int)
    )
    for theme in stacked_order:
        sub = safe.loc[safe["tema"].eq(theme)].copy(deep=False)
        if sub.empty:
            continue
        values = (
            pd.to_numeric(sub["issues_value"], errors="coerce").fillna(0.0).astype(float).tolist()
        )
        labels = sub[x_col].astype(str).tolist()
        total_custom = [[int(totals.get(label, 0))] for label in labels]
        color_hex = str(theme_color_map.get(theme) or BBVA_LIGHT.serene_blue)
        fig.add_trace(
            go.Bar(
                x=labels,
                y=values,
                name=str(theme),
                marker=dict(color=color_hex),
                text=[str(int(value)) if float(value) > 0 else "" for value in values],
                textposition="inside",
                textfont=dict(color=segment_text_color(color_hex, dark_mode=dark_mode), size=11),
                customdata=total_custom,
                legendrank=int(legend_rank.get(theme, len(legend_rank))),
                hovertemplate=(
                    "Tema: %{fullData.name}<br>"
                    f"{x_title}: %{{x}}<br>"
                    f"{y_title}: %{{y}}<br>"
                    "Total columna: %{customdata[0]}<extra></extra>"
                ),
            )
        )

    fig.add_trace(
        go.Scatter(
            x=axis_labels,
            y=[float(value) + max(float(totals.max()), 1.0) * 0.055 for value in totals.tolist()],
            mode="text",
            text=[str(int(value)) for value in totals.tolist()],
            textposition="top center",
            showlegend=False,
            hoverinfo="skip",
            textfont=dict(size=12, color=BBVA_LIGHT.white if dark_mode else BBVA_LIGHT.midnight),
        )
    )
    fig.update_layout(
        height=380,
        margin=dict(l=16, r=16, t=18, b=170),
        xaxis_title=x_title,
        yaxis_title=y_title,
        hovermode="x",
        xaxis_title_standoff=18,
        barmode="stack",
        bargap=0.20,
        uniformtext=dict(minsize=10, mode="hide"),
    )
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=axis_labels)
    max_total = float(totals.max()) if not totals.empty else 0.0
    total_offset = max(max_total * 0.055, 0.16)
    fig.update_yaxes(range=[0, max_total + (total_offset * 2.3) if max_total > 0 else 1.0])
    fig = apply_plotly_bbva(fig, showlegend=True, dark_mode=dark_mode)
    for trace in list(getattr(fig, "data", []) or []):
        try:
            if str(getattr(trace, "type", "")).strip().lower() != "bar":
                continue
            trace_name = str(getattr(trace, "name", "") or "").strip()
            fill = str(theme_color_map.get(trace_name) or "")
            if not fill:
                continue
            trace.textfont = dict(color=segment_text_color(fill, dark_mode=dark_mode), size=11)
        except Exception:
            continue
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.54,
            xanchor="center",
            x=0.5,
            traceorder="normal",
            title=dict(text=""),
        ),
        margin=dict(l=16, r=16, t=18, b=170),
    )
    return _fig_payload(fig)


def _active_source_ids(scoped_df: pd.DataFrame, *, query: DashboardQuery) -> list[str]:
    if query.workspace.source_id:
        return [str(query.workspace.source_id)]
    if (
        not isinstance(scoped_df, pd.DataFrame)
        or scoped_df.empty
        or "source_id" not in scoped_df.columns
    ):
        return []
    return sorted(
        {
            str(source_id).strip()
            for source_id in scoped_df["source_id"].fillna("").astype(str).tolist()
            if str(source_id).strip()
        }
    )


def _dominant_value(df: pd.DataFrame, column: str, fallback: str) -> str:
    safe = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    if safe.empty or column not in safe.columns:
        return fallback
    series = normalize_text_col(safe[column], fallback)
    counts = series.value_counts()
    if counts.empty:
        return fallback
    return str(counts.index[0])


def _build_period_summary_payload(
    settings: Settings,
    *,
    dff: pd.DataFrame,
    query: DashboardQuery,
    source_ids: Sequence[str],
) -> dict[str, Any]:
    safe = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    if safe.empty:
        return {
            "caption": "",
            "cards": [],
            "groups": [],
            "showOpenSplit": False,
            "sourceBreakdown": [],
        }

    labels = source_label_map(
        settings,
        country=str(query.workspace.country or "").strip(),
        source_ids=source_ids,
    )
    result = build_country_quincenal_result(
        df=safe,
        settings=settings,
        country=str(query.workspace.country or "").strip(),
        source_ids=source_ids,
        source_label_by_id=labels,
    )
    summary = result.aggregate.summary
    groups = result.aggregate.groups
    open_total_group = pd.concat(
        [groups.open_focus, groups.open_other], axis=0, ignore_index=True
    ).copy(deep=False)
    show_open_split = should_show_open_split(
        maestras_total=int(summary.open_focus_total),
        others_total=int(summary.open_other_total),
        open_total=int(summary.open_total),
    )

    cards = [
        {
            "cardId": "new_now",
            "kicker": "Insights · Creadas",
            "metric": f"{int(summary.new_now):,}",
            "detail": (
                f"Δ {float(summary.new_delta_pct or 0.0) * 100.0:+.1f}% vs quincena previa"
                if summary.new_delta_pct is not None
                else "Sin referencia en quincena previa"
            ),
            "label": QUINCENAL_SCOPE_CREATED_CURRENT,
            "quincenalScopeLabel": QUINCENAL_SCOPE_CREATED_CURRENT,
            "issueKeys": _issue_keys(groups.new_now),
        },
        {
            "cardId": "closed_now",
            "kicker": "Insights · Cerradas",
            "metric": f"{int(summary.closed_now):,}",
            "detail": (
                f"Δ {float(summary.closed_delta_pct or 0.0) * 100.0:+.1f}% vs quincena previa"
                if summary.closed_delta_pct is not None
                else "Sin referencia en quincena previa"
            ),
            "label": QUINCENAL_SCOPE_CLOSED_CURRENT,
            "quincenalScopeLabel": QUINCENAL_SCOPE_CLOSED_CURRENT,
            "issueKeys": _issue_keys(groups.closed_now),
        },
        {
            "cardId": "resolution_now",
            "kicker": "Insights · Resolución",
            "metric": _fmt_days(summary.resolution_days_now),
            "detail": (
                f"Δ {float(summary.resolution_delta_pct or 0.0) * 100.0:+.1f}% vs quincena previa"
                if summary.resolution_delta_pct is not None
                else "Sin referencia en quincena previa"
            ),
            "label": QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
            "quincenalScopeLabel": QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
            "issueKeys": _issue_keys(groups.resolved_now),
        },
        {
            "cardId": "open_total",
            "kicker": "Insights · Abiertas totales",
            "metric": f"{int(summary.open_total):,}",
            "detail": "Backlog abierto en el scope actual",
            "label": QUINCENAL_SCOPE_OPEN_TOTAL,
            "quincenalScopeLabel": QUINCENAL_SCOPE_OPEN_TOTAL,
            "issueKeys": _issue_keys(open_total_group),
        },
    ]
    if show_open_split:
        cards.extend(
            [
                {
                    "cardId": "open_focus",
                    "kicker": str(summary.open_focus_card_kicker),
                    "metric": f"{int(summary.open_focus_total):,}",
                    "detail": str(summary.open_focus_card_detail),
                    "label": str(summary.open_focus_label),
                    "quincenalScopeLabel": str(summary.open_focus_label),
                    "issueKeys": _issue_keys(groups.open_focus),
                },
                {
                    "cardId": "open_other",
                    "kicker": str(summary.open_other_card_kicker),
                    "metric": f"{int(summary.open_other_total):,}",
                    "detail": str(summary.open_other_card_detail),
                    "label": str(summary.open_other_label),
                    "quincenalScopeLabel": str(summary.open_other_label),
                    "issueKeys": _issue_keys(groups.open_other),
                },
            ]
        )

    groups_payload: list[dict[str, Any]] = []
    if show_open_split:
        groups_payload.extend(
            [
                {
                    "label": str(summary.open_focus_label),
                    "count": int(summary.open_focus_total),
                    "helpText": "",
                    "quincenalScopeLabel": str(summary.open_focus_label),
                    "issueKeys": _issue_keys(groups.open_focus),
                    "items": _issue_records_from_df(groups.open_focus, limit=20),
                },
                {
                    "label": str(summary.open_other_label),
                    "count": int(summary.open_other_total),
                    "helpText": "",
                    "quincenalScopeLabel": str(summary.open_other_label),
                    "issueKeys": _issue_keys(groups.open_other),
                    "items": _issue_records_from_df(groups.open_other, limit=20),
                },
            ]
        )
    groups_payload.extend(
        [
            {
                "label": "Creadas en la quincena previa",
                "count": int(summary.new_before),
                "helpText": "quincena previa",
                "quincenalScopeLabel": QUINCENAL_SCOPE_CREATED_PREVIOUS,
                "issueKeys": _issue_keys(groups.new_before),
                "items": _issue_records_from_df(groups.new_before, limit=20),
            },
            {
                "label": "Creadas en la quincena actual",
                "count": int(summary.new_now),
                "helpText": "quincena actual",
                "quincenalScopeLabel": QUINCENAL_SCOPE_CREATED_CURRENT,
                "issueKeys": _issue_keys(groups.new_now),
                "items": _issue_records_from_df(groups.new_now, limit=20),
            },
            {
                "label": "Creadas en el mes actual",
                "count": int(summary.new_accumulated),
                "helpText": "mes actual",
                "quincenalScopeLabel": QUINCENAL_SCOPE_CREATED_MONTH,
                "issueKeys": _issue_keys(groups.new_accumulated),
                "items": _issue_records_from_df(groups.new_accumulated, limit=20),
            },
            {
                "label": "Cerradas en la quincena",
                "count": int(summary.closed_now),
                "helpText": "quincena actual",
                "quincenalScopeLabel": QUINCENAL_SCOPE_CLOSED_CURRENT,
                "issueKeys": _issue_keys(groups.closed_now),
                "items": _issue_records_from_df(groups.closed_now, limit=20),
            },
            {
                "label": "Días de resolución incidencias cerradas en la quincena actual",
                "count": int(len(groups.resolved_now)),
                "helpText": "cerradas quincena actual",
                "quincenalScopeLabel": QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
                "issueKeys": _issue_keys(groups.resolved_now),
                "items": _issue_records_from_df(
                    groups.resolved_now,
                    limit=20,
                    age_days_col="resolution_days",
                    sort_by_col="resolution_days",
                    sort_desc=True,
                ),
            },
        ]
    )

    source_breakdown: list[dict[str, Any]] = []
    if query.workspace.scope_mode == "country" and result.by_source:
        focus_col_label = str(summary.open_focus_label or "foco abierto")
        other_col_label = str(summary.open_other_label or "otras incidencias")
        for source_id in result.source_ids:
            source_scope = result.by_source.get(source_id)
            if source_scope is None:
                continue
            source_summary = source_scope.summary
            source_breakdown.append(
                {
                    "source": labels.get(source_id, source_id),
                    "abiertas": int(source_summary.open_total),
                    "focus": {
                        "label": focus_col_label,
                        "value": int(source_summary.open_focus_total),
                    },
                    "other": {
                        "label": other_col_label,
                        "value": int(source_summary.open_other_total),
                    },
                    "nuevasAhora": int(source_summary.new_now),
                    "cerradasAhora": int(source_summary.closed_now),
                    "resolucionAhora": _fmt_days(source_summary.resolution_days_now),
                }
            )

    return {
        "caption": f"{summary.scope_label or query.workspace.country} · {format_window_label(summary.window)}",
        "cards": cards,
        "groups": groups_payload,
        "showOpenSplit": bool(show_open_split),
        "sourceBreakdown": source_breakdown,
    }


def _build_functionality_payload(
    *,
    dff: pd.DataFrame,
    dff_quincenal: pd.DataFrame,
    view_mode: str,
    status_filters: Sequence[str] | None,
    priority_filters: Sequence[str] | None,
    functionality_filters: Sequence[str] | None,
    apply_default_status_when_empty: bool,
    dark_mode: bool,
) -> dict[str, Any]:
    combo_ctx = build_insights_combo_context(
        accumulated_df=dff,
        quincenal_df=dff_quincenal,
        view_mode=view_mode,
        selected_statuses=list(status_filters or []),
        selected_priorities=list(priority_filters or []),
        selected_functionalities=list(functionality_filters or []),
        apply_default_status_when_empty=apply_default_status_when_empty,
    )
    filtered_df = combo_ctx.filtered_df
    history_ctx = build_insights_combo_context(
        accumulated_df=dff,
        quincenal_df=dff_quincenal,
        view_mode=INSIGHTS_VIEW_MODE_ACCUMULATED,
        selected_statuses=list(combo_ctx.selected_statuses),
        selected_priorities=list(combo_ctx.selected_priorities),
        selected_functionalities=list(combo_ctx.selected_functionalities),
        apply_default_status_when_empty=False,
    )
    use_accumulated_scope = combo_ctx.view_mode == INSIGHTS_VIEW_MODE_ACCUMULATED

    theme_payload = prepare_open_theme_payload(open_only(filtered_df), top_n=10)
    tmp_open = theme_payload.get("tmp_open")
    if not isinstance(tmp_open, pd.DataFrame):
        tmp_open = pd.DataFrame()
    else:
        tmp_open = tmp_open.copy(deep=False)
    if not tmp_open.empty:
        if "status" in tmp_open.columns:
            tmp_open["status"] = normalize_text_col(tmp_open["status"], "(sin estado)")
        else:
            tmp_open["status"] = "(sin estado)"
        if "priority" in tmp_open.columns:
            tmp_open["priority"] = normalize_text_col(tmp_open["priority"], "(sin priority)")
        else:
            tmp_open["priority"] = "(sin priority)"
        if "assignee" in tmp_open.columns:
            tmp_open["assignee"] = normalize_text_col(tmp_open["assignee"], "(sin asignar)")
        else:
            tmp_open["assignee"] = "(sin asignar)"
        if "summary" in tmp_open.columns:
            tmp_open["summary"] = tmp_open["summary"].fillna("").astype(str)
        if "created" in tmp_open.columns:
            created = pd.to_datetime(tmp_open["created"], errors="coerce", utc=True).dt.tz_localize(
                None
            )
            now = pd.Timestamp.utcnow().tz_localize(None)
            tmp_open["__age_days"] = ((now - created).dt.total_seconds() / 86400.0).clip(lower=0.0)
        else:
            tmp_open["__age_days"] = pd.NA

    top_tbl = theme_payload.get("top_tbl")
    if not isinstance(top_tbl, pd.DataFrame):
        top_tbl = pd.DataFrame(columns=["tema", "open_count", "pct_open"])
    else:
        top_tbl = top_tbl.copy(deep=False)

    selected_themes = [
        str(topic).strip()
        for topic in top_tbl.get("tema", pd.Series([], dtype=str)).tolist()
        if str(topic).strip()
    ]
    theme_color_map = build_theme_color_map(theme_order=selected_themes, dark_mode=dark_mode)
    history_filtered = (
        history_ctx.filtered_df
        if isinstance(history_ctx.filtered_df, pd.DataFrame)
        else pd.DataFrame()
    )
    topic_summaries = build_topic_expandable_summaries(
        history_df=history_filtered,
        open_df=tmp_open,
        theme_col="__theme",
        top_root_causes=3,
        flow_window_days=30,
    )
    trend_df = pd.DataFrame()
    if use_accumulated_scope:
        history_open = open_only(history_filtered)
        if not history_open.empty and selected_themes:
            trend_df = build_theme_fortnight_trend(
                history_open,
                theme_whitelist=selected_themes,
                cumulative=True,
            )
    else:
        open_theme_df = open_only(filtered_df)
        if not open_theme_df.empty and selected_themes:
            trend_df = build_theme_daily_trend(
                open_theme_df,
                theme_whitelist=selected_themes,
            )
    chart_payload = _build_theme_trend_figure(
        trend_df,
        theme_order=selected_themes,
        use_accumulated_scope=use_accumulated_scope,
        dark_mode=dark_mode,
    )

    total_open = int(len(tmp_open))
    topics: list[dict[str, Any]] = []
    for _, row in top_tbl.iterrows():
        topic = str(row.get("tema", "") or "").strip()
        if not topic:
            continue
        sub = (
            tmp_open.loc[tmp_open["__theme"].eq(topic)].copy(deep=False)
            if "__theme" in tmp_open.columns
            else pd.DataFrame()
        )
        if not sub.empty:
            sub["__prio_rank"] = (
                sub["priority"].astype(str).map(priority_rank).fillna(99).astype(int)
                if "priority" in sub.columns
                else 99
            )
            sub = sub.sort_values(
                by=["__prio_rank", "__age_days", "updated" if "updated" in sub.columns else "key"],
                ascending=[True, False, False],
                kind="mergesort",
                na_position="last",
            )
        topic_summary = topic_summaries.get(topic)
        flow = getattr(topic_summary, "flow", None)
        root_causes = tuple(getattr(topic_summary, "root_causes", ()) or ())
        topics.append(
            {
                "topic": topic,
                "color": str(theme_color_map.get(topic) or BBVA_LIGHT.serene_blue),
                "count": int(row.get("open_count", 0) or 0),
                "pct": float(row.get("pct_open", 0.0) or 0.0),
                "dominantStatus": _dominant_value(sub, "status", "(sin estado)"),
                "dominantPriority": _dominant_value(sub, "priority", "(sin priority)"),
                "brief": build_topic_brief(topic=topic, sub_df=sub, total_open=total_open),
                "flow": (
                    {
                        "createdCount": int(getattr(flow, "created_count", 0) or 0),
                        "resolvedCount": int(getattr(flow, "resolved_count", 0) or 0),
                        "pctDelta": float(getattr(flow, "pct_delta", 0.0) or 0.0),
                        "direction": str(getattr(flow, "direction", "stable") or "stable"),
                        "windowDays": int(getattr(flow, "window_days", 0) or 0),
                    }
                    if flow is not None
                    else None
                ),
                "rootCauses": [
                    {
                        "label": str(getattr(root, "label", "") or ""),
                        "count": int(getattr(root, "count", 0) or 0),
                    }
                    for root in root_causes
                    if str(getattr(root, "label", "") or "").strip()
                ],
                "issues": _issue_records_from_df(sub, limit=20, age_days_col="__age_days"),
            }
        )

    return {
        "combo": {
            "viewMode": combo_ctx.view_mode,
            "viewModeOptions": [
                {"value": mode, "label": INSIGHTS_VIEW_MODE_LABELS.get(mode, mode)}
                for mode in INSIGHTS_VIEW_MODE_OPTIONS
            ],
            "statusOptions": list(combo_ctx.status_options),
            "priorityOptions": list(combo_ctx.priority_options),
            "functionalityOptions": list(combo_ctx.functionality_options),
            "selectedStatuses": list(combo_ctx.selected_statuses),
            "selectedPriorities": list(combo_ctx.selected_priorities),
            "selectedFunctionalities": list(combo_ctx.selected_functionalities),
        },
        "chart": {
            "title": "Tendencia por funcionalidad",
            "subtitle": (
                "Vista quincenal acumulada"
                if use_accumulated_scope
                else "Vista diaria de la quincena analizada"
            ),
            "figure": chart_payload,
        }
        if chart_payload is not None
        else None,
        "topics": topics,
        "tip": "El % indica el peso real de cada tema dentro del backlog abierto filtrado.",
    }


def _build_duplicates_payload(dff_quincenal: pd.DataFrame) -> dict[str, Any]:
    df2 = open_only(dff_quincenal).copy(deep=False)
    if df2.empty:
        return {
            "brief": "No hay incidencias abiertas con los filtros actuales.",
            "titleGroups": [],
            "heuristicGroups": [],
        }
    if "status" in df2.columns:
        df2["status"] = normalize_text_col(df2["status"], "(sin estado)")
    if "priority" in df2.columns:
        df2["priority"] = normalize_text_col(df2["priority"], "(sin priority)")
    if "summary" in df2.columns:
        df2["summary"] = df2["summary"].fillna("").astype(str)

    payload = prepare_duplicates_payload(df2)
    duplicate_stats = payload.get("duplicate_stats")
    duplicate_groups = int(getattr(duplicate_stats, "groups", 0) or 0)
    duplicate_issues = int(getattr(duplicate_stats, "issues", 0) or 0)
    clusters = payload.get("clusters")
    if not isinstance(clusters, list):
        clusters = []
    title_groups_payload: list[dict[str, Any]] = []
    for summary, keys in list(payload.get("top_titles") or []):
        key_list = [str(key).strip() for key in list(keys or []) if str(key).strip()]
        if not key_list:
            continue
        sub = apply_issue_key_scope(df2, keys=key_list)
        title_groups_payload.append(
            {
                "summary": str(summary or "").strip(),
                "count": len(key_list),
                "issues": _issue_records_from_df(sub, limit=20),
            }
        )
    heuristic_groups_payload: list[dict[str, Any]] = []
    for cluster in clusters[:12]:
        key_list = [
            str(key).strip() for key in list(getattr(cluster, "keys", []) or []) if str(key).strip()
        ]
        if not key_list:
            continue
        sub = apply_issue_key_scope(df2, keys=key_list)
        heuristic_groups_payload.append(
            {
                "summary": str(getattr(cluster, "summary", "") or "").strip(),
                "count": int(getattr(cluster, "size", len(key_list)) or len(key_list)),
                "dominantStatus": _dominant_value(sub, "status", "(sin estado)"),
                "dominantPriority": _dominant_value(sub, "priority", "(sin priority)"),
                "issues": _issue_records_from_df(sub, limit=20),
            }
        )
    return {
        "brief": build_duplicates_brief(
            total_open=int(len(df2)),
            duplicate_groups=duplicate_groups,
            duplicate_issues=duplicate_issues,
            heuristic_clusters=int(len(clusters)),
        ),
        "titleGroups": title_groups_payload,
        "heuristicGroups": heuristic_groups_payload,
    }


def _build_people_payload(dff_quincenal: pd.DataFrame) -> dict[str, Any]:
    open_df = open_only(dff_quincenal)
    if open_df.empty or "assignee" not in open_df.columns:
        return {"cards": []}

    df2 = open_df.copy(deep=False)
    df2["assignee"] = normalize_text_col(df2["assignee"], "(sin asignar)")
    df2["status"] = (
        normalize_text_col(df2["status"], "(sin estado)")
        if "status" in df2.columns
        else "(sin estado)"
    )
    df2["priority"] = (
        normalize_text_col(df2["priority"], "(sin priority)")
        if "priority" in df2.columns
        else "(sin priority)"
    )
    has_created = "created" in df2.columns
    if has_created:
        created = pd.to_datetime(df2["created"], errors="coerce", utc=True).dt.tz_localize(None)
        now = pd.Timestamp.utcnow().tz_localize(None)
        df2["age_days"] = ((now - created).dt.total_seconds() / 86400.0).clip(lower=0.0)
    else:
        df2["age_days"] = pd.NA

    total_open = int(len(df2))
    counts = df2.groupby("assignee").size().sort_values(ascending=False).head(12)
    cards: list[dict[str, Any]] = []
    for assignee, count in counts.items():
        sub = df2.loc[df2["assignee"].eq(str(assignee))].copy(deep=False)
        sub["__bucket"] = sub["status"].astype(str).map(_status_bucket)
        bcounts = sub["__bucket"].value_counts()
        b_entrada = int(bcounts.get("entrada", 0))
        b_curso = int(bcounts.get("en_curso", 0))
        b_salida = int(bcounts.get("salida", 0))
        b_bloq = int(bcounts.get("bloqueado", 0))
        flow_risk_pct = _pct(b_entrada + b_bloq, int(count))
        sub["__w"] = sub["priority"].astype(str).map(_priority_weight)
        w_total = float(sub["__w"].sum()) if int(count) else 0.0
        w_bad = (
            float(sub.loc[sub["__bucket"].isin(["entrada", "bloqueado"]), "__w"].sum())
            if int(count)
            else 0.0
        )
        crit_risk_pct = (w_bad / w_total * 100.0) if w_total > 0 else 0.0
        risk_score = 0.6 * flow_risk_pct + 0.4 * crit_risk_pct
        aging_p90_days = (
            float(sub["age_days"].quantile(0.90)) if sub["age_days"].notna().any() else None
        )
        recommendations = build_people_plan_recommendations(
            assignee=str(assignee),
            open_count=int(count),
            flow_risk_pct=float(flow_risk_pct),
            critical_risk_pct=float(crit_risk_pct),
            blocked_count=b_bloq,
            in_progress_count=b_curso,
            exit_count=b_salida,
            aging_p90_days=aging_p90_days,
        )
        oldest = (
            sub.dropna(subset=["age_days"])
            .sort_values("age_days", ascending=False, kind="mergesort")
            .head(3)
            if sub["age_days"].notna().any()
            else pd.DataFrame(columns=list(sub.columns))
        )
        cards.append(
            {
                "assignee": str(assignee),
                "openCount": int(count),
                "sharePct": _pct(int(count), total_open),
                "statusBreakdown": [
                    {"status": str(status), "count": int(value)}
                    for status, value in sub["status"].value_counts().items()
                ],
                "risk": {
                    "label": _risk_label(risk_score),
                    "flowRiskPct": float(flow_risk_pct),
                    "criticalRiskPct": float(crit_risk_pct),
                },
                "pushPct": _pct(b_salida, int(count)),
                "blockedCount": b_bloq,
                "aging": {
                    "value": (
                        f"{float(aging_p90_days):.0f}d" if aging_p90_days is not None else "—"
                    ),
                    "caption": "Casos más lentos"
                    if aging_p90_days is not None
                    else "Sin fecha de creación",
                },
                "recommendations": list(recommendations[:4]),
                "oldestIssues": _issue_records_from_df(oldest, limit=3, age_days_col="age_days"),
            }
        )
    return {"cards": cards}


def _build_ops_health_payload(dff_quincenal: pd.DataFrame) -> dict[str, Any]:
    dff = dff_quincenal if isinstance(dff_quincenal, pd.DataFrame) else pd.DataFrame()
    open_df = open_only(dff)
    dominant_priority = _dominant_value(open_df, "priority", "-")
    dominant_priority_count = 0
    if not open_df.empty and "priority" in open_df.columns:
        priorities = normalize_text_col(open_df["priority"], "(sin priority)")
        counts = priorities.value_counts()
        if not counts.empty:
            dominant_priority_count = int(counts.iloc[0])

    oldest = pd.DataFrame()
    if not open_df.empty and "created" in open_df.columns:
        tmp = open_df.copy(deep=False)
        created = pd.to_datetime(tmp["created"], errors="coerce", utc=True).dt.tz_localize(None)
        now = pd.Timestamp.utcnow().tz_localize(None)
        tmp["age_days"] = ((now - created).dt.total_seconds() / 86400.0).clip(lower=0.0)
        oldest = tmp.dropna(subset=["age_days"]).sort_values(
            "age_days",
            ascending=False,
            kind="mergesort",
        )

    return {
        "kpis": [
            {"label": "Issues (filtradas)", "value": f"{int(len(dff)):,}", "detail": ""},
            {"label": "Abiertas (filtradas)", "value": f"{int(len(open_df)):,}", "detail": ""},
            {
                "label": "Prioridad dominante",
                "value": f"{dominant_priority_count:,}",
                "detail": dominant_priority,
            },
        ],
        "brief": list(build_ops_health_brief(dff=dff, open_df=open_df)),
        "oldestIssues": _issue_records_from_df(oldest, limit=10, age_days_col="age_days"),
    }


def build_intelligence_snapshot(
    settings: Settings,
    *,
    query: DashboardQuery,
    insights_view_mode: str = "quincenal",
    insights_status_filters: Sequence[str] | None = None,
    insights_priority_filters: Sequence[str] | None = None,
    insights_functionality_filters: Sequence[str] | None = None,
    insights_status_manual: bool = False,
) -> dict[str, Any]:
    scoped_df = load_workspace_dataframe(settings, query=query)
    dff = apply_filters(scoped_df, query.filters)
    source_ids = _active_source_ids(scoped_df, query=query)
    dff = apply_dashboard_issue_scope(
        dff,
        settings=settings,
        country=query.workspace.country,
        source_ids=source_ids,
        quincenal_scope=query.quincenal_scope,
        issue_keys=query.issue_scope_keys,
        sort_col=query.issue_sort_col,
        like_query=query.issue_like_query,
    )
    dff_quincenal = _insights_quincenal_df(settings=settings, dff=dff)
    functionality = _build_functionality_payload(
        dff=dff,
        dff_quincenal=dff_quincenal,
        view_mode=insights_view_mode,
        status_filters=insights_status_filters,
        priority_filters=insights_priority_filters,
        functionality_filters=insights_functionality_filters,
        apply_default_status_when_empty=not bool(insights_status_manual),
        dark_mode=bool(query.dark_mode),
    )
    duplicates = _build_duplicates_payload(dff_quincenal)
    people = _build_people_payload(dff_quincenal)
    ops_health = _build_ops_health_payload(dff_quincenal)
    return {
        "tabs": [
            {"id": "summary", "label": "Resumen quincenal"},
            {"id": "functionality", "label": "Por funcionalidad"},
            {"id": "duplicates", "label": "Duplicados"},
            {"id": "people", "label": "Personas"},
            {"id": "opsHealth", "label": "Salud operativa"},
        ],
        "periodSummary": _build_period_summary_payload(
            settings,
            dff=dff,
            query=query,
            source_ids=source_ids,
        ),
        "functionality": functionality,
        "duplicates": duplicates,
        "people": people,
        "opsHealth": ops_health,
    }
