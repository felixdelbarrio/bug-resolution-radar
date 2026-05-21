from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.finalist_discrepancies import (
    ANALYSIS_MODE_COUNTRY_FINALIST_STATUS,
    apply_effective_finalist_country_mode,
    build_finalist_status_discrepancies,
    build_jira_helix_links,
    extract_helix_ids_from_text,
)
from bug_resolution_radar.config import Settings


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country": "México",
                "source_type": "jira",
                "source_id": "jira:mexico:senda",
                "source_alias": "Senda",
                "key": "MEX-1",
                "summary": "Jira pendiente",
                "description": "Relacionado con inc000104154954 e INC000104154954.",
                "status": "To Rework",
                "priority": "High",
                "assignee": "Ana",
                "created": "2026-05-01T00:00:00Z",
                "updated": "2026-05-05T00:00:00Z",
                "resolved": pd.NaT,
                "url": "https://jira.example.com/browse/MEX-1",
            },
            {
                "country": "México",
                "source_type": "jira",
                "source_id": "jira:mexico:senda",
                "source_alias": "Senda",
                "key": "MEX-2",
                "summary": "Jira finalista",
                "description": "Relacionado con INC000104154955.",
                "status": "Accepted",
                "priority": "Medium",
                "assignee": "Luis",
                "created": "2026-05-01T00:00:00Z",
                "updated": "2026-05-05T00:00:00Z",
                "resolved": pd.NaT,
                "url": "https://jira.example.com/browse/MEX-2",
            },
            {
                "country": "México",
                "source_type": "helix",
                "source_id": "helix:mexico:smartit",
                "source_alias": "Helix",
                "key": "INC000104154954",
                "summary": "Helix cerrado",
                "description": "Detalle",
                "status": "Closed",
                "priority": "High",
                "created": "2026-04-29T00:00:00Z",
                "updated": "2026-05-03T00:00:00Z",
                "resolved": "2026-05-03T00:00:00Z",
                "url": "https://helix.example.com/INC000104154954",
            },
            {
                "country": "México",
                "source_type": "helix",
                "source_id": "helix:mexico:smartit",
                "source_alias": "Helix",
                "key": "INC000104154955",
                "summary": "Helix cerrado 2",
                "description": "Detalle",
                "status": "Closed",
                "updated": "2026-05-03T00:00:00Z",
                "resolved": "2026-05-03T00:00:00Z",
            },
            {
                "country": "España",
                "source_type": "helix",
                "source_id": "helix:espana:smartit",
                "key": "INC000104154954",
                "status": "Closed",
            },
        ]
    )


def test_extract_helix_ids_from_text_normalizes_and_dedupes() -> None:
    assert extract_helix_ids_from_text("inc000104154954 / INC000104154954 / INC123") == (
        "INC000104154954",
    )


def test_build_jira_helix_links_crosses_by_country() -> None:
    links = build_jira_helix_links(
        _df(),
        country="México",
        source_ids=["jira:mexico:senda", "helix:mexico:smartit"],
    )

    assert links["jira_key"].tolist() == ["MEX-1", "MEX-2"]
    assert set(links["helix_id"].tolist()) == {"INC000104154954", "INC000104154955"}
    assert set(links["country"].tolist()) == {"México"}


def test_discrepancy_when_helix_finalist_and_jira_open() -> None:
    out = build_finalist_status_discrepancies(
        _df(),
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda", "helix:mexico:smartit"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    assert out["jira_key"].tolist() == ["MEX-1"]
    assert out.iloc[0]["helix_id"] == "INC000104154954"
    assert bool(out.iloc[0]["helix_status_is_finalist"]) is True
    assert bool(out.iloc[0]["jira_status_is_finalist"]) is False


def test_no_discrepancy_when_both_finalists() -> None:
    out = build_finalist_status_discrepancies(
        _df().loc[lambda frame: frame["key"].isin(["MEX-2", "INC000104154955"])],
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda", "helix:mexico:smartit"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    assert out.empty


def test_no_discrepancy_when_helix_finalized_outside_window() -> None:
    out = build_finalist_status_discrepancies(
        _df(),
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda", "helix:mexico:smartit"],
        reference_day=pd.Timestamp("2026-05-02"),
    )

    assert out.empty


def test_country_finalist_mode_uses_country_helix_and_closes_jira_effectively() -> None:
    settings = Settings(FINALIST_STATUS_ANALYSIS_MODE=ANALYSIS_MODE_COUNTRY_FINALIST_STATUS)
    discrepancies = build_finalist_status_discrepancies(
        _df(),
        settings=settings,
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    enriched = apply_effective_finalist_country_mode(
        _df().loc[lambda frame: frame["source_type"].eq("jira")],
        discrepancies=discrepancies,
        reference_window=pd.Timestamp("2026-05-10"),
    )

    assert discrepancies["jira_key"].tolist() == ["MEX-1"]
    assert pd.to_datetime(enriched.loc[enriched["key"].eq("MEX-1"), "resolved"]).notna().all()
    assert pd.to_datetime(enriched.loc[enriched["key"].eq("MEX-2"), "resolved"]).isna().all()
