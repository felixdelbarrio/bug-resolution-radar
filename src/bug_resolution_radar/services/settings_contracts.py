"""Serialization helpers for configuration payloads exposed over the API."""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, List

from bug_resolution_radar.config import (
    Settings,
    all_configured_sources,
    country_rollup_sources,
    helix_sources,
    jira_sources,
    load_settings,
    save_settings,
    supported_countries,
    to_env_json,
)
from bug_resolution_radar.repositories.issues_store import load_issues_df
from bug_resolution_radar.services.workspace import (
    available_sources_by_country,
    merge_sources_by_country,
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
        clean: Dict[str, str] = {"country": country, "alias": alias}
        if source_type == "jira":
            jql = str(raw.get("jql") or "").strip()
            if not jql:
                continue
            clean["jql"] = jql
        else:
            for key in ("service_origin_buug", "service_origin_n1", "service_origin_n2"):
                value = str(raw.get(key) or "").strip()
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


def _group_configured_sources_by_country(settings: Settings) -> Dict[str, List[Dict[str, str]]]:
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for row in all_configured_sources(settings):
        country = str(row.get("country") or "").strip()
        source_id = str(row.get("source_id") or "").strip()
        if not country or not source_id:
            continue
        grouped.setdefault(country, []).append(
            {str(key): str(value).strip() for key, value in dict(row).items() if str(value).strip()}
        )
    for country, rows in list(grouped.items()):
        grouped[country] = sorted(rows, key=_source_sort_key)
    return grouped


def _rollup_eligible_sources_by_country(settings: Settings) -> Dict[str, List[Dict[str, str]]]:
    configured = _group_configured_sources_by_country(settings)
    try:
        df_all = load_issues_df(settings.DATA_PATH)
    except Exception:
        df_all = None
    inferred = available_sources_by_country(settings, df_all=df_all)
    return merge_sources_by_country(configured, inferred)


def load_settings_payload() -> Dict[str, Any]:
    settings = load_settings()
    return {
        "values": settings.model_dump(),
        "supportedCountries": supported_countries(settings),
        "jiraSources": jira_sources(settings),
        "helixSources": helix_sources(settings),
        "countryRollupSources": country_rollup_sources(settings),
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
    merged_values["SUPPORTED_COUNTRIES"] = ",".join(
        [
            str(item).strip()
            for item in list(payload.get("supportedCountries") or [])
            if str(item).strip()
        ]
    )
    merged_values["JIRA_SOURCES_JSON"] = to_env_json(
        _normalize_source_rows(list(payload.get("jiraSources") or []), source_type="jira")
    )
    merged_values["HELIX_SOURCES_JSON"] = to_env_json(
        _normalize_source_rows(list(payload.get("helixSources") or []), source_type="helix")
    )
    merged_values["COUNTRY_ROLLUP_SOURCES_JSON"] = to_env_json(
        [
            {
                "country": str(country or "").strip(),
                "source_ids": [
                    str(source_id).strip()
                    for source_id in list(source_ids or [])
                    if str(source_id).strip()
                ],
            }
            for country, source_ids in dict(payload.get("countryRollupSources") or {}).items()
            if str(country or "").strip()
        ]
    )
    merged_values["JIRA_INGEST_DISABLED_SOURCES_JSON"] = _normalize_disabled_source_ids(
        list(payload.get("jiraDisabledSourceIds") or [])
    )
    merged_values["HELIX_INGEST_DISABLED_SOURCES_JSON"] = _normalize_disabled_source_ids(
        list(payload.get("helixDisabledSourceIds") or [])
    )

    new_settings = Settings.model_validate(merged_values)
    save_settings(new_settings)
    return load_settings_payload()
