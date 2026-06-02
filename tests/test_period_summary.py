from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from bug_resolution_radar.analytics.period_summary import (
    build_country_quincenal_result,
    build_quincenal_delta,
)
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


def test_quincenal_delta_display_rules_avoid_extreme_percentages() -> None:
    zero_reference = build_quincenal_delta(
        metric_key="created",
        current_value=4,
        previous_value=0,
        value_kind="count",
    )
    assert zero_reference.current_value == 4.0
    assert zero_reference.previous_value == 0.0
    assert zero_reference.absolute_delta == 4.0
    assert zero_reference.relative_delta is None
    assert zero_reference.display_kind == "absolute"
    assert zero_reference.display_text == "Δ +4 vs quincena previa"
    assert "%" not in zero_reference.display_text

    small_reference = build_quincenal_delta(
        metric_key="created",
        current_value=15,
        previous_value=1,
        value_kind="count",
    )
    assert small_reference.relative_delta == 14.0
    assert small_reference.display_kind == "absolute"
    assert small_reference.display_text == "Δ +14 vs quincena previa"
    assert small_reference.badge_text == "+14"
    assert "1400" not in small_reference.display_text

    neutral = build_quincenal_delta(
        metric_key="closed",
        current_value=0,
        previous_value=0,
        value_kind="count",
    )
    assert neutral.display_kind == "neutral"
    assert neutral.direction == "neutral"
    assert neutral.semantic_tone == "neutral"
    assert neutral.display_text == "Sin cambios vs quincena previa"

    percent_allowed = build_quincenal_delta(
        metric_key="closed",
        current_value=6,
        previous_value=4,
        value_kind="count",
    )
    assert percent_allowed.relative_delta == 0.5
    assert percent_allowed.display_kind == "percent"
    assert percent_allowed.display_text == "Δ +50.0% vs quincena previa"
    assert percent_allowed.semantic_tone == "flow"

    tiny_resolution_reference = build_quincenal_delta(
        metric_key="resolution_days",
        current_value=2.955,
        previous_value=0.020,
        value_kind="days",
        current_sample_size=3,
        previous_sample_size=3,
    )
    assert round(float(tiny_resolution_reference.relative_delta or 0.0) * 100.0, 0) == 14675
    assert tiny_resolution_reference.display_kind == "absolute"
    assert tiny_resolution_reference.display_text == "Δ +2.9 días vs quincena previa"
    assert "1467" not in tiny_resolution_reference.display_text
    assert "%" not in tiny_resolution_reference.badge_text

    null_resolution = build_quincenal_delta(
        metric_key="resolution_days",
        current_value=None,
        previous_value=None,
        value_kind="days",
    )
    assert null_resolution.display_kind == "no_reference"
    assert null_resolution.badge_text == "—"


def test_build_country_quincenal_result_computes_aggregate_and_maestras(tmp_path: Path) -> None:
    helix_dump = tmp_path / "helix_dump.json"
    _write_helix_dump(helix_dump)
    settings = Settings(
        HELIX_DATA_PATH=str(helix_dump),
        OPEN_ISSUES_FOCUS_MODE="maestras",
    )

    now = pd.Timestamp("2026-03-12T00:00:00+00:00")
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
    assert summary.open_focus_total == 1
    assert summary.open_other_total == 3
    assert summary.maestras_total == 1
    assert summary.others_total == 3
    assert summary.open_focus_label == "Maestras abiertas"
    assert summary.new_now == 2
    assert summary.new_before == 3
    assert summary.closed_now == 1
    assert summary.new_accumulated == 5
    assert summary.resolution_days_now is not None
    assert int(round(summary.resolution_days_now)) == 19
    assert summary.resolution_days_min_now is not None
    assert summary.resolution_days_max_now is not None
    assert int(round(summary.resolution_days_min_now)) == 19
    assert int(round(summary.resolution_days_max_now)) == 19
    assert set(result.by_source.keys()) == {"helix:mexico:senda", "helix:mexico:gema"}


