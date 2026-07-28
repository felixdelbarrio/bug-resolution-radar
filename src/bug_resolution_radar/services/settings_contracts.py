"""Serialization helpers for configuration payloads exposed over the API."""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, List

from bug_resolution_radar.common.security import validate_navigation_url
from bug_resolution_radar.config import (
    Settings,
    country_rollup_sources,
    helix_service_origin_buug_for_country,
    helix_sources,
    jira_root_cause_labels_by_country,
    jira_sources,
    load_settings,
    normalize_country_name,
    save_settings,
    supported_countries,
    to_env_json,
)
from bug_resolution_radar.repositories.issues_store import load_issues_workspace_index
from bug_resolution_radar.services.workspace import (
    configured_sources_by_country,
    merge_sources_by_country,
    sources_by_country_from_index,
)


def _fold_sort_token(value: Any) -> str:
    folded = unicodedata.normalize("NFKD", str(value or ""))
    return folded.encode("ascii", "ignore").decode("ascii").casefold().strip()


def _source_sort_key(row: Dict[str, Any]) -> tuple[str, str]:
    return _fold_sort_token(row.get("country")), _fold_sort_token(row.get("alias"))


def _normalize_source_rows(
    rows: List[Dict[str, Any]],
    *,
    source_type: str,
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for raw in list(rows or []):
        country = str(raw.get("country") or "").strip()
        alias = str(raw.get("alias") or "").strip()
        if not country or not alias:
            continue
        source_id = str(raw.get("source_id") or "").strip()
        clean: Dict[str, str] = {"country": country, "alias": alias}
        if source_id:
            clean["source_id"] = source_id
        if source_type == "jira":
            po_team_leader = str(raw.get("po_team_leader") or "").strip()
            if po_team_leader:
                clean["po_team_leader"] = po_team_leader
            dashboard_url = validate_navigation_url(
                str(raw.get("dashboard_url") or ""),
                field_name="Cuadro de mando Jira",
            )
            if dashboard_url:
                clean["dashboard_url"] = dashboard_url
            jql = str(raw.get("jql") or "").strip()
            if not jql:
                continue
            clean["jql"] = jql
        else:
            clean["service_origin_buug"] = helix_service_origin_buug_for_country(country)
            for key in ("service_origin_buug", "service_origin_n1", "service_origin_n2"):
                value = str(raw.get(key) or "").strip()
                if key == "service_origin_buug":
                    value = clean["service_origin_buug"]
                if value:
                    clean[key] = value
        out.append(clean)
    return sorted(out, key=_source_sort_key)


def _normalize_disabled_source_ids(values: List[Any]) -> str:
    out: List[str] = []
    seen: set[str] = set()
    for raw in list(values or []):
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def _normalize_bool_setting(value: Any, *, default: bool = False) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return "true" if default else "false"
    if token in {"1", "true", "t", "yes", "y", "on"}:
        return "true"
    if token in {"0", "false", "f", "no", "n", "off"}:
        return "false"
    return "true" if default else "false"


def _normalize_country_rollup_sources(
    values: Dict[str, Any],
    *,
    settings: Settings,
) -> List[Dict[str, Any]]:
    allowed_by_country: Dict[str, set[str]] = {}
    for country, sources in _rollup_eligible_sources_by_country(settings).items():
        for source in list(sources or []):
            source_id = str(source.get("source_id") or "").strip()
            if country and source_id:
                allowed_by_country.setdefault(str(country), set()).add(source_id)
    country_by_token = {
        _fold_sort_token(country): country
        for country in allowed_by_country
        if _fold_sort_token(country)
    }

    rows: List[Dict[str, Any]] = []
    for country, source_ids in dict(values or {}).items():
        country_txt = country_by_token.get(_fold_sort_token(country), str(country or "").strip())
        if not country_txt:
            continue
        allowed = allowed_by_country.get(country_txt, set())
        selected: List[str] = []
        seen: set[str] = set()
        for raw_source_id in list(source_ids or []):
            source_id = str(raw_source_id or "").strip()
            if not source_id or source_id in seen:
                continue
            if source_id not in allowed:
                continue
            seen.add(source_id)
            selected.append(source_id)
        if selected:
            rows.append({"country": country_txt, "source_ids": selected})
    return rows


def _normalize_label_tokens(values: Any) -> List[str]:
    raw_values = (
        values if isinstance(values, list) else str(values or "").replace(";", ",").split(",")
    )
    rows: List[str] = []
    seen: set[str] = set()
    for raw in list(raw_values or []):
        label = str(raw or "").strip()
        key = _fold_sort_token(label)
        if not label or key in seen:
            continue
        seen.add(key)
        rows.append(label)
    return rows


def _normalize_root_cause_label_rows(
    values: Dict[str, Any],
    *,
    settings: Settings,
) -> List[Dict[str, Any]]:
    country_by_token = {
        _fold_sort_token(country): country
        for country in supported_countries(settings)
        if _fold_sort_token(country)
    }
    rows: List[Dict[str, Any]] = []
    for raw_country, raw_labels in dict(values or {}).items():
        country = country_by_token.get(
            _fold_sort_token(raw_country), str(raw_country or "").strip()
        )
        labels = _normalize_label_tokens(raw_labels)
        if country and labels:
            rows.append({"country": country, "labels": labels})
    return sorted(rows, key=lambda row: _fold_sort_token(row.get("country")))


def _rollup_eligible_sources_by_country(settings: Settings) -> Dict[str, List[Dict[str, str]]]:
    configured = configured_sources_by_country(settings)
    try:
        index_payload = load_issues_workspace_index(settings.DATA_PATH)
    except Exception:
        index_payload = {}
    return merge_sources_by_country(
        configured,
        sources_by_country_from_index(index_payload, settings=settings),
    )


def load_settings_payload() -> Dict[str, Any]:
    settings = load_settings()
    return {
        "values": settings.model_dump(),
        "supportedCountries": supported_countries(settings),
        "jiraSources": jira_sources(settings),
        "helixSources": helix_sources(settings),
        "countryRollupSources": country_rollup_sources(settings),
        "jiraRootCauseLabelsByCountry": jira_root_cause_labels_by_country(settings),
        "rollupEligibleSourcesByCountry": _rollup_eligible_sources_by_country(settings),
        "jiraDisabledSourceIds": json.loads(
            str(getattr(settings, "JIRA_INGEST_DISABLED_SOURCES_JSON", "[]") or "[]")
        ),
        "helixDisabledSourceIds": json.loads(
            str(getattr(settings, "HELIX_INGEST_DISABLED_SOURCES_JSON", "[]") or "[]")
        ),
    }


def save_settings_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = load_settings()
    current_values = current.model_dump()
    incoming_values = dict(payload.get("values") or {})

    merged_values = {**current_values, **incoming_values}
    normalized_countries: List[str] = []
    for item in list(payload.get("supportedCountries") or []):
        country = normalize_country_name(item) or str(item or "").strip()
        if country and country not in normalized_countries:
            normalized_countries.append(country)
    merged_values["SUPPORTED_COUNTRIES"] = ",".join(normalized_countries)
    merged_values["JIRA_SOURCES_JSON"] = to_env_json(
        _normalize_source_rows(list(payload.get("jiraSources") or []), source_type="jira")
    )
    merged_values["HELIX_SOURCES_JSON"] = to_env_json(
        _normalize_source_rows(list(payload.get("helixSources") or []), source_type="helix")
    )
    settings_for_rollups = Settings.model_validate(merged_values)
    merged_values["COUNTRY_ROLLUP_SOURCES_JSON"] = to_env_json(
        _normalize_country_rollup_sources(
            dict(payload.get("countryRollupSources") or {}),
            settings=settings_for_rollups,
        )
    )
    merged_values["JIRA_ROOT_CAUSE_LABELS_BY_COUNTRY_JSON"] = to_env_json(
        _normalize_root_cause_label_rows(
            dict(payload.get("jiraRootCauseLabelsByCountry") or {}),
            settings=settings_for_rollups,
        )
    )
    merged_values["JIRA_INGEST_DISABLED_SOURCES_JSON"] = _normalize_disabled_source_ids(
        list(payload.get("jiraDisabledSourceIds") or [])
    )
    merged_values["HELIX_INGEST_DISABLED_SOURCES_JSON"] = _normalize_disabled_source_ids(
        list(payload.get("helixDisabledSourceIds") or [])
    )
    merged_values["PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED"] = _normalize_bool_setting(
        merged_values.get("PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED"),
        default=False,
    )

    new_settings = Settings.model_validate(merged_values)
    save_settings(new_settings)
    return load_settings_payload()
