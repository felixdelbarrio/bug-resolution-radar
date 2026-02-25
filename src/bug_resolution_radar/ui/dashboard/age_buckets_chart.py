"""Shared age-buckets chart helpers (issue-level distribution)."""

from __future__ import annotations

import hashlib
from typing import Sequence

import pandas as pd
import plotly.graph_objects as go

from bug_resolution_radar.ui.common import (
    normalize_text_col,
    priority_rank,
    status_color_map,
)
from bug_resolution_radar.ui.style import apply_plotly_bbva

AGE_BUCKET_ORDER: tuple[str, ...] = ("0-2", "3-7", "8-14", "15-30", ">30")
AGE_BUCKET_LABELS_DAYS: dict[str, str] = {
    "0-2": "0-2 días",
    "3-7": "3-7 días",
    "8-14": "8-14 días",
    "15-30": "15-30 días",
    ">30": ">30 días",
}


def _to_dt_naive(s: pd.Series) -> pd.Series:
    """Convert to naive datetime64 for safe arithmetic/comparisons."""
    if s is None:
        return pd.Series([], dtype="datetime64[ns]")
    out = pd.to_datetime(s, errors="coerce")
    try:
        if hasattr(out.dt, "tz") and out.dt.tz is not None:
            out = out.dt.tz_localize(None)
    except Exception:
        try:
            out = out.dt.tz_localize(None)
        except Exception:
            pass
    return out


def _stable_jitter(token: str, *, amplitude: float = 0.18) -> float:
    digest = hashlib.md5(token.encode("utf-8"), usedforsecurity=False).hexdigest()
    n = int(digest[:8], 16) / float(0xFFFFFFFF)
    return (n * 2.0 - 1.0) * amplitude


def _priority_sort_key(priority: object) -> tuple[int, str]:
    p = str(priority or "").strip()
    pl = p.lower()
    if pl == "supone un impedimento":
        return (-1, pl)
    return (priority_rank(p), pl)


def build_age_bucket_points(issues_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare issue-level rows with age bucket and age days."""
    if issues_df is None or issues_df.empty or "created" not in issues_df.columns:
        return pd.DataFrame()

    df = issues_df.copy(deep=False)
    created_dt = _to_dt_naive(df["created"])
    df = df.assign(__created_dt=created_dt)
    df = df[df["__created_dt"].notna()].copy(deep=False)
    if df.empty:
        return pd.DataFrame()

    now = pd.Timestamp.utcnow().tz_localize(None)
    df["__age_days"] = (now - df["__created_dt"]).dt.total_seconds() / 86400.0
    df["__age_days"] = df["__age_days"].clip(lower=0.0)
    if "status" not in df.columns:
        df["status"] = "(sin estado)"
    else:
        df["status"] = normalize_text_col(df["status"], "(sin estado)")

    df["bucket"] = pd.cut(
        df["__age_days"],
        bins=[-float("inf"), 2, 7, 14, 30, float("inf")],
        labels=list(AGE_BUCKET_ORDER),
        right=True,
        include_lowest=True,
        ordered=True,
    )
    df = df[df["bucket"].notna()].copy(deep=False)
    if df.empty:
        return pd.DataFrame()
    if "priority" in df.columns:
        df["priority"] = normalize_text_col(df["priority"], "(sin priority)")
    else:
        df["priority"] = "(sin priority)"
    if "key" not in df.columns:
        df["key"] = ""
    if "summary" not in df.columns:
        df["summary"] = ""
    return df


def build_age_buckets_issue_distribution(
    *,
    issues: pd.DataFrame,
    status_order: Sequence[str],
    bucket_order: Sequence[str] = AGE_BUCKET_ORDER,
) -> go.Figure:
    """Render issue-by-issue distribution across age buckets."""
    fig = go.Figure()
    bucket_to_x = {bucket: float(idx + 1) for idx, bucket in enumerate(bucket_order)}
    colors = status_color_map(status_order)
    priority_order = sorted(
        issues["priority"].astype(str).unique().tolist(),
        key=_priority_sort_key,
    )
    if not priority_order:
        priority_order = ["(sin priority)"]
    priority_to_y = {p: float(len(priority_order) - idx) for idx, p in enumerate(priority_order)}

    # Small offset by status + deterministic jitter by issue key to avoid overplot.
    if len(status_order) <= 1:
        offsets = {str(status_order[0]): 0.0} if status_order else {}
    else:
        spread = 0.34
        step = spread / float(len(status_order) - 1)
        offsets = {str(st): (-spread / 2.0) + (idx * step) for idx, st in enumerate(status_order)}

    for status in status_order:
        sub = issues[issues["status"].astype(str) == str(status)].copy(deep=False)
        if sub.empty:
            continue

        xs: list[float] = []
        ys: list[float] = []
        customdata: list[list[object]] = []
        for row in sub.itertuples(index=False):
            bucket_name = str(getattr(row, "bucket", "") or "")
            base_x = bucket_to_x.get(bucket_name)
            age_days = float(getattr(row, "__age_days", 0.0) or 0.0)
            priority_name = str(getattr(row, "priority", "") or "(sin priority)")
            base_y = priority_to_y.get(priority_name)
            if base_x is None:
                continue
            if base_y is None:
                continue
            key_txt = str(getattr(row, "key", "") or "")
            summary_txt = str(getattr(row, "summary", "") or "")
            jitter_token = f"{key_txt}|{summary_txt}|{bucket_name}|{age_days:.4f}"
            y_jitter = _stable_jitter(f"{jitter_token}|{priority_name}", amplitude=0.23)
            x_val = base_x + float(offsets.get(str(status), 0.0)) + _stable_jitter(jitter_token)
            xs.append(x_val)
            ys.append(base_y + y_jitter)
            customdata.append(
                [
                    AGE_BUCKET_LABELS_DAYS.get(bucket_name, bucket_name),
                    key_txt,
                    priority_name,
                    summary_txt,
                    age_days,
                ]
            )
        if not xs:
            continue

        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                name=str(status),
                customdata=customdata,
                hovertemplate=(
                    "Estado: %{fullData.name}<br>"
                    "Rango: %{customdata[0]}<br>"
                    "Criticidad: %{customdata[2]}<br>"
                    "Edad: %{customdata[4]:.1f} d<br>"
                    "Key: %{customdata[1]}<br>"
                    "Resumen: %{customdata[3]}<extra></extra>"
                ),
                marker=dict(
                    size=10,
                    color=colors.get(str(status)),
                    opacity=0.88,
                    symbol="circle",
                    line=dict(width=0.6, color="rgba(255,255,255,0.55)"),
                ),
            )
        )

    fig.update_layout(
        title_text="",
        xaxis_title="Rango de antigüedad (días)",
        yaxis_title="Criticidad",
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=[bucket_to_x[b] for b in bucket_order],
        ticktext=[AGE_BUCKET_LABELS_DAYS.get(b, str(b)) for b in bucket_order],
        range=[0.5, len(bucket_order) + 0.5],
    )
    fig.update_yaxes(
        tickmode="array",
        tickvals=[priority_to_y[p] for p in priority_order],
        ticktext=priority_order,
        range=[0.5, float(len(priority_order)) + 0.5],
    )
    fig = apply_plotly_bbva(fig, showlegend=True)
    return fig
