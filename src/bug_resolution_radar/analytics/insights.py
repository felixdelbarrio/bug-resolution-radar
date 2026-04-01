"""Dataframe-level insight builders used by analytics and narrative summaries."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

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

THEME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Softoken", ("softoken", "token", "firma", "otp")),
    ("Cr\u00e9dito", ("credito", "cr\u00e9dito", "cvv", "tarjeta", "tdc")),
    ("Monetarias", ("monetarias", "saldo", "nomina", "n\u00f3mina")),
    ("Tareas", ("tareas", "task", "acciones", "dashboard")),
    ("Pagos", ("pago", "pagos", "tpv", "cobranza")),
    ("Transferencias", ("transferencia", "spei", "swift", "divisas")),
    ("Login y acceso", ("login", "acceso", "face id", "biometr", "password", "tokenbnc")),
    ("Notificaciones", ("notificacion", "notificaci\u00f3n", "push", "mensaje")),
)

THEME_LEGEND_PRIORITY: tuple[str, ...] = (
    "Pagos",
    "Monetarias",
    "Login y acceso",
    "Transferencias",
    "Notificaciones",
    "Otros",
)

_EMPTY_THEME_TREND_COLUMNS: tuple[str, ...] = (
    "quincena_start",
    "quincena_end",
    "quincena_label",
    "tema",
    "issues",
    "issues_cumulative",
    "issues_value",
)
_EMPTY_THEME_DAILY_COLUMNS: tuple[str, ...] = (
    "date",
    "date_label",
    "tema",
    "issues",
    "issues_value",
)
_OTHER_THEME_TOKENS: tuple[str, ...] = ("otros", "other")


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _to_dt_naive(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(series, errors="coerce", utc=True)
    try:
        return out.dt.tz_convert(None)
    except Exception:
        try:
            return out.dt.tz_localize(None)
        except Exception:
            return out


def _normalize_theme_token(value: object) -> str:
    txt = str(value or "").strip().lower()
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return txt


def is_other_theme_label(value: object) -> bool:
    return _normalize_theme_token(value) in _OTHER_THEME_TOKENS


def _ordered_unique_theme_labels(labels: Iterable[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in labels:
        label = str(raw or "").strip()
        if not label:
            continue
        token = label.casefold()
        if token in seen:
            continue
        seen.add(token)
        out.append(label)
    return out


def _coerce_theme_count(value: object) -> int:
    try:
        if pd.isna(value):
            return 0
    except Exception:
        pass

    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value)

    token = str(value or "").strip()
    if not token:
        return 0
    try:
        return int(float(token))
    except Exception:
        return 0


def _theme_count_maps(
    counts_by_label: Mapping[object, object] | pd.Series | None,
) -> tuple[dict[str, int], dict[str, int]]:
    exact: dict[str, int] = {}
    normalized: dict[str, int] = {}
    if counts_by_label is None:
        return exact, normalized

    items: Iterable[tuple[object, object]]
    if isinstance(counts_by_label, pd.Series):
        items = counts_by_label.items()
    else:
        items = counts_by_label.items()

    for raw_label, raw_count in items:
        label = str(raw_label or "").strip()
        if not label:
            continue
        count = _coerce_theme_count(raw_count)
        exact[label] = count
        norm = _normalize_theme_token(label)
        if not norm:
            continue
        if norm not in normalized or count > normalized[norm]:
            normalized[norm] = count
    return exact, normalized


def order_theme_labels_by_volume(
    labels: Iterable[object],
    *,
    counts_by_label: Mapping[object, object] | pd.Series | None = None,
    others_last: bool = True,
) -> list[str]:
    unique = _ordered_unique_theme_labels(labels)
    if not unique:
        return []

    has_counts = counts_by_label is not None
    exact_counts, normalized_counts = _theme_count_maps(counts_by_label)
    order_pos = {label: idx for idx, label in enumerate(unique)}

    def _count_for(label: str) -> int:
        if label in exact_counts:
            return exact_counts[label]
        return normalized_counts.get(_normalize_theme_token(label), 0)

    return sorted(
        unique,
        key=lambda label: (
            bool(others_last and is_other_theme_label(label)),
            -_count_for(label),
            _normalize_theme_token(label) if has_counts else "",
            order_pos[label],
        ),
    )


def sort_theme_table_by_volume(
    top_tbl: pd.DataFrame,
    *,
    label_col: str = "tema",
    count_col: str = "open_count",
    others_last: bool = True,
) -> pd.DataFrame:
    if not isinstance(top_tbl, pd.DataFrame) or top_tbl.empty:
        return top_tbl
    if label_col not in top_tbl.columns or count_col not in top_tbl.columns:
        return top_tbl

    work = top_tbl.copy(deep=False)
    labels = work[label_col].fillna("").astype(str).str.strip()
    counts = pd.to_numeric(work[count_col], errors="coerce").fillna(0).astype(int)
    work[label_col] = labels
    work[count_col] = counts

    ordered_labels = order_theme_labels_by_volume(
        labels.tolist(),
        counts_by_label=dict(zip(labels.tolist(), counts.tolist())),
        others_last=others_last,
    )
    if not ordered_labels:
        return work.loc[:, top_tbl.columns].reset_index(drop=True)

    order_map = {label: idx for idx, label in enumerate(ordered_labels)}
    work["__theme_order"] = work[label_col].map(order_map).fillna(len(order_map)).astype(int)
    ordered = work.sort_values(
        by=["__theme_order", count_col],
        ascending=[True, False],
        kind="mergesort",
    )
    return ordered.loc[:, top_tbl.columns].reset_index(drop=True)


def classify_theme(
    summary: object,
    *,
    theme_rules: Sequence[tuple[str, Sequence[str]]] | None = None,
    default_theme: str = "Otros",
) -> str:
    """Map an issue summary to a functional theme bucket."""
    text = _normalize_theme_token(summary)
    if not text:
        return default_theme

    rules = list(theme_rules or THEME_RULES)
    for theme_name, keys in rules:
        for kw in list(keys or []):
            token = _normalize_theme_token(kw)
            if token and re.search(rf"\b{re.escape(token)}\b", text):
                return str(theme_name)
    return default_theme


def theme_counts(open_df: pd.DataFrame) -> pd.Series:
    """Count open issues by classified theme, excluding blank summaries."""
    df = _safe_df(open_df)
    if df.empty or "summary" not in df.columns:
        return pd.Series(dtype="int64")
    summaries = df["summary"].fillna("").astype(str).str.strip()
    summaries = summaries[summaries != ""]
    if summaries.empty:
        return pd.Series(dtype="int64")
    return summaries.map(classify_theme).value_counts()


def top_non_other_theme(open_df: pd.DataFrame) -> tuple[str, int]:
    vc = theme_counts(open_df)
    if vc.empty:
        return "-", 0
    non_other = vc[~vc.index.astype(str).map(is_other_theme_label)]
    if non_other.empty:
        return "\u2014", 0
    return str(non_other.index[0]), int(non_other.iloc[0])


def order_theme_labels(
    labels: Iterable[object],
    *,
    priority: Sequence[str] | None = None,
) -> list[str]:
    """Return deduplicated labels with business-priority themes first."""
    unique: list[str] = []
    seen: set[str] = set()
    for raw in labels:
        label = str(raw or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        unique.append(label)
    if not unique:
        return []

    preferred = list(priority or THEME_LEGEND_PRIORITY)
    head = [theme for theme in preferred if theme in seen]
    tail = [theme for theme in unique if theme not in set(head)]
    return head + tail


def prepare_open_theme_payload(
    open_df: pd.DataFrame,
    *,
    top_n: int = 10,
) -> dict[str, pd.DataFrame]:
    """Build top-theme payload for open issues (shared by UI and reports)."""
    tmp_open = _safe_df(open_df).copy(deep=False)
    empty_tbl = pd.DataFrame(columns=["tema", "open_count", "pct_open"])
    if tmp_open.empty:
        return {"tmp_open": tmp_open, "top_tbl": empty_tbl}

    if "summary" not in tmp_open.columns:
        return {"tmp_open": tmp_open, "top_tbl": empty_tbl}

    tmp_open["summary"] = tmp_open["summary"].fillna("").astype(str)
    tmp_open["__theme"] = tmp_open["summary"].map(classify_theme)
    counts = tmp_open["__theme"].value_counts().sort_values(ascending=False)
    if counts.empty:
        return {"tmp_open": tmp_open, "top_tbl": empty_tbl}

    top_n_safe = max(int(top_n or 10), 1)
    labels = [str(t) for t in counts.index.tolist()]
    non_other = [theme for theme in labels if not is_other_theme_label(theme)]
    other_labels = [theme for theme in labels if is_other_theme_label(theme)]
    if other_labels:
        other_label = other_labels[0]
        body_limit = max(top_n_safe - 1, 0)
        if len(non_other) > body_limit:
            top_themes = non_other[:body_limit] + [other_label]
        else:
            top_themes = non_other + [other_label]
    else:
        top_themes = non_other[:top_n_safe]

    total_open = int(len(tmp_open))
    top_tbl = pd.DataFrame(
        {
            "tema": top_themes,
            "open_count": [int(counts[t]) for t in top_themes],
            "pct_open": [
                (float(counts[t]) / float(total_open) * 100.0 if total_open else 0.0)
                for t in top_themes
            ],
        }
    )
    top_tbl = sort_theme_table_by_volume(top_tbl)
    return {"tmp_open": tmp_open, "top_tbl": top_tbl}


def _quincena_axis(created: pd.Series) -> pd.DataFrame:
    month_start = created.dt.to_period("M").dt.to_timestamp()
    month_end = month_start + pd.offsets.MonthEnd(0)
    first_half = created.dt.day <= 15
    quincena_start = month_start.where(first_half, month_start + pd.Timedelta(days=15))
    quincena_end = (month_start + pd.Timedelta(days=14)).where(first_half, month_end)
    month_label = month_start.dt.strftime("%Y-%m")
    quincena_label = (month_label + " \u00b7 1-15").where(
        first_half,
        month_label + " \u00b7 16-" + month_end.dt.day.astype(str),
    )
    return pd.DataFrame(
        {
            "quincena_start": quincena_start,
            "quincena_end": quincena_end,
            "quincena_label": quincena_label,
        }
    )


def _daily_axis(created: pd.Series) -> pd.DataFrame:
    quincena = _quincena_axis(created)
    day_start = pd.Timestamp(quincena["quincena_start"].min()).normalize()
    day_end = pd.Timestamp(quincena["quincena_end"].max()).normalize()
    days = pd.date_range(start=day_start, end=day_end, freq="D")
    return pd.DataFrame(
        {
            "date": days,
            "date_label": days.strftime("%Y-%m-%d"),
        }
    )


def build_theme_daily_trend(
    df: pd.DataFrame,
    *,
    theme_whitelist: Sequence[str] | None = None,
    theme_rules: Sequence[tuple[str, Sequence[str]]] | None = None,
) -> pd.DataFrame:
    """
    Build daily trend points by theme for the analyzed fortnight scope.

    Returns a normalized long table with:
    - date / date_label
    - tema
    - issues (daily count)
    - issues_value (alias for charting)
    """
    safe = _safe_df(df)
    if safe.empty or "created" not in safe.columns or "summary" not in safe.columns:
        return pd.DataFrame(columns=list(_EMPTY_THEME_DAILY_COLUMNS))

    work = safe.loc[:, ["created", "summary"]].copy(deep=False)
    work["summary"] = work["summary"].fillna("").astype(str)
    created = _to_dt_naive(work["created"])
    valid = created.notna()
    if not bool(valid.any()):
        return pd.DataFrame(columns=list(_EMPTY_THEME_DAILY_COLUMNS))

    work = work.loc[valid].copy(deep=False)
    created = created.loc[valid]
    work["date"] = created.dt.floor("D").to_numpy(copy=False)
    work["tema"] = [
        classify_theme(summary, theme_rules=theme_rules) for summary in work["summary"].tolist()
    ]

    theme_order: list[str]
    if theme_whitelist is not None:
        requested_order = order_theme_labels_by_volume(theme_whitelist, others_last=True)
        present = set(work["tema"].unique().tolist())
        theme_order = [theme for theme in requested_order if theme in present]
        if not theme_order:
            return pd.DataFrame(columns=list(_EMPTY_THEME_DAILY_COLUMNS))
        work = work.loc[work["tema"].isin(theme_order)].copy(deep=False)
    else:
        totals = work["tema"].value_counts()
        theme_order = order_theme_labels_by_volume(
            totals.index.tolist(),
            counts_by_label=totals,
            others_last=True,
        )
        if not theme_order:
            return pd.DataFrame(columns=list(_EMPTY_THEME_DAILY_COLUMNS))

    grouped = (
        work.groupby(["date", "tema"], as_index=False).size().rename(columns={"size": "issues"})
    )
    day_axis = _daily_axis(created)
    if day_axis.empty:
        return pd.DataFrame(columns=list(_EMPTY_THEME_DAILY_COLUMNS))

    grid = pd.MultiIndex.from_product(
        [day_axis["date"].tolist(), theme_order],
        names=["date", "tema"],
    ).to_frame(index=False)
    trend = (
        grid.merge(day_axis, on="date", how="left")
        .merge(grouped, on=["date", "tema"], how="left")
        .fillna({"issues": 0})
    )
    trend["issues"] = pd.to_numeric(trend["issues"], errors="coerce").fillna(0).astype(int)
    trend["tema"] = pd.Categorical(trend["tema"], categories=theme_order, ordered=True)
    trend = trend.sort_values(["date", "tema"], ascending=[True, True]).reset_index(drop=True)
    trend["issues_value"] = trend["issues"]
    trend["tema"] = trend["tema"].astype(str)
    return trend.loc[:, list(_EMPTY_THEME_DAILY_COLUMNS)]


def build_theme_fortnight_trend(
    df: pd.DataFrame,
    *,
    theme_whitelist: Sequence[str] | None = None,
    cumulative: bool = False,
    theme_rules: Sequence[tuple[str, Sequence[str]]] | None = None,
) -> pd.DataFrame:
    """
    Build fortnight trend points by theme.

    Returns a normalized long table with:
    - quincena_start / quincena_end / quincena_label
    - tema
    - issues (fortnight count)
    - issues_cumulative (running total by theme)
    - issues_value (issues or issues_cumulative based on `cumulative`)
    """
    safe = _safe_df(df)
    if safe.empty or "created" not in safe.columns or "summary" not in safe.columns:
        return pd.DataFrame(columns=list(_EMPTY_THEME_TREND_COLUMNS))

    work = safe.loc[:, ["created", "summary"]].copy(deep=False)
    work["summary"] = work["summary"].fillna("").astype(str)
    created = _to_dt_naive(work["created"])
    valid = created.notna()
    if not bool(valid.any()):
        return pd.DataFrame(columns=list(_EMPTY_THEME_TREND_COLUMNS))

    work = work.loc[valid].copy(deep=False)
    created = created.loc[valid]
    axis = _quincena_axis(created)
    work["quincena_start"] = axis["quincena_start"].to_numpy(copy=False)
    work["quincena_end"] = axis["quincena_end"].to_numpy(copy=False)
    work["quincena_label"] = axis["quincena_label"].to_numpy(copy=False)
    work["tema"] = [
        classify_theme(summary, theme_rules=theme_rules) for summary in work["summary"].tolist()
    ]

    theme_order: list[str]
    if theme_whitelist is not None:
        requested_order = order_theme_labels_by_volume(theme_whitelist, others_last=True)
        present = set(work["tema"].unique().tolist())
        theme_order = [theme for theme in requested_order if theme in present]
        if not theme_order:
            return pd.DataFrame(columns=list(_EMPTY_THEME_TREND_COLUMNS))
        work = work.loc[work["tema"].isin(theme_order)].copy(deep=False)
    else:
        totals = work["tema"].value_counts()
        theme_order = order_theme_labels_by_volume(
            totals.index.tolist(),
            counts_by_label=totals,
            others_last=True,
        )
        if not theme_order:
            return pd.DataFrame(columns=list(_EMPTY_THEME_TREND_COLUMNS))

    grouped = (
        work.groupby(
            ["quincena_start", "quincena_end", "quincena_label", "tema"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "issues"})
    )

    axis_tbl = (
        grouped.loc[:, ["quincena_start", "quincena_end", "quincena_label"]]
        .drop_duplicates(subset=["quincena_start"])
        .sort_values("quincena_start", ascending=True)
    )
    if axis_tbl.empty:
        return pd.DataFrame(columns=list(_EMPTY_THEME_TREND_COLUMNS))

    grid = pd.MultiIndex.from_product(
        [axis_tbl["quincena_start"].tolist(), theme_order],
        names=["quincena_start", "tema"],
    ).to_frame(index=False)

    trend = (
        grid.merge(axis_tbl, on="quincena_start", how="left")
        .merge(
            grouped.loc[:, ["quincena_start", "tema", "issues"]],
            on=["quincena_start", "tema"],
            how="left",
        )
        .fillna({"issues": 0})
    )
    trend["issues"] = pd.to_numeric(trend["issues"], errors="coerce").fillna(0).astype(int)
    trend["tema"] = pd.Categorical(trend["tema"], categories=theme_order, ordered=True)
    trend = trend.sort_values(["quincena_start", "tema"], ascending=[True, True]).reset_index(
        drop=True
    )
    trend["issues_cumulative"] = (
        trend.groupby("tema", observed=False)["issues"].cumsum().astype(int)
    )
    if cumulative:
        trend["issues_value"] = trend["issues_cumulative"]
    else:
        trend["issues_value"] = trend["issues"]
    trend["tema"] = trend["tema"].astype(str)
    return trend.loc[:, list(_EMPTY_THEME_TREND_COLUMNS)]


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
