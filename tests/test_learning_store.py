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
    assert state_mx.get("shown_counts", {}).get("a") == 2
    assert inter_mx == 7
    assert state_es.get("shown_counts", {}).get("b") == 1
    assert inter_es == 3


def test_learning_scope_key_and_default_path() -> None:
    assert learning_scope_key("México", "jira:mexico:core") == "México::jira:mexico:core"
    assert learning_scope_key("", "") == "global::all-sources"

    settings = Settings(INSIGHTS_LEARNING_PATH="data/custom_learning.json")
    assert default_learning_path(settings) == Path("data/custom_learning.json")
