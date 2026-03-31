from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.insights import (
    _tokenize_summary,
    build_theme_fortnight_trend,
    find_similar_issue_clusters,
    order_theme_labels,
    prepare_open_theme_payload,
)


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
        "2026-01 \u00b7 1-15",
        "2026-01 \u00b7 16-31",
        "2026-02 \u00b7 1-15",
    ]
    pagos = trend.loc[trend["tema"] == "Pagos", "issues"].tolist()
    pagos_acc = trend.loc[trend["tema"] == "Pagos", "issues_cumulative"].tolist()
    assert pagos == [1, 1, 0]
    assert pagos_acc == [1, 2, 2]
    assert trend["issues_value"].equals(trend["issues_cumulative"])


def test_order_theme_labels_prioritizes_business_focus_themes() -> None:
    ordered = order_theme_labels(["Otros", "Softoken", "Pagos", "Monetarias"])
    assert ordered == ["Pagos", "Monetarias", "Otros", "Softoken"]
