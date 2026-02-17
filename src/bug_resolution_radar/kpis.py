"""KPI computation functions for backlog monitoring views."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px

from .config import Settings
from .utils import parse_age_buckets, parse_int_list

_DT_COLS = ("created", "updated", "resolved")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_int(value: object, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


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


def _empty_age_buckets_chart() -> Any:
    return px.bar(
        pd.DataFrame({"bucket": pd.Series(dtype=str), "count": pd.Series(dtype=int)}),
        x="bucket",
        y="count",
    )


def compute_kpis(df: pd.DataFrame, settings: Settings) -> Dict[str, Any]:
    now = pd.Timestamp(_utcnow())
    fort_days = _safe_int(settings.KPI_FORTNIGHT_DAYS, default=15)
    work_df = _ensure_datetime_columns(df)

    if work_df.empty:
        return {
            "issues_total": 0,
            "issues_open": 0,
            "issues_closed": 0,
            "open_now_total": 0,
            "open_now_by_priority": {},
            "new_fortnight_total": 0,
            "new_fortnight_by_priority": {},
            "closed_fortnight_total": 0,
            "closed_fortnight_by_resolution_type": {},
            "mean_resolution_days": 0.0,
            "mean_resolution_days_by_priority": {},
            "pct_open_gt_x_days": "n/a",
            "age_buckets_chart": _empty_age_buckets_chart(),
            "timeseries_chart": _empty_timeseries_chart(),
            "top_open_table": pd.DataFrame(columns=["summary", "open_count"]),
        }

    total_issues = int(len(work_df))
    has_created = "created" in work_df.columns
    has_resolved = "resolved" in work_df.columns
    has_priority = "priority" in work_df.columns
    has_resolution_type = "resolution_type" in work_df.columns
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
    open_mask = ~resolved_notna
    open_now_total = int(open_mask.sum())
    priority = work_df["priority"].fillna("").astype(str) if has_priority else pd.Series(dtype=str)

    def by_priority_mask(mask: pd.Series) -> Dict[str, int]:
        if not has_priority:
            return {}
        counts = priority.loc[mask].value_counts()
        return {str(priority_name): int(count) for priority_name, count in counts.items()}

    fort_start = now - timedelta(days=fort_days)
    new_fort_mask = created_notna & (created >= fort_start) if has_created else created_notna
    closed_fort_mask = resolved_notna & (resolved >= fort_start)
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

    try:
        x_days_list = parse_int_list(settings.KPI_OPEN_AGE_X_DAYS)
    except Exception:
        x_days_list = []

    open_age_days = (
        ((now - created.loc[open_mask & created_notna]).dt.total_seconds() / 86400.0)
        .clip(lower=0.0)
        .astype(float)
    )

    pct_parts: List[str] = []
    if not open_age_days.empty:
        for x in sorted(set(x_days_list)):
            pct = 100.0 * float((open_age_days > x).mean())
            pct_parts.append(f">{x}d: {pct:.1f}%")
    pct_open_gt_x = " | ".join(pct_parts) if pct_parts else "n/a"

    try:
        buckets = parse_age_buckets(settings.KPI_AGE_BUCKETS)
    except Exception:
        buckets = []

    bucket_labels: List[str] = []
    bucket_counts: List[int] = []
    if not open_age_days.empty:
        for lo, hi in buckets:
            if hi >= 10**8:
                label = f">{lo}"
                count = int((open_age_days > lo).sum())
            else:
                label = f"{lo}-{hi}"
                count = int(((open_age_days >= lo) & (open_age_days <= hi)).sum())
            bucket_labels.append(label)
            bucket_counts.append(count)

    age_buckets_df = pd.DataFrame({"bucket": bucket_labels, "count": bucket_counts})
    age_buckets_chart = (
        px.bar(age_buckets_df, x="bucket", y="count")
        if not age_buckets_df.empty
        else _empty_age_buckets_chart()
    )

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
        "new_fortnight_total": int(new_fort_mask.sum()),
        "new_fortnight_by_priority": by_priority_mask(new_fort_mask),
        "closed_fortnight_total": int(closed_fort_mask.sum()),
        "closed_fortnight_by_resolution_type": (
            work_df.loc[closed_fort_mask, "resolution_type"].fillna("").value_counts().to_dict()
            if has_resolution_type
            else {}
        ),
        "mean_resolution_days": mean_resolution_days,
        "mean_resolution_days_by_priority": mean_by_priority,
        "pct_open_gt_x_days": pct_open_gt_x,
        "age_buckets_chart": age_buckets_chart,
        "timeseries_chart": timeseries_chart,
        "top_open_table": top_open,
    }
