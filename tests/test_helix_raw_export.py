from __future__ import annotations

import pandas as pd

from bug_resolution_radar.models.schema_helix import HelixWorkItem
from bug_resolution_radar.services.helix_raw_export import (
    build_helix_raw_export_frame,
)


def test_build_helix_raw_export_frame_returns_none_for_mixed_scope() -> None:
    df = pd.DataFrame(
        [
            {"key": "INC-1", "source_type": "helix", "source_id": "helix:mx:web"},
            {"key": "JIRA-1", "source_type": "jira", "source_id": "jira:mx:web"},
        ]
    )

    out = build_helix_raw_export_frame(df, helix_items_by_merge_key={})

    assert out is None


def test_build_helix_raw_export_frame_builds_raw_rows_and_front_columns() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "INC-1",
                "source_type": "helix",
                "source_id": "helix:mx:web",
                "url": "https://smartit/inc-1",
            }
        ]
    )
    item = HelixWorkItem(
        id="INC-1",
        source_id="helix:mx:web",
        url="https://smartit/inc-1",
        raw_fields={
            "Status": "Open",
            "Submit Date": "2026-02-25T10:44:24+00:00",
            "Nested": {"a": 1},
        },
    )

    out = build_helix_raw_export_frame(
        df,
        helix_items_by_merge_key={"helix:mx:web::INC-1": item},
    )

    assert isinstance(out, pd.DataFrame)
    assert list(out.columns[:7]) == [
        "ID de la Incidencia",
        "id",
        "priority",
        "summary",
        "status",
        "assignee",
        "incidentType",
    ]
    assert out.loc[0, "ID de la Incidencia"] == "INC-1"
    assert out.loc[0, "id"] == "INC-1"
    assert out.loc[0, "__item_url__"] == "https://smartit/inc-1"
    assert out.loc[0, "Status"] == "Open"
    assert out.loc[0, "Nested"] == '{"a": 1}'


def test_build_helix_raw_export_frame_prefers_historical_helix_front_fields() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "INC-9",
                "source_type": "helix",
                "source_id": "helix:mx:web",
                "url": "https://smartit/inc-9",
            }
        ]
    )
    item = HelixWorkItem(
        id="INC-9",
        source_id="helix:mx:web",
        url="https://smartit/inc-9",
        summary="Caida Payments",
        status="Closed",
        priority="High",
        assignee="Alice",
        incident_type="Consultation",
        service="Payments",
        customer_name="BBVA CCR",
        matrix_service_n1="Matrix N1",
        source_service_n1="Source N1",
        start_datetime="2026-04-17T08:00:00+00:00",
        closed_date="2026-04-17T09:00:00+00:00",
        last_modified="2026-04-17T09:10:00+00:00",
        target_date="2026-04-18T00:00:00+00:00",
        raw_fields={
            "Status": "Closed",
            "InstanceId": "WI-123",
            "Short Description": "Caida Payments",
        },
    )

    out = build_helix_raw_export_frame(
        df,
        helix_items_by_merge_key={"helix:mx:web::INC-9": item},
    )

    assert isinstance(out, pd.DataFrame)
    assert out.loc[0, "id"] == "INC-9"
    assert out.loc[0, "priority"] == "High"
    assert out.loc[0, "summary"] == "Caida Payments"
    assert out.loc[0, "status"] == "Closed"
    assert out.loc[0, "assignee"] == "Alice"
    assert out.loc[0, "incidentType"] == "Consultation"
    assert out.loc[0, "service"] == "Payments"
    assert out.loc[0, "customerName"] == "BBVA CCR"
    assert out.loc[0, "bbva_matrixservicen1"] == "Matrix N1"
    assert out.loc[0, "bbva_sourceservicen1"] == "Source N1"
    assert out.loc[0, "bbva_startdatetime"] == "2026-04-17T08:00:00+00:00"
    assert out.loc[0, "bbva_closeddate"] == "2026-04-17T09:00:00+00:00"
    assert out.loc[0, "lastModifiedDate"] == "2026-04-17T09:10:00+00:00"
    assert out.loc[0, "targetDate"] == "2026-04-18T00:00:00+00:00"
    assert out.loc[0, "workItemId"] == "WI-123"
    assert out.loc[0, "Status"] == "Closed"
    assert out.loc[0, "Short Description"] == "Caida Payments"


def test_build_helix_raw_export_frame_keeps_row_when_raw_fields_are_empty() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "INC-2",
                "source_type": "helix",
                "source_id": "helix:mx:web",
                "url": "https://smartit/inc-2",
            }
        ]
    )
    item = HelixWorkItem(
        id="INC-2",
        source_id="helix:mx:web",
        url="https://smartit/inc-2",
        raw_fields={},
    )

    out = build_helix_raw_export_frame(
        df,
        helix_items_by_merge_key={"helix:mx:web::INC-2": item},
    )

    assert isinstance(out, pd.DataFrame)
    assert len(out) == 1
    assert out.loc[0, "ID de la Incidencia"] == "INC-2"
