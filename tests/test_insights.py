from __future__ import annotations

import pandas as pd

from bug_resolution_radar.insights import _tokenize_summary, find_similar_issue_clusters


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
