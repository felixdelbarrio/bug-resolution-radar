"""Exact-title duplicate analytics shared across report and insights modules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ExactTitleDuplicateStats:
    """Summary counters for exact-title duplicate pressure."""

    groups: int = 0
    issues: int = 0


def exact_title_summary_counts(
    df: pd.DataFrame,
    *,
    summary_col: str = "summary",
) -> pd.Series:
    """Count non-empty summaries without sorting (fast path for metrics)."""
    if not isinstance(df, pd.DataFrame) or df.empty or summary_col not in df.columns:
        return pd.Series(dtype="int64")
    summaries = df[summary_col].fillna("").astype(str).str.strip()
    summaries = summaries[summaries != ""]
    if summaries.empty:
        return pd.Series(dtype="int64")
    return summaries.value_counts(sort=False)


def exact_title_duplicate_stats(
    df: pd.DataFrame,
    *,
    summary_col: str = "summary",
) -> ExactTitleDuplicateStats:
    """Return duplicate group count and issue count for repeated summaries."""
    counts = exact_title_summary_counts(df, summary_col=summary_col)
    if counts.empty:
        return ExactTitleDuplicateStats()
    repeated = counts[counts > 1]
    if repeated.empty:
        return ExactTitleDuplicateStats()
    return ExactTitleDuplicateStats(groups=int(repeated.size), issues=int(repeated.sum()))


def exact_title_groups(
    df: pd.DataFrame,
    *,
    summary_col: str = "summary",
    key_col: str = "key",
    dedupe_keys: bool = False,
) -> dict[str, list[str]]:
    """
    Build repeated exact-title groups with their issue keys.

    Returns only groups with at least two keys.
    """
    if (
        not isinstance(df, pd.DataFrame)
        or df.empty
        or summary_col not in df.columns
        or key_col not in df.columns
    ):
        return {}

    work = df.loc[:, [summary_col, key_col]].copy(deep=False)
    work[summary_col] = work[summary_col].fillna("").astype(str).str.strip()
    work[key_col] = work[key_col].fillna("").astype(str).str.strip()
    work = work[(work[summary_col] != "") & (work[key_col] != "")]
    if work.empty:
        return {}

    if dedupe_keys:
        work = work.drop_duplicates(subset=[summary_col, key_col], keep="first")

    grouped = work.groupby(summary_col, sort=False, observed=True)[key_col].agg(list)
    if grouped.empty:
        return {}

    repeated = grouped[grouped.map(len) > 1]
    if repeated.empty:
        return {}

    if not dedupe_keys:
        return {str(title): list(keys) for title, keys in repeated.items()}

    out: dict[str, list[str]] = {}
    for raw_title, raw_keys in repeated.items():
        title = str(raw_title).strip()
        if not title:
            continue
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw_key in list(raw_keys or []):
            key = str(raw_key).strip()
            if not key:
                continue
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(key)
        if len(cleaned) > 1:
            out[title] = cleaned
    return out


def sort_exact_title_groups(
    title_groups: Mapping[str, Sequence[str]],
    *,
    limit: int | None = None,
) -> list[tuple[str, list[str]]]:
    """Sort exact-title groups by descending size and apply optional cap."""
    items: list[tuple[str, list[str]]] = []
    for raw_title, raw_keys in title_groups.items():
        title = str(raw_title).strip()
        if not title:
            continue
        keys = [str(k).strip() for k in list(raw_keys or []) if str(k).strip()]
        if len(keys) > 1:
            items.append((title, keys))

    items.sort(key=lambda item: len(item[1]), reverse=True)
    if isinstance(limit, int) and limit > 0:
        return items[:limit]
    return items
