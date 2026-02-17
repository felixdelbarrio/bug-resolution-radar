from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.insights.engine import (
    build_duplicates_brief,
    build_trend_insight_pack,
    classify_theme,
    top_non_other_theme,
)


def test_classify_theme_handles_accented_credit_terms() -> None:
    assert classify_theme("Error en tarjeta de crédito y CVV") == "Crédito"
    assert classify_theme("Fallo en biometria y login") == "Login y acceso"


def test_top_non_other_theme_ignores_otros_bucket() -> None:
    open_df = pd.DataFrame(
        {
            "summary": [
                "Fallo softoken en token OTP",
                "Error de token en firma",
                "Incidencia sin patron",
            ]
        }
    )
    top_theme, top_count = top_non_other_theme(open_df)
    assert top_theme == "Softoken"
    assert top_count == 2


def test_timeseries_pack_builds_actionable_cards() -> None:
    dff = pd.DataFrame(
        {
            "created": pd.to_datetime(
                [
                    "2026-01-20",
                    "2026-01-21",
                    "2026-01-22",
                    "2026-01-25",
                    "2026-01-28",
                ],
                utc=True,
            ),
            "resolved": pd.to_datetime(
                ["2026-01-21", "2026-01-29", None, None, None],
                utc=True,
                errors="coerce",
            ),
        }
    )
    open_df = pd.DataFrame(
        {
            "priority": ["High", "Highest"],
            "status": ["New", "Analysing"],
            "created": pd.to_datetime(["2026-01-20", "2026-01-24"], utc=True),
        }
    )

    pack = build_trend_insight_pack("timeseries", dff=dff, open_df=open_df)
    assert len(pack.metrics) == 3
    assert len(pack.cards) >= 1
    assert any("Criticas" in c.title for c in pack.cards)


def test_duplicates_brief_reports_high_duplicate_pressure() -> None:
    txt = build_duplicates_brief(
        total_open=100,
        duplicate_groups=12,
        duplicate_issues=24,
        heuristic_clusters=7,
    )
    assert "Presion por duplicidad" in txt


def test_priority_pack_flags_unassigned_critical_items() -> None:
    now = pd.Timestamp.utcnow().tz_localize(None)
    open_df = pd.DataFrame(
        {
            "priority": ["Highest", "High", "Medium", "Low"],
            "status": ["New", "Analysing", "In Progress", "Test"],
            "assignee": ["", None, "alice", "bob"],
            "created": pd.to_datetime(
                [now - pd.Timedelta(days=20), now - pd.Timedelta(days=12), now, now], utc=True
            ),
            "updated": pd.to_datetime(
                [now - pd.Timedelta(days=10), now - pd.Timedelta(days=8), now, now], utc=True
            ),
        }
    )
    pack = build_trend_insight_pack("open_priority_pie", dff=pd.DataFrame(), open_df=open_df)
    titles = {c.title for c in pack.cards}
    assert "Criticas sin owner" in titles


def test_status_pack_flags_stalled_dominant_state() -> None:
    now = pd.Timestamp.utcnow().tz_localize(None)
    open_df = pd.DataFrame(
        {
            "status": ["In Progress", "In Progress", "In Progress", "Test", "Test"],
            "priority": ["High", "Medium", "Low", "Low", "Low"],
            "assignee": ["ana", "ana", "ana", "luis", "maria"],
            "updated": pd.to_datetime(
                [
                    now - pd.Timedelta(days=18),
                    now - pd.Timedelta(days=14),
                    now - pd.Timedelta(days=11),
                    now - pd.Timedelta(days=2),
                    now - pd.Timedelta(days=1),
                ],
                utc=True,
            ),
        }
    )
    pack = build_trend_insight_pack("open_status_bar", dff=pd.DataFrame(), open_df=open_df)
    assert any("sin avance" in c.title.lower() for c in pack.cards)
