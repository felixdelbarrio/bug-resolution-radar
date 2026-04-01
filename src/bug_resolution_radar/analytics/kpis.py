"""KPI computation functions for backlog monitoring views."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timezone
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

    needs_parse: list[str] = []
    needs_localize: list[str] = []
    for col in _DT_COLS:
        if col not in df.columns:
            continue
        col_dtype = df[col].dtype
        if isinstance(col_dtype, pd.DatetimeTZDtype):
            continue
        if pd.api.types.is_datetime64_dtype(col_dtype):
            needs_localize.append(col)
            continue
        needs_parse.append(col)

    if not needs_parse and not needs_localize:
        return df.copy(deep=False)

    out = df.copy(deep=False)
    for col in needs_localize:
        out[col] = out[col].dt.tz_localize("UTC")
    for col in needs_parse:
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


def _normalize_status_token(value: object) -> str:
    txt = str(value or "").strip().lower()
    if not txt:
        return ""
    txt = unicodedata.normalize("NFKD", txt)
    return "".join(ch for ch in txt if not unicodedata.combining(ch) and ch.isalnum())


def build_timeseries_daily(
    df: pd.DataFrame,
    *,
    lookback_days: int = 90,
    include_deployed: bool = False,
) -> pd.DataFrame:
    """
    Canonical daily flow payload shared by dashboard charts and insights.

    Columns:
    - date
    - created
    - closed
    - open_backlog_proxy
    - deployed (optional, only when include_deployed=True)
    """
    work_df = _ensure_datetime_columns(df)
    if work_df.empty:
        cols = ["date", "created", "closed", "open_backlog_proxy"]
        if include_deployed:
            cols.append("deployed")
        return pd.DataFrame(columns=cols)

    created = (
        work_df["created"]
        if "created" in work_df.columns
        else pd.Series(pd.NaT, index=work_df.index, dtype="datetime64[ns, UTC]")
    )
    resolved = (
        work_df["resolved"]
        if "resolved" in work_df.columns
        else pd.Series(pd.NaT, index=work_df.index, dtype="datetime64[ns, UTC]")
    )
    updated = (
        work_df["updated"]
        if "updated" in work_df.columns
        else pd.Series(pd.NaT, index=work_df.index, dtype="datetime64[ns, UTC]")
    )

    deployed_ts = pd.Series(pd.NaT, index=work_df.index, dtype="datetime64[ns, UTC]")
    if include_deployed and "status" in work_df.columns:
        status_norm = work_df["status"].fillna("").astype(str).map(_normalize_status_token)
        deployed_mask = status_norm.eq("deployed")
        if deployed_mask.any():
            deployed_ts = resolved.where(deployed_mask)
            deployed_ts = deployed_ts.where(deployed_ts.notna(), updated.where(deployed_mask))
            deployed_ts = deployed_ts.where(deployed_ts.notna(), created.where(deployed_mask))

    event_series: list[pd.Series] = [created, resolved]
    if include_deployed:
        event_series.append(deployed_ts)

    end_candidates: list[pd.Timestamp] = []
    for event in event_series:
        valid = event.dropna()
        if valid.empty:
            continue
        end_candidates.append(pd.Timestamp(valid.max()).normalize())
    if not end_candidates:
        cols = ["date", "created", "closed", "open_backlog_proxy"]
        if include_deployed:
            cols.append("deployed")
        return pd.DataFrame(columns=cols)

    end_ts = max(end_candidates)
    lookback_span = max(int(lookback_days or 0), 1)
    start_ts = end_ts - pd.Timedelta(days=lookback_span - 1)
    days = pd.date_range(start=start_ts, end=end_ts, freq="D")

    created_daily = (
        created.loc[created.notna() & (created >= start_ts)].dt.floor("D").value_counts(sort=False)
    )
    closed_daily = (
        resolved.loc[resolved.notna() & (resolved >= start_ts)]
        .dt.floor("D")
        .value_counts(sort=False)
    )
    deployed_daily = (
        deployed_ts.loc[deployed_ts.notna() & (deployed_ts >= start_ts)]
        .dt.floor("D")
        .value_counts(sort=False)
        if include_deployed
        else pd.Series(dtype="int64")
    )

    daily = pd.DataFrame({"date": pd.DatetimeIndex(days).tz_localize(None)})
    daily["created"] = created_daily.reindex(days, fill_value=0).to_numpy()
    daily["closed"] = closed_daily.reindex(days, fill_value=0).to_numpy()
    net = daily["created"] - daily["closed"]
    daily["open_backlog_proxy"] = net.cumsum().clip(lower=0)
    if include_deployed:
        daily["deployed"] = deployed_daily.reindex(days, fill_value=0).to_numpy()
    return daily


def compute_kpis(
    df: pd.DataFrame,
    settings: Settings,
    *,
    include_timeseries_chart: bool = True,
) -> Dict[str, Any]:
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
            "timeseries_chart": _empty_timeseries_chart() if include_timeseries_chart else None,
            "timeseries_daily": pd.DataFrame(
                columns=["date", "created", "closed", "open_backlog_proxy"]
            ),
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

    timeseries_chart = None
    timeseries_daily = pd.DataFrame(columns=["date", "created", "closed", "open_backlog_proxy"])
    if include_timeseries_chart:
        timeseries_daily = build_timeseries_daily(
            work_df,
            lookback_days=90,
            include_deployed=False,
        )
        if timeseries_daily.empty:
            timeseries_chart = _empty_timeseries_chart()
        else:
            timeseries_chart = px.line(
                timeseries_daily,
                x="date",
                y=["created", "closed", "open_backlog_proxy"],
            )

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
        "timeseries_daily": timeseries_daily,
        "top_open_table": top_open,
    }
