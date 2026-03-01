from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.pages import config_page


def test_selected_sources_from_editor_builds_source_id_when_missing() -> None:
    df = pd.DataFrame(
        [
            {
                "__delete__": True,
                "__source_id__": "",
                "country": "México",
                "alias": "Core",
            }
        ]
    )

    selected_ids, labels = config_page._selected_sources_from_editor(df, source_type="jira")

    expected = config_page.build_source_id("jira", "México", "Core")
    assert selected_ids == [expected]
    assert labels[expected] == "México · Core"


def test_selected_sources_from_editor_keeps_selection_without_source_id_or_alias() -> None:
    df = pd.DataFrame(
        [
            {
                "__delete__": True,
                "__source_id__": "",
                "country": "México",
                "alias": "",
            }
        ]
    )

    selected_ids, labels = config_page._selected_sources_from_editor(df, source_type="helix")

    assert len(selected_ids) == 1
    token = selected_ids[0]
    assert token.startswith(config_page._DELETE_ROW_TOKEN_PREFIX)
    assert labels[token] == "México · Sin alias"


def test_source_ids_for_cache_purge_ignores_ephemeral_tokens_and_deduplicates() -> None:
    selected_ids = [
        f"{config_page._DELETE_ROW_TOKEN_PREFIX}helix:1",
        "helix:mexico:core",
        "helix:mexico:core",
    ]

    purge_ids = config_page._source_ids_for_cache_purge(selected_ids)

    assert purge_ids == ["helix:mexico:core"]
