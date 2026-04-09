from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.topic_expandable_summary import (
    build_root_cause_labels,
    build_root_cause_map,
    build_topic_expandable_summaries,
    infer_root_cause_label,
    summarize_root_causes,
)


def test_infer_root_cause_label_detects_known_patterns() -> None:
    assert (
        infer_root_cause_label("No se visualiza el dashboard del cliente") == "Visualización / UI"
    )
    assert infer_root_cause_label("Login falla por token caducado") == "Autenticación y sesión"
    assert (
        infer_root_cause_label(
            "INC0001 - PAGOS / SENDA BNC / TRANSFERENCIAS EN TIEMPO REAL / 00853291"
        )
        == "Transferencias en tiempo real"
    )


def test_infer_root_cause_label_uses_theme_fallback_for_unknown_text() -> None:
    assert (
        infer_root_cause_label("Error funcional no especificado en pagos")
        == "Fallo funcional en Pagos"
    )


def test_infer_root_cause_label_uses_description_context() -> None:
    assert (
        infer_root_cause_label(
            "Incidencia operativa sin detalle",
            description=(
                "El usuario reporta timeout y error 504 al consultar el endpoint del servicio"
            ),
        )
        == "Conectividad / timeout"
    )


def test_build_root_cause_map_promotes_semantic_phrase_on_structured_summaries() -> None:
    rows = [
        "INC0001 - PAGOS / BBVA.MX / LIQUIDEZ A TU ALCANCE / 2026-04-01",
        "INC0002 - PAGOS / BBVA.MX / LIQUIDEZ A TU ALCANCE / 2026-04-02",
    ]
    out = build_root_cause_map(rows)
    assert out[rows[0]] == "Liquidez Tu Alcance"
    assert out[rows[1]] == "Liquidez Tu Alcance"


def test_build_root_cause_labels_disambiguates_same_summary_using_description() -> None:
    labels = build_root_cause_labels(
        [
            "Incidencia operativa sin detalle",
            "Incidencia operativa sin detalle",
        ],
        descriptions=[
            "Login falla por token invalido en el inicio de sesion",
            "Timeout al invocar API backend de pagos",
        ],
    )
    assert labels == ("Autenticación y sesión", "Integración API / backend")


def test_summarize_root_causes_returns_top_k() -> None:
    ranked = summarize_root_causes(
        [
            "No se visualiza dashboard",
            "No se visualiza dashboard en IOS",
            "Timeout al consultar servicio",
            "Login con token invalido",
        ],
        top_k=3,
    )
    assert len(ranked) == 3
    assert ranked[0].label == "Visualización / UI"
    assert ranked[0].count == 2


def test_summarize_root_causes_uses_description_for_grouping() -> None:
    ranked = summarize_root_causes(
        [
            "Incidencia sin detalle",
            "Incidencia sin detalle",
            "Incidencia sin detalle",
        ],
        descriptions=[
            "Timeout y error 504 al consultar servicio externo",
            "Demora y latencia de conexion en app",
            "Error de login por token vencido",
        ],
        top_k=2,
    )
    assert ranked[0].label == "Conectividad / timeout"
    assert ranked[0].count == 2
    assert ranked[1].label == "Autenticación y sesión"
    assert ranked[1].count == 1


def test_build_topic_expandable_summaries_builds_flow_and_root_causes() -> None:
    history_df = pd.DataFrame(
        [
            # Tareas: 4 creadas en ventana, 1 resuelta en ventana -> empeora 75%
            {
                "summary": "TAREAS PENDIENTES - No se visualiza dashboard",
                "created": "2026-03-28T10:00:00+00:00",
                "resolved": None,
                "status": "New",
            },
            {
                "summary": "TAREAS PENDIENTES - Error en dashboard",
                "created": "2026-03-27T10:00:00+00:00",
                "resolved": None,
                "status": "Analysing",
            },
            {
                "summary": "TAREAS PENDIENTES - Timeout dashboard",
                "created": "2026-03-26T10:00:00+00:00",
                "resolved": None,
                "status": "New",
            },
            {
                "summary": "TAREAS PENDIENTES - No permite guardar",
                "created": "2026-03-25T10:00:00+00:00",
                "resolved": "2026-03-30T10:00:00+00:00",
                "status": "Done",
            },
            # Pagos: 1 creada en ventana, 3 resueltas en ventana -> mejora 66.7%
            {
                "summary": "Error de pagos en transfer",
                "created": "2026-03-29T10:00:00+00:00",
                "resolved": "2026-03-29T16:00:00+00:00",
                "status": "Done",
            },
            {
                "summary": "Error de pagos en transfer",
                "created": "2026-01-10T10:00:00+00:00",
                "resolved": "2026-03-30T10:00:00+00:00",
                "status": "Done",
            },
            {
                "summary": "Error de pagos en transfer",
                "created": "2026-01-12T10:00:00+00:00",
                "resolved": "2026-03-31T10:00:00+00:00",
                "status": "Done",
            },
        ]
    )
    open_df = pd.DataFrame(
        [
            {"summary": "TAREAS PENDIENTES - No se visualiza dashboard"},
            {"summary": "TAREAS PENDIENTES - No se visualiza dashboard"},
            {"summary": "TAREAS PENDIENTES - Timeout dashboard"},
            {"summary": "Error de pagos en transfer"},
        ]
    )

    out = build_topic_expandable_summaries(
        history_df=history_df,
        open_df=open_df,
        flow_window_days=30,
        top_root_causes=3,
    )

    tareas = out["Tareas"]
    assert tareas.flow.direction == "worsening"
    assert tareas.flow.created_count == 4
    assert tareas.flow.resolved_count == 1
    assert round(tareas.flow.pct_delta, 1) == 75.0
    assert tareas.root_causes
    assert tareas.root_causes[0].label == "Visualización / UI"
    assert tareas.root_causes[0].count == 2

    pagos = out["Pagos"]
    assert pagos.flow.direction == "improving"
    assert pagos.flow.created_count == 1
    assert pagos.flow.resolved_count == 3
    assert round(pagos.flow.pct_delta, 1) == 66.7
