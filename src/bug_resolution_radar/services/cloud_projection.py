"""Desktop-authoritative, immutable projection consumed by the GPC WebApp."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, cast

import pandas as pd

from bug_resolution_radar.analytics.analysis_window import parse_analysis_lookback_months
from bug_resolution_radar.analytics.filtering import FilterState
from bug_resolution_radar.analytics.insights import THEME_RULES
from bug_resolution_radar.analytics.issues import CRITICAL_PRIORITY_COMPACT_TOKENS
from bug_resolution_radar.analytics.period_summary import (
    _quincena_last_finished_only,
    open_issues_focus_mode,
    source_label_map,
)
from bug_resolution_radar.analytics.status_semantics import (
    CORE_FINAL_STATUS_TOKENS,
    FINALIST_STATUS_TOKENS,
    is_finalist_status,
)
from bug_resolution_radar.config import (
    Settings,
    jira_root_cause_labels_by_country,
    jira_sources,
)
from bug_resolution_radar.reports.period_followup_ppt import PeriodFollowupReportResult
from bug_resolution_radar.reports.service import (
    build_report_filters,
    generate_period_followup_report_artifact,
)
from bug_resolution_radar.services.dashboard_snapshot import (
    DashboardQuery,
    build_dashboard_snapshot,
    build_intelligence_snapshot,
    build_issue_rows,
    build_trend_detail,
    load_scope_context,
)
from bug_resolution_radar.services.workspace import WorkspaceSelection

PROJECTION_SCHEMA = "bug-resolution-radar-cloud-projection"
PROJECTION_SCHEMA_VERSION = 3
SEMANTIC_CONTRACT = "desktop-authoritative-v3"
REPORT_PATH = "artifacts/period_followup.pptx"
REPORT_MIME_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
TREND_IDS: tuple[str, ...] = (
    "timeseries",
    "age_buckets",
    "open_status_bar",
    "open_priority_pie",
    "resolution_hist",
)
_CLOUD_ACTION_KEYS = frozenset(
    {
        "filters",
        "statusFilters",
        "priorityFilters",
        "assigneeFilters",
        "functionalityFilters",
        "issueKeys",
        "quincenalScopeLabel",
        "selected",
        "combo",
        "statusOptions",
        "priorityOptions",
        "functionalityOptions",
        "selectedStatuses",
        "selectedPriorities",
        "selectedFunctionalities",
    }
)
_HIDDEN_WEBAPP_STATUS_TOKENS = frozenset({"discarded", "deleted"})


@dataclass(frozen=True)
class CloudProjectionArtifact:
    projection: dict[str, Any]
    projection_content: bytes
    report_content: bytes


def _json_safe(value: Any) -> Any:
    """Return plain JSON values and reject non-deterministic NaN/Infinity tokens."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except Exception:
            pass
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _strip_cloud_actions(value: Any) -> Any:
    """Remove desktop drill-down/filter metadata from immutable cloud views."""
    if isinstance(value, Mapping):
        return {
            str(key): _strip_cloud_actions(item)
            for key, item in value.items()
            if str(key) not in _CLOUD_ACTION_KEYS
        }
    if isinstance(value, list):
        return [_strip_cloud_actions(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_cloud_actions(item) for item in value]
    return value


def _scope_reference_date(frame: pd.DataFrame) -> str:
    candidates: list[pd.Timestamp] = []
    for column in ("updated", "resolved", "created"):
        if column not in frame.columns:
            continue
        parsed = pd.to_datetime(frame[column], errors="coerce", utc=True)
        if parsed.notna().any():
            candidates.append(pd.Timestamp(parsed.max()).tz_convert(None))
    if not candidates:
        return str(pd.Timestamp.now("UTC").date().isoformat())
    return str(max(candidates).date().isoformat())


def _normalized_generated_at(value: datetime | str | None) -> str:
    if value is None:
        stamp = datetime.now(timezone.utc)
    else:
        stamp = pd.Timestamp(value).to_pydatetime()
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        else:
            stamp = stamp.astimezone(timezone.utc)
    return stamp.isoformat(timespec="seconds")


def _scope_key(country: str, source_ids: Sequence[str]) -> str:
    folded = unicodedata.normalize("NFKD", str(country or "").strip())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    folded = " ".join(folded.casefold().split())
    source_token = source_ids[0] if len(source_ids) == 1 else "*"
    return f"{folded}::{source_token}"


def _scope_label(
    settings: Settings,
    *,
    country: str,
    scope_mode: str,
    source_ids: Sequence[str],
) -> str:
    if scope_mode == "country" or len(source_ids) != 1:
        return f"{country} · Agregado"
    labels = source_label_map(settings, country=country, source_ids=source_ids)
    label = str(labels.get(source_ids[0]) or source_ids[0]).split("·")[0].strip()
    return f"{country} · {label}"


def _semantic_trace(settings: Settings) -> dict[str, Any]:
    return {
        "sourceOfTruth": "desktop",
        "analysisLookbackMonths": int(parse_analysis_lookback_months(settings)),
        "fortnightCalendar": {
            "timezone": "UTC",
            "first": {"startDay": 1, "endDay": 14},
            "second": {"startDay": 15, "endDay": "month-end"},
            "lastFinishedOnly": bool(_quincena_last_finished_only(settings)),
        },
        "closure": {
            "effectiveFinalistStatusTokens": list(FINALIST_STATUS_TOKENS),
            "coreFinalStatusTokens": list(CORE_FINAL_STATUS_TOKENS),
            "resolvedTimestampTakesPrecedence": True,
            "coreFinalStatusMayUseUpdatedTimestamp": True,
            "verifiedHelixFinalistOverlay": True,
        },
        "prioritySets": {
            "openFocus": sorted(CRITICAL_PRIORITY_COMPACT_TOKENS),
            "periodRisk": sorted(CRITICAL_PRIORITY_COMPACT_TOKENS),
            "functionalityFollowup": sorted(CRITICAL_PRIORITY_COMPACT_TOKENS),
        },
        "openIssuesFocusMode": open_issues_focus_mode(settings),
        "functionalityRules": [
            {"label": label, "tokens": list(tokens)} for label, tokens in THEME_RULES
        ],
        "rootCauseLabelsByCountry": jira_root_cause_labels_by_country(settings),
    }


def _metric_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(str(value or "0").replace(",", "").rstrip("d")))
    except (TypeError, ValueError):
        return 0