def test_build_country_quincenal_result_exposes_safe_delta_objects() -> None:
    reference_day = pd.Timestamp("2026-03-20T00:00:00+00:00")
    rows: list[dict[str, object]] = [
        {
            "key": "PREV-1",
            "summary": "Referencia mínima",
            "status": "Resolved",
            "priority": "High",
            "created": "2026-03-02T00:00:00+00:00",
            "updated": "2026-03-02T00:30:00+00:00",
            "resolved": "2026-03-02T00:30:00+00:00",
            "country": "México",
            "source_id": "jira:mexico:core",
            "source_type": "jira",
        }
    ]
    for idx in range(15):
        created_day = 15 + (idx % 6)
        row: dict[str, object] = {
            "key": f"CUR-{idx + 1}",
            "summary": "Actual",
            "status": "New",
            "priority": "Medium",
            "created": f"2026-03-{created_day:02d}T00:00:00+00:00",
            "updated": f"2026-03-{created_day:02d}T00:00:00+00:00",
            "resolved": None,
            "country": "México",
            "source_id": "jira:mexico:core",
            "source_type": "jira",
        }
        if idx < 2:
            row["status"] = "Resolved"
            row["created"] = f"2026-03-{15 + idx:02d}T00:00:00+00:00"
            row["resolved"] = f"2026-03-{18 + idx:02d}T00:00:00+00:00"
        rows.append(row)

    result = build_country_quincenal_result(
        df=pd.DataFrame(rows),
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:core"],
        reference_day=reference_day,
    )

    summary = result.aggregate.summary
    assert summary.new_now == 15
    assert summary.new_before == 1
    assert summary.new_delta.current_value == 15.0
    assert summary.new_delta.previous_value == 1.0
    assert summary.new_delta.absolute_delta == 14.0
    assert summary.new_delta.relative_delta == 14.0
    assert summary.new_delta.display_kind == "absolute"
    assert summary.new_delta.display_text == "Δ +14 vs quincena previa"
    assert summary.new_delta_pct is None

    assert summary.closed_delta.display_kind == "absolute"
    assert summary.closed_delta.semantic_tone == "flow"
    assert summary.resolution_delta.current_sample_size == 2
    assert summary.resolution_delta.previous_sample_size == 1
    assert summary.resolution_delta.display_kind == "absolute"
    assert "%" not in summary.resolution_delta.display_text
    assert summary.resolution_delta_pct is None


def test_build_country_quincenal_result_defaults_to_high_criticality_focus() -> None:
    now = pd.Timestamp("2026-03-15T00:00:00+00:00")
    settings = Settings()
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Alta 1",
                "status": "New",
                "priority": "High",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
            {
                "key": "A-2",
                "summary": "Alta 2",
                "status": "In Progress",
                "priority": "Highest",
                "created": (now - pd.Timedelta(days=3)).isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
            {
                "key": "A-3",
                "summary": "Media",
                "status": "New",
                "priority": "Medium",
                "created": (now - pd.Timedelta(days=4)).isoformat(),
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
        reference_day=now,
    )

    summary = result.aggregate.summary
    assert summary.open_group_mode == "criticidad_alta"
    assert summary.open_focus_label == "Incidencias con criticidad alta"
    assert summary.open_other_label == "Otras incidencias"
    assert summary.open_focus_total == 2
    assert summary.open_other_total == 1


def test_build_country_quincenal_result_uses_current_partial_fortnight_by_default() -> None:
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
    assert window.current_start == date(2026, 3, 15)
    assert window.current_end == date(2026, 3, 26)
    assert window.previous_start == date(2026, 3, 1)
    assert window.previous_end == date(2026, 3, 14)
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
                "key": "A-4",
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
    assert window.current_start == date(2026, 3, 1)
    assert window.current_end == date(2026, 3, 14)
    assert window.previous_start == date(2026, 2, 15)
    assert window.previous_end == date(2026, 2, 28)
    assert result.aggregate.summary.new_now == 1
    assert result.aggregate.summary.new_before == 1


def test_build_country_quincenal_result_defaults_reference_day_to_service_today(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(
        "bug_resolution_radar.analytics.period_summary.TimeWindowService.today",
        lambda self: pd.Timestamp("2026-03-12"),
    )
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
                "status": "Resolved",
                "created": "2026-03-10T00:00:00+00:00",
                "updated": "2026-03-10T00:00:00+00:00",
                "resolved": "2026-03-18T00:00:00+00:00",
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
    )

    window = result.aggregate.summary.window
    assert window.current_start == date(2026, 3, 1)
    assert window.current_end == date(2026, 3, 12)


def test_build_country_quincenal_result_orders_open_focus_by_priority_then_status() -> None:
    now = pd.Timestamp("2026-03-15T00:00:00+00:00")
    settings = Settings()
    df = pd.DataFrame(
        [
            {
                "key": "K-NEW",
                "summary": "Caso nuevo",
                "status": "New",
                "priority": "High",
                "created": "2026-03-10T00:00:00+00:00",
                "updated": "2026-03-14T00:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
            {
                "key": "K-ANA",
                "summary": "Caso en analisis",
                "status": "Analysing",
                "priority": "High",
                "created": "2026-03-10T00:00:00+00:00",
                "updated": "2026-03-14T00:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:core",
                "source_type": "jira",
            },
            {
                "key": "K-RTV",
                "summary": "Caso listo para verificar",
                "status": "Ready To Verify",
                "priority": "High",
                "created": "2026-03-10T00:00:00+00:00",
                "updated": "2026-03-14T00:00:00+00:00",
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
        source_label_by_id={"jira:mexico:core": "Core · JIRA"},
        reference_day=now,
    )

    open_focus = result.aggregate.groups.open_focus
    assert open_focus["key"].tolist() == ["K-RTV", "K-ANA", "K-NEW"]
