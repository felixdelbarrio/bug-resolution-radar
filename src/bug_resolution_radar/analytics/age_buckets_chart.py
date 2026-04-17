"""Shared age-buckets chart helpers (issue-level + aggregated distributions)."""

from __future__ import annotations

import hashlib
from typing import Sequence

import pandas as pd
import plotly.graph_objects as go

from bug_resolution_radar.analytics.issues import normalize_text_col, priority_rank
from bug_resolution_radar.theme.design_tokens import BBVA_DARK, BBVA_LIGHT, hex_to_rgba
from bug_resolution_radar.theme.plotly_style import apply_plotly_bbva
from bug_resolution_radar.theme.semantic_colors import priority_color_map, status_color_map

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

    now = pd.Timestamp.now("UTC").tz_localize(None)
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
    dark_mode: bool = False,
) -> go.Figure:
    """Render issue-by-issue distribution across age buckets."""
    fig = go.Figure()
    bucket_to_x = {bucket: float(idx + 1) for idx, bucket in enumerate(bucket_order)}
    colors = status_color_map(status_order)
    marker_line_color = hex_to_rgba(
        (BBVA_DARK if dark_mode else BBVA_LIGHT).ink,
        0.55,
        fallback=BBVA_LIGHT.ink,
    )
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
                    line=dict(width=0.6, color=marker_line_color),
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
    fig = apply_plotly_bbva(fig, showlegend=True, dark_mode=dark_mode)
    return fig


def build_age_bucket_priority_distribution(
    *,
    issues: pd.DataFrame,
    bucket_order: Sequence[str] = AGE_BUCKET_ORDER,
) -> pd.DataFrame:
    """Aggregate issues by age bucket + priority for stacked open-incidents views."""
    cols = ["bucket", "bucket_label", "priority", "count"]
    if issues is None or issues.empty or "bucket" not in issues.columns:
        return pd.DataFrame(columns=cols)

    df = issues.copy(deep=False)
    if "priority" in df.columns:
        df["priority"] = normalize_text_col(df["priority"], "(sin priority)")
    else:
        df["priority"] = "(sin priority)"
    df = df[df["bucket"].notna()].copy(deep=False)
    if df.empty:
        return pd.DataFrame(columns=cols)

    grouped = (
        df.groupby(["bucket", "priority"], dropna=False, observed=True)
        .size()
        .reset_index(name="count")
    )
    if grouped.empty:
        return pd.DataFrame(columns=cols)

    grouped["bucket"] = grouped["bucket"].astype(str)
    grouped = grouped[grouped["bucket"].isin([str(x) for x in list(bucket_order)])].copy(deep=False)
    if grouped.empty:
        return pd.DataFrame(columns=cols)

    grouped["bucket"] = pd.Categorical(
        grouped["bucket"],
        categories=[str(x) for x in list(bucket_order)],
        ordered=True,
    )
    grouped["__priority_sort"] = grouped["priority"].map(_priority_sort_key)
    grouped = grouped.sort_values(["bucket", "__priority_sort", "priority"]).drop(
        columns="__priority_sort"
    )
    grouped["bucket_label"] = (
        grouped["bucket"].astype(str).map(lambda b: AGE_BUCKET_LABELS_DAYS.get(b, b))
    )
    grouped["count"] = grouped["count"].astype(int)
    return grouped[cols]


def _add_bar_totals(
    fig: go.Figure,
    *,
    x_values: Sequence[str],
    y_totals: Sequence[float],
    font_size: int = 12,
    dark_mode: bool = False,
) -> None:
    if not x_values or not y_totals:
        return
    ymax = max(float(v) for v in y_totals) if y_totals else 0.0
    offset = max(1.0, ymax * 0.04)
    text_color = (BBVA_DARK if dark_mode else BBVA_LIGHT).ink
    fig.add_scatter(
        x=list(x_values),
        y=[float(v) + offset for v in list(y_totals)],
        mode="text",
        text=[f"{int(v)}" for v in list(y_totals)],
        textposition="top center",
        textfont=dict(size=font_size, color=text_color),
        hoverinfo="skip",
        showlegend=False,
        cliponaxis=False,
    )
    fig.update_yaxes(range=[0, ymax + (offset * 2.4)])


def build_age_buckets_open_priority_stacked(
    *,
    grouped: pd.DataFrame,
    bucket_order: Sequence[str] = AGE_BUCKET_ORDER,
    dark_mode: bool = False,
) -> go.Figure:
    """Render stacked columns: open incidents by age bucket and priority."""
    fig = go.Figure()
    safe = grouped if isinstance(grouped, pd.DataFrame) else pd.DataFrame()
    bucket_keys = [str(x) for x in list(bucket_order)]
    bucket_labels = [AGE_BUCKET_LABELS_DAYS.get(b, b) for b in bucket_keys]
    priority_colors = priority_color_map()
    neutral_color = priority_colors.get("(sin priority)", "#9AA3B2")

    if safe.empty:
        fig.update_layout(
            title_text="",
            barmode="stack",
            xaxis_title="Antigüedad (días)",
            yaxis_title="Incidencias abiertas",
        )
        fig = apply_plotly_bbva(fig, showlegend=True, dark_mode=dark_mode)
        return fig

    by_bucket_priority = {
        (str(row.bucket), str(row.priority)): int(row.count) for row in safe.itertuples(index=False)
    }
    priorities = sorted(
        safe["priority"].astype(str).unique().tolist(),
        key=_priority_sort_key,
    )
    # Most critical priorities are rendered last so they stay visually on top of each stack.
    stacked_priority_order = list(reversed(priorities))

    for priority in stacked_priority_order:
        values: list[int] = []
        labels: list[str] = []
        for bucket in bucket_keys:
            value = int(by_bucket_priority.get((bucket, str(priority)), 0))
            values.append(value)
            labels.append(str(value) if value > 0 else "")
        fig.add_trace(
            go.Bar(
                x=bucket_labels,
                y=values,
                name=str(priority),
                marker=dict(color=priority_colors.get(str(priority), neutral_color)),
                text=labels,
                textposition="inside",
                insidetextanchor="middle",
                hovertemplate=(
                    "Antigüedad: %{x}<br>"
                    "Prioridad: %{fullData.name}<br>"
                    "Incidencias abiertas: %{y}<extra></extra>"
                ),
            )
        )

    totals = [
        sum(int(by_bucket_priority.get((bucket, str(priority)), 0)) for priority in priorities)
        for bucket in bucket_keys
    ]
    _add_bar_totals(
        fig,
        x_values=bucket_labels,
        y_totals=[float(x) for x in totals],
        font_size=12,
        dark_mode=dark_mode,
    )
    fig.update_layout(
        title_text="",
        barmode="stack",
        xaxis_title="Antigüedad (días)",
        yaxis_title="Incidencias abiertas",
        bargap=0.18,
    )
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=bucket_labels)
    fig = apply_plotly_bbva(fig, showlegend=True, dark_mode=dark_mode)
    fig.update_layout(legend=dict(traceorder="reversed"))
    return fig
