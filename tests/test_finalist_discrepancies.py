from __future__ import annotations

import numpy as np
import pandas as pd

from bug_resolution_radar.analytics.finalist_discrepancies import (
    POST_JQL_LOOKUP_HELIX_KIND,
    apply_effective_finalist_lookup_state,
    apply_effective_finalist_lookup_state_for_scope,
    build_finalist_status_discrepancies,
    build_jira_helix_links,
    extract_helix_ids_from_text,
    split_root_cause_evolutive_discrepancies,
)
from bug_resolution_radar.analytics.finalist_discrepancy_lists import (
    build_finalist_discrepancy_issue_list,
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
                "po_team_leader": "Víctor Expósito",
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
                "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                "source_alias": "Lookup estados finalistas Jira",
                "helix_lookup_kind": POST_JQL_LOOKUP_HELIX_KIND,
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
                "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                "source_alias": "Lookup estados finalistas Jira",
                "helix_lookup_kind": POST_JQL_LOOKUP_HELIX_KIND,
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
        source_ids=["jira:mexico:senda"],
    )

    assert links["jira_key"].tolist() == ["MEX-1", "MEX-2"]
    assert set(links["helix_id"].tolist()) == {"INC000104154954", "INC000104154955"}
    assert set(links["country"].tolist()) == {"México"}


def test_build_jira_helix_links_reads_helix_id_from_jira_summary() -> None:
    df = pd.DataFrame(
        [
            {
                "country": "México",
                "source_type": "jira",
                "source_id": "jira:mexico:senda",
                "source_alias": "Senda",
                "key": "EAM-93998",
                "summary": "[Incidentes] - INC000104154954 - Causa raíz",
                "description": "Plantilla de seguimiento sin ID Helix.",
                "status": "To Rework",
            },
            {
                "country": "México",
                "source_type": "helix",
                "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                "source_alias": "Lookup estados finalistas Jira",
                "helix_lookup_kind": POST_JQL_LOOKUP_HELIX_KIND,
                "key": "INC000104154954",
                "summary": "Helix cerrado",
                "description": "Detalle",
                "status": "Closed",
            },
        ]
    )

    links = build_jira_helix_links(
        df,
        country="México",
        source_ids=["jira:mexico:senda"],
    )

    assert links[["helix_id", "jira_key"]].to_dict("records") == [
        {"helix_id": "INC000104154954", "jira_key": "EAM-93998"}
    ]


