from __future__ import annotations

import pandas as pd

from bug_resolution_radar.analytics.duplicates import (
    ExactTitleDuplicateStats,
    exact_title_duplicate_stats,
    exact_title_groups,
    exact_title_summary_counts,
    sort_exact_title_groups,
)


def test_exact_title_summary_counts_ignores_empty_summaries() -> None:
    df = pd.DataFrame(
        {
            "summary": ["A", "A", "B", "", None, "  "],
        }
    )

    counts = exact_title_summary_counts(df, summary_col="summary")

    assert counts.to_dict() == {"A": 2, "B": 1}


def test_exact_title_duplicate_stats_returns_groups_and_issues() -> None:
    df = pd.DataFrame(
        {
            "summary": ["A", "A", "A", "B", "B", "C"],
        }
    )

    stats = exact_title_duplicate_stats(df, summary_col="summary")

    assert stats == ExactTitleDuplicateStats(groups=2, issues=5)


def test_exact_title_groups_returns_only_repeated_titles() -> None:
    df = pd.DataFrame(
        [
            {"summary": "A", "key": "MX-1"},
            {"summary": "A", "key": "MX-2"},
            {"summary": "B", "key": "MX-3"},
            {"summary": "", "key": "MX-4"},
            {"summary": "C", "key": ""},
        ]
    )

    groups = exact_title_groups(df, summary_col="summary", key_col="key")

    assert groups == {"A": ["MX-1", "MX-2"]}


def test_exact_title_groups_can_dedupe_repeated_keys() -> None:
    df = pd.DataFrame(
        [
            {"summary": "A", "key": "MX-1"},
            {"summary": "A", "key": "MX-1"},
            {"summary": "A", "key": "MX-2"},
        ]
    )

    groups = exact_title_groups(df, summary_col="summary", key_col="key", dedupe_keys=True)

    assert groups == {"A": ["MX-1", "MX-2"]}


def test_sort_exact_title_groups_orders_by_cluster_size_and_applies_limit() -> None:
    groups = {
        "A": ["MX-1", "MX-2", "MX-3"],
        "B": ["MX-4", "MX-5"],
        "C": ["MX-6", "MX-7", "MX-8", "MX-9"],
    }

    top = sort_exact_title_groups(groups, limit=2)

    assert top == [
        ("C", ["MX-6", "MX-7", "MX-8", "MX-9"]),
        ("A", ["MX-1", "MX-2", "MX-3"]),
    ]
