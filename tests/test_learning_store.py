from __future__ import annotations

from pathlib import Path

from bug_resolution_radar.config import Settings
from bug_resolution_radar.ui.insights.learning_store import (
    InsightsLearningStore,
    default_learning_path,
    learning_scope_key,
)


def test_learning_store_persists_per_scope(tmp_path: Path) -> None:
    path = tmp_path / "insights_learning.json"
    store = InsightsLearningStore(path)
    store.load()
    store.set_scope(
        "Mexico::jira:mexico:core",
        state={"shown_counts": {"a": 2}},
        interactions=7,
        country="México",
        source_id="jira:mexico:core",
        snapshot={"open_total": 101, "blocked_count": 9},
    )
    store.set_scope(
        "Spain::jira:espana:retail",
        state={"shown_counts": {"b": 1}},
        interactions=3,
        country="España",
        source_id="jira:espana:retail",
    )
    store.save()

    reloaded = InsightsLearningStore(path)
    reloaded.load()
    state_mx, inter_mx = reloaded.get_scope("Mexico::jira:mexico:core")
    state_es, inter_es = reloaded.get_scope("Spain::jira:espana:retail")
    _, _, snapshot_mx = reloaded.get_scope_bundle("Mexico::jira:mexico:core")
    assert state_mx.get("shown_counts", {}).get("a") == 2
    assert inter_mx == 7
    assert int(snapshot_mx.get("open_total", 0) or 0) == 101
    assert int(snapshot_mx.get("blocked_count", 0) or 0) == 9
    assert state_es.get("shown_counts", {}).get("b") == 1
    assert inter_es == 3


def test_learning_scope_key_and_default_path() -> None:
    assert learning_scope_key("México", "jira:mexico:core") == "México::jira:mexico:core"
    assert learning_scope_key("", "") == "global::all-sources"

    settings = Settings(INSIGHTS_LEARNING_PATH="data/custom_learning.json")
    assert default_learning_path(settings) == Path("data/custom_learning.json")


def test_learning_store_remove_source() -> None:
    store = InsightsLearningStore(Path("/tmp/unused-learning.json"))
    store._raw = {
        "version": 1,
        "scopes": {
            "México::jira:mexico:core": {
                "state": {"a": 1},
                "interactions": 2,
                "source_id": "jira:mexico:core",
            },
            "España::jira:espana:retail": {
                "state": {"b": 1},
                "interactions": 3,
                "source_id": "jira:espana:retail",
            },
            "Peru::jira:mexico:core": {
                "state": {"c": 1},
                "interactions": 4,
                # Fallback de versiones antiguas sin source_id explícito.
                "source_id": "",
            },
        },
    }

    removed = store.remove_source("jira:mexico:core")
    assert removed == 2
    scopes = store._raw.get("scopes", {})
    assert "México::jira:mexico:core" not in scopes
    assert "Peru::jira:mexico:core" not in scopes
    assert "España::jira:espana:retail" in scopes
