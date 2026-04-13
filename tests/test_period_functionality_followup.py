from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.period_functionality_followup import (
    build_period_functionality_followup_summary,
)
from bug_resolution_radar.analytics.period_summary import (
    build_country_quincenal_result,
    source_label_map,
)
from bug_resolution_radar.config import Settings


def test_build_period_functionality_followup_summary_uses_centralized_metrics() -> None:
    settings = Settings()
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Login falla en acceso de usuario",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "url": "https://jira.example/A-1",
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-2",
                "summary": "Error de login en acceso biometrico",
                "status": "Ready To Verify",
                "priority": "Highest",
                "created": "2026-04-03T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "B-1",
                "summary": "TAREAS PENDIENTES - No se visualiza dashboard",
                "status": "New",
                "priority": "High",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "B-2",
                "summary": "TAREAS PENDIENTES - Timeout dashboard",
                "status": "New",
                "priority": "High",
                "created": "2026-03-20T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "C-1",
                "summary": "CRÉDITO - API no responde",
                "status": "Blocked",
                "priority": "High",
                "created": "2026-04-02T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "D-1",
                "summary": "Monetarias - ajuste de saldo",
                "status": "New",
                "priority": "Medium",
                "created": "2026-04-04T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    labels = source_label_map(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
    )
    quincenal = build_country_quincenal_result(
        df=dff,
        settings=settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        source_label_by_id=labels,
    )

    summary = build_period_functionality_followup_summary(
        scope_result=quincenal.aggregate,
        jira_base_url="https://jira.example",
        priority_filters=["High", "Highest", "Supone un impedimento"],
        top_n=3,
        top_root_causes=3,
    )

    assert summary.total_open_critical == 5
    assert summary.is_critical_focus
    assert len(summary.top_rows) == 3
    assert summary.top_rows[0].functionality == "Login y acceso"
    assert summary.top_rows[0].new_count == 2
    assert summary.top_rows[0].open_total == 2

    assert summary.mitigation_ready_to_verify.count == 1
    assert summary.mitigation_new.count == 3
    assert summary.mitigation_blocked.count == 1
    assert summary.mitigation_non_critical.count == 0

    assert len(summary.zoom_slides) == 3
    login_zoom = summary.zoom_slides[0]
    assert login_zoom.functionality == "Login y acceso"
    assert login_zoom.current_open_critical_count == 2
    assert login_zoom.issues
    assert login_zoom.issues[0].url.startswith("https://jira.example/")


def test_build_period_functionality_followup_summary_dedupes_zoom_issue_keys() -> None:
    settings = Settings()
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "INC original - descripcion antigua",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": "2026-04-08T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-1",
                "summary": "INC original - descripcion actualizada",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-2",
                "summary": "Pago rechazado por timeout",
                "status": "Analysing",
                "priority": "Medium",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    labels = source_label_map(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
    )
    quincenal = build_country_quincenal_result(
        df=dff,
        settings=settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        source_label_by_id=labels,
    )

    summary = build_period_functionality_followup_summary(
        scope_result=quincenal.aggregate,
        jira_base_url="https://jira.example",
        top_n=3,
        top_root_causes=3,
    )

    zoom_rows = [issue for zoom in summary.zoom_slides for issue in list(zoom.issues)]
    keys = [issue.key for issue in zoom_rows]
    assert len(keys) == len(set(keys))
    a1 = [issue for issue in zoom_rows if issue.key == "A-1"]
    assert len(a1) == 1
    assert a1[0].summary == "INC original - descripcion actualizada"


def test_build_period_functionality_followup_summary_infers_root_cause_from_description() -> None:
    settings = Settings()
    dff = pd.DataFrame(
        [
            {
                "key": "P-1",
                "summary": "Incidencia operativa sin detalle",
                "description": "Timeout intermitente y error 504 al consultar endpoint backend",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "P-2",
                "summary": "Pago rechazado CONVATEC",
                "description": "Validacion de reglas de negocio en backend de pagos",
                "status": "Analysing",
                "priority": "Medium",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    labels = source_label_map(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
    )
    quincenal = build_country_quincenal_result(
        df=dff,
        settings=settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        source_label_by_id=labels,
    )

    summary = build_period_functionality_followup_summary(
        scope_result=quincenal.aggregate,
        jira_base_url="https://jira.example",
        top_n=3,
        top_root_causes=3,
    )

    issues = [issue for zoom in summary.zoom_slides for issue in list(zoom.issues)]
    p1 = [issue for issue in issues if issue.key == "P-1"]
    assert len(p1) == 1
    assert p1[0].root_cause == "Conectividad / timeout"


def test_build_period_functionality_followup_summary_orders_zoom_rows_by_priority_then_status() -> (
    None
):
    settings = Settings()
    dff = pd.DataFrame(
        [
            {
                "key": "PAY-RTV",
                "summary": "PAGOS - caso listo para verificar",
                "status": "Ready To Verify",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "PAY-ANA",
                "summary": "PAGOS - caso en analisis",
                "status": "Analysing",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "PAY-NEW",
                "summary": "PAGOS - caso nuevo",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": "2026-04-10T09:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
        ]
    )
    labels = source_label_map(
        settings,
        country="México",
        source_ids=["jira:mexico:senda"],
    )
    quincenal = build_country_quincenal_result(
        df=dff,
        settings=settings,
        country="México",
        source_ids=["jira:mexico:senda"],
        source_label_by_id=labels,
    )

    summary = build_period_functionality_followup_summary(
        scope_result=quincenal.aggregate,
        jira_base_url="https://jira.example",
        top_n=1,
        top_root_causes=3,
    )

    assert len(summary.zoom_slides) == 1
    keys = [issue.key for issue in summary.zoom_slides[0].issues]
    assert keys == ["PAY-RTV", "PAY-ANA", "PAY-NEW"]
