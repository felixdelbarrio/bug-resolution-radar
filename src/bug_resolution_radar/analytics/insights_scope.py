"""Centralized scope + combo filters for Insights pages, charts and reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd

from bug_resolution_radar.analytics.insights import build_theme_render_order, classify_theme
from bug_resolution_radar.analytics.status_semantics import effective_closed_mask

INSIGHTS_VIEW_MODE_QUINCENAL = "quincenal"
INSIGHTS_VIEW_MODE_ACCUMULATED = "acumulada"
INSIGHTS_VIEW_MODE_OPTIONS: tuple[str, str] = (
    INSIGHTS_VIEW_MODE_QUINCENAL,
    INSIGHTS_VIEW_MODE_ACCUMULATED,
)
INSIGHTS_VIEW_MODE_LABELS: dict[str, str] = {
    INSIGHTS_VIEW_MODE_QUINCENAL: "Valores quincena actual",
    INSIGHTS_VIEW_MODE_ACCUMULATED: "Vista acumulada",
}

_DEFAULT_EXCLUDED_STATUS_TOKENS: tuple[str, ...] = (
    "accepted",
    "ready to deploy",
    "deployed",
    "discarded",
)
_DEFAULT_STATUS_SELECTION_ORDER: tuple[str, ...] = (
    "new",
    "analysing",
    "en progreso",
    "to rework",
    "blocked",
    "test",
    "ready to verify",
)
_CANONICAL_STATUS_ORDER: tuple[str, ...] = (
    "new",
    "analysing",
    "ready",
    "blocked",
    "en progreso",
    "to rework",
    "test",
    "ready to verify",
    "accepted",
    "ready to deploy",
    "deployed",
)
_PRIORITY_ORDER: tuple[str, ...] = (
    "highest",
    "high",
    "medium",
    "low",
    "lowest",
)


@dataclass(frozen=True)
class InsightsComboContext:
    """Current view + available options + sanitized selections + filtered dataframe."""

    view_mode: str
    scoped_df: pd.DataFrame
    filtered_df: pd.DataFrame
    status_options: tuple[str, ...]
    priority_options: tuple[str, ...]
    functionality_options: tuple[str, ...]
    selected_statuses: tuple[str, ...]
    selected_priorities: tuple[str, ...]
    selected_functionalities: tuple[str, ...]


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _normalize_token(value: object) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    token = token.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", token).strip()


def _normalize_text_col(series: pd.Series | None, fallback: str) -> pd.Series:
    if series is None:
        return pd.Series([], dtype=str)
    return series.fillna(fallback).astype(str).replace("", fallback)


def _ordered_unique(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        txt = str(raw or "").strip()
        if not txt:
            continue
        key = txt.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(txt)
    return out


def _order_status_values(statuses: Iterable[object]) -> list[str]:
    unique = _ordered_unique(statuses)
    if not unique:
        return []
    rank_map = {token: idx for idx, token in enumerate(_CANONICAL_STATUS_ORDER)}
    pos = {value: idx for idx, value in enumerate(unique)}
    return sorted(
        unique,
        key=lambda value: (rank_map.get(_normalize_token(value), 10_000), pos[value]),
    )


def _priority_rank(value: object) -> int:
    token = _normalize_token(value)
    if token in _PRIORITY_ORDER:
        return _PRIORITY_ORDER.index(token)
    return 99


def _order_priority_values(priorities: Iterable[object]) -> list[str]:
    unique = _ordered_unique(priorities)
    if not unique:
        return []
    pos = {value: idx for idx, value in enumerate(unique)}
    return sorted(
        unique,
        key=lambda value: (_priority_rank(value), _normalize_token(value), pos[value]),
    )


def normalize_insights_view_mode(value: object) -> str:
    token = _normalize_token(value)
    if token == INSIGHTS_VIEW_MODE_ACCUMULATED:
        return INSIGHTS_VIEW_MODE_ACCUMULATED
    return INSIGHTS_VIEW_MODE_QUINCENAL


def resolve_insights_view_df(
    *,
    accumulated_df: pd.DataFrame,
    quincenal_df: pd.DataFrame,
    view_mode: object,
) -> pd.DataFrame:
    mode = normalize_insights_view_mode(view_mode)
    if mode == INSIGHTS_VIEW_MODE_ACCUMULATED:
        return _safe_df(accumulated_df)
    return _safe_df(quincenal_df)


def default_status_selection(
    status_options: Sequence[str],
    *,
    excluded_status_tokens: Sequence[str] = _DEFAULT_EXCLUDED_STATUS_TOKENS,
) -> list[str]:
    options = _ordered_unique(status_options)
    if not options:
        return []
    excludes = [_normalize_token(value) for value in excluded_status_tokens]
    preferred_aliases: dict[str, str] = {
        "in progress": "en progreso",
    }
    preferred_rank = {
        token: idx for idx, token in enumerate(_DEFAULT_STATUS_SELECTION_ORDER)
    }

    selected_preferred: list[str] = []
    for status in options:
        status_token = _normalize_token(status)
        status_token = preferred_aliases.get(status_token, status_token)
        if status_token not in preferred_rank:
            continue
        if any(ex and ex in _normalize_token(status) for ex in excludes):
            continue
        selected_preferred.append(status)

    if selected_preferred:
        return sorted(
            selected_preferred,
            key=lambda status: preferred_rank.get(
                preferred_aliases.get(_normalize_token(status), _normalize_token(status)),
                10_000,
            ),
        )

    selected = []
    for status in options:
        if any(ex and ex in _normalize_token(status) for ex in excludes):
            continue
        selected.append(status)
    return selected if selected else options


def _sanitize_selection(selected: Sequence[str] | None, options: Sequence[str]) -> list[str]:
    allowed = {str(opt): True for opt in list(options or [])}
    out: list[str] = []
    for raw in list(selected or []):
        txt = str(raw or "").strip()
        if not txt or txt not in allowed:
            continue
        out.append(txt)
    seen: set[str] = set()
    deduped: list[str] = []
    for txt in out:
        if txt in seen:
            continue
        seen.add(txt)
        deduped.append(txt)
    return deduped


def ensure_insights_theme_col(
    df: pd.DataFrame,
    *,
    summary_col: str = "summary",
    theme_col: str = "__insights_theme",
) -> pd.DataFrame:
    safe = _safe_df(df)
    if safe.empty or summary_col not in safe.columns:
        return safe
    work = safe.copy(deep=False)
    if (
        theme_col in work.columns
        and pd.to_numeric(work[theme_col].astype(str).str.len(), errors="coerce")
        .fillna(0)
        .gt(0)
        .all()
    ):
        return work

    summaries = work[summary_col].fillna("").astype(str)
    unique_summaries = pd.unique(summaries.to_numpy(copy=False)).tolist()
    theme_map = {txt: classify_theme(txt) for txt in unique_summaries}
    work[theme_col] = summaries.map(theme_map).to_numpy(copy=False)
    return work


def _functionality_options_from_df(
    df: pd.DataFrame,
    *,
    theme_col: str,
) -> list[str]:
    safe = _safe_df(df)
    if safe.empty:
        return []
    open_mask = ~effective_closed_mask(safe)
    open_df = safe.loc[open_mask]
    themed = ensure_insights_theme_col(open_df, theme_col=theme_col)
    if themed.empty or theme_col not in themed.columns:
        return []
    counts = themed[theme_col].fillna("").astype(str).value_counts()
    counts = counts[counts.index != ""]
    if counts.empty:
        return []
    order = build_theme_render_order(
        counts.index.tolist(),
        counts_by_label=counts,
        others_last=True,
        others_at_x_axis=True,
    )
    return list(order.display_order)


def build_insights_combo_context(
    *,
    accumulated_df: pd.DataFrame,
    quincenal_df: pd.DataFrame,
    view_mode: object,
    selected_statuses: Sequence[str] | None = None,
    selected_priorities: Sequence[str] | None = None,
    selected_functionalities: Sequence[str] | None = None,
    apply_default_status_when_empty: bool = False,
    excluded_status_tokens: Sequence[str] = _DEFAULT_EXCLUDED_STATUS_TOKENS,
    theme_col: str = "__insights_theme",
) -> InsightsComboContext:
    mode = normalize_insights_view_mode(view_mode)
    scoped = resolve_insights_view_df(
        accumulated_df=accumulated_df,
        quincenal_df=quincenal_df,
        view_mode=mode,
    )
    if scoped.empty:
        return InsightsComboContext(
            view_mode=mode,
            scoped_df=scoped,
            filtered_df=scoped,
            status_options=(),
            priority_options=(),
            functionality_options=(),
            selected_statuses=(),
            selected_priorities=(),
            selected_functionalities=(),
        )

    status_norm = (
        _normalize_text_col(scoped["status"], "(sin estado)")
        if "status" in scoped.columns
        else None
    )
    priority_norm = (
        _normalize_text_col(scoped["priority"], "(sin priority)")
        if "priority" in scoped.columns
        else None
    )

    status_options = (
        tuple(_order_status_values(status_norm.unique().tolist()))
        if status_norm is not None
        else ()
    )
    priority_options = (
        tuple(_order_priority_values(priority_norm.unique().tolist()))
        if priority_norm is not None
        else ()
    )

    statuses = _sanitize_selection(selected_statuses, status_options)
    if apply_default_status_when_empty and not statuses and status_options:
        statuses = default_status_selection(
            status_options,
            excluded_status_tokens=excluded_status_tokens,
        )
    priorities = _sanitize_selection(selected_priorities, priority_options)

    mask = pd.Series(True, index=scoped.index)
    if statuses and status_norm is not None:
        mask &= status_norm.isin(statuses)
    if priorities and priority_norm is not None:
        mask &= priority_norm.isin(priorities)

    pre_functionality = scoped.loc[mask].copy(deep=False)
    functionality_options = tuple(
        _functionality_options_from_df(pre_functionality, theme_col=theme_col)
    )
    functionalities = _sanitize_selection(selected_functionalities, functionality_options)

    filtered = pre_functionality
    if functionalities:
        themed = ensure_insights_theme_col(pre_functionality, theme_col=theme_col)
        filtered = themed.loc[themed[theme_col].isin(functionalities)].copy(deep=False)

    return InsightsComboContext(
        view_mode=mode,
        scoped_df=scoped,
        filtered_df=filtered,
        status_options=status_options,
        priority_options=priority_options,
        functionality_options=functionality_options,
        selected_statuses=tuple(statuses),
        selected_priorities=tuple(priorities),
        selected_functionalities=tuple(functionalities),
    )
