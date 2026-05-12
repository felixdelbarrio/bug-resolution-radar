"""Pure quincenal KPI calculators for issue flows and resolution metrics."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from bug_resolution_radar.analytics.status_semantics import (
    is_core_final_status,
    is_finalist_status,
)
from bug_resolution_radar.analytics.time_windows import QuincenalWindow


def _empty_bool(index: pd.Index) -> pd.Series:
    return pd.Series(False, index=index, dtype=bool)


def _to_utc_naive(series: pd.Series | None, *, index: pd.Index) -> pd.Series:
    if series is None:
        return pd.Series(pd.NaT, index=index, dtype="datetime64[ns]")
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    try:
        return parsed.dt.tz_convert(None)
    except Exception:
        try:
            return parsed.dt.tz_localize(None)
        except Exception:
            return parsed


@dataclass(frozen=True)
class NormalizedIssueFrame:
    df: pd.DataFrame
    created_at: pd.Series
    updated_at: pd.Series
    resolved_at: pd.Series
    finalized_at: pd.Series
    closed_mask: pd.Series

    @classmethod
    def from_df(cls, df: pd.DataFrame | None) -> "NormalizedIssueFrame":
        safe = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        index = safe.index
        created = _to_utc_naive(safe["created"] if "created" in safe.columns else None, index=index)
        updated = _to_utc_naive(safe["updated"] if "updated" in safe.columns else None, index=index)
        resolved = _to_utc_naive(
            safe["resolved"] if "resolved" in safe.columns else None,
            index=index,
        )

        if "status" in safe.columns:
            status = safe["status"].fillna("").astype(str)
            finalist_status = status.map(is_finalist_status).fillna(False).astype(bool)
            core_final_status = status.map(is_core_final_status).fillna(False).astype(bool)
        else:
            finalist_status = _empty_bool(index)
            core_final_status = _empty_bool(index)

        closed = resolved.notna() | finalist_status
        finalized = resolved.copy()
        proxy_mask = finalized.isna() & core_final_status & updated.notna()
        if proxy_mask.any():
            finalized.loc[proxy_mask] = updated.loc[proxy_mask]
        finalized = finalized.where(resolved.notna() | core_final_status)

        return cls(
            df=safe,
            created_at=created,
            updated_at=updated,
            resolved_at=resolved,
            finalized_at=finalized,
            closed_mask=closed.fillna(False).astype(bool),
        )

    @property
    def created_day(self) -> pd.Series:
        return self.created_at.dt.normalize()

    @property
    def finalized_day(self) -> pd.Series:
        return self.finalized_at.dt.normalize()

    @property
    def resolved_day(self) -> pd.Series:
        return self.resolved_at.dt.normalize()


@dataclass(frozen=True)
class CreatedIncidentsResult:
    current_mask: pd.Series
    previous_mask: pd.Series
    total_mask: pd.Series
    current: int
    previous: int
    total: int


class CreatedIncidentsCalculator:
    def calculate(
        self,
        frame: NormalizedIssueFrame,
        *,
        window: QuincenalWindow,
    ) -> CreatedIncidentsResult:
        created_day = frame.created_day
        current_start = pd.Timestamp(window.current_start)
        current_end = pd.Timestamp(window.current_end)
        previous_start = pd.Timestamp(window.previous_start)
        previous_end = pd.Timestamp(window.previous_end)
        current = created_day.between(current_start, current_end, inclusive="both")
        previous = created_day.between(
            previous_start,
            previous_end,
            inclusive="both",
        )
        current = current.fillna(False).astype(bool)
        previous = previous.fillna(False).astype(bool)
        total = (current | previous).fillna(False).astype(bool)
        return CreatedIncidentsResult(
            current_mask=current,
            previous_mask=previous,
            total_mask=total,
            current=int(current.sum()),
            previous=int(previous.sum()),
            total=int(total.sum()),
        )


@dataclass(frozen=True)
class ClosedIncidentsResult:
    current_mask: pd.Series
    previous_mask: pd.Series
    current: int
    previous: int


class ClosedIncidentsCalculator:
    def calculate(
        self,
        frame: NormalizedIssueFrame,
        *,
        window: QuincenalWindow,
    ) -> ClosedIncidentsResult:
        resolved_day = frame.resolved_day
        assignable_closed = frame.resolved_at.notna()
        current_start = pd.Timestamp(window.current_start)
        current_end = pd.Timestamp(window.current_end)
        previous_start = pd.Timestamp(window.previous_start)
        previous_end = pd.Timestamp(window.previous_end)
        current = assignable_closed & resolved_day.between(
            current_start,
            current_end,
            inclusive="both",
        )
        previous = assignable_closed & resolved_day.between(
            previous_start,
            previous_end,
            inclusive="both",
        )
        current = current.fillna(False).astype(bool)
        previous = previous.fillna(False).astype(bool)
        return ClosedIncidentsResult(
            current_mask=current,
            previous_mask=previous,
            current=int(current.sum()),
            previous=int(previous.sum()),
        )


@dataclass(frozen=True)
class ResolutionMetricsResult:
    current_mask: pd.Series
    previous_mask: pd.Series
    current_days: pd.Series
    previous_days: pd.Series
    current_mean: float | None
    current_min: float | None
    current_max: float | None
    previous_mean: float | None


def _stats(values: pd.Series) -> tuple[float | None, float | None, float | None]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return None, None, None
    return float(clean.mean()), float(clean.min()), float(clean.max())


class ResolutionMetricsCalculator:
    def calculate(
        self,
        frame: NormalizedIssueFrame,
        *,
        window: QuincenalWindow,
    ) -> ResolutionMetricsResult:
        resolved_day = frame.resolved_day
        raw_days = (frame.resolved_at - frame.created_at).dt.total_seconds() / 86400.0
        valid = (
            frame.created_at.notna()
            & frame.resolved_at.notna()
            & raw_days.notna()
            & raw_days.ge(0.0)
        )
        current_start = pd.Timestamp(window.current_start)
        current_end = pd.Timestamp(window.current_end)
        previous_start = pd.Timestamp(window.previous_start)
        previous_end = pd.Timestamp(window.previous_end)
        current = valid & resolved_day.between(
            current_start,
            current_end,
            inclusive="both",
        )
        previous = valid & resolved_day.between(
            previous_start,
            previous_end,
            inclusive="both",
        )
        current = current.fillna(False).astype(bool)
        previous = previous.fillna(False).astype(bool)
        current_days = raw_days.loc[current].astype(float)
        previous_days = raw_days.loc[previous].astype(float)
        current_mean, current_min, current_max = _stats(current_days)
        previous_mean, _, _ = _stats(previous_days)
        return ResolutionMetricsResult(
            current_mask=current,
            previous_mask=previous,
            current_days=current_days,
            previous_days=previous_days,
            current_mean=current_mean,
            current_min=current_min,
            current_max=current_max,
            previous_mean=previous_mean,
        )


def build_inclusion_debug_frame(
    frame: NormalizedIssueFrame,
    *,
    window: QuincenalWindow,
    id_col: str = "key",
) -> pd.DataFrame:
    """Return current-window inclusion flags for tests and diagnostics."""

    created = CreatedIncidentsCalculator().calculate(frame, window=window)
    closed = ClosedIncidentsCalculator().calculate(frame, window=window)
    if id_col in frame.df.columns:
        issue_ids = frame.df[id_col].fillna("").astype(str)
    elif "id" in frame.df.columns:
        issue_ids = frame.df["id"].fillna("").astype(str)
    else:
        issue_ids = pd.Series(frame.df.index.astype(str), index=frame.df.index, dtype=str)

    return pd.DataFrame(
        {
            "ID": issue_ids,
            "created_date": frame.created_at.dt.strftime("%Y-%m-%d").fillna(""),
            "resolved_date": frame.resolved_at.dt.strftime("%Y-%m-%d").fillna(""),
            "included_in_created": created.current_mask.astype(bool),
            "included_in_closed": closed.current_mask.astype(bool),
        },
        index=frame.df.index,
    ).reset_index(drop=True)
