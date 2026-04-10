"""Backend contracts for the ingestion workspace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from bug_resolution_radar.config import Settings, helix_sources, jira_sources, save_settings
from bug_resolution_radar.models.schema import IssuesDocument
from bug_resolution_radar.models.schema_helix import HelixDocument
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.issues_store import load_issues_doc


def _parse_json_str_list(raw: object) -> list[str]:
    txt = str(raw or "").strip()
    if not txt:
        return []
    try:
        payload = json.loads(txt)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in payload:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _jira_last_ingest_payload(issues_doc: IssuesDocument) -> dict[str, Any]:
    jira_source_ids = {
        str(issue.source_id or "").strip()
        for issue in issues_doc.issues
        if str(issue.source_type or "").strip().lower() == "jira"
    }
    return {
        "schema_version": issues_doc.schema_version,
        "ingested_at": issues_doc.ingested_at,
        "jira_base_url": issues_doc.jira_base_url,
        "query": issues_doc.query,
        "jira_source_count": len([source_id for source_id in jira_source_ids if source_id]),
        "issues_count": len(issues_doc.issues),
    }


def _helix_last_ingest_payload(helix_doc: HelixDocument, *, helix_path: str) -> dict[str, Any]:
    helix_source_ids = {str(item.source_id or "").strip() for item in helix_doc.items}
    return {
        "schema_version": helix_doc.schema_version,
        "ingested_at": helix_doc.ingested_at,
        "helix_base_url": helix_doc.helix_base_url,
        "query": helix_doc.query,
        "helix_source_count": len([source_id for source_id in helix_source_ids if source_id]),
        "items_count": len(helix_doc.items),
        "data_path": helix_path,
    }


def _helix_data_path(settings: Settings) -> str:
    path = str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip()
    return path or "data/helix.json"


def _selected_source_ids(
    *,
    configured_source_ids: list[str],
    disabled_source_ids: list[str],
) -> list[str]:
    disabled = set(disabled_source_ids)
    return [source_id for source_id in configured_source_ids if source_id not in disabled]


def ingest_overview_payload(settings: Settings) -> dict[str, Any]:
    jira_cfg = list(jira_sources(settings))
    helix_cfg = list(helix_sources(settings))
    issues_doc = load_issues_doc(settings.DATA_PATH)
    helix_path = _helix_data_path(settings)
    helix_repo = HelixRepo(Path(helix_path))
    helix_doc = helix_repo.load() or HelixDocument.empty()

    jira_source_ids = [
        str(source.get("source_id", "")).strip()
        for source in jira_cfg
        if str(source.get("source_id", "")).strip()
    ]
    helix_source_ids = [
        str(source.get("source_id", "")).strip()
        for source in helix_cfg
        if str(source.get("source_id", "")).strip()
    ]
    jira_disabled = [
        source_id
        for source_id in _parse_json_str_list(
            getattr(settings, "JIRA_INGEST_DISABLED_SOURCES_JSON", "[]")
        )
        if source_id in jira_source_ids
    ]
    helix_disabled = [
        source_id
        for source_id in _parse_json_str_list(
            getattr(settings, "HELIX_INGEST_DISABLED_SOURCES_JSON", "[]")
        )
        if source_id in helix_source_ids
    ]

    return {
        "jira": {
            "configuredCount": len(jira_cfg),
            "selectedSourceIds": _selected_source_ids(
                configured_source_ids=jira_source_ids,
                disabled_source_ids=jira_disabled,
            ),
            "lastIngest": _jira_last_ingest_payload(issues_doc),
        },
        "helix": {
            "configuredCount": len(helix_cfg),
            "selectedSourceIds": _selected_source_ids(
                configured_source_ids=helix_source_ids,
                disabled_source_ids=helix_disabled,
            ),
            "lastIngest": _helix_last_ingest_payload(helix_doc, helix_path=helix_path),
        },
    }


def persist_ingest_selection(
    settings: Settings,
    *,
    connector: str,
    selected_source_ids: list[str],
) -> Settings:
    connector_token = str(connector or "").strip().lower()
    if connector_token == "jira":
        valid_source_ids = [
            str(source.get("source_id", "")).strip()
            for source in jira_sources(settings)
            if str(source.get("source_id", "")).strip()
        ]
        disabled_key = "JIRA_INGEST_DISABLED_SOURCES_JSON"
    elif connector_token == "helix":
        valid_source_ids = [
            str(source.get("source_id", "")).strip()
            for source in helix_sources(settings)
            if str(source.get("source_id", "")).strip()
        ]
        disabled_key = "HELIX_INGEST_DISABLED_SOURCES_JSON"
    else:
        raise ValueError("Conector de ingesta no soportado.")

    selected = {
        str(source_id).strip()
        for source_id in list(selected_source_ids or [])
        if str(source_id).strip() in set(valid_source_ids)
    }
    disabled_source_ids = [source_id for source_id in valid_source_ids if source_id not in selected]
    new_settings = settings.model_copy(
        update={
            disabled_key: json.dumps(
                disabled_source_ids,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        }
    )
    save_settings(new_settings)
    return new_settings
