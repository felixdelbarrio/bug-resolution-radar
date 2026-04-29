from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.period_risk_issue_lists import (
    build_aged_open_issue_list,
    build_high_priority_open_issue_list,
    build_period_risk_issue_lists,
)


def test_high_priority_open_issue_list_orders_by_age_first() -> None:
    analysis_day = pd.Timestamp("2026-04-29")
    df = pd.DataFrame(
        [
            {
                "key": "NEW-HIGHEST",
                "summary": "Bloqueo login",
                "status": "New",
                "priority": "Highest",
                "created": "2026-04-20T00:00:00+00:00",
            },
            {
                "key": "OLD-ALTO",
                "summary": "Pagos no responde",
                "status": "Analysing",
                "priority": "Alto",
                "created": "2026-03-01T00:00:00+00:00",
            },
            {
                "key": "MEDIUM",
                "summary": "Aviso menor",
                "status": "New",
                "priority": "Medium",
                "created": "2026-02-01T00:00:00+00:00",
            },
            {
                "key": "CLOSED-HIGH",
                "summary": "Cerrada",
                "status": "Closed",
                "priority": "High",
                "created": "2026-01-01T00:00:00+00:00",
                "resolved": "2026-01-02T00:00:00+00:00",
            },
        ]
    )

    rows = build_high_priority_open_issue_list(df, analysis_day=analysis_day)

    assert [row.key for row in rows] == ["OLD-ALTO", "NEW-HIGHEST"]
    assert rows[0].open_days == 59


def test_aged_open_issue_list_orders_by_criticality_then_age() -> None:
    analysis_day = pd.Timestamp("2026-04-29")
    df = pd.DataFrame(
        [
            {
                "key": "HIGH-OLD",
                "summary": "Transferencias fallan",
                "status": "New",
                "priority": "High",
                "created": "2026-03-01T00:00:00+00:00",
            },
            {
                "key": "VERY-HIGH",
                "summary": "App caída",
                "status": "Blocked",
                "priority": "Very High",
                "created": "2026-03-20T00:00:00+00:00",
            },
            {
                "key": "MEDIUM-OLDER",
                "summary": "Dato descuadrado",
                "status": "Analysing",
                "priority": "Medium",
                "created": "2026-02-01T00:00:00+00:00",
            },
            {
                "key": "RECENT-HIGH",
                "summary": "Reciente",
                "status": "New",
                "priority": "Muy alto",
                "created": "2026-04-15T00:00:00+00:00",
            },
        ]
    )

    rows = build_aged_open_issue_list(df, analysis_day=analysis_day)
    bundled = build_period_risk_issue_lists(df, analysis_day=analysis_day)

    assert [row.key for row in rows] == ["VERY-HIGH", "HIGH-OLD", "MEDIUM-OLDER"]
    assert [row.key for row in bundled.aged] == ["VERY-HIGH", "HIGH-OLD", "MEDIUM-OLDER"]
    assert rows[1].functionality
