"""Centralized functionality follow-up metrics shared by PPT and Insights."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from bug_resolution_radar.analytics.insights import classify_theme, is_other_theme_label
from bug_resolution_radar.analytics.insights_scope import (
    INSIGHTS_VIEW_MODE_QUINCENAL,
    build_insights_combo_context,
)
from bug_resolution_radar.analytics.period_summary import QuincenalScopeResult
from bug_resolution_radar.analytics.topic_expandable_summary import (
    RootCauseRank,
    infer_root_cause_label,
    summarize_root_causes,
)

_MONTH_NAMES_ES: tuple[str, ...] = (
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)
_CRITICAL_PRIORITY_TOKENS: frozenset[str] = frozenset(
    {
        "high",
        "highest",
        "veryhigh",
        "impedimento",
        "suponeunimpedimento",
    }
)


@dataclass(frozen=True)
class FunctionalityTopRow:
    rank: int
    functionality: str
    new_count: int
    open_total: int


@dataclass(frozen=True)
class MitigationBucket:
    count: int
    avg_open_days: float


@dataclass(frozen=True)
class FunctionalityIssueRow:
    key: str
    summary: str
    root_cause: str
    status: str
    priority: str
    open_days: int
    url: str


@dataclass(frozen=True)
class FunctionalityZoomSlide:
    functionality: str
    current_open_critical_count: int
    root_causes: tuple[RootCauseRank, ...]
    issues: tuple[FunctionalityIssueRow, ...]


@dataclass(frozen=True)
class PeriodFunctionalityFollowupSummary:
    period_label: str
    total_open_critical: int
    is_critical_focus: bool
    top_rows: tuple[FunctionalityTopRow, ...]
    tail_rows: tuple[FunctionalityTopRow, ...]
    mitigation_ready_to_verify: MitigationBucket
    mitigation_new: MitigationBucket
    mitigation_blocked: MitigationBucket
    mitigation_non_critical: MitigationBucket
    zoom_slides: tuple[FunctionalityZoomSlide, ...]


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


def _normalize_status(value: object) -> str:
    txt = str(value or "").strip().lower()
    txt = txt.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", txt).strip()


def _compact_token(value: object) -> str:
    token = _normalize_status(value)
    return "".join(ch for ch in token if ch.isalnum())


def _is_critical_priority_selection(priorities: Sequence[str] | None) -> bool:
    selected = [str(v or "").strip() for v in list(priorities or []) if str(v or "").strip()]
    if not selected:
        return False
    normalized = {_compact_token(v) for v in selected}
    if not normalized:
        return False
    return normalized.issubset(_CRITICAL_PRIORITY_TOKENS)


def _apply_combo_filters(
    *,
    open_df: pd.DataFrame,
    status_filters: Sequence[str] | None,
    priority_filters: Sequence[str] | None,
    functionality_filters: Sequence[str] | None,
    apply_default_status_when_empty: bool,
) -> tuple[pd.DataFrame, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    ctx = build_insights_combo_context(
        accumulated_df=open_df,
        quincenal_df=open_df,
        view_mode=INSIGHTS_VIEW_MODE_QUINCENAL,
        selected_statuses=list(status_filters or []),
        selected_priorities=list(priority_filters or []),
        selected_functionalities=list(functionality_filters or []),
        apply_default_status_when_empty=bool(apply_default_status_when_empty),
        theme_col="__theme",
    )
    return (
        _safe_df(ctx.filtered_df),
        tuple(ctx.selected_statuses),
        tuple(ctx.selected_priorities),
        tuple(ctx.selected_functionalities),
    )


def _created_current_window_mask(
    df: pd.DataFrame,
    *,
    created_col: str,
    window_start: pd.Timestamp,
    window_end: pd.Timestamp,
) -> pd.Series:
    if created_col not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)
    created = _to_dt_naive(df[created_col])
    created_day = created.dt.normalize()
    return created_day.notna() & created_day.between(window_start, window_end, inclusive="both")


def _analysis_day(df: pd.DataFrame, *, fallback: pd.Timestamp) -> pd.Timestamp:
    safe = _safe_df(df)
    if safe.empty:
        return pd.Timestamp(fallback).normalize()

    candidates: list[pd.Timestamp] = []
    for col in ("updated", "created", "resolved"):
        if col not in safe.columns:
            continue
        parsed = _to_dt_naive(safe[col]).dropna()
        if parsed.empty:
            continue
        candidates.append(pd.Timestamp(parsed.max()))

    if candidates:
        return max(candidates).normalize()
    return pd.Timestamp(fallback).normalize()


def _period_label_es(start: pd.Timestamp, end: pd.Timestamp) -> str:
    s = pd.Timestamp(start).normalize()
    e = pd.Timestamp(end).normalize()
    s_month = _MONTH_NAMES_ES[max(min(int(s.month), 12), 1) - 1]
    e_month = _MONTH_NAMES_ES[max(min(int(e.month), 12), 1) - 1]
    return f"Quincena {s.strftime('%d')}/{s_month} - {e.strftime('%d')}/{e_month}"


def _avg_open_days(
    df: pd.DataFrame,
    *,
    created_col: str,
    reference_day: pd.Timestamp,
) -> float:
    safe = _safe_df(df)
    if safe.empty or created_col not in safe.columns:
        return 0.0
    created = _to_dt_naive(safe[created_col])
    if created.empty or not created.notna().any():
        return 0.0
    age_days = ((reference_day - created).dt.total_seconds() / 86400.0).clip(lower=0.0)
    return float(pd.to_numeric(age_days, errors="coerce").dropna().mean() or 0.0)


def _build_key_to_url_map(df: pd.DataFrame, *, jira_base_url: str = "") -> dict[str, str]:
    safe = _safe_df(df)
    out: dict[str, str] = {}
    if safe.empty or "key" not in safe.columns:
        return out

    keys = safe["key"].fillna("").astype(str).str.strip()
    if "url" in safe.columns:
        urls = safe["url"].fillna("").astype(str).str.strip()
        for key, url in zip(keys.tolist(), urls.tolist()):
            if key and url and key not in out:
                out[key] = url

    base = str(jira_base_url or "").strip().rstrip("/")
    if base:
        for key in keys.tolist():
            if not key:
                continue
            out.setdefault(key, f"{base}/browse/{key}")
    return out


def _rank_theme_rows(stats: pd.DataFrame) -> list[FunctionalityTopRow]:
    safe = _safe_df(stats)
    if safe.empty:
        return []
    work = safe.copy(deep=False)
    work["functionality"] = work["functionality"].fillna("").astype(str).str.strip()
    work = work[work["functionality"] != ""]
    if work.empty:
        return []

    work["new_count"] = pd.to_numeric(work["new_count"], errors="coerce").fillna(0).astype(int)
    work["open_total"] = pd.to_numeric(work["open_total"], errors="coerce").fillna(0).astype(int)
    work["__is_other"] = work["functionality"].map(is_other_theme_label)
    work = work.sort_values(
        by=["__is_other", "new_count", "open_total", "functionality"],
        ascending=[True, False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    out: list[FunctionalityTopRow] = []
    for idx, row in work.iterrows():
        out.append(
            FunctionalityTopRow(
                rank=int(idx + 1),
                functionality=str(row.get("functionality", "") or "").strip(),
                new_count=int(row.get("new_count", 0) or 0),
                open_total=int(row.get("open_total", 0) or 0),
            )
        )
    return out


def _theme_root_cause_map(df: pd.DataFrame) -> pd.DataFrame:
    safe = _safe_df(df)
    if safe.empty:
        return safe
    if "summary" not in safe.columns:
        work = safe.copy(deep=False)
        work["summary"] = ""
        return work

    work = safe.copy(deep=False)
    summary_series = work["summary"].fillna("").astype(str)
    unique_summaries = pd.unique(summary_series.to_numpy(copy=False)).tolist()
    theme_map = {text: classify_theme(text) for text in unique_summaries}
    cause_map = {text: infer_root_cause_label(text) for text in unique_summaries}
    work["__theme"] = summary_series.map(theme_map).to_numpy(copy=False)
    work["__root_cause"] = summary_series.map(cause_map).to_numpy(copy=False)
    return work


def build_period_functionality_followup_summary(
    *,
    scope_result: QuincenalScopeResult,
    jira_base_url: str = "",
    created_col: str = "created",
    status_col: str = "status",
    priority_col: str = "priority",
    summary_col: str = "summary",
    key_col: str = "key",
    status_filters: Sequence[str] | None = None,
    priority_filters: Sequence[str] | None = None,
    functionality_filters: Sequence[str] | None = None,
    apply_default_status_when_empty: bool = True,
    top_n: int = 3,
    top_root_causes: int = 3,
) -> PeriodFunctionalityFollowupSummary:
    scope = scope_result
    window = scope.summary.window
    period_label = _period_label_es(window.current_start, window.current_end)

    open_base = _theme_root_cause_map(_safe_df(scope.open_df))
    open_filtered, selected_statuses, selected_priorities, selected_functionalities = (
        _apply_combo_filters(
            open_df=open_base,
            status_filters=status_filters,
            priority_filters=priority_filters,
            functionality_filters=functionality_filters,
            apply_default_status_when_empty=apply_default_status_when_empty,
        )
    )
    critical_focus = _is_critical_priority_selection(selected_priorities)

    del selected_statuses, selected_functionalities  # used to drive filtering in shared pipeline

    reference_day = _analysis_day(scope.dff, fallback=window.current_end)
    if open_base.empty:
        zero = MitigationBucket(count=0, avg_open_days=0.0)
        return PeriodFunctionalityFollowupSummary(
            period_label=period_label,
            total_open_critical=0,
            is_critical_focus=critical_focus,
            top_rows=(),
            tail_rows=(),
            mitigation_ready_to_verify=zero,
            mitigation_new=zero,
            mitigation_blocked=zero,
            mitigation_non_critical=zero,
            zoom_slides=(),
        )

    if open_filtered.empty:
        zero = MitigationBucket(count=0, avg_open_days=0.0)
        return PeriodFunctionalityFollowupSummary(
            period_label=period_label,
            total_open_critical=0,
            is_critical_focus=critical_focus,
            top_rows=(),
            tail_rows=(),
            mitigation_ready_to_verify=zero,
            mitigation_new=zero,
            mitigation_blocked=zero,
            mitigation_non_critical=zero,
            zoom_slides=(),
        )

    created_mask = _created_current_window_mask(
        open_filtered,
        created_col=created_col,
        window_start=window.current_start,
        window_end=window.current_end,
    )
    status_norm = (
        open_filtered[status_col].map(_normalize_status)
        if status_col in open_filtered.columns
        else pd.Series("", index=open_filtered.index, dtype=str)
    )

    open_current = open_filtered.loc[created_mask].copy(deep=False)

    theme_total = (
        open_filtered["__theme"].value_counts().rename_axis("functionality").rename("open_total")
        if not open_filtered.empty
        else pd.Series(dtype="int64", name="open_total")
    )
    theme_new = (
        open_current["__theme"].value_counts().rename_axis("functionality").rename("new_count")
        if not open_current.empty
        else pd.Series(dtype="int64", name="new_count")
    )
    theme_stats = pd.concat([theme_new, theme_total], axis=1).fillna(0).reset_index()
    theme_rows = _rank_theme_rows(theme_stats)

    top_n_safe = max(int(top_n or 3), 1)
    top_rows = tuple(theme_rows[:top_n_safe])
    tail_rows = tuple(theme_rows[top_n_safe:])

    def _bucket(mask: pd.Series, df: pd.DataFrame) -> MitigationBucket:
        subset = df.loc[mask].copy(deep=False) if not df.empty else pd.DataFrame()
        return MitigationBucket(
            count=int(len(subset)),
            avg_open_days=float(
                _avg_open_days(subset, created_col=created_col, reference_day=reference_day)
            ),
        )

    ready_mask = status_norm.str.contains("ready to verify", regex=False)
    new_mask = status_norm.eq("new") | status_norm.str.startswith("new ")
    blocked_mask = status_norm.str.contains("block", regex=False) | status_norm.str.contains(
        "bloque", regex=False
    )
    covered_mask = ready_mask | new_mask | blocked_mask

    mitigation_ready = _bucket(ready_mask.loc[open_filtered.index], open_filtered)
    mitigation_new = _bucket(new_mask.loc[open_filtered.index], open_filtered)
    mitigation_blocked = _bucket(blocked_mask.loc[open_filtered.index], open_filtered)
    mitigation_non_critical = _bucket(~covered_mask.loc[open_filtered.index], open_filtered)

    key_to_url = _build_key_to_url_map(scope.dff, jira_base_url=jira_base_url)
    zoom_themes = [row.functionality for row in list(top_rows)[:top_n_safe]]
    zoom_slides: list[FunctionalityZoomSlide] = []
    for functionality in zoom_themes:
        sub = open_current.loc[
            open_current["__theme"].fillna("").astype(str).eq(functionality)
        ].copy(deep=False)
        roots = summarize_root_causes(
            sub[summary_col].fillna("").astype(str).tolist() if summary_col in sub.columns else [],
            top_k=top_root_causes,
        )
        created = (
            _to_dt_naive(sub[created_col])
            if created_col in sub.columns
            else pd.Series(pd.NaT, index=sub.index, dtype="datetime64[ns]")
        )
        age_days = ((reference_day - created).dt.total_seconds() / 86400.0).clip(lower=0.0)
        work = sub.copy(deep=False)
        work["__open_days"] = pd.to_numeric(age_days, errors="coerce").fillna(0.0)
        sort_cols = ["__open_days"]
        ascending = [False]
        if key_col in work.columns:
            sort_cols.append(key_col)
            ascending.append(True)
        work = work.sort_values(sort_cols, ascending=ascending, kind="mergesort")

        issue_rows: list[FunctionalityIssueRow] = []
        for _, row in work.iterrows():
            key = str(row.get(key_col, "") or "").strip() if key_col in work.columns else ""
            if not key:
                continue
            summary = (
                str(row.get(summary_col, "") or "").strip() if summary_col in work.columns else ""
            )
            status = (
                str(row.get(status_col, "") or "").strip() if status_col in work.columns else ""
            )
            priority = (
                str(row.get(priority_col, "") or "").strip() if priority_col in work.columns else ""
            )
            root = str(row.get("__root_cause", "") or "").strip() or infer_root_cause_label(summary)
            issue_rows.append(
                FunctionalityIssueRow(
                    key=key,
                    summary=summary,
                    root_cause=root,
                    status=status,
                    priority=priority,
                    open_days=max(int(round(float(row.get("__open_days", 0.0) or 0.0))), 0),
                    url=str(key_to_url.get(key, "") or "").strip(),
                )
            )

        zoom_slides.append(
            FunctionalityZoomSlide(
                functionality=functionality,
                current_open_critical_count=int(len(sub)),
                root_causes=tuple(roots),
                issues=tuple(issue_rows),
            )
        )

    return PeriodFunctionalityFollowupSummary(
        period_label=period_label,
        total_open_critical=int(len(open_filtered)),
        is_critical_focus=critical_focus,
        top_rows=top_rows,
        tail_rows=tail_rows,
        mitigation_ready_to_verify=mitigation_ready,
        mitigation_new=mitigation_new,
        mitigation_blocked=mitigation_blocked,
        mitigation_non_critical=mitigation_non_critical,
        zoom_slides=tuple(zoom_slides),
    )
