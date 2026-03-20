from __future__ import annotations

from bug_resolution_radar.config import Settings, country_rollup_sources, rollup_source_ids


def test_country_rollup_sources_keeps_only_configured_source_ids() -> None:
    settings = Settings(
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"Core","jql":"project = CORE"},'
            '{"country":"México","alias":"Retail","jql":"project = RET"}]'
        ),
        COUNTRY_ROLLUP_SOURCES_JSON=(
            '[{"country":"México","source_ids":["jira:mexico:core","jira:mexico:missing"]}]'
        ),
    )

    out = country_rollup_sources(settings)

    assert out == {"México": ["jira:mexico:core"]}


def test_rollup_source_ids_falls_back_to_available_when_not_configured() -> None:
    settings = Settings(
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
        COUNTRY_ROLLUP_SOURCES_JSON="[]",
    )

    out = rollup_source_ids(
        settings,
        country="México",
        available_source_ids=["jira:mexico:core", "jira:mexico:retail"],
    )

    assert out == ["jira:mexico:core", "jira:mexico:retail"]
