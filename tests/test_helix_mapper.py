from __future__ import annotations

import pytest

from bug_resolution_radar.ingest.helix_mapper import (
    is_allowed_helix_business_incident_type,
    map_helix_incident_type,
    map_helix_priority,
    map_helix_status,
    map_helix_values_to_item,
)
from bug_resolution_radar.models.schema_helix import HelixWorkItem
from bug_resolution_radar.ui.pages.ingest_page import _helix_item_to_issue


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("Asignado", "Analysing"),
        ("Asignado a proveedor", "Blocked"),
        ("Autorización de aplicación", "Blocked"),
        ("Autorización de cierre", "Blocked"),
        ("Autorización de construcción", "Blocked"),
        ("Autorización de inicio", "Blocked"),
        ("Autorización de planificación", "Blocked"),
        ("Autorización de prueba", "Blocked"),
        ("Bajo investigación", "Analysing"),
        ("Borrador", "New"),
        ("Cancelada", "Accepted"),
        ("Cancelado", "Accepted"),
        ("Cerrado", "Closed"),
        ("Corregido", "Ready To Verify"),
        ("En cesta", "New"),
        ("En curso", "En progreso"),
        ("En Implantación", "Ready to Deploy"),
        ("En revisión", "Ready To Verify"),
        ("Enviado", "New"),
        ("Esperando (automáticas)", "Blocked"),
        ("Esperando autorización", "Blocked"),
        ("Ninguna acción planificada", "Accepted"),
        ("Nuevo", "New"),
        ("Pendiente", "Analysing"),
        ("Petición de autorización", "Blocked"),
        ("Petición de Cambio", "Analysing"),
        ("Planificación", "Analysing"),
        ("Planificación en curso", "Analysing"),
        ("Planificado para corrección", "En progreso"),
        ("Por fases", "En progreso"),
        ("Programado", "Analysing"),
        ("Pte. Autorización", "Blocked"),
        ("Rechazado", "Accepted"),
        ("Registrado", "New"),
        ("Resuelto", "Resolved"),
        ("Revisión", "Ready To Verify"),
        ("Terminado", "Closed"),
        ("Assigned", "Analysing"),
        ("Resolved", "Resolved"),
        ("Closed", "Closed"),
    ],
)
def test_map_helix_status_uses_requested_workflow_mapping(raw_status: str, expected: str) -> None:
    assert map_helix_status(raw_status) == expected


def test_map_helix_status_uses_generic_closed_and_open_fallbacks() -> None:
    assert map_helix_status("Closed by automation") == "Closed"
    assert map_helix_status("Open in queue") == "New"
    assert map_helix_status("Estado no mapeado") == "New"


@pytest.mark.parametrize(
    ("raw_priority", "expected"),
    [
        ("Very High", "Highest"),
        ("High", "High"),
        ("Moderate", "Medium"),
        ("Medium", "Medium"),
        ("Low", "Low"),
        ("Unknown", "Unknown"),
    ],
)
def test_map_helix_priority_matches_jira_equivalents(raw_priority: str, expected: str) -> None:
    assert map_helix_priority(raw_priority) == expected


def test_map_helix_values_to_item_keeps_query_fields_and_raw_status() -> None:
    item = map_helix_values_to_item(
        values={
            "id": "INC0001",
            "summary": "Issue de prueba",
            "status": {"value": "Assigned"},
            "priority": "Moderate",
            "incidentType": "Security Incident",
            "service": {"name": "Payments"},
            "impactedService": {"name": "SENDA GLOBAL (FRONTALES GLOBALES EMPRESAS)"},
            "assignee": {"fullName": "Ana"},
            "customer": {"company": {"name": "BBVA México"}},
            "slaStatus": "atRisk",
            "customFields": {
                "bbva_startdatetime": 1704067200000,
                "bbva_closeddate": 1704153600000,
                "bbva_matrixservicen1": "Matriz N1",
                "bbva_sourceservicen1": "Source N1",
            },
            "EmptyField": "",
            "NoneField": None,
        },
        base_url="https://itsmhelixbbva-smartit.onbmc.com/smartit",
        country="México",
        source_alias="MX SmartIT",
        source_id="helix:mexico:mx-smartit",
    )

    assert item is not None
    assert item.id == "INC0001"
    assert item.summary == "Issue de prueba"
    assert item.status == "Analysing"
    assert item.status_raw == "Assigned"
    assert item.priority == "Medium"
    assert item.incident_type == "Incidencia"
    assert item.service == "Payments"
    assert item.impacted_service == "SENDA GLOBAL (FRONTALES GLOBALES EMPRESAS)"
    assert item.assignee == "Ana"
    assert item.customer_name == "BBVA México"
    assert item.sla_status == ""
    assert item.start_datetime == "2024-01-01T00:00:00+00:00"
    assert item.closed_date == "2024-01-02T00:00:00+00:00"
    assert item.matrix_service_n1 == "Matriz N1"
    assert item.source_service_n1 == "Source N1"
    assert item.url == "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console"
    assert item.raw_fields.get("id") == "INC0001"
    assert item.raw_fields.get("priority") == "Moderate"
    assert "EmptyField" not in item.raw_fields
    assert "NoneField" not in item.raw_fields


