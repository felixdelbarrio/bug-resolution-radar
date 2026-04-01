from __future__ import annotations

import pandas as pd

from bug_resolution_radar.ui.insights.top_topics import _theme_color_map
from bug_resolution_radar.ui.insights.top_topics import (
    _priority_ordered_topics,
    _rank_topic_candidates,
)


def test_theme_color_map_keeps_login_and_credit_distinct_in_dark_mode() -> None:
    theme_order = [
        "Pagos",
        "Tareas",
        "Monetarias",
        "Crédito",
        "Login y acceso",
        "Softoken",
        "Transferencias",
        "Notificaciones",
        "Otros",
    ]
    color_map = _theme_color_map(theme_order=theme_order, dark_mode=True)
    assert color_map["Login y acceso"] != color_map["Crédito"]
    assert len({color_map[name] for name in theme_order}) == len(theme_order)


def test_theme_color_map_matches_credit_label_with_or_without_accent() -> None:
    accented = _theme_color_map(theme_order=["Crédito"], dark_mode=False)
    plain = _theme_color_map(theme_order=["Credito"], dark_mode=False)
    assert accented["Crédito"] == plain["Credito"]


def test_priority_ordered_topics_prefers_critical_themes_over_volume() -> None:
    top_tbl = pd.DataFrame(
        [
            {"tema": "Tema Bajo", "open_count": 12, "pct_open": 40.0},
            {"tema": "Tema Alto", "open_count": 4, "pct_open": 13.3},
            {"tema": "Tema Crítico", "open_count": 2, "pct_open": 6.7},
        ]
    )
    tmp_open = pd.DataFrame(
        [
            {"__theme": "Tema Bajo", "priority": "Low"},
            {"__theme": "Tema Bajo", "priority": "Low"},
            {"__theme": "Tema Alto", "priority": "High"},
            {"__theme": "Tema Alto", "priority": "Medium"},
            {"__theme": "Tema Crítico", "priority": "Highest"},
        ]
    )

    ordered = _priority_ordered_topics(top_tbl, tmp_open=tmp_open)
    assert ordered["tema"].tolist() == ["Tema Crítico", "Tema Alto", "Tema Bajo"]


def test_rank_topic_candidates_orders_by_priority_before_score() -> None:
    sub = pd.DataFrame(
        [
            {
                "key": "X-1",
                "priority": "High",
                "__age_days": 5.0,
                "updated": "2026-03-30T00:00:00+00:00",
                "assignee": "(sin asignar)",
            },
            {
                "key": "X-2",
                "priority": "Low",
                "__age_days": 120.0,
                "updated": "2025-12-01T00:00:00+00:00",
                "assignee": "(sin asignar)",
            },
        ]
    )

    ranked = _rank_topic_candidates(sub)
    assert ranked.iloc[0]["key"] == "X-1"
