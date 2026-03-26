from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bug_resolution_radar.analytics.period_summary import build_country_quincenal_result
from bug_resolution_radar.config import Settings


def _write_helix_dump(path: Path) -> None:
    payload = {
        "schema_version": "1.0",
        "ingested_at": "2026-03-15T00:00:00+00:00",
        "helix_base_url": "",
        "query": "",
        "items": [
            {
                "id": "B-1",
                "summary": "Incidencia maestra",
                "status": "New",
                "status_raw": "New",
                "priority": "High",
                "incident_type": "Incidencia",
                "service": "",
                "impacted_service": "",
                "assignee": "",
                "customer_name": "",
                "sla_status": "",
                "target_date": None,
                "last_modified": "2026-03-15T00:00:00+00:00",
                "start_datetime": "2026-03-10T00:00:00+00:00",
                "closed_date": None,
                "matrix_service_n1": "",
                "source_service_n1": "",
                "url": "",
                "country": "México",
                "source_alias": "Senda",
                "source_id": "helix:mexico:senda",
                "raw_fields": {"BBVA_SEL_GIM_Maestra": "Si"},
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_country_quincenal_result_computes_aggregate_and_maestras(tmp_path: Path) -> None:
    helix_dump = tmp_path / "helix_dump.json"
    _write_helix_dump(helix_dump)
    settings = Settings(HELIX_DATA_PATH=str(helix_dump))

    now = pd.Timestamp("2026-03-15T00:00:00+00:00")
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Nueva A",
                "status": "New",
                "priority": "High",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "helix:mexico:senda",
                "source_type": "helix",
            },
            {
                "key": "A-2",
                "summary": "Cerrada A",
                "status": "Resolved",
                "priority": "Medium",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=20)).isoformat(),
                "updated": now.isoformat(),
                "resolved": (now - pd.Timedelta(days=1)).isoformat(),
                "country": "México",
                "source_id": "helix:mexico:senda",
                "source_type": "helix",
            },
            {
                "key": "A-3",
                "summary": "Anterior A",
                "status": "New",
                "priority": "Low",
                "assignee": "Ana",
                "created": (now - pd.Timedelta(days=16)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "helix:mexico:senda",
                "source_type": "helix",
            },
            {
                "key": "B-1",
                "summary": "Nueva B maestra",
                "status": "New",
                "priority": "Highest",
                "assignee": "Luis",
                "created": (now - pd.Timedelta(days=5)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "helix:mexico:gema",
                "source_type": "helix",
            },
            {
                "key": "B-2",
                "summary": "Anterior B",
                "status": "New",
                "priority": "Low",
                "assignee": "Luis",
                "created": (now - pd.Timedelta(days=25)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "helix:mexico:gema",
                "source_type": "helix",
            },
        ]
    )

    result = build_country_quincenal_result(
        df=df,
        settings=settings,
        country="México",
        source_ids=["helix:mexico:senda", "helix:mexico:gema"],
        source_label_by_id={
            "helix:mexico:senda": "Senda · HELIX",
            "helix:mexico:gema": "Gema · HELIX",
        },
        reference_day=now,
    )

    summary = result.aggregate.summary
    assert summary.open_total == 4
    assert summary.maestras_total == 1
    assert summary.others_total == 3
    assert summary.new_now == 2
    assert summary.new_before == 3
    assert summary.closed_now == 1
    assert summary.new_accumulated == 2
    assert summary.resolution_days_now is not None
    assert int(round(summary.resolution_days_now)) == 19
    assert set(result.by_source.keys()) == {"helix:mexico:senda", "helix:mexico:gema"}


def test_build_country_quincenal_result_uses_natural_month_fortnight_by_default() -> None:
    ref_day = pd.Timestamp("2026-03-26T00:00:00+00:00")
    settings = Settings(
        QUINCENA_LAST_FINISHED_ONLY="false",
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
    )
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Segunda quincena mes actual",
                "status": "New",
                "created": "2026-03-20T00:00:00+00:00",
                "updated": "2026-03-20T00:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
            {
                "key": "A-2",
                "summary": "Primera quincena mes actual",
                "status": "New",
                "created": "2026-03-10T00:00:00+00:00",
                "updated": "2026-03-10T00:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
        ]
    )

    result = build_country_quincenal_result(
        df=df,
        settings=settings,
        country="México",
        source_ids=["jira:mexico:core"],
        reference_day=ref_day,
    )

    window = result.aggregate.summary.window
    assert window.current_start == pd.Timestamp("2026-03-16")
    assert window.current_end == pd.Timestamp("2026-03-31")
    assert window.previous_start == pd.Timestamp("2026-03-01")
    assert window.previous_end == pd.Timestamp("2026-03-15")
    assert result.aggregate.summary.new_now == 1
    assert result.aggregate.summary.new_before == 1


def test_build_country_quincenal_result_uses_last_finished_when_enabled() -> None:
    ref_day = pd.Timestamp("2026-03-26T00:00:00+00:00")
    settings = Settings(
        QUINCENA_LAST_FINISHED_ONLY="true",
        JIRA_SOURCES_JSON='[{"country":"México","alias":"Core","jql":"project = CORE"}]',
    )
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Primera quincena mes actual",
                "status": "New",
                "created": "2026-03-10T00:00:00+00:00",
                "updated": "2026-03-10T00:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
            {
                "key": "A-2",
                "summary": "Segunda quincena mes actual",
                "status": "New",
                "created": "2026-03-20T00:00:00+00:00",
                "updated": "2026-03-20T00:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
            {
                "key": "A-3",
                "summary": "Segunda quincena mes previo",
                "status": "New",
                "created": "2026-02-20T00:00:00+00:00",
                "updated": "2026-02-20T00:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
        ]
    )

    result = build_country_quincenal_result(
        df=df,
        settings=settings,
        country="México",
        source_ids=["jira:mexico:core"],
        reference_day=ref_day,
    )

    window = result.aggregate.summary.window
    assert window.current_start == pd.Timestamp("2026-03-01")
    assert window.current_end == pd.Timestamp("2026-03-15")
    assert window.previous_start == pd.Timestamp("2026-02-16")
    assert window.previous_end == pd.Timestamp("2026-02-28")
    assert result.aggregate.summary.new_now == 1
    assert result.aggregate.summary.new_before == 1
