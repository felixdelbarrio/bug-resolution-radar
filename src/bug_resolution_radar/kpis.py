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
        return df.copy()

    out = df.copy(deep=False)
    for col in _DT_COLS:
        if col in out.columns:
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
    if "resolved" in work_df.columns:
        open_mask = work_df["resolved"].isna()
    else:
        open_mask = pd.Series([True] * total_issues, index=work_df.index)

    open_df = work_df[open_mask]
    open_now_total = int(open_mask.sum())

    def by_priority(sub: pd.DataFrame) -> Dict[str, int]:
        if sub.empty or "priority" not in sub.columns:
            return {}
        counts = sub["priority"].fillna("").astype(str).value_counts()
        return {str(priority): int(count) for priority, count in counts.items()}

    fort_start = now - timedelta(days=fort_days)
    if "created" in work_df.columns:
        new_fort = work_df[work_df["created"] >= fort_start]
    else:
        new_fort = work_df.iloc[0:0]

    if "resolved" in work_df.columns:
        closed_fort = work_df[work_df["resolved"].notna() & (work_df["resolved"] >= fort_start)]
    else:
        closed_fort = work_df.iloc[0:0]

    if "resolved" in work_df.columns and "created" in work_df.columns:
        closed_all = work_df[work_df["resolved"].notna() & work_df["created"].notna()]
    else:
        closed_all = work_df.iloc[0:0]

    if closed_all.empty:
        mean_resolution_days = 0.0
        mean_by_priority: Dict[str, float] = {}
    else:
        resolution_days = (
            closed_all["resolved"] - closed_all["created"]
        ).dt.total_seconds() / 86400.0
        mean_resolution_days = float(resolution_days.mean())
        if "priority" in closed_all.columns:
            grouped = (
                closed_all.assign(res_days=resolution_days)
                .groupby("priority", dropna=False)["res_days"]
                .mean()
                .sort_values()
                .round(2)
            )
            mean_by_priority = grouped.to_dict()
        else:
            mean_by_priority = {}

    try:
        x_days_list = parse_int_list(settings.KPI_OPEN_AGE_X_DAYS)
    except Exception:
        x_days_list = []

    if len(open_df) > 0 and "created" in open_df.columns:
        open_age_days = ((now - open_df["created"]).dt.total_seconds() / 86400.0).clip(lower=0.0)
    else:
        open_age_days = pd.Series(dtype=float)

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
    if "created" in work_df.columns:
        created_daily = (
            work_df[work_df["created"].notna() & (work_df["created"] >= start)]
            .assign(date=lambda d: d["created"].dt.date)
            .groupby("date")
            .size()
            .reset_index(name="created")
        )
    else:
        created_daily = pd.DataFrame(columns=["date", "created"])

    if "resolved" in work_df.columns:
        closed_daily = (
            work_df[work_df["resolved"].notna() & (work_df["resolved"] >= start)]
            .assign(date=lambda d: d["resolved"].dt.date)
            .groupby("date")
            .size()
            .reset_index(name="closed")
        )
    else:
        closed_daily = pd.DataFrame(columns=["date", "closed"])

    if not created_daily.empty or not closed_daily.empty:
        daily = pd.merge(created_daily, closed_daily, on="date", how="outer").fillna(0)
        daily["date"] = pd.to_datetime(daily["date"])
        daily = daily.sort_values("date")
        daily["open_delta"] = daily["created"] - daily["closed"]
        daily["open_backlog_proxy"] = daily["open_delta"].cumsum()
        timeseries_chart = px.line(daily, x="date", y=["created", "closed", "open_backlog_proxy"])
    else:
        timeseries_chart = _empty_timeseries_chart()

    if not open_df.empty and "summary" in open_df.columns:
        top_open = (
            open_df["summary"]
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
        "open_now_by_priority": by_priority(open_df),
        "new_fortnight_total": int(len(new_fort)),
        "new_fortnight_by_priority": by_priority(new_fort),
        "closed_fortnight_total": int(len(closed_fort)),
        "closed_fortnight_by_resolution_type": (
            closed_fort["resolution_type"].fillna("").value_counts().to_dict()
            if "resolution_type" in closed_fort.columns
            else {}
        ),
        "mean_resolution_days": mean_resolution_days,
        "mean_resolution_days_by_priority": mean_by_priority,
        "pct_open_gt_x_days": pct_open_gt_x,
        "age_buckets_chart": age_buckets_chart,
        "timeseries_chart": timeseries_chart,
        "top_open_table": top_open,
    }
