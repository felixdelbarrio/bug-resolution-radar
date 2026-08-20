from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.execution_evolution import (
    _executive_message,
    _FlowMetrics,
    build_execution_evolution,
)


def _issue(
    key: str,
    created: str,
    *,
    updated: str = "2026-08-20",
    resolved: str | None = None,
    status: str = "Open",
    priority: str = "Medium",
) -> dict[str, object]:
    return {
        "key": key,
        "created": created,
        "updated": updated,
        "resolved": resolved,
        "status": status,
        "priority": priority,
    }


def test_execution_evolution_reconstructs_year_and_fortnight_flows() -> None:
    frame = pd.DataFrame(
        [
            _issue("A", "2025-12-20"),
            _issue("B", "2026-01-05", resolved="2026-08-03", status="Closed"),
            _issue("C", "2026-08-02"),
            _issue("D", "2026-08-05", resolved="2026-08-10", status="Resolved"),
            _issue("E", "2026-08-16", priority="Lowest"),
            _issue("F", "2026-08-17", resolved="2026-08-19", status="Closed"),
            _issue("G", "2026-08-18", updated="2026-08-20", status="Deployed"),
            _issue("H", "2026-08-16", priority="High"),
        ]
    )

    result = build_execution_evolution(dff=frame, reference_day="2026-08-20")

    assert result["referenceDate"] == "2026-08-20"
    previous = result["fortnight"]["previous"]
    current = result["fortnight"]["current"]
    assert {key: previous[key] for key in ("backlogStart", "backlogEnd", "created", "closed")} == {
        "backlogStart": 2,
        "backlogEnd": 2,
        "created": 2,
        "closed": 2,
    }
    assert {
        key: current[key]
        for key in ("backlogStart", "backlogEnd", "created", "closed", "criticalOpen", "aged30Open")
    } == {
        "backlogStart": 2,
        "backlogEnd": 4,
        "created": 4,
        "closed": 2,
        "criticalOpen": 1,
        "aged30Open": 1,
    }
    assert result["annual"]["backlogStart"] == 1
    assert result["annual"]["backlogEnd"] == 4
    assert result["annual"]["created"] == 7
    assert result["annual"]["closed"] == 4
    assert len(result["timeline"]) == 16
    assert previous["averageOpen"] == 2.4
    assert current["averageOpen"] == 4.3
    assert current["resolutionDays"] == 2.0

    for period in (
        result["annual"],
        result["fortnight"]["previous"],
        result["fortnight"]["current"],
    ):
        assert period["backlogDelta"] == period["created"] - period["closed"]
        assert period["backlogEnd"] == period["backlogStart"] + period["backlogDelta"]

    assert result["executive"]["tone"] == "negative"
    assert result["executive"]["title"] == "1 incidencia crítica requiere atención"
    assert "Permanecen 1 incidencia abierta" in result["executive"]["summary"]
    assert (
        "Carga media: 4,3 incidencias (+1,9 frente a 2,4); señala mayor presión durante el periodo."
        in result["executive"]["summary"]
    )
    assert "Resolución: 2,0 días de media (-105,5); mejora." in result["executive"]["summary"]
    average_kpi = next(
        metric for metric in result["fortnight"]["kpis"] if metric["id"] == "averageOpen"
    )
    assert average_kpi == {
        "id": "averageOpen",
        "label": "Cartera abierta media",
        "current": 4.3,
        "previous": 2.4,
        "delta": 1.9,
        "unit": "average",
        "tone": "negative",
    }
    assert result["learningMeasurement"]["critical_count"] == 1
    assert result["learningMeasurement"]["average_open_14"] == 4.3
    assert result["learningMeasurement"]["resolution_days_14"] == 2.0


