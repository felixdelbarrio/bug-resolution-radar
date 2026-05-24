from __future__ import annotations

from bug_resolution_radar.common.issue_links import (
    build_helix_issue_url,
    build_issue_url_maps,
    build_jira_issue_url,
    linkify_issue_references,
    normalize_helix_id,
    normalize_jira_key,
)


def test_issue_link_builders_validate_ids_and_use_existing_urls() -> None:
    assert normalize_jira_key("eam-94000") == "EAM-94000"
    assert normalize_jira_key("not-an-issue") == ""
    assert normalize_helix_id("inc000104154954") == "INC000104154954"
    assert normalize_helix_id("INC123") == ""

    assert (
        build_jira_issue_url(
            "EAM-94000",
            existing_url="https://jira.example/browse/EAM-94000",
        )
        == "https://jira.example/browse/EAM-94000"
    )
    assert build_jira_issue_url("bad key", base_url="https://jira.example") == ""
    assert (
        build_jira_issue_url(
            "SKSEMEX-89158",
            base_url="https://jira.example/browse/OLD-1",
        )
        == "https://jira.example/browse/SKSEMEX-89158"
    )

    assert (
        build_helix_issue_url(
            "INC000104154954",
            existing_url="https://helix.example/INC000104154954",
        )
        == "https://helix.example/INC000104154954"
    )
    assert build_helix_issue_url("INC123", base_url="https://helix.example") == ""


def test_build_issue_url_maps_uses_only_resolved_helix_urls() -> None:
    jira_urls, helix_urls = build_issue_url_maps(
        [
            {
                "key": "EAM-94000",
                "source_type": "jira",
                "url": "https://jira.example/browse/EAM-94000",
            },
            {
                "key": "INC000104154954",
                "source_type": "helix",
                "url": "https://helix.example/incident/IDG123",
            },
            {
                "helix_id": "INC000104154955",
                "helix_url": "",
            },
        ],
        jira_base_url="https://jira.example",
        helix_base_url="https://helix.example/ticket-console",
    )

    assert jira_urls == {"EAM-94000": "https://jira.example/browse/EAM-94000"}
    assert helix_urls == {"INC000104154954": "https://helix.example/incident/IDG123"}


def test_linkify_issue_references_keeps_text_and_links_valid_tokens() -> None:
    segments = linkify_issue_references(
        "Ver EAM-94000 y INC000104154954; ignorar INC123.",
        jira_urls={"EAM-94000": "https://jira.example/browse/EAM-94000"},
        helix_urls={"INC000104154954": "https://helix.example/INC000104154954"},
    )

    rendered = "".join(segment.text for segment in segments)
    assert rendered == "Ver EAM-94000 y INC000104154954; ignorar INC123."
    assert [segment.url for segment in segments if segment.kind == "jira"] == [
        "https://jira.example/browse/EAM-94000"
    ]
    assert [segment.url for segment in segments if segment.kind == "helix"] == [
        "https://helix.example/INC000104154954"
    ]
