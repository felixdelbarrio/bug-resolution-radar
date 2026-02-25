"""Dataframe-level insight builders used by analytics and narrative summaries."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import pandas as pd

_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Lightweight stopword list (ES + EN) to avoid clustering on glue words.
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "con",
    "de",
    "del",
    "do",
    "el",
    "en",
    "for",
    "from",
    "if",
    "in",
    "is",
    "la",
    "las",
    "los",
    "no",
    "of",
    "on",
    "or",
    "para",
    "por",
    "que",
    "se",
    "sin",
    "the",
    "to",
    "un",
    "una",
    "with",
    "y",
}


def _tokenize_summary(text: str) -> set[str]:
    if not text:
        return set()
    toks = [t.lower() for t in _WORD_RE.findall(text)]
    out = {t for t in toks if len(t) >= 3 and t not in _STOPWORDS}
    return out


class _DSU:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


@dataclass(frozen=True)
class SimilarityCluster:
    size: int
    summary: str
    keys: list[str]
    priorities: list[str]
    statuses: list[str]


def find_similar_issue_clusters(
    df: pd.DataFrame,
    *,
    only_open: bool = True,
    min_cluster_size: int = 2,
    jaccard_threshold: float = 0.55,
    min_shared_tokens: int = 3,
    max_issues: int = 400,
) -> list[SimilarityCluster]:
    """
    Cheap, dependency-free clustering based on Jaccard(token_set(summary)).

    Notes:
    - Uses an inverted index to avoid O(n^2) on large sets.
    - Caps max_issues for runtime predictability.
    """
    if df.empty or "summary" not in df.columns or "key" not in df.columns:
        return []

    cols = ["summary", "key"]
    if "priority" in df.columns:
        cols.append("priority")
    if "status" in df.columns:
        cols.append("status")

    work = df.loc[:, cols]
    if only_open and "resolved" in df.columns:
        work = work.loc[df["resolved"].isna()]

    work = work.dropna(subset=["summary", "key"])
    if len(work) > max_issues:
        work = work.head(max_issues)
    if work.empty:
        return []

    summaries = work["summary"].astype(str).tolist()
    keys = work["key"].astype(str).tolist()
    priorities = (
        work["priority"].fillna("").astype(str).tolist()
        if "priority" in work.columns
        else [""] * len(work)
    )
    statuses = (
        work["status"].fillna("").astype(str).tolist()
        if "status" in work.columns
        else [""] * len(work)
    )

    toksets = [_tokenize_summary(s) for s in summaries]
    tok_freq: Counter[str] = Counter(t for ts in toksets for t in ts)
    n = len(toksets)

    # Drop ultra-common tokens that create too many candidates.
    too_common = {t for t, c in tok_freq.items() if c >= max(25, int(0.25 * n))}

    token_to_ids: dict[str, list[int]] = defaultdict(list)
    for i, ts in enumerate(toksets):
        for t in ts:
            if t in too_common:
                continue
            token_to_ids[t].append(i)

    dsu = _DSU(n)

    for i, ts in enumerate(toksets):
        if not ts:
            continue
        cand_shared: Counter[int] = Counter()
        for t in ts:
            if t in too_common:
                continue
            for j in token_to_ids.get(t, []):
                if j <= i:
                    continue
                cand_shared[j] += 1

        for j, shared in cand_shared.items():
            if shared < min_shared_tokens:
                continue
            inter = len(toksets[i].intersection(toksets[j]))
            if inter < min_shared_tokens:
                continue
            uni = len(toksets[i].union(toksets[j]))
            if uni == 0:
                continue
            score = inter / uni
            if score >= jaccard_threshold:
                dsu.union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[dsu.find(i)].append(i)

    clusters: list[SimilarityCluster] = []
    for ids in groups.values():
        if len(ids) < min_cluster_size:
            continue
        # Representative summary: most common (or first if all unique).
        rep = Counter(summaries[i] for i in ids).most_common(1)[0][0]
        clusters.append(
            SimilarityCluster(
                size=len(ids),
                summary=rep,
                keys=[keys[i] for i in ids],
                priorities=[priorities[i] for i in ids],
                statuses=[statuses[i] for i in ids],
            )
        )

    clusters.sort(key=lambda c: c.size, reverse=True)
    return clusters
