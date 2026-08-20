from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.backlog_evolution import build_evolution_insight
from bug_resolution_radar.analytics.insights import (
    _tokenize_summary,
    build_theme_daily_trend,
    build_theme_fortnight_trend,
    build_theme_render_order,
    find_similar_issue_clusters,
    is_other_theme_label,
    order_theme_labels,
    order_theme_labels_by_volume,
    prepare_open_theme_payload,
    sort_theme_table_by_volume,
)
from bug_resolution_radar.analytics.issues import is_critical_priority, priority_rank
from bug_resolution_radar.analytics.trend_insights import build_trend_insight_pack


def test_tokenize_summary_removes_stopwords_and_short_tokens() -> None:
    tokens = _tokenize_summary("The API fails on login and on app startup")
    assert "the" not in tokens
    assert "and" not in tokens
    assert "api" in tokens
    assert "login" in tokens


def test_find_similar_issue_clusters_detects_duplicates() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Payment API timeout when submitting transfer",
                "resolved": pd.NaT,
            },
            {
                "key": "A-2",
                "summary": "Payment API timeout while submitting transfer",
                "resolved": pd.NaT,
            },
            {"key": "A-3", "summary": "UI typo on dashboard", "resolved": pd.NaT},
        ]
    )

    clusters = find_similar_issue_clusters(
        df,
        only_open=True,
        min_cluster_size=2,
        jaccard_threshold=0.4,
        min_shared_tokens=2,
    )
    assert len(clusters) == 1
    assert clusters[0].size == 2
    assert set(clusters[0].keys) == {"A-1", "A-2"}


def test_find_similar_issue_clusters_respects_only_open_flag() -> None:
    df = pd.DataFrame(
        [
            {
                "key": "B-1",
                "summary": "Service down in production cluster",
                "resolved": "2025-01-02T00:00:00+00:00",
            },
            {"key": "B-2", "summary": "Service down in production cluster", "resolved": pd.NaT},
        ]
    )

    closed_filtered = find_similar_issue_clusters(df, only_open=True)
    include_closed = find_similar_issue_clusters(
        df, only_open=False, min_shared_tokens=2, jaccard_threshold=0.4
    )

    assert closed_filtered == []
    assert len(include_closed) == 1
    assert include_closed[0].size == 2


def test_find_similar_issue_clusters_handles_missing_columns() -> None:
    assert find_similar_issue_clusters(pd.DataFrame({"id": [1, 2]})) == []


def test_prepare_open_theme_payload_includes_other_bucket_after_top_themes() -> None:
    open_df = pd.DataFrame(
        {
            "summary": [
                "Error en pagos con TPV",
                "Error en pagos con TPV",
                "Fallo en login con password",
                "Texto libre sin patron funcional",
            ]
        }
    )
    payload = prepare_open_theme_payload(open_df, top_n=3)
    top_tbl = payload["top_tbl"]
    assert top_tbl["tema"].tolist() == ["Pagos", "Login y acceso", "Otros"]
    assert top_tbl["open_count"].tolist() == [2, 1, 1]


def test_build_theme_fortnight_trend_builds_raw_and_cumulative_series() -> None:
    df = pd.DataFrame(
        {
            "summary": [
                "Error de pagos",
                "Error de pagos",
                "Fallo de login biometria",
                "Incidencia sin clasificar",
            ],
            "created": [
                "2026-01-03T10:00:00+00:00",
                "2026-01-19T10:00:00+00:00",
                "2026-01-23T10:00:00+00:00",
                "2026-02-02T10:00:00+00:00",
            ],
        }
    )
    trend = build_theme_fortnight_trend(
        df,
        theme_whitelist=["Pagos", "Login y acceso", "Otros"],
        cumulative=True,
    )
    assert trend["tema"].drop_duplicates().tolist() == ["Pagos", "Login y acceso", "Otros"]
    assert trend["quincena_label"].drop_duplicates().tolist() == [
        "2026-01 \u00b7 1-14",
        "2026-01 \u00b7 15-31",
        "2026-02 \u00b7 1-14",
    ]
    pagos = trend.loc[trend["tema"] == "Pagos", "issues"].tolist()
    pagos_acc = trend.loc[trend["tema"] == "Pagos", "issues_cumulative"].tolist()
    assert pagos == [1, 1, 0]
    assert pagos_acc == [1, 2, 2]
    assert trend["issues_value"].equals(trend["issues_cumulative"])


def test_build_theme_daily_trend_uses_day_axis_inside_fortnight() -> None:
    df = pd.DataFrame(
        {
            "summary": [
                "Error de pagos",
                "Error de pagos",
                "Fallo de login biometria",
            ],
            "created": [
                "2026-01-16T10:00:00+00:00",
                "2026-01-18T10:00:00+00:00",
                "2026-01-18T15:00:00+00:00",
            ],
        }
    )
    trend = build_theme_daily_trend(
        df,
        theme_whitelist=["Pagos", "Login y acceso"],
    )
    assert trend["tema"].drop_duplicates().tolist() == ["Pagos", "Login y acceso"]
    assert trend["date_label"].iloc[0] == "2026-01-15"
    assert trend["date_label"].iloc[-1] == "2026-01-31"
    pagos_daily = trend.loc[trend["tema"] == "Pagos", "issues"].tolist()
    assert pagos_daily[0] == 0  # 2026-01-15 canonical fortnight boundary
    assert pagos_daily[1] == 1  # 2026-01-16
    assert pagos_daily[2] == 0  # 2026-01-17 gap
    assert pagos_daily[3] == 1  # 2026-01-18


