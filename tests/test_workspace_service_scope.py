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
