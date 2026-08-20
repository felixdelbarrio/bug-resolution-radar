from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.execution_evolution import build_execution_evolution


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
    assert {key: previous[key] for key in (
        "backlogStart", "backlogEnd", "created", "closed"
    )} == {
        "backlogStart": 2,
        "backlogEnd": 2,
        "created": 2,
        "closed": 2,
    }
    assert {key: current[key] for key in (
        "backlogStart", "backlogEnd", "created", "closed", "criticalOpen", "aged30Open"
    )} == {
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

    for period in (result["annual"], result["fortnight"]["previous"], result["fortnight"]["current"]):
        assert period["backlogDelta"] == period["created"] - period["closed"]
        assert period["backlogEnd"] == period["backlogStart"] + period["backlogDelta"]

    assert "Permanecen 1 incidencias" in result["executive"]["summary"]
    assert result["learningMeasurement"]["critical_count"] == 1


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
    assert "No hay incidencias abiertas de criticidad alta o muy alta" in result["executive"]["summary"]


def test_execution_evolution_is_complete_for_an_empty_scope() -> None:
    result = build_execution_evolution(dff=pd.DataFrame(), reference_day="2026-08-20")

    assert result["annual"]["backlogEnd"] == 0
    assert result["fortnight"]["current"]["created"] == 0
    assert result["timeline"] == []
    assert result["hasData"] is False
    assert result["executive"]["title"] == "Sin datos para evaluar la evolución"
    assert result["executive"]["focus"] == []
