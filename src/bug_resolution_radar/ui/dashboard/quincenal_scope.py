"""Shared helpers for quincenal issue scopes across filters and Issues tab."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.period_summary import (
    build_country_quincenal_result,
    source_label_map,
)
from bug_resolution_radar.config import Settings


def _issue_keys(df: pd.DataFrame | None) -> List[str]:
    if df is None or df.empty or "key" not in df.columns:
        return []
    out: List[str] = []
    seen: set[str] = set()
    for raw in df["key"].fillna("").astype(str).tolist():
        key = str(raw or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def should_show_open_split(*, maestras_total: int, others_total: int, open_total: int) -> bool:
    """Return True when maestra/other open split adds distinct value."""
    maestras = max(int(maestras_total or 0), 0)
    others = max(int(others_total or 0), 0)
    open_total_safe = max(int(open_total or 0), 0)
    return not (maestras == 0 and others == open_total_safe)


def quincenal_scope_options(df: pd.DataFrame, *, settings: Settings | None) -> Dict[str, List[str]]:
    """Return quincenal issue subsets for the current workspace scope."""
    if settings is None or df is None or df.empty:
        return {"Todas": []}

    country = str(st.session_state.get("workspace_country") or "").strip()
    if not country and "country" in df.columns:
        country = str(df["country"].fillna("").astype(str).iloc[0]).strip()

    source_ids: List[str] = []
    mode = str(st.session_state.get("workspace_scope_mode") or "source").strip().lower()
    if mode == "source":
        selected_source = str(st.session_state.get("workspace_source_id") or "").strip()
        if selected_source:
            source_ids = [selected_source]
    if not source_ids and "source_id" in df.columns:
        source_ids = sorted({sid for sid in df["source_id"].fillna("").astype(str).tolist() if sid})

    labels = source_label_map(settings, country=country, source_ids=source_ids)
    result = build_country_quincenal_result(
        df=df,
        settings=settings,
        country=country,
        source_ids=source_ids,
        source_label_by_id=labels,
    )
    groups = result.aggregate.groups
    summary = result.aggregate.summary
    open_total_df = pd.concat([groups.maestras_open, groups.others_open], ignore_index=True).copy(
        deep=False
    )
    show_open_split = should_show_open_split(
        maestras_total=int(summary.maestras_total),
        others_total=int(summary.others_total),
        open_total=int(summary.open_total),
    )
    options: Dict[str, List[str]] = {
        "Todas": [],
        "Nuevas (quincena actual)": _issue_keys(groups.new_now),
        "Nuevas (quincena previa)": _issue_keys(groups.new_before),
        "Nuevas (acumulado)": _issue_keys(groups.new_accumulated),
        "Cerradas (quincena actual)": _issue_keys(groups.closed_now),
        "Resolución (cerradas ahora)": _issue_keys(groups.resolved_now),
        "Abiertas totales": _issue_keys(open_total_df),
    }
    if show_open_split:
        options["Maestras abiertas"] = _issue_keys(groups.maestras_open)
        options["Otras abiertas"] = _issue_keys(groups.others_open)
    return {label: keys for label, keys in options.items() if label == "Todas" or keys}


def apply_issue_key_scope(df: pd.DataFrame, *, keys: List[str]) -> pd.DataFrame:
    """Apply a key subset filter (uppercase-normalized) over issue dataframe."""
    if df is None or df.empty or not keys or "key" not in df.columns:
        return pd.DataFrame() if df is None else df
    allowed = {str(k or "").strip().upper() for k in keys if str(k or "").strip()}
    if not allowed:
        return df
    mask = df["key"].fillna("").astype(str).str.strip().str.upper().isin(allowed)
    return df.loc[mask].copy(deep=False)
