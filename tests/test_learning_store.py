from __future__ import annotations

from pathlib import Path

from bug_resolution_radar.config import Settings
from bug_resolution_radar.services.insights_learning_store import (
    InsightsLearningStore,
    default_learning_path,
    learning_scope_key,
)


def test_learning_store_persists_per_scope(tmp_path: Path) -> None:
    path = tmp_path / "insights_learning.json"
    store = InsightsLearningStore(path)
    store.load()
    store.record_snapshot(
        "Mexico::jira:mexico:core",
        snapshot={"reference_date": "2026-08-20", "open_total": 101, "year_closed": 45},
        country="México",
        source_id="jira:mexico:core",
    )
    store.record_snapshot(
        "Spain::jira:espana:retail",
        snapshot={"reference_date": "2026-08-20", "open_total": 55, "year_closed": 31},
        country="España",
        source_id="jira:espana:retail",
    )
    store.save()

    reloaded = InsightsLearningStore(path)
    reloaded.load()
    baseline, changed = reloaded.record_snapshot(
        "Mexico::jira:mexico:core",
        snapshot={"reference_date": "2026-08-20", "open_total": 101, "year_closed": 45},
        country="México",
        source_id="jira:mexico:core",
    )
    assert baseline == {}
    assert changed is False
    assert reloaded.count_all_scopes() == 2


def test_learning_scope_key_and_default_path() -> None:
    assert learning_scope_key("México", "jira:mexico:core") == "México::jira:mexico:core"
    assert learning_scope_key("", "") == "global::all-sources"

    settings = Settings(INSIGHTS_LEARNING_PATH="data/custom_learning.json")
    assert default_learning_path(settings) == Path("data/custom_learning.json")


def test_learning_store_remove_source() -> None:
    store = InsightsLearningStore(Path("/tmp/unused-learning.json"))
    store._raw = {
        "version": 3,
        "scopes": {
            "México::jira:mexico:core": {
                "measurements": [{"open_total": 2}],
                "source_id": "jira:mexico:core",
            },
            "España::jira:espana:retail": {
                "measurements": [{"open_total": 3}],
                "source_id": "jira:espana:retail",
            },
            "Peru::jira:mexico:core": {
                "measurements": [{"open_total": 4}],
                "source_id": "jira:mexico:core",
            },
        },
    }

    removed = store.remove_source("jira:mexico:core")
    assert removed == 2
    scopes = store._raw.get("scopes", {})
    assert "México::jira:mexico:core" not in scopes
    assert "Peru::jira:mexico:core" not in scopes
    assert "España::jira:espana:retail" in scopes


def test_learning_store_keeps_previous_distinct_snapshot_as_baseline(tmp_path: Path) -> None:
    store = InsightsLearningStore(tmp_path / "learning.json")
    store.load()
    scope = "México::*"

    baseline, changed = store.record_snapshot(
        scope,
        snapshot={"reference_date": "2026-08-13", "open_total": 120},
        country="México",
        source_id="*",
    )
    assert baseline == {}
    assert changed is True

    baseline, changed = store.record_snapshot(
        scope,
        snapshot={"reference_date": "2026-08-20", "open_total": 108},
        country="México",
        source_id="*",
    )
    assert baseline["open_total"] == 120
    assert changed is True

    baseline, changed = store.record_snapshot(
        scope,
        snapshot={"reference_date": "2026-08-20", "open_total": 108},
        country="México",
        source_id="*",
    )
    assert baseline["open_total"] == 120
    assert changed is False
