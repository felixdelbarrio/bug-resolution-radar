from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px

from .config import Settings
from .utils import parse_age_buckets, parse_int_list


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_kpis(df: pd.DataFrame, settings: Settings) -> Dict[str, Any]:
    now = _utcnow()
    fort_days = int(settings.KPI_FORTNIGHT_DAYS)

    for col in ["created", "updated", "resolved"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    open_df = df[df["resolved"].isna()]
    open_now_total = len(open_df)

    def by_priority(sub: pd.DataFrame) -> Dict[str, int]:
        if "priority" not in sub.columns:
            return {}
        return sub["priority"].fillna("").value_counts().to_dict()

    fort_start = now - timedelta(days=fort_days)
    new_fort = df[df["created"] >= fort_start]
    closed_fort = df[df["resolved"].notna() & (df["resolved"] >= fort_start)]

    closed_all = df[df["resolved"].notna() & df["created"].notna()].copy()
    if len(closed_all) > 0:
        closed_all["res_days"] = (closed_all["resolved"] - closed_all["created"]).dt.total_seconds() / 86400.0
        mean_resolution_days = float(closed_all["res_days"].mean())
        mean_by_priority = (
            closed_all.groupby("priority")["res_days"].mean().sort_values().round(2).to_dict()
            if "priority" in closed_all.columns
            else {}
        )
    else:
        mean_resolution_days = 0.0
        mean_by_priority = {}

    x_days_list = parse_int_list(settings.KPI_OPEN_AGE_X_DAYS)
    pct_parts: List[str] = []
    if len(open_df) > 0 and "created" in open_df.columns:
        open_df = open_df.copy()
        open_df["open_age_days"] = (now - open_df["created"]).dt.total_seconds() / 86400.0
        for x in x_days_list:
            pct = 100.0 * float((open_df["open_age_days"] > x).mean())
            pct_parts.append(f">{x}d: {pct:.1f}%")
    pct_open_gt_x = " | ".join(pct_parts) if pct_parts else "n/a"

    buckets = parse_age_buckets(settings.KPI_AGE_BUCKETS)
    bucket_labels: List[str] = []
    bucket_counts: List[int] = []
    if len(open_df) > 0 and "created" in open_df.columns:
        for lo, hi in buckets:
            if hi >= 10**8:
                label = f">{lo}"
                count = int((open_df["open_age_days"] > lo).sum())
            else:
                label = f"{lo}-{hi}"
                count = int(((open_df["open_age_days"] >= lo) & (open_df["open_age_days"] <= hi)).sum())
            bucket_labels.append(label)
            bucket_counts.append(count)
    age_buckets_df = pd.DataFrame({"bucket": bucket_labels, "count": bucket_counts})
    age_buckets_chart = px.bar(age_buckets_df, x="bucket", y="count")

    range_days = 90
    start = now - timedelta(days=range_days)
    created_daily = (
        df[df["created"].notna() & (df["created"] >= start)]
        .assign(date=lambda d: d["created"].dt.date)
        .groupby("date")
        .size()
        .reset_index(name="created")
    )
    closed_daily = (
        df[df["resolved"].notna() & (df["resolved"] >= start)]
        .assign(date=lambda d: d["resolved"].dt.date)
        .groupby("date")
        .size()
        .reset_index(name="closed")
    )
    daily = pd.merge(created_daily, closed_daily, on="date", how="outer").fillna(0)
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date")
    daily["open_delta"] = daily["created"] - daily["closed"]
    daily["open_backlog_proxy"] = daily["open_delta"].cumsum()
    timeseries_chart = px.line(daily, x="date", y=["created", "closed", "open_backlog_proxy"])

    top_open = (
        open_df.assign(summary=open_df["summary"].fillna(""))
        .groupby("summary")
        .size()
        .sort_values(ascending=False)
        .head(10)
        .reset_index()
        .rename(columns={0: "open_count"})
    )

    return {
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
