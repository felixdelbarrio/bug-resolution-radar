from __future__ import annotations

from typing import Any

import pandas as pd

from bug_resolution_radar.config import Settings
from bug_resolution_radar.services import workspace
from bug_resolution_radar.services.workspace import WorkspaceSelection, apply_workspace_source_scope


def test_apply_workspace_source_scope_passes_only_country_source_ids_to_rollup(
    monkeypatch: Any,
) -> None:
    df = pd.DataFrame(
        [
            {"key": "MX-1", "country": "México", "source_id": "jira:mexico:core"},
            {"key": "MX-2", "country": "México", "source_id": "jira:mexico:retail"},
            {"key": "ES-1", "country": "España", "source_id": "jira:espana:core"},
        ]
    )
    captured: dict[str, list[str]] = {}

    def _fake_rollup_source_ids(
        settings: Settings,
        *,
        country: str,
        available_source_ids: list[str] | None = None,
    ) -> list[str]:
        _ = settings
        captured["country"] = [country]
        captured["available_source_ids"] = list(available_source_ids or [])
        return ["jira:mexico:retail"]

    monkeypatch.setattr(workspace, "rollup_source_ids", _fake_rollup_source_ids)

    out = apply_workspace_source_scope(
        df,
        settings=Settings(),
        selection=WorkspaceSelection(country="México", scope_mode="country"),
    )

    assert captured["country"] == ["México"]
    assert captured["available_source_ids"] == ["jira:mexico:core", "jira:mexico:retail"]
    assert out["key"].tolist() == ["MX-2"]


def test_country_normalization_scales_with_unique_countries(monkeypatch: Any) -> None:
    frame = pd.DataFrame({"country": ["mexico", "España"] * 1000, "key": range(2000)})
    original = workspace._canonical_country
    calls = []

    def counted(value: object, *, settings: Settings) -> str:
        calls.append(value)
        return original(value, settings=settings)

    monkeypatch.setattr(workspace, "_canonical_country", counted)
    result = apply_workspace_source_scope(
        frame, settings=Settings(), selection=WorkspaceSelection(country="México")
    )
    assert result["key"].tolist() == list(range(0, 2000, 2))
    assert len(calls) == 3  # Selection plus the two distinct stored country names.


def test_inferred_sources_preserve_first_metadata_and_canonical_deduplication() -> None:
    frame = pd.DataFrame(
        [
            {"country": "mexico", "source_id": "jira:mx", "source_alias": "First"},
            {"country": "mexico", "source_id": "jira:mx", "source_alias": "Later"},
            {"country": "México", "source_id": "jira:mx", "source_alias": "Duplicate"},
            {"country": "España", "source_id": "helix:es", "alias": "Fallback"},
        ]
    ).fillna("")
    result = workspace.inferred_sources_by_country(frame, settings=Settings())
    assert result["México"] == [
        {"country": "México", "source_id": "jira:mx", "alias": "First", "source_type": "jira"}
    ]
    assert result["España"][0]["alias"] == "Fallback"
