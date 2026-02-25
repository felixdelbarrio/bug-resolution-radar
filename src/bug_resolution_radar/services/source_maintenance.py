"""Source configuration maintenance and cache hygiene helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from bug_resolution_radar.config import Settings, helix_sources, jira_sources, to_env_json
from bug_resolution_radar.models.schema import IssuesDocument
from bug_resolution_radar.models.schema_helix import HelixDocument
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.ui.common import load_issues_doc, save_issues_doc
from bug_resolution_radar.ui.insights.learning_store import (
    InsightsLearningStore,
    default_learning_path,
)

_CACHE_DEFS: tuple[tuple[str, str], ...] = (
    ("issues", "Cache de issues normalizadas"),
    ("helix", "Cache Helix (raw/normalizado)"),
    ("learning", "Cache de aprendizaje (Insights)"),
)


def _sid(value: object) -> str:
    return str(value or "").strip().lower()


def _helix_data_path(settings: Settings) -> Path:
    raw = str(getattr(settings, "HELIX_DATA_PATH", "") or "").strip()
    return Path(raw or "data/helix.json")


def _cache_defs() -> List[tuple[str, str]]:
    return list(_CACHE_DEFS)


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

    payload = []
    for row in kept:
        source_payload = {
            "country": str(row.get("country") or "").strip(),
            "alias": str(row.get("alias") or "").strip(),
            "base_url": str(row.get("base_url") or "").strip(),
            "organization": str(row.get("organization") or "").strip(),
            "browser": str(row.get("browser") or "").strip() or "chrome",
            "proxy": str(row.get("proxy") or "").strip(),
            "ssl_verify": str(row.get("ssl_verify") or "").strip() or "true",
        }
        service_origin_buug = str(row.get("service_origin_buug") or "").strip()
        service_origin_n1 = str(row.get("service_origin_n1") or "").strip()
        service_origin_n2 = str(row.get("service_origin_n2") or "").strip()
        if service_origin_buug:
            source_payload["service_origin_buug"] = service_origin_buug
        if service_origin_n1:
            source_payload["service_origin_n1"] = service_origin_n1
        if service_origin_n2:
            source_payload["service_origin_n2"] = service_origin_n2
        payload.append(source_payload)
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


def cache_inventory(settings: Settings) -> List[Dict[str, Any]]:
    """Return available persisted caches with current record counts and paths."""
    issues_path = Path(
        str(getattr(settings, "DATA_PATH", "data/issues.json") or "data/issues.json")
    )
    helix_path = _helix_data_path(settings)
    learning_path = default_learning_path(settings)

    issues_records = len(load_issues_doc(str(issues_path)).issues)

    helix_items = 0
    helix_doc = HelixRepo(helix_path).load()
    if helix_doc is not None:
        helix_items = len(helix_doc.items)

    learning_store = InsightsLearningStore(learning_path)
    learning_store.load()
    learning_scopes = learning_store.count_all_scopes()

    counts = {
        "issues": int(issues_records),
        "helix": int(helix_items),
        "learning": int(learning_scopes),
    }
    paths = {
        "issues": issues_path,
        "helix": helix_path,
        "learning": learning_path,
    }

    rows: List[Dict[str, Any]] = []
    for cache_id, label in _cache_defs():
        rows.append(
            {
                "cache_id": cache_id,
                "label": label,
                "records": int(counts.get(cache_id, 0) or 0),
                "path": str(paths.get(cache_id, "")),
            }
        )
    return rows


def reset_cache_store(settings: Settings, cache_id: str) -> Dict[str, Any]:
    """Reset a persisted cache store to an empty state and report counters."""
    target = str(cache_id or "").strip().lower()
    inventory = {row["cache_id"]: row for row in cache_inventory(settings)}
    if target not in inventory:
        raise ValueError(f"Unsupported cache id: {cache_id}")

    if target == "issues":
        path = Path(str(getattr(settings, "DATA_PATH", "data/issues.json") or "data/issues.json"))
        before_doc = load_issues_doc(str(path))
        before = len(before_doc.issues)
        save_issues_doc(str(path), IssuesDocument.empty())
        after = len(load_issues_doc(str(path)).issues)
    elif target == "helix":
        path = _helix_data_path(settings)
        repo = HelixRepo(path)
        before_helix_doc = repo.load()
        before = len(before_helix_doc.items) if before_helix_doc is not None else 0
        repo.save(HelixDocument.empty())
        after_helix_doc = repo.load()
        after = len(after_helix_doc.items) if after_helix_doc is not None else 0
    elif target == "learning":
        path = default_learning_path(settings)
        store = InsightsLearningStore(path)
        store.load()
        before = store.count_all_scopes()
        store.clear_all()
        store.save()
        store.load()
        after = store.count_all_scopes()
    else:
        raise ValueError(f"Unsupported cache id: {cache_id}")

    row = inventory[target]
    return {
        "cache_id": target,
        "label": str(row.get("label") or target),
        "path": str(row.get("path") or ""),
        "before": int(before),
        "after": int(after),
        "reset": int(max(0, before - after)),
    }