def test_execution_evolution_never_invents_critical_incidents() -> None:
    frame = pd.DataFrame(
        [
            _issue("A", "2026-08-01", priority="Medium"),
            _issue("B", "2026-08-18", priority="Low"),
        ]
    )

    result = build_execution_evolution(dff=frame, reference_day="2026-08-20")

    assert result["period"]["criticalOpen"] == 0
    assert all(not line.startswith("Criticidad:") for line in result["period"]["focus"])
    assert "Sin incidencias abiertas de criticidad alta" in result["executive"]["summary"]


def test_execution_evolution_is_complete_for_an_empty_scope() -> None:
    result = build_execution_evolution(dff=pd.DataFrame(), reference_day="2026-08-20")

    assert result["annual"]["backlogEnd"] == 0
    assert result["fortnight"]["current"]["created"] == 0
    assert result["timeline"] == []
    assert result["hasData"] is False
    assert result["executive"]["title"] == "Sin datos para evaluar la evolución"
    assert result["executive"]["focus"] == []


def test_execution_evolution_omits_resolution_comparison_without_two_valid_samples() -> None:
    frame = pd.DataFrame([_issue("A", "2026-08-01")])

    result = build_execution_evolution(dff=frame, reference_day="2026-08-20")

    summary = result["executive"]["summary"]
    assert "carga media" in summary.lower()
    assert "resolución:" not in summary.lower()
    assert result["fortnight"]["current"]["resolutionDays"] is None


def test_executive_message_is_concise_and_yellow_for_mixed_screenshot_signals() -> None:
    previous = _FlowMetrics(
        start=pd.Timestamp("2026-08-01").date(),
        end=pd.Timestamp("2026-08-14").date(),
        backlog_start=76,
        backlog_end=128,
        created=101,
        closed=49,
        resolution_days=18.5,
        average_open=85.5,
        critical_end=0,
        aged30_end=21,
    )
    current = _FlowMetrics(
        start=pd.Timestamp("2026-08-15").date(),
        end=pd.Timestamp("2026-08-20").date(),
        backlog_start=128,
        backlog_end=108,
        created=15,
        closed=35,
        resolution_days=20.0,
        average_open=115.5,
        critical_end=0,
        aged30_end=21,
    )
    annual = _FlowMetrics(
        start=pd.Timestamp("2026-01-01").date(),
        end=pd.Timestamp("2026-08-20").date(),
        backlog_start=108,
        backlog_end=108,
        created=600,
        closed=600,
        resolution_days=17.0,
        average_open=101.0,
        critical_end=0,
        aged30_end=21,
    )

    tone, title, summary = _executive_message(
        annual=annual,
        current=current,
        previous=previous,
    )

    assert tone == "mixed"
    assert title == "Backlog reducido en 20 incidencias"
    assert summary == (
        "Se cerraron 35 incidencias frente a 15 nuevas; la cartera termina en 108. "
        "Carga media: 115,5 incidencias (+30,0 frente a 85,5); señala mayor presión "
        "durante el periodo. Resolución: 20,0 días de media (+1,5); empeora. "
        "En el año, el backlog se mantiene en el nivel de partida. "
        "Sin incidencias abiertas de criticidad alta."
    )
    assert summary.count("108") == 1


def test_executive_message_is_green_only_without_deterioration_or_critical_alerts() -> None:
    previous = _FlowMetrics(
        start=pd.Timestamp("2026-08-01").date(),
        end=pd.Timestamp("2026-08-14").date(),
        backlog_start=110,
        backlog_end=100,
        created=20,
        closed=30,
        resolution_days=12.0,
        average_open=105.0,
        critical_end=0,
        aged30_end=12,
    )
    current = _FlowMetrics(
        start=pd.Timestamp("2026-08-15").date(),
        end=pd.Timestamp("2026-08-20").date(),
        backlog_start=100,
        backlog_end=90,
        created=15,
        closed=25,
        resolution_days=9.0,
        average_open=95.0,
        critical_end=0,
        aged30_end=8,
    )

    tone, _, _ = _executive_message(annual=current, current=current, previous=previous)

    assert tone == "positive"
