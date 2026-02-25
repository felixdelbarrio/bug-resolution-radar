"""KPI computation functions for backlog monitoring views."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pandas as pd
import plotly.express as px

from bug_resolution_radar.config import Settings
from .status_semantics import effective_closed_mask

_DT_COLS = ("created", "updated", "resolved")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_datetime_columns(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    if df.empty:
        return df.copy(deep=False)

    needs_cast = []
    for col in _DT_COLS:
        if col not in df.columns:
            continue
        col_dtype = df[col].dtype
        if not isinstance(col_dtype, pd.DatetimeTZDtype):
            needs_cast.append(col)

    if not needs_cast:
        return df.copy(deep=False)

    out = df.copy(deep=False)
    for col in needs_cast:
        out[col] = pd.to_datetime(out[col], utc=True, errors="coerce")
    return out


def _empty_timeseries_chart() -> Any:
    empty_ts = pd.DataFrame(
        {
            "date": pd.to_datetime([]),
            "created": pd.Series(dtype=float),
            "closed": pd.Series(dtype=float),
            "open_backlog_proxy": pd.Series(dtype=float),
        }
    )
    return px.line(empty_ts, x="date", y=["created", "closed", "open_backlog_proxy"])


def compute_kpis(df: pd.DataFrame, settings: Settings) -> Dict[str, Any]:
    now = pd.Timestamp(_utcnow())
    _ = settings  # signature preserved for API compatibility
    work_df = _ensure_datetime_columns(df)

    if work_df.empty:
        return {
            "issues_total": 0,
            "issues_open": 0,
            "issues_closed": 0,
            "open_now_total": 0,
            "open_now_by_priority": {},
            "mean_resolution_days": 0.0,
            "mean_resolution_days_by_priority": {},
            "timeseries_chart": _empty_timeseries_chart(),
            "top_open_table": pd.DataFrame(columns=["summary", "open_count"]),
        }

    total_issues = int(len(work_df))
    has_created = "created" in work_df.columns
    has_resolved = "resolved" in work_df.columns
    has_priority = "priority" in work_df.columns
    has_summary = "summary" in work_df.columns

    if has_created:
        created = work_df["created"]
    else:
        created = pd.Series(pd.NaT, index=work_df.index, dtype="datetime64[ns, UTC]")

    if has_resolved:
        resolved = work_df["resolved"]
    else:
        resolved = pd.Series(pd.NaT, index=work_df.index, dtype="datetime64[ns, UTC]")

    created_notna = created.notna()
    resolved_notna = resolved.notna()
    closed_mask = effective_closed_mask(work_df)
    open_mask = ~closed_mask
    open_now_total = int(open_mask.sum())
    priority = work_df["priority"].fillna("").astype(str) if has_priority else pd.Series(dtype=str)

    def by_priority_mask(mask: pd.Series) -> Dict[str, int]:
        if not has_priority:
            return {}
        counts = priority.loc[mask].value_counts()
        return {str(priority_name): int(count) for priority_name, count in counts.items()}

    closed_all_mask = created_notna & resolved_notna

    resolution_days = (
        (
            (resolved.loc[closed_all_mask] - created.loc[closed_all_mask]).dt.total_seconds()
            / 86400.0
        )
        .clip(lower=0.0)
        .astype(float)
    )
    if resolution_days.empty:
        mean_resolution_days = 0.0
        mean_by_priority: Dict[str, float] = {}
    else:
        mean_resolution_days = float(resolution_days.mean())
        if has_priority:
            res_df = pd.DataFrame(
                {
                    "priority": priority.loc[closed_all_mask].to_numpy(),
                    "res_days": resolution_days.to_numpy(),
                }
            )
            grouped = (
                res_df.groupby("priority", dropna=False)["res_days"].mean().sort_values().round(2)
            )
            mean_by_priority = grouped.to_dict()
        else:
            mean_by_priority = {}

    range_days = 90
    start = now - timedelta(days=range_days)

    created_daily = (
        created.loc[created_notna & (created >= start)].dt.floor("D").value_counts(sort=False)
        if has_created
        else pd.Series(dtype=int)
    )
    closed_daily = (
        resolved.loc[resolved_notna & (resolved >= start)].dt.floor("D").value_counts(sort=False)
        if has_resolved
        else pd.Series(dtype=int)
    )

    if created_daily.empty and closed_daily.empty:
        timeseries_chart = _empty_timeseries_chart()
    else:
        all_dates = created_daily.index.union(closed_daily.index).sort_values()
        daily = pd.DataFrame({"date": all_dates})
        daily["created"] = created_daily.reindex(all_dates, fill_value=0).to_numpy()
        daily["closed"] = closed_daily.reindex(all_dates, fill_value=0).to_numpy()
        daily["open_backlog_proxy"] = (daily["created"] - daily["closed"]).cumsum()
        timeseries_chart = px.line(daily, x="date", y=["created", "closed", "open_backlog_proxy"])

    if open_now_total > 0 and has_summary:
        top_open = (
            work_df.loc[open_mask, "summary"]
            .fillna("")
            .astype(str)
            .value_counts()
            .head(10)
            .rename_axis("summary")
            .reset_index(name="open_count")
        )
    else:
        top_open = pd.DataFrame(columns=["summary", "open_count"])

    return {
        "issues_total": total_issues,
        "issues_open": open_now_total,
        "issues_closed": max(total_issues - open_now_total, 0),
        "open_now_total": open_now_total,
        "open_now_by_priority": by_priority_mask(open_mask),
        "mean_resolution_days": mean_resolution_days,
        "mean_resolution_days_by_priority": mean_by_priority,
        "timeseries_chart": timeseries_chart,
        "top_open_table": top_open,
    }
