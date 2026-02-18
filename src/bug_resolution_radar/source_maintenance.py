"""Source configuration maintenance and cache hygiene helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from bug_resolution_radar.config import Settings, helix_sources, jira_sources, to_env_json
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.ui.common import load_issues_doc, save_issues_doc
from bug_resolution_radar.ui.insights.learning_store import (
    InsightsLearningStore,
    default_learning_path,
)


def _sid(value: object) -> str:
    return str(value or "").strip().lower()


def _helix_data_path(settings: Settings) -> Path:
    raw = str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip()
    return Path(raw or "data/helix.json")


def remove_jira_source_from_settings(settings: Settings, source_id: str) -> Tuple[Settings, bool]:
    """Remove a Jira source from settings and disable legacy Jira fallback."""
    target = _sid(source_id)
    if not target:
        return settings, False

    current = jira_sources(settings)
    kept = [row for row in current if _sid(row.get("source_id")) != target]
    removed = len(kept) != len(current)
    if not removed:
        return settings, False

    payload = [
        {
            "country": str(row.get("country") or "").strip(),
            "alias": str(row.get("alias") or "").strip(),
            "jql": str(row.get("jql") or "").strip(),
        }
        for row in kept
    ]
    updated = settings.model_copy(
        update={
            "JIRA_SOURCES_JSON": to_env_json(payload),
            # Avoid resurrecting deleted sources via legacy fallback.
            "JIRA_JQL": "",
        }
    )
    return updated, True


def remove_helix_source_from_settings(settings: Settings, source_id: str) -> Tuple[Settings, bool]:
    """Remove a Helix source from settings and disable legacy Helix fallback."""
    target = _sid(source_id)
    if not target:
        return settings, False

    current = helix_sources(settings)
    kept = [row for row in current if _sid(row.get("source_id")) != target]
    removed = len(kept) != len(current)
    if not removed:
        return settings, False

    payload = [
        {
            "country": str(row.get("country") or "").strip(),
            "alias": str(row.get("alias") or "").strip(),
            "base_url": str(row.get("base_url") or "").strip(),
            "organization": str(row.get("organization") or "").strip(),
            "browser": str(row.get("browser") or "").strip() or "chrome",
            "proxy": str(row.get("proxy") or "").strip(),
            "ssl_verify": str(row.get("ssl_verify") or "").strip() or "true",
        }
        for row in kept
    ]
    updated = settings.model_copy(
        update={
            "HELIX_SOURCES_JSON": to_env_json(payload),
            # Avoid resurrecting deleted sources via legacy fallback.
            "HELIX_BASE_URL": "",
            "HELIX_ORGANIZATION": "",
        }
    )
    return updated, True


def purge_source_cache(settings: Settings, source_id: str) -> Dict[str, int]:
    """Delete cached records associated with a source from persisted stores."""
    target = _sid(source_id)
    if not target:
        return {"issues_removed": 0, "helix_items_removed": 0, "learning_scopes_removed": 0}

    issues_doc = load_issues_doc(settings.DATA_PATH)
    issues_before = len(issues_doc.issues)
    issues_doc.issues = [i for i in issues_doc.issues if _sid(i.source_id) != target]
    issues_removed = issues_before - len(issues_doc.issues)
    if issues_removed > 0:
        save_issues_doc(settings.DATA_PATH, issues_doc)

    helix_items_removed = 0
    helix_repo = HelixRepo(_helix_data_path(settings))
    helix_doc = helix_repo.load()
    if helix_doc is not None:
        helix_before = len(helix_doc.items)
        helix_doc.items = [i for i in helix_doc.items if _sid(i.source_id) != target]
        helix_items_removed = helix_before - len(helix_doc.items)
        if helix_items_removed > 0:
            helix_repo.save(helix_doc)

    learning_scopes_removed = 0
    learning_store = InsightsLearningStore(default_learning_path(settings))
    learning_store.load()
    learning_scopes_removed = learning_store.remove_source(target)
    if learning_scopes_removed > 0:
        learning_store.save()

    return {
        "issues_removed": issues_removed,
        "helix_items_removed": helix_items_removed,
        "learning_scopes_removed": learning_scopes_removed,
    }


def source_cache_impact(settings: Settings, source_id: str) -> Dict[str, int]:
    """Count persisted records associated with a source without mutating storage."""
    target = _sid(source_id)
    if not target:
        return {"issues_records": 0, "helix_items": 0, "learning_scopes": 0}

    issues_doc = load_issues_doc(settings.DATA_PATH)
    issues_records = sum(1 for i in issues_doc.issues if _sid(i.source_id) == target)

    helix_items = 0
    helix_doc = HelixRepo(_helix_data_path(settings)).load()
    if helix_doc is not None:
        helix_items = sum(1 for i in helix_doc.items if _sid(i.source_id) == target)

    learning_store = InsightsLearningStore(default_learning_path(settings))
    learning_store.load()
    learning_scopes = learning_store.count_source_scopes(target)

    return {
        "issues_records": int(issues_records),
        "helix_items": int(helix_items),
        "learning_scopes": int(learning_scopes),
    }