def test_discrepancy_when_helix_finalist_and_jira_open() -> None:
    out = build_finalist_status_discrepancies(
        _df(),
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    assert out["jira_key"].tolist() == ["MEX-1"]
    assert out.iloc[0]["helix_id"] == "INC000104154954"
    assert out.iloc[0]["po_team_leader"] == "Víctor Expósito"
    assert bool(out.iloc[0]["helix_status_is_finalist"]) is True
    assert bool(out.iloc[0]["jira_status_is_finalist"]) is False


def test_root_cause_evolutive_split_uses_configured_country_labels() -> None:
    df = _df()
    df["labels"] = [tuple() for _ in range(len(df))]
    df.at[0, "labels"] = ["CAUSA_RAIZ", "otro"]
    discrepancies = build_finalist_status_discrepancies(
        df,
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    root_cause, remaining = split_root_cause_evolutive_discrepancies(
        discrepancies,
        settings=Settings(
            JIRA_ROOT_CAUSE_LABELS_BY_COUNTRY_JSON=(
                '[{"country":"México","labels":["causa_raiz"]}]'
            )
        ),
        country="México",
    )

    assert root_cause["jira_key"].tolist() == ["MEX-1"]
    assert root_cause.iloc[0]["root_cause_matched_labels"] == ("CAUSA_RAIZ",)
    assert remaining.empty


def test_root_cause_evolutive_split_handles_parquet_array_labels() -> None:
    df = _df()
    df["labels"] = [np.array([], dtype=object) for _ in range(len(df))]
    df.at[0, "labels"] = np.array(["#ENTERPRISEWEB_Incidentes", "SOLUCION_RAIZ"], dtype=object)
    discrepancies = build_finalist_status_discrepancies(
        df,
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    root_cause, remaining = split_root_cause_evolutive_discrepancies(
        discrepancies,
        settings=Settings(
            JIRA_ROOT_CAUSE_LABELS_BY_COUNTRY_JSON=(
                '[{"country":"México","labels":["SOLUCION_RAIZ"]}]'
            )
        ),
        country="México",
    )

    assert root_cause["jira_key"].tolist() == ["MEX-1"]
    assert root_cause.iloc[0]["root_cause_matched_labels"] == ("SOLUCION_RAIZ",)
    assert remaining.empty


def test_no_discrepancy_when_both_finalists() -> None:
    out = build_finalist_status_discrepancies(
        _df().loc[lambda frame: frame["key"].isin(["MEX-2", "INC000104154955"])],
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    assert out.empty


def test_no_discrepancy_when_helix_finalized_outside_window() -> None:
    out = build_finalist_status_discrepancies(
        _df(),
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-02"),
    )

    assert out.empty


def test_lookup_finalist_state_uses_ad_hoc_helix_and_closes_jira_effectively() -> None:
    settings = Settings()
    discrepancies = build_finalist_status_discrepancies(
        _df(),
        settings=settings,
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    enriched = apply_effective_finalist_lookup_state(
        _df().loc[lambda frame: frame["source_type"].eq("jira")],
        discrepancies=discrepancies,
        reference_window=pd.Timestamp("2026-05-10"),
    )

    assert discrepancies["jira_key"].tolist() == ["MEX-1"]
    assert pd.to_datetime(enriched.loc[enriched["key"].eq("MEX-1"), "resolved"]).notna().all()
    assert pd.to_datetime(enriched.loc[enriched["key"].eq("MEX-2"), "resolved"]).isna().all()


def test_effective_finalist_scope_uses_historical_helix_outside_visible_window() -> None:
    visible = pd.DataFrame(
        [
            {
                "country": "México",
                "source_type": "jira",
                "source_id": "jira:mexico:senda",
                "key": "MEX-OLD-HELIX",
                "summary": "INC000102885426 seguimiento pendiente",
                "description": "",
                "status": "En progreso",
                "created": "2026-05-01T00:00:00Z",
                "updated": "2026-05-20T00:00:00Z",
                "resolved": None,
            }
        ]
    )
    history = pd.concat(
        [
            visible,
            pd.DataFrame(
                [
                    {
                        "country": "México",
                        "source_type": "helix",
                        "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                        "source_alias": "Lookup estados finalistas Jira",
                        "helix_lookup_kind": POST_JQL_LOOKUP_HELIX_KIND,
                        "key": "INC000102885426",
                        "summary": "BBVA Net Cash",
                        "description": "",
                        "status": "Closed",
                        "created": "2025-03-19T00:00:00Z",
                        "updated": "2025-04-25T23:08:13Z",
                        "resolved": "2025-04-25T23:08:09Z",
                        "url": "https://helix.example/incident/IDG102885426",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    enriched, discrepancies = apply_effective_finalist_lookup_state_for_scope(
        visible,
        history_df=history,
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-24"),
    )

    assert discrepancies["jira_key"].tolist() == ["MEX-OLD-HELIX"]
    assert pd.to_datetime(enriched["resolved"], errors="coerce").notna().all()
    assert enriched["__effective_helix_id"].tolist() == ["INC000102885426"]


def test_finalist_status_uses_only_ad_hoc_helix_even_when_configured_exists() -> None:
    df = pd.concat(
        [
            _df().loc[lambda frame: frame["key"].isin(["MEX-1", "INC000104154954"])],
            pd.DataFrame(
                [
                    {
                        "country": "México",
                        "source_type": "helix",
                        "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                        "source_alias": "Lookup estados finalistas Jira",
                        "helix_lookup_kind": POST_JQL_LOOKUP_HELIX_KIND,
                        "key": "INC000104154954",
                        "summary": "Helix ad hoc",
                        "description": "Lookup ad hoc",
                        "status": "Resolved",
                        "updated": "2026-05-04T00:00:00Z",
                        "resolved": "2026-05-04T00:00:00Z",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    out = build_finalist_status_discrepancies(
        df,
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-10"),
    )

    assert out["helix_source_id"].tolist() == ["helix:mexico:lookup-estados-finalistas-jira"]


def test_helix_id_maps_to_multiple_jira_and_dedupes_by_jira_key() -> None:
    df = pd.DataFrame(
        [
            {
                "country": "México",
                "source_type": "jira",
                "source_id": "jira:mexico:senda",
                "source_alias": "Senda",
                "key": "EAM-94000",
                "summary": "Jira A",
                "description": "Cruce con INC000104154954",
                "status": "To Rework",
                "priority": "High",
                "assignee": "Ana",
                "created": "2026-05-01T00:00:00Z",
                "updated": "2026-05-10T00:00:00Z",
                "resolved": pd.NaT,
                "url": "https://jira.example.com/browse/EAM-94000",
            },
            {
                "country": "México",
                "source_type": "jira",
                "source_id": "jira:mexico:senda",
                "source_alias": "Senda",
                "key": "EAM-93998",
                "summary": "[Incidentes] - INC000104154954 - Jira B",
                "description": "Plantilla de seguimiento sin ID Helix.",
                "status": "To Rework",
                "priority": "High",
                "assignee": "Bea",
                "created": "2026-04-25T00:00:00Z",
                "updated": "2026-05-10T00:00:00Z",
                "resolved": pd.NaT,
                "url": "https://jira.example.com/browse/EAM-93998",
            },
            {
                "country": "México",
                "source_type": "jira",
                "source_id": "jira:mexico:senda",
                "source_alias": "Senda",
                "key": "EAM-93998",
                "summary": "[Incidentes] - INC000104154954 - Jira B duplicada",
                "description": "Plantilla duplicada sin ID Helix.",
                "status": "To Rework",
                "priority": "High",
                "assignee": "Bea",
                "created": "2026-04-25T00:00:00Z",
                "updated": "2026-05-10T00:00:00Z",
                "resolved": pd.NaT,
                "url": "https://jira.example.com/browse/EAM-93998",
            },
            {
                "country": "México",
                "source_type": "jira",
                "source_id": "jira:mexico:senda",
                "source_alias": "Senda",
                "key": "EAM-1",
                "summary": "Jira single",
                "description": "Cruce con INC000104154955",
                "status": "Open",
                "priority": "Medium",
                "assignee": "Cris",
                "created": "2026-05-05T00:00:00Z",
                "updated": "2026-05-10T00:00:00Z",
                "resolved": pd.NaT,
                "url": "https://jira.example.com/browse/EAM-1",
            },
            {
                "country": "México",
                "source_type": "helix",
                "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                "source_alias": "Lookup estados finalistas Jira",
                "helix_lookup_kind": POST_JQL_LOOKUP_HELIX_KIND,
                "key": "INC000104154954",
                "summary": "Helix multi",
                "description": "Cliente INC000104154954 cerrado",
                "status": "Closed",
                "updated": "2026-05-03T00:00:00Z",
                "resolved": "2026-05-03T00:00:00Z",
                "url": "https://helix.example.com/INC000104154954",
            },
            {
                "country": "México",
                "source_type": "helix",
                "source_id": "helix:mexico:lookup-estados-finalistas-jira",
                "source_alias": "Lookup estados finalistas Jira",
                "helix_lookup_kind": POST_JQL_LOOKUP_HELIX_KIND,
                "key": "INC000104154955",
                "summary": "Helix single",
                "description": "",
                "status": "Closed",
                "updated": "2026-05-03T00:00:00Z",
                "resolved": "2026-05-03T00:00:00Z",
                "url": "https://helix.example.com/INC000104154955",
            },
        ]
    )

    links = build_jira_helix_links(
        df,
        country="México",
        source_ids=["jira:mexico:senda"],
    )
    grouped = {
        helix_id: sorted(bucket["jira_key"].tolist())
        for helix_id, bucket in links.groupby("helix_id")
    }
    assert grouped["INC000104154954"] == ["EAM-93998", "EAM-94000"]
    assert grouped["INC000104154955"] == ["EAM-1"]

    out = build_finalist_status_discrepancies(
        df,
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:senda"],
        reference_day=pd.Timestamp("2026-05-21"),
    )
    assert out["jira_key"].tolist() == ["EAM-93998", "EAM-94000", "EAM-1"]


def test_finalist_discrepancy_rows_expose_helix_text_or_explicit_fallback() -> None:
    rows = build_finalist_discrepancy_issue_list(
        pd.DataFrame(
            [
                {
                    "helix_id": "INC000104154954",
                    "helix_summary": "Título Helix",
                    "helix_description": "Detalle Helix INC000104154954",
                    "helix_status": "Closed",
                    "jira_key": "EAM-94000",
                    "jira_summary": "Jira",
                    "jira_status": "To Rework",
                    "jira_priority": "High",
                    "jira_open_days": 2,
                },
                {
                    "helix_id": "INC000104154955",
                    "helix_summary": "",
                    "helix_description": "",
                    "helix_status": "Closed",
                    "jira_key": "EAM-1",
                    "jira_summary": "Jira",
                    "jira_status": "Open",
                    "jira_priority": "Medium",
                    "jira_open_days": 1,
                },
            ]
        )
    )

    by_helix = {row.helix_id: row.helix_text for row in rows}
    assert by_helix["INC000104154954"] == "Título Helix\nDetalle Helix INC000104154954"
    assert by_helix["INC000104154955"] == "Sin descripción Helix"
