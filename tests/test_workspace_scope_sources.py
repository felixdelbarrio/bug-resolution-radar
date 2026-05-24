from __future__ import annotations

import pandas as pd

from bug_resolution_radar.config import Settings, build_source_id, rollup_source_ids
from bug_resolution_radar.services.workspace import sources_with_results_by_country


def _settings_with_jira_sources() -> Settings:
    return Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"MX Core","jql":"project = 1"},'
            '{"country":"México","alias":"MX BEX","jql":"project = 2"},'
            '{"country":"España","alias":"ES Core","jql":"project = 3"}]'
        ),
    )


def test_scope_sources_only_include_source_ids_with_results() -> None:
    settings = _settings_with_jira_sources()
    mx_core_id = build_source_id("jira", "México", "MX Core")
    es_core_id = build_source_id("jira", "España", "ES Core")

    grouped = sources_with_results_by_country(
        settings,
        df_all=pd.DataFrame(
            [
                {"country": "México", "source_id": mx_core_id},
                {"country": "España", "source_id": es_core_id},
            ]
        ),
    )
    assert set(grouped.keys()) == {"México", "España"}
    assert [row["source_id"] for row in grouped["México"]] == [mx_core_id]
    assert [row["source_id"] for row in grouped["España"]] == [es_core_id]


def test_scope_sources_requires_source_id_metadata() -> None:
    settings = _settings_with_jira_sources()

    grouped = sources_with_results_by_country(
        settings,
        df_all=pd.DataFrame(
            [
                {"country": "México"},
                {"country": "México"},
            ]
        ),
    )
    assert grouped == {}


def test_scope_sources_empty_when_there_are_no_results() -> None:
    settings = _settings_with_jira_sources()
    assert sources_with_results_by_country(settings, df_all=pd.DataFrame()) == {}


def test_configured_rollup_source_ids_for_country_filters_by_available_source_ids() -> None:
    mx_core_id = build_source_id("jira", "México", "MX Core")
    mx_bex_id = build_source_id("jira", "México", "MX BEX")
    settings = Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"MX Core","jql":"project = 1"},'
            '{"country":"México","alias":"MX BEX","jql":"project = 2"}]'
        ),
        COUNTRY_ROLLUP_SOURCES_JSON=(
            f'[{{"country":"México","source_ids":["{mx_core_id}","{mx_bex_id}"]}}]'
        ),
    )

    selected = rollup_source_ids(
        settings,
        country="México",
        available_source_ids=[mx_core_id],
    )

    assert selected == [mx_core_id]


def test_rollup_source_ids_for_country_falls_back_to_available_sources() -> None:
    settings = _settings_with_jira_sources()
    mx_core_id = build_source_id("jira", "México", "MX Core")

    selected = rollup_source_ids(
        settings,
        country="México",
        available_source_ids=[mx_core_id],
    )

    assert selected == [mx_core_id]


def test_country_rollup_scope_true_when_country_has_configured_rollup() -> None:
    mx_core_id = build_source_id("jira", "México", "MX Core")
    settings = Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        JIRA_SOURCES_JSON='[{"country":"México","alias":"MX Core","jql":"project = 1"}]',
        COUNTRY_ROLLUP_SOURCES_JSON=(f'[{{"country":"México","source_ids":["{mx_core_id}"]}}]'),
    )
    has_rollup = bool(
        rollup_source_ids(
            settings,
            country="México",
            available_source_ids=[
                source["source_id"]
                for source in sources_with_results_by_country(
                    settings,
                    df_all=pd.DataFrame([{"country": "México", "source_id": mx_core_id}]),
                ).get("México", [])
            ],
        )
    )

    assert has_rollup is True


def test_country_rollup_scope_uses_available_sources_when_no_explicit_rollup() -> None:
    mx_core_id = build_source_id("jira", "México", "MX Core")
    settings = Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        JIRA_SOURCES_JSON='[{"country":"México","alias":"MX Core","jql":"project = 1"}]',
        COUNTRY_ROLLUP_SOURCES_JSON="[]",
    )
    has_rollup = bool(
        rollup_source_ids(
            settings,
            country="México",
            available_source_ids=[
                source["source_id"]
                for source in sources_with_results_by_country(
                    settings,
                    df_all=pd.DataFrame([{"country": "México", "source_id": mx_core_id}]),
                ).get("México", [])
            ],
        )
    )

    assert has_rollup is True