def test_order_theme_labels_prioritizes_business_focus_themes() -> None:
    ordered = order_theme_labels(["Otros", "Softoken", "Pagos", "Monetarias"])
    assert ordered == ["Pagos", "Monetarias", "Otros", "Softoken"]


def test_order_theme_labels_by_volume_puts_others_last() -> None:
    ordered = order_theme_labels_by_volume(
        ["Otros", "Pagos", "Monetarias", "Login y acceso"],
        counts_by_label={"Otros": 67, "Pagos": 30, "Monetarias": 15, "Login y acceso": 4},
    )
    assert ordered == ["Pagos", "Monetarias", "Login y acceso", "Otros"]


def test_sort_theme_table_by_volume_applies_shared_ordering_rule() -> None:
    top_tbl = pd.DataFrame(
        [
            {"tema": "Otros", "open_count": 67, "pct_open": 51.1},
            {"tema": "Pagos", "open_count": 30, "pct_open": 22.9},
            {"tema": "Monetarias", "open_count": 15, "pct_open": 11.5},
            {"tema": "Transferencias", "open_count": 4, "pct_open": 3.1},
        ]
    )

    out = sort_theme_table_by_volume(top_tbl)
    assert out["tema"].tolist() == ["Pagos", "Monetarias", "Transferencias", "Otros"]
    assert out["open_count"].tolist() == [30, 15, 4, 67]


def test_build_theme_render_order_aligns_stack_with_legend_and_others_on_x_axis() -> None:
    order = build_theme_render_order(
        ["Otros", "Pagos", "Monetarias", "Login y acceso"],
        counts_by_label={"Otros": 67, "Pagos": 30, "Monetarias": 15, "Login y acceso": 4},
        others_last=True,
        others_at_x_axis=True,
    )

    assert list(order.display_order) == ["Pagos", "Monetarias", "Login y acceso", "Otros"]
    assert list(order.stack_order_bottom_to_top) == [
        "Otros",
        "Login y acceso",
        "Monetarias",
        "Pagos",
    ]


def test_build_theme_trends_whitelist_moves_others_to_last_position() -> None:
    df = pd.DataFrame(
        {
            "summary": [
                "Error de pagos",
                "Fallo de login biometria",
                "Texto sin clasificar",
            ],
            "created": [
                "2026-01-16T10:00:00+00:00",
                "2026-01-16T10:30:00+00:00",
                "2026-01-16T11:00:00+00:00",
            ],
        }
    )

    whitelist = ["Otros", "Pagos", "Login y acceso"]
    daily = build_theme_daily_trend(df, theme_whitelist=whitelist)
    fortnight = build_theme_fortnight_trend(df, theme_whitelist=whitelist, cumulative=True)

    assert daily["tema"].drop_duplicates().tolist() == ["Pagos", "Login y acceso", "Otros"]
    assert fortnight["tema"].drop_duplicates().tolist() == ["Pagos", "Login y acceso", "Otros"]
    assert is_other_theme_label("Otros")


def test_medium_is_not_classified_as_critical_and_lowest_keeps_its_rank() -> None:
    assert is_critical_priority("Supone un impedimento")
    assert is_critical_priority("Highest")
    assert is_critical_priority("High")
    assert not is_critical_priority("Medium")
    assert priority_rank("Lowest") > priority_rank("Low")


def test_priority_insights_do_not_invent_high_priority_signals_for_medium_backlog() -> None:
    open_df = pd.DataFrame(
        [
            {
                "status": "New",
                "priority": "Medium",
                "created": "2026-08-01T00:00:00+00:00",
                "updated": "2026-08-01T00:00:00+00:00",
            }
            for _ in range(8)
        ]
    )
    pack = build_trend_insight_pack("open_priority_pie", dff=open_df, open_df=open_df)
    text = " ".join(f"{card.title} {card.body}" for card in pack.cards).casefold()

    assert "concentracion de prioridad" in text
    assert "inflacion de prioridades altas" not in text
    assert "mayor impacto" not in text


def test_evolution_insight_reports_week_over_week_direction_from_material_changes() -> None:
    insight = build_evolution_insight(
        {
            "reference_date": "2026-08-20",
            "open_total": 108,
            "critical_count": 0,
            "blocked_count": 2,
            "aged30_count": 18,
            "stale_14_count": 12,
            "net_14": -4,
        },
        {
            "reference_date": "2026-08-13",
            "open_total": 120,
            "critical_count": 5,
            "blocked_count": 4,
            "aged30_count": 25,
            "stale_14_count": 12,
            "net_14": 3,
        },
    )

    assert insight is not None
    assert "WoW" in insight.title
    assert insight.direction == "improves"
    assert "Prioridades críticas baja de 5 a 0" in insight.body