def _is_hidden_webapp_status(value: Any) -> bool:
    return str(value or "").strip().casefold() in _HIDDEN_WEBAPP_STATUS_TOKENS


def _manager_source_catalog(
    settings: Settings,
    *,
    country: str,
    source_ids: Sequence[str],
) -> list[dict[str, str]]:
    selected = set(source_ids)
    rows: list[dict[str, str]] = []
    for source in jira_sources(settings):
        source_id = str(source.get("source_id") or "").strip()
        if source_id not in selected or str(source.get("country") or "").strip() != country:
            continue
        rows.append(
            {
                "sourceId": source_id,
                "alias": str(source.get("alias") or "").strip(),
                "poTeamLeader": str(source.get("po_team_leader") or "").strip(),
                "dashboardUrl": str(source.get("dashboard_url") or "").strip(),
            }
        )
    return rows


def _series_text(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series("", index=frame.index, dtype=str)
    return frame[column].fillna("").astype(str).str.strip()


def _unique_issue_count(frame: pd.DataFrame, *, key_columns: Sequence[str]) -> int:
    if frame.empty:
        return 0
    for column in key_columns:
        if column in frame.columns:
            values = _series_text(frame, column)
            non_empty = values.loc[values.ne("")]
            if not non_empty.empty:
                return int(non_empty.nunique())
    return int(len(frame))


def _manager_rollups(
    *,
    context: Any,
    sources: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    source_by_id = {str(row.get("sourceId") or ""): row for row in sources}

    def with_manager(frame: pd.DataFrame) -> pd.DataFrame:
        work = frame.copy(deep=False) if isinstance(frame, pd.DataFrame) else pd.DataFrame()
        if work.empty:
            return work
        configured = _series_text(work, "source_id").map(
            lambda source_id: str(source_by_id.get(source_id, {}).get("poTeamLeader") or "").strip()
        )
        existing = _series_text(work, "po_team_leader")
        work = work.copy()
        work["__manager"] = existing.where(existing.ne(""), configured)
        work["__manager"] = work["__manager"].replace("", "Sin responsable configurado")
        return work

    open_frame = with_manager(context.open_df)
    root_frame = with_manager(context.root_cause_evolutives)
    finalist_frame = with_manager(context.finalist_discrepancies)
    managers = sorted(
        set(_series_text(open_frame, "__manager"))
        | set(_series_text(root_frame, "__manager"))
        | set(_series_text(finalist_frame, "__manager")),
        key=lambda value: unicodedata.normalize("NFKD", value).casefold(),
    )
    rows: list[dict[str, Any]] = []
    for manager in managers:
        open_bucket = open_frame.loc[_series_text(open_frame, "__manager").eq(manager)]
        root_bucket = root_frame.loc[_series_text(root_frame, "__manager").eq(manager)]
        finalist_bucket = finalist_frame.loc[_series_text(finalist_frame, "__manager").eq(manager)]
        manager_source_ids = set(_series_text(open_bucket, "source_id"))
        manager_source_ids.update(_series_text(root_bucket, "source_id"))
        manager_source_ids.update(_series_text(finalist_bucket, "source_id"))
        dashboard_url = next(
            (
                str(source_by_id[source_id].get("dashboardUrl") or "")
                for source_id in sorted(manager_source_ids)
                if source_id in source_by_id
                and str(source_by_id[source_id].get("dashboardUrl") or "")
            ),
            "",
        )
        rows.append(
            {
                "name": manager,
                "dashboardUrl": dashboard_url,
                "openIssues": _unique_issue_count(open_bucket, key_columns=("issue_uid", "key")),
                "rootCauseEvolutives": _unique_issue_count(
                    root_bucket, key_columns=("jira_key", "key")
                ),
                "finalistDiscrepancies": _unique_issue_count(
                    finalist_bucket, key_columns=("jira_key", "key")
                ),
            }
        )
    return rows


def _newsletter_facts(
    *,
    insights: Mapping[str, Any],
    context: Any,
    sources: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    period = insights.get("periodSummary")
    period = period if isinstance(period, Mapping) else {}
    cards = period.get("cards")
    cards = cards if isinstance(cards, list) else []
    by_id = {
        str(card.get("cardId") or ""): card
        for card in cards
        if isinstance(card, Mapping) and str(card.get("cardId") or "")
    }
    evolution = insights.get("executionEvolution")
    evolution = evolution if isinstance(evolution, Mapping) else {}
    fortnight = evolution.get("fortnight")
    fortnight = fortnight if isinstance(fortnight, Mapping) else {}
    current_period = fortnight.get("current")
    current_period = current_period if isinstance(current_period, Mapping) else {}
    previous_period = fortnight.get("previous")
    previous_period = previous_period if isinstance(previous_period, Mapping) else {}
    executive = evolution.get("executive")
    executive = executive if isinstance(executive, Mapping) else {}

    def card_metric(card_id: str) -> int:
        card = by_id.get(card_id, {})
        return _metric_int(card.get("metric"))

    created_current = _metric_int(current_period.get("created"))
    created_previous = _metric_int(previous_period.get("created"))
    closed_current = _metric_int(current_period.get("closed"))
    closed_previous = _metric_int(previous_period.get("closed"))
    current_open = _metric_int(current_period.get("backlogEnd"))
    previous_open = _metric_int(current_period.get("backlogStart"))
    focus_open = card_metric("open_focus")
    other_open = card_metric("open_other")
    focus_card = by_id.get("open_focus", {})
    focus_label = str(focus_card.get("label") or "Foco abierto")
    resolution_value = current_period.get("resolutionDays")
    resolution_current = f"{float(resolution_value):.1f}d" if resolution_value is not None else "—"
    backlog_delta = current_open - previous_open

    aged_open = _metric_int(current_period.get("aged30Open"))

    show_open_split = bool(period.get("showOpenSplit"))
    valid_open_split = show_open_split and focus_open + other_open == current_open
    metrics = {
        "createdCurrent": created_current,
        "createdPrevious": created_previous,
        "closedCurrent": closed_current,
        "closedPrevious": closed_previous,
        "currentOpen": current_open,
        "agedOpen": aged_open,
        "resolutionCurrent": resolution_current,
    }
    if valid_open_split:
        metrics["focusOpen"] = focus_open
        metrics["otherOpen"] = other_open
    critical_open = _metric_int(current_period.get("criticalOpen"))
    rollups = _manager_rollups(context=context, sources=sources)
    summary = str(executive.get("summary") or "").strip()
    responsible_paragraphs = [
        (
            f"{row['name']}: {row['openIssues']} incidencias abiertas, "
            f"de las cuales {row['rootCauseEvolutives']} son evolutivos para solucionar "
            f"causas raíces y {row['finalistDiscrepancies']} son discrepancias finalistas."
        )
        for row in rollups
    ]
    return {
        "periodLabel": str(period.get("caption") or ""),
        "focusLabel": focus_label if valid_open_split else "",
        "metrics": metrics,
        "previousOpen": previous_open,
        "backlogDelta": backlog_delta,
        "criticalOpen": critical_open,
        "evolution": {
            "tone": str(executive.get("tone") or "neutral"),
            "title": str(executive.get("title") or "Evolución del periodo"),
            "summary": summary,
            "focus": [str(item) for item in list(executive.get("focus") or []) if str(item)],
            "yearLabel": str((evolution.get("annual") or {}).get("label") or ""),
            "fortnightLabel": str(current_period.get("label") or ""),
        },
        "responsibleRollups": rollups,
        "draft": {
            "subject": f"Seguimiento quincenal de incidencias · {str(period.get('caption') or '')}",
            "greeting": "Buenos días,",
            "intro": (
                "Adjunto el informe correspondiente al seguimiento de incidencias "
                "de la última quincena:"
            ),
            "reportLinkLabel": "Enlace a la presentación",
            "summary": summary,
            "responsibleIntro": (
                "Conforme al análisis realizado, los datos por responsable son los siguientes:"
            ),
            "responsibleParagraphs": responsible_paragraphs,
            "closing": "Esperamos que esta información os sea de utilidad.",
        },
    }


def _projection_query(
    *,
    country: str,
    scope_mode: str,
    source_ids: Sequence[str],
) -> DashboardQuery:
    source_id = source_ids[0] if scope_mode == "source" else ""
    return DashboardQuery(
        workspace=WorkspaceSelection(
            country=country,
            source_id=source_id,
            scope_mode=scope_mode,
        ),
        filters=FilterState(status=[], priority=[], assignee=[]),
        source_ids=tuple(source_ids),
        quincenal_scope="Todas",
        chart_ids=TREND_IDS,
        dark_mode=False,
    )


def _propagate_issue_links(views: dict[str, Any]) -> dict[str, Any]:
    """Attach desktop identity and URL to every unambiguous issue reference."""
    issue_rows = (views.get("issues") or {}).get("rows") or []
    refs_by_key: dict[str, list[tuple[str, str]]] = {}
    for row in issue_rows:
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("key") or "").strip()
        uid = str(row.get("issue_uid") or "").strip()
        url = str(row.get("url") or "").strip()
        if key and uid:
            refs_by_key.setdefault(key, []).append((uid, url))
    unique_refs = {
        key: values[0]
        for key, values in refs_by_key.items()
        if len({uid for uid, _url in values}) == 1
    }

    def enrich(value: Any) -> Any:
        if isinstance(value, Mapping):
            out = {str(key): enrich(item) for key, item in value.items()}
            issue_key = str(out.get("key") or "").strip()
            if issue_key and not str(out.get("issue_uid") or "").strip():
                reference = unique_refs.get(issue_key)
                if reference:
                    out["issue_uid"] = reference[0]
                    if reference[1] and not str(out.get("url") or "").strip():
                        out["url"] = reference[1]
            return out
        if isinstance(value, list):
            return [enrich(item) for item in value]
        return value

    return cast(dict[str, Any], enrich(views))


def _materialize_issue_references(value: Any, issue_rows: Sequence[Mapping[str, Any]]) -> Any:
    """Turn desktop filter keys into immutable, directly navigable issue records."""
    refs_by_key: dict[str, list[dict[str, str]]] = {}
    for row in issue_rows:
        key = str(row.get("key") or "").strip()
        uid = str(row.get("issue_uid") or "").strip()
        if not key or not uid:
            continue
        refs_by_key.setdefault(key, []).append(
            {
                "key": key,
                "issue_uid": uid,
                "url": str(row.get("url") or "").strip(),
                "summary": str(row.get("summary") or "").strip(),
                "status": str(row.get("status") or "").strip(),
                "priority": str(row.get("priority") or "").strip(),
            }
        )
    unique_refs: dict[str, dict[str, str]] = {}
    for key, rows in refs_by_key.items():
        identities = {row["issue_uid"] for row in rows}
        urls = {row["url"] for row in rows if row["url"]}
        if len(identities) == 1:
            unique_refs[key] = rows[0]
        elif len(urls) == 1:
            unique_refs[key] = {**rows[0], "issue_uid": "", "url": next(iter(urls))}

    def convert(item: Any) -> Any:
        if isinstance(item, Mapping):
            out = {
                str(key): convert(nested) for key, nested in item.items() if str(key) != "issueKeys"
            }
            issue_keys = item.get("issueKeys")
            if isinstance(issue_keys, Sequence) and not isinstance(issue_keys, str):
                referenced = [
                    unique_refs[key]
                    for raw_key in issue_keys
                    if (key := str(raw_key or "").strip()) in unique_refs
                ]
                if referenced and "issues" not in out:
                    out["issues"] = referenced
            return out
        if isinstance(item, list):
            return [convert(nested) for nested in item]
        if isinstance(item, tuple):
            return [convert(nested) for nested in item]
        return item

    return convert(value)


def build_cloud_projection_artifact(
    settings: Settings,
    *,
    country: str,
    source_ids: Sequence[str],
    scope_mode: str,
    generated_at: datetime | str | None = None,
    report_result: PeriodFollowupReportResult | None = None,
) -> CloudProjectionArtifact:
    """Materialize every cloud view and attach the exact local PPTX bytes."""
    country_text = str(country or "").strip()
    clean_source_ids = tuple(
        sorted(
            {
                str(source_id or "").strip()
                for source_id in source_ids
                if str(source_id or "").strip()
            }
        )
    )
    mode = str(scope_mode or "").strip().casefold()
    if not country_text:
        raise ValueError("Selecciona un país antes de exportar la vista.")
    if mode not in {"country", "source"}:
        raise ValueError("El modo de ámbito no es válido.")
    if not clean_source_ids:
        raise ValueError("Selecciona al menos un origen antes de exportar la vista.")
    if mode == "source" and len(clean_source_ids) != 1:
        raise ValueError("La vista por origen debe contener exactamente un origen.")

    stamp = _normalized_generated_at(generated_at)
    query = _projection_query(
        country=country_text,
        scope_mode=mode,
        source_ids=clean_source_ids,
    )
    context = load_scope_context(settings, query=query, include_kpis=True)
    if context.dff.empty:
        raise ValueError("La vista seleccionada no contiene incidencias para exportar.")
    reference_date = _scope_reference_date(context.dff)

    overview = build_dashboard_snapshot(settings, query=query)
    overview_chart_ids = [
        str(chart.get("id") or "")
        for chart in list(overview.get("charts") or [])
        if isinstance(chart, Mapping)
    ]
    if overview_chart_ids != list(TREND_IDS):
        raise ValueError("El escritorio no ha materializado el catálogo completo de gráficos GPC.")
    matrix = overview.get("statusPriorityMatrix")
    if isinstance(matrix, Mapping):
        matrix_rows = [
            row
            for row in list(matrix.get("rows") or [])
            if isinstance(row, Mapping)
            and not is_finalist_status(row.get("status"))
            and not _is_hidden_webapp_status(row.get("status"))
        ]
        priority_totals: dict[str, int] = {}
        for row in matrix_rows:
            for cell in list(row.get("cells") or []):
                if not isinstance(cell, Mapping):
                    continue
                priority = str(cell.get("priority") or "")
                priority_totals[priority] = priority_totals.get(priority, 0) + _metric_int(
                    cell.get("count")
                )
        filtered_matrix = dict(matrix)
        filtered_matrix["rows"] = matrix_rows
        filtered_matrix["total"] = sum(_metric_int(row.get("count")) for row in matrix_rows)
        filtered_matrix["priorities"] = [
            {
                **dict(priority),
                "count": priority_totals.get(str(priority.get("priority") or ""), 0),
            }
            for priority in list(matrix.get("priorities") or [])
            if isinstance(priority, Mapping)
        ]
        overview["statusPriorityMatrix"] = filtered_matrix
    intelligence = build_intelligence_snapshot(
        settings,
        query=query,
        insights_tab="all",
        insights_view_mode="accumulated",
    )
    cloud_insight_ids = {
        "evolution",
        "summary",
        "functionality",
        "duplicates",
        "rootCauseEvolutives",
        "finalistDiscrepancies",
        "people",
    }
    insight_catalog = [
        item
        for item in list(intelligence.get("tabs") or [])
        if str(item.get("id") or "") in cloud_insight_ids
    ]
    insights = {
        "catalog": insight_catalog,
        "byId": {
            "evolution": {"executionEvolution": intelligence.get("executionEvolution") or {}},
            "summary": {"periodSummary": intelligence.get("periodSummary") or {}},
            "functionality": intelligence.get("functionality") or {},
            "duplicates": intelligence.get("duplicates") or {},
            "rootCauseEvolutives": intelligence.get("rootCauseEvolutives") or {},
            "finalistDiscrepancies": intelligence.get("finalistDiscrepancies") or {},
            "people": intelligence.get("people") or {},
        },
    }
    trend_details = {
        trend_id: build_trend_detail(settings, query=query, chart_id=trend_id)
        for trend_id in TREND_IDS
    }
    trend_catalog = [
        {
            "id": trend_id,
            "title": str((trend_details[trend_id].get("chart") or {}).get("title") or ""),
            "subtitle": str((trend_details[trend_id].get("chart") or {}).get("subtitle") or ""),
            "group": str((trend_details[trend_id].get("chart") or {}).get("group") or ""),
        }
        for trend_id in TREND_IDS
    ]
    issues = build_issue_rows(
        settings,
        query=query,
        offset=0,
        limit=max(int(len(context.dff)), 1),
        sort_by="key",
        sort_dir="asc",
    )
    visible_issue_rows = [
        row
        for row in list(issues.get("rows") or [])
        if isinstance(row, Mapping) and not _is_hidden_webapp_status(row.get("status"))
    ]
    issues = {**issues, "rows": visible_issue_rows, "total": len(visible_issue_rows)}
    if "totalRows" in issues:
        issues["totalRows"] = len(visible_issue_rows)
    raw_views = {
        "overview": overview,
        "insights": insights,
        "trends": {"catalog": trend_catalog, "byId": trend_details},
        "issues": issues,
    }
    issue_rows = [row for row in list(issues.get("rows") or []) if isinstance(row, Mapping)]
    views = _propagate_issue_links(
        _strip_cloud_actions(_materialize_issue_references(raw_views, issue_rows))
    )

    if report_result is None:
        report_result = generate_period_followup_report_artifact(
            settings,
            country=country_text,
            source_ids=clean_source_ids,
            filters=build_report_filters(),
            reference_day=reference_date,
        )
    report_content = bytes(report_result.content)
    report = {
        "fileName": str(report_result.file_name),
        "mimeType": REPORT_MIME_TYPE,
        "sha256": sha256_bytes(report_content),
        "bytes": len(report_content),
        "slideCount": int(report_result.slide_count),
    }
    manager_sources = _manager_source_catalog(
        settings,
        country=country_text,
        source_ids=clean_source_ids,
    )
    newsletter = _newsletter_facts(
        insights=intelligence,
        context=context,
        sources=manager_sources,
    )
    facts_sha256 = sha256_bytes(canonical_json_bytes(newsletter))
    revision_payload = {
        "country": country_text,
        "scopeMode": mode,
        "sourceIds": list(clean_source_ids),
        "referenceDate": reference_date,
        "administration": {"jiraSources": manager_sources},
        "views": views,
        "newsletterFacts": newsletter,
        "report": report,
    }
    data_version = sha256_bytes(canonical_json_bytes(revision_payload))[:24]
    scope = {
        "scopeKey": _scope_key(country_text, clean_source_ids),
        "scopeLabel": _scope_label(
            settings,
            country=country_text,
            scope_mode=mode,
            source_ids=clean_source_ids,
        ),
        "country": country_text,
        "scopeMode": mode,
        "sourceIds": list(clean_source_ids),
        "dataVersion": data_version,
        "referenceDate": reference_date,
        "immutable": True,
    }
    projection = {
        "schema": PROJECTION_SCHEMA,
        "schemaVersion": PROJECTION_SCHEMA_VERSION,
        "semanticContract": SEMANTIC_CONTRACT,
        "generatedAt": stamp,
        "scope": scope,
        "semantics": _semantic_trace(settings),
        "administration": {"jiraSources": manager_sources},
        "views": views,
        "newsletterFacts": newsletter,
        "report": report,
        "factsSha256": facts_sha256,
    }
    projection_content = canonical_json_bytes(projection)
    return CloudProjectionArtifact(
        projection=_json_safe(projection),
        projection_content=projection_content,
        report_content=report_content,
    )
