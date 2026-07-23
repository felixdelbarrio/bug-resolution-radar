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
from bug_resolution_radar.analytics.period_functionality_followup import (
    _CRITICAL_PRIORITY_TOKENS as FUNCTIONALITY_CRITICAL_PRIORITY_TOKENS,
)
from bug_resolution_radar.analytics.period_risk_issue_lists import (
    _HIGH_PRIORITY_COMPACT_TOKENS as PERIOD_RISK_PRIORITY_TOKENS,
)
from bug_resolution_radar.analytics.period_summary import (
    _CRITICAL_PRIORITY_TOKENS as OPEN_FOCUS_PRIORITY_TOKENS,
)
from bug_resolution_radar.analytics.period_summary import (
    _quincena_last_finished_only,
    open_issues_focus_mode,
    source_label_map,
)
from bug_resolution_radar.analytics.status_semantics import (
    CORE_FINAL_STATUS_TOKENS,
    FINALIST_STATUS_TOKENS,
)
from bug_resolution_radar.config import Settings, jira_root_cause_labels_by_country
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
    build_kanban_columns,
    build_trend_detail,
    load_scope_context,
)
from bug_resolution_radar.services.workspace import WorkspaceSelection

PROJECTION_SCHEMA = "bug-resolution-radar-cloud-projection"
PROJECTION_SCHEMA_VERSION = 1
SEMANTIC_CONTRACT = "desktop-authoritative-v1"
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
            "openFocus": sorted(str(token) for token in OPEN_FOCUS_PRIORITY_TOKENS),
            "periodRisk": sorted(str(token) for token in PERIOD_RISK_PRIORITY_TOKENS),
            "functionalityFollowup": sorted(
                str(token) for token in FUNCTIONALITY_CRITICAL_PRIORITY_TOKENS
            ),
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


def _newsletter_facts(
    *,
    overview: Mapping[str, Any],
    insights: Mapping[str, Any],
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

    def card_metric(card_id: str) -> int:
        card = by_id.get(card_id, {})
        return _metric_int(card.get("metric"))

    def previous_metric(card_id: str) -> int:
        card = by_id.get(card_id, {})
        delta = card.get("delta")
        delta = delta if isinstance(delta, Mapping) else {}
        return _metric_int(delta.get("previousValue"))

    created_current = card_metric("new_now")
    created_previous = previous_metric("new_now")
    closed_current = card_metric("closed_now")
    closed_previous = previous_metric("closed_now")
    current_open = card_metric("open_total")
    focus_open = card_metric("open_focus")
    other_open = card_metric("open_other")
    focus_card = by_id.get("open_focus", {})
    focus_label = str(focus_card.get("label") or "Foco abierto")
    resolution_card = by_id.get("resolution_now", {})
    resolution_current = str(resolution_card.get("metric") or "0.0d")

    aged_open = 0
    for item in overview.get("overviewKpis", []) if isinstance(overview, Mapping) else []:
        if not isinstance(item, Mapping):
            continue
        if "> 30" in str(item.get("label") or ""):
            aged_open = _metric_int(item.get("value"))
            break

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
    facts = [
        {
            "id": "backlog",
            "statement": f"El backlog abierto del ámbito contiene {current_open} incidencias.",
        },
        {
            "id": "flow",
            "statement": (
                f"En la quincena actual se crearon {created_current} incidencias y se "
                f"cerraron {closed_current}."
            ),
        },
        {
            "id": "aging",
            "statement": f"Hay {aged_open} incidencias abiertas con más de 30 días.",
        },
        {
            "id": "resolution",
            "statement": (
                "El tiempo medio de resolución de las incidencias cerradas en la "
                f"quincena actual es {resolution_current}."
            ),
        },
    ]
    if valid_open_split:
        facts.insert(
            2,
            {
                "id": "focus",
                "statement": (
                    f"El foco «{focus_label}» reúne {focus_open} incidencias abiertas; "
                    f"el resto suma {other_open}."
                ),
            },
        )
    return {
        "periodLabel": str(period.get("caption") or ""),
        "focusLabel": focus_label if valid_open_split else "",
        "metrics": metrics,
        "facts": facts,
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


def _propagate_issue_uids(views: dict[str, Any]) -> dict[str, Any]:
    """Attach the desktop issue identity to every unambiguous issue reference."""
    issue_rows = (views.get("issues") or {}).get("rows") or []
    uids_by_key: dict[str, list[str]] = {}
    for row in issue_rows:
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("key") or "").strip()
        uid = str(row.get("issue_uid") or "").strip()
        if key and uid:
            uids_by_key.setdefault(key, []).append(uid)
    unique_uids = {key: values[0] for key, values in uids_by_key.items() if len(set(values)) == 1}

    def enrich(value: Any) -> Any:
        if isinstance(value, Mapping):
            out = {str(key): enrich(item) for key, item in value.items()}
            issue_key = str(out.get("key") or "").strip()
            if issue_key and not str(out.get("issue_uid") or "").strip():
                issue_uid = unique_uids.get(issue_key)
                if issue_uid:
                    out["issue_uid"] = issue_uid
            return out
        if isinstance(value, list):
            return [enrich(item) for item in value]
        return value

    return cast(dict[str, Any], enrich(views))


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
    intelligence = build_intelligence_snapshot(settings, query=query, insights_tab="all")
    insights = {
        "catalog": list(intelligence.get("tabs") or []),
        "byId": {
            "summary": {"periodSummary": intelligence.get("periodSummary") or {}},
            "functionality": intelligence.get("functionality") or {},
            "duplicates": intelligence.get("duplicates") or {},
            "rootCauseEvolutives": intelligence.get("rootCauseEvolutives") or {},
            "finalistDiscrepancies": intelligence.get("finalistDiscrepancies") or {},
            "people": intelligence.get("people") or {},
            "opsHealth": intelligence.get("opsHealth") or {},
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
    kanban = build_kanban_columns(settings, query=query)
    views = _propagate_issue_uids(
        _strip_cloud_actions(
            {
                "overview": overview,
                "insights": insights,
                "trends": {"catalog": trend_catalog, "byId": trend_details},
                "issues": issues,
                "kanban": kanban,
            }
        )
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
    newsletter = _newsletter_facts(overview=overview, insights=intelligence)
    facts_sha256 = sha256_bytes(canonical_json_bytes(newsletter))
    revision_payload = {
        "country": country_text,
        "scopeMode": mode,
        "sourceIds": list(clean_source_ids),
        "referenceDate": reference_date,
        "views": views,
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