def test_map_helix_values_to_item_reads_custom_attributes_container() -> None:
    item = map_helix_values_to_item(
        values={
            "id": "INC0002",
            "status": "Nuevo",
            "customAttributes": {
                "bbva_startdatetime": "2026-02-02T00:00:00Z",
                "bbva_closeddate": "2026-02-20T00:00:00Z",
                "bbva_matrixservicen1": "Core",
                "bbva_sourceservicen1": "Legacy",
            },
        },
        base_url="https://itsmhelixbbva-smartit.onbmc.com/smartit",
        country="México",
        source_alias="MX SmartIT",
        source_id="helix:mexico:mx-smartit",
    )

    assert item is not None
    assert item.start_datetime == "2026-02-02T00:00:00Z"
    assert item.closed_date == "2026-02-20T00:00:00Z"
    assert item.matrix_service_n1 == "Core"
    assert item.source_service_n1 == "Legacy"


def test_map_helix_values_to_item_reads_arsql_flat_fields_case_insensitive() -> None:
    item = map_helix_values_to_item(
        values={
            "id": "INC0003",
            "status": "Resolved",
            "BBVA_SourceServiceN1": "ENTERPRISE WEB",
            "BBVA_MatrixServiceN1": "MATRIX",
            "BBVA_ClosedDate": 1704153600000,
        },
        base_url="https://itsmhelixbbva-smartit.onbmc.com/smartit",
        country="México",
        source_alias="MX SmartIT",
        source_id="helix:mexico:mx-smartit",
    )

    assert item is not None
    assert item.source_service_n1 == "ENTERPRISE WEB"
    assert item.matrix_service_n1 == "MATRIX"
    assert item.closed_date == "2024-01-02T00:00:00+00:00"


def test_map_helix_incident_type_prefers_business_field_and_keeps_consulta() -> None:
    values = {
        "incidentType": "Incident",
        "BBVA_Tipo_de_Incidencia": "Consulta",
    }
    assert map_helix_incident_type("Incident", values) == "Consulta"
    assert is_allowed_helix_business_incident_type("Consulta") is True
    assert is_allowed_helix_business_incident_type("Incidencia") is True
    assert is_allowed_helix_business_incident_type("Evento Monitorización") is True
    assert is_allowed_helix_business_incident_type("Request") is False


def test_map_helix_incident_type_maps_monitoring_event() -> None:
    values = {"Tipo de Incidencia": "Evento Monitorización"}
    assert map_helix_incident_type("Incident", values) == "Evento Monitorización"


def test_map_helix_values_to_item_uses_configured_dashboard_url() -> None:
    item = map_helix_values_to_item(
        values={"id": "INC9999", "status": "Open"},
        base_url="https://itsmhelixbbva-smartit.onbmc.com/smartit",
        country="México",
        source_alias="MX SmartIT",
        source_id="helix:mexico:mx-smartit",
        ticket_console_url="https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console",
    )

    assert item is not None
    assert item.url == "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console"


def test_helix_item_to_issue_maps_labels_and_components_as_requested() -> None:
    issue = _helix_item_to_issue(
        HelixWorkItem(
            id="INC0009",
            summary="test",
            status="Analysing",
            priority="Medium",
            incident_type="User Service Restoration",
            impacted_service="SENDA GLOBAL (FRONTALES GLOBALES EMPRESAS)",
            matrix_service_n1="ENTERPRISE WEB",
            source_service_n1="ENTERPRISE WEB",
            start_datetime="2024-01-01T00:00:00+00:00",
            closed_date=None,
        )
    )

    assert issue.type == "User Service Restoration"
    assert issue.labels == ["ENTERPRISE WEB ENTERPRISE WEB"]
    assert issue.components == ["SENDA GLOBAL (FRONTALES GLOBALES EMPRESAS)"]
