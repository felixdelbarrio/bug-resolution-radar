"""Executive risk issue lists for period follow-up reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from bug_resolution_radar.analytics.insights import classify_theme
from bug_resolution_radar.analytics.issues import (
    normalize_text_col,
    priority_rank,
    status_progress_rank,
)
from bug_resolution_radar.analytics.status_semantics import effective_closed_mask
from bug_resolution_radar.analytics.topic_expandable_summary import infer_root_cause_label


@dataclass(frozen=True)
class PeriodRiskIssueRow:
    key: str
    summary: str
    functionality: str
    assignee: str
    status: str
    priority: str
    open_days: int
    url: str = ""
    po_team_leader: str = ""


@dataclass(frozen=True)
class PeriodRiskIssueLists:
    high_priority: tuple[PeriodRiskIssueRow, ...]
    aged: tuple[PeriodRiskIssueRow, ...]


_HIGH_PRIORITY_COMPACT_TOKENS: frozenset[str] = frozenset(
    {
        "suponeunimpedimento",
        "impedimento",
        "highest",
        "veryhigh",
        "muyalto",
        "high",
        "alto",
    }
)
_ROOT_CAUSE_COLUMNS: tuple[str, ...] = (
    "root_cause",
    "rootCause",
    "causa_raiz",
    "causa raíz",
    "functionality",
    "funcionalidad",
    "theme",
    "__theme",
)


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


def _analysis_day(df: pd.DataFrame, *, fallback: pd.Timestamp | None = None) -> pd.Timestamp:
    safe = _safe_df(df)
    candidates: list[pd.Timestamp] = []
    for column in ("updated", "created", "resolved"):
        if safe.empty or column not in safe.columns:
            continue
        parsed = _to_dt_naive(safe[column]).dropna()
        if not parsed.empty:
            candidates.append(pd.Timestamp(parsed.max()))
    if candidates:
        return max(candidates).normalize()
    if fallback is not None:
        return pd.Timestamp(fallback).normalize()
    return pd.Timestamp.now().normalize()


def _compact_priority(value: object) -> str:
    token = str(value or "").strip().lower()
    token = token.replace("_", " ").replace("-", " ")
    token = re.sub(r"\s+", " ", token).strip()
    return "".join(ch for ch in token if ch.isalnum())


def _risk_priority_rank(value: object) -> int:
    compact = _compact_priority(value)
    if compact in {"suponeunimpedimento", "impedimento", "highest", "veryhigh", "muyalto"}:
        return 0
    if compact in {"high", "alto"}:
        return 1
    return priority_rank(str(value or ""))


def _is_high_priority(value: object) -> bool:
    return _compact_priority(value) in _HIGH_PRIORITY_COMPACT_TOKENS


def _first_text(row: pd.Series, columns: Sequence[str]) -> str:
    for column in columns:
        if column not in row.index:
            continue
        value = str(row.get(column, "") or "").strip()
        if value:
            return value
    return ""


def _display_functionality(row: pd.Series) -> str:
    explicit = _first_text(row, _ROOT_CAUSE_COLUMNS)
    if explicit:
        return explicit
    summary = str(row.get("summary", "") or "").strip()
    description = str(row.get("description", "") or "").strip()
    theme_hint = classify_theme(summary) if summary else None
    return infer_root_cause_label(summary, description=description, theme_hint=theme_hint)


def _prepare_open_issue_frame(
    df: pd.DataFrame | None,
    *,
    analysis_day: pd.Timestamp | None = None,
    fallback_analysis_day: pd.Timestamp | None = None,
) -> pd.DataFrame:
    safe = _safe_df(df)
    if safe.empty:
        return pd.DataFrame()
    closed_mask = effective_closed_mask(safe)
    open_df = safe.loc[~closed_mask].copy(deep=False)
    if open_df.empty:
        return open_df

    reference_day = pd.Timestamp(
        analysis_day
        if analysis_day is not None
        else _analysis_day(safe, fallback=fallback_analysis_day)
    ).normalize()
    work = open_df.copy(deep=False)
    if "created" in work.columns:
        created = _to_dt_naive(work["created"])
        age_days = ((reference_day - created).dt.total_seconds() / 86400.0).clip(lower=0.0)
        work["__open_days"] = pd.to_numeric(age_days, errors="coerce").fillna(0.0)
    else:
        work["__open_days"] = 0.0
    if "priority" in work.columns:
        work["__priority_rank"] = work["priority"].map(_risk_priority_rank)
        work["__is_high_priority"] = work["priority"].map(_is_high_priority)
    else:
        work["__priority_rank"] = 99
        work["__is_high_priority"] = False
    if "key" in work.columns:
        work["__issue_key"] = work["key"].fillna("").astype(str).str.strip()
    else:
        work["__issue_key"] = ""
    if "status" in work.columns:
        work["__status_rank"] = work["status"].map(status_progress_rank)
    else:
        work["__status_rank"] = 99
    if "assignee" in work.columns:
        work["__assignee"] = (
            normalize_text_col(work["assignee"], "(sin asignar)")
            .astype(str)
            .str.strip()
            .replace("", "(sin asignar)")
        )
    else:
        work["__assignee"] = "(sin asignar)"
    if "po_team_leader" in work.columns:
        work["__po_team_leader"] = work["po_team_leader"].fillna("").astype(str).str.strip()
    else:
        work["__po_team_leader"] = ""
    return work.loc[work["__issue_key"].ne("")].copy(deep=False)


def _rows_from_prepared(df: pd.DataFrame) -> tuple[PeriodRiskIssueRow, ...]:
    safe = _safe_df(df)
    if safe.empty:
        return ()
    rows: list[PeriodRiskIssueRow] = []
    for _, row in safe.iterrows():
        rows.append(
            PeriodRiskIssueRow(
                key=str(row.get("__issue_key", "") or "").strip(),
                summary=str(row.get("summary", "") or "").strip(),
                functionality=_display_functionality(row),
                assignee=str(row.get("__assignee", "(sin asignar)") or "").strip()
                or "(sin asignar)",
                po_team_leader=str(row.get("__po_team_leader", "") or "").strip(),
                status=str(row.get("status", "") or "").strip(),
                priority=str(row.get("priority", "") or "").strip(),
                open_days=int(round(float(row.get("__open_days", 0.0) or 0.0))),
                url=str(row.get("url", "") or "").strip(),
            )
        )
    return tuple(rows)


def _build_high_priority_from_prepared(df: pd.DataFrame) -> tuple[PeriodRiskIssueRow, ...]:
    safe = _safe_df(df)
    if safe.empty:
        return ()
    high = safe.loc[safe["__is_high_priority"].astype(bool)].copy(deep=False)
    if high.empty:
        return ()
    high = high.sort_values(
        by=["__priority_rank", "__open_days", "__status_rank", "__issue_key"],
        ascending=[True, False, True, True],
        kind="mergesort",
    )
    return _rows_from_prepared(high)


def _build_aged_from_prepared(
    df: pd.DataFrame,
    *,
    min_open_days: int,
) -> tuple[PeriodRiskIssueRow, ...]:
    safe = _safe_df(df)
    if safe.empty:
        return ()
    aged = safe.loc[
        pd.to_numeric(safe["__open_days"], errors="coerce").fillna(0.0).gt(min_open_days)
    ]
    aged = aged.copy(deep=False)
    if aged.empty:
        return ()
    aged = aged.sort_values(
        by=["__open_days", "__priority_rank", "__status_rank", "__issue_key"],
        ascending=[False, True, True, True],
        kind="mergesort",
    )
    return _rows_from_prepared(aged)


def build_period_risk_issue_lists(
    df: pd.DataFrame | None,
    *,
    analysis_day: pd.Timestamp | None = None,
    fallback_analysis_day: pd.Timestamp | None = None,
    aged_min_open_days: int = 30,
) -> PeriodRiskIssueLists:
    prepared = _prepare_open_issue_frame(
        df,
        analysis_day=analysis_day,
        fallback_analysis_day=fallback_analysis_day,
    )
    return PeriodRiskIssueLists(
        high_priority=_build_high_priority_from_prepared(prepared),
        aged=_build_aged_from_prepared(prepared, min_open_days=aged_min_open_days),
    )


def build_high_priority_open_issue_list(
    df: pd.DataFrame | None,
    *,
    analysis_day: pd.Timestamp | None = None,
    fallback_analysis_day: pd.Timestamp | None = None,
) -> tuple[PeriodRiskIssueRow, ...]:
    prepared = _prepare_open_issue_frame(
        df,
        analysis_day=analysis_day,
        fallback_analysis_day=fallback_analysis_day,
    )
    return _build_high_priority_from_prepared(prepared)


def build_aged_open_issue_list(
    df: pd.DataFrame | None,
    *,
    analysis_day: pd.Timestamp | None = None,
    fallback_analysis_day: pd.Timestamp | None = None,
    min_open_days: int = 30,
) -> tuple[PeriodRiskIssueRow, ...]:
    prepared = _prepare_open_issue_frame(
        df,
        analysis_day=analysis_day,
        fallback_analysis_day=fallback_analysis_day,
    )
    return _build_aged_from_prepared(prepared, min_open_days=min_open_days)
