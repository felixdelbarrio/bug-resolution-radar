"""Duplicate-detection payload helpers shared by UI and reports."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from bug_resolution_radar.analytics.duplicates import (
    ExactTitleDuplicateStats,
    exact_title_duplicate_stats,
    exact_title_groups,
    sort_exact_title_groups,
)
from bug_resolution_radar.analytics.insights import SimilarityCluster, find_similar_issue_clusters


def _col_exists(df: pd.DataFrame, name: str) -> bool:
    return isinstance(df, pd.DataFrame) and name in df.columns


def _as_naive_utc(series: pd.Series) -> pd.Series:
    out = pd.to_datetime(series, errors="coerce", utc=True)
    try:
        return out.dt.tz_convert(None)
    except Exception:
        try:
            return out.dt.tz_localize(None)
        except Exception:
            return out


def _dedupe_heuristic_clusters(
    *,
    clusters: list[SimilarityCluster],
    exact_title_groups_payload: dict[str, list[str]],
) -> list[SimilarityCluster]:
    if not clusters or not exact_title_groups_payload:
        return clusters

    normalized_exact_groups: dict[str, set[str]] = {}
    exact_key_sets: list[set[str]] = []
    for raw_title, raw_keys in exact_title_groups_payload.items():
        title = str(raw_title or "").strip()
        keys = {str(key).strip() for key in list(raw_keys or []) if str(key).strip()}
        if len(keys) <= 1:
            continue
        if title:
            normalized_exact_groups[title] = keys
        exact_key_sets.append(keys)

    if not exact_key_sets:
        return clusters

    deduped: list[SimilarityCluster] = []
    for cluster in clusters:
        cluster_keys = {
            str(key).strip() for key in list(getattr(cluster, "keys", []) or []) if str(key).strip()
        }
        if len(cluster_keys) <= 1:
            deduped.append(cluster)
            continue

        if any(cluster_keys == exact_keys for exact_keys in exact_key_sets):
            continue

        representative_title = str(getattr(cluster, "summary", "") or "").strip()
        exact_keys = normalized_exact_groups.get(representative_title)
        if exact_keys and cluster_keys.issubset(exact_keys):
            continue

        deduped.append(cluster)

    return deduped


def prepare_duplicates_payload(df2: pd.DataFrame) -> dict[str, Any]:
    key_to_extra: dict[str, tuple[float | None, str | None]] = {}

    if _col_exists(df2, "key"):
        extra_cols = ["key"]
        if _col_exists(df2, "created"):
            extra_cols.append("created")
        if _col_exists(df2, "assignee"):
            extra_cols.append("assignee")

        extra_df = df2.loc[:, extra_cols].copy(deep=False)
        extra_df["key"] = extra_df["key"].fillna("").astype(str).str.strip()
        extra_df = extra_df[extra_df["key"] != ""].drop_duplicates(subset=["key"], keep="first")

        age_series = pd.Series([pd.NA] * len(extra_df), index=extra_df.index)
        if "created" in extra_df.columns:
            created_naive = _as_naive_utc(extra_df["created"])
            now = pd.Timestamp.utcnow().tz_localize(None)
            age_series = ((now - created_naive).dt.total_seconds() / 86400.0).clip(lower=0.0)

        assignee_series = (
            extra_df["assignee"].fillna("").astype(str).str.strip()
            if "assignee" in extra_df.columns
            else pd.Series([""] * len(extra_df), index=extra_df.index, dtype=str)
        )

        key_to_extra = {
            key: (
                float(age) if pd.notna(age) else None,
                assignee if assignee else None,
            )
            for key, age, assignee in zip(
                extra_df["key"].tolist(), age_series.tolist(), assignee_series.tolist()
            )
        }

    title_groups = exact_title_groups(df2, summary_col="summary", key_col="key")
    top_titles = sort_exact_title_groups(title_groups, limit=12)
    duplicate_stats = exact_title_duplicate_stats(df2, summary_col="summary")

    title_export = pd.DataFrame(
        [
            {"cluster_size": len(keys), "summary": title, "keys": ", ".join(keys)}
            for title, keys in top_titles
        ]
    )

    clusters = find_similar_issue_clusters(df2, only_open=False)
    clusters = _dedupe_heuristic_clusters(
        clusters=clusters,
        exact_title_groups_payload=title_groups,
    )
    heur_export = pd.DataFrame(
        [
            {
                "cluster_size": int(getattr(cluster, "size", 0) or 0),
                "summary": str(getattr(cluster, "summary", "") or ""),
                "keys": ", ".join(
                    [
                        str(key).strip()
                        for key in list(getattr(cluster, "keys", []) or [])
                        if str(key).strip()
                    ]
                ),
                "status_dominante": (
                    Counter(
                        [str(status or "") for status in getattr(cluster, "statuses", [])]
                    ).most_common(1)[0][0]
                    if getattr(cluster, "statuses", [])
                    else ""
                ),
                "priority_dominante": (
                    Counter(
                        [str(priority or "") for priority in getattr(cluster, "priorities", [])]
                    ).most_common(1)[0][0]
                    if getattr(cluster, "priorities", [])
                    else ""
                ),
            }
            for cluster in clusters[:12]
        ]
    )

    if not isinstance(duplicate_stats, ExactTitleDuplicateStats):
        duplicate_stats = exact_title_duplicate_stats(df2, summary_col="summary")

    return {
        "top_titles": top_titles,
        "title_export": title_export,
        "clusters": clusters,
        "heur_export": heur_export,
        "key_to_extra": key_to_extra,
        "duplicate_stats": duplicate_stats,
    }
