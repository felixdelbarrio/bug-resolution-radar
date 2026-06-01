"""Pure filtering helpers shared by API and UI adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence

import pandas as pd

from bug_resolution_radar.analytics.issue_functionality import (
    FUNCTIONALITY_COL,
    ensure_issue_functionality_columns,
)
from bug_resolution_radar.analytics.issues import normalize_text_col, open_issues_only
from bug_resolution_radar.analytics.quincenal_scope import (
    QUINCENAL_SCOPE_ALL,
    apply_issue_key_scope,
    normalize_quincenal_scope_label,
    quincenal_scope_options,
)
from bug_resolution_radar.config import Settings


@dataclass(frozen=True)
class FilterState:
    status: List[str]
    priority: List[str]
    assignee: List[str]
    functionality: List[str] = field(default_factory=list)


def normalize_filter_tokens(values: Sequence[str] | None) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in list(values or []):
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def apply_filters(df: pd.DataFrame, fs: FilterState) -> pd.DataFrame:
    """Apply canonical dashboard filters to a dataframe."""
    if df is None or df.empty:
        return pd.DataFrame()

    base = ensure_issue_functionality_columns(df) if fs.functionality else df
    mask = pd.Series(True, index=base.index)

    status_norm: pd.Series | None = None
    if "status" in base.columns:
        status_norm = normalize_text_col(base["status"], "(sin estado)")
        if fs.status:
            mask &= status_norm.isin(fs.status)

    priority_norm: pd.Series | None = None
    if "priority" in base.columns:
        priority_norm = normalize_text_col(base["priority"], "(sin priority)")
        if fs.priority:
            mask &= priority_norm.isin(fs.priority)

    if fs.assignee and "assignee" in base.columns:
        assignee_norm = normalize_text_col(base["assignee"], "(sin asignar)")
        mask &= assignee_norm.isin(fs.assignee)

    functionality_norm: pd.Series | None = None
    if FUNCTIONALITY_COL in base.columns:
        functionality_norm = normalize_text_col(base[FUNCTIONALITY_COL], "(sin funcionalidad)")
        if fs.functionality:
            mask &= functionality_norm.isin(fs.functionality)

    dff = base.loc[mask].copy(deep=False)
    if status_norm is not None:
        dff["status"] = status_norm.loc[mask].to_numpy()
    if priority_norm is not None:
        dff["priority"] = priority_norm.loc[mask].to_numpy()
    if functionality_norm is not None:
        dff[FUNCTIONALITY_COL] = functionality_norm.loc[mask].to_numpy()
    return dff


def apply_text_like_filter(
    df: pd.DataFrame,
    *,
    column: str,
    query: str,
) -> pd.DataFrame:
    """Apply a lightweight literal-like filter over a single column."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    col_name = str(column or "").strip()
    q = str(query or "").strip()
    if not col_name or not q or col_name not in df.columns:
        return df

    series = df[col_name]
    try:
        if pd.api.types.is_datetime64_any_dtype(series) or isinstance(
            series.dtype, pd.DatetimeTZDtype
        ):
            text = pd.to_datetime(series, errors="coerce", utc=True).dt.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        else:
            text = series.astype("string")
        mask = text.fillna("").str.contains(q, case=False, regex=False, na=False)
    except Exception:
        text = series.astype(str)
        mask = text.str.contains(q, case=False, regex=False, na=False)

    if bool(mask.all()):
        return df
    return df.loc[mask].copy(deep=False)


def apply_dashboard_issue_scope(
    df: pd.DataFrame,
    *,
    settings: Settings,
    country: str,
    source_ids: Sequence[str],
    quincenal_scope: str = QUINCENAL_SCOPE_ALL,
    issue_keys: Sequence[str] | None = None,
    sort_col: str = "",
    like_query: str = "",
) -> pd.DataFrame:
    """Apply quincenal scope + explicit issue subset + like filter."""
    scoped = df
    quincenal_label = normalize_quincenal_scope_label(quincenal_scope)
    if (
        quincenal_label != QUINCENAL_SCOPE_ALL
        and isinstance(scoped, pd.DataFrame)
        and not scoped.empty
    ):
        options = quincenal_scope_options(
            scoped,
            settings=settings,
            country=country,
            source_ids=source_ids,
        )
        if quincenal_label in options:
            scoped = apply_issue_key_scope(scoped, keys=options[quincenal_label])

    if (
        issue_keys
        and isinstance(scoped, pd.DataFrame)
        and not scoped.empty
        and "key" in scoped.columns
    ):
        scoped = apply_issue_key_scope(scoped, keys=issue_keys)

    return apply_text_like_filter(scoped, column=sort_col, query=like_query)


def open_only(df: pd.DataFrame) -> pd.DataFrame:
    return open_issues_only(df)
