"""Pure helpers for quincenal issue scopes shared by UI and reports."""

from __future__ import annotations

from typing import Dict, List, Sequence

import pandas as pd

from bug_resolution_radar.analytics.period_summary import (
    build_country_quincenal_result,
    open_issue_grouping,
    source_label_map,
)
from bug_resolution_radar.config import Settings

QUINCENAL_SCOPE_ALL = "Todas"
QUINCENAL_SCOPE_CREATED_CURRENT = "Creadas en la quincena actual"
QUINCENAL_SCOPE_CREATED_PREVIOUS = "Creadas en la quincena previa"
QUINCENAL_SCOPE_CREATED_MONTH = "Creadas en el mes actual"
QUINCENAL_SCOPE_CLOSED_CURRENT = "Cerradas en la quincena"
QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT = (
    "Días de resolución incidencias cerradas en la quincena actual"
)
QUINCENAL_SCOPE_OPEN_TOTAL = "Abiertas totales"
QUINCENAL_SCOPE_MAESTRAS_OPEN = "Maestras abiertas"
QUINCENAL_SCOPE_CRITICAL_HIGH_OPEN = "Incidencias con criticidad alta"
QUINCENAL_SCOPE_OTHERS_OPEN = "Otras incidencias"

_LEGACY_LABEL_TO_CANONICAL: Dict[str, str] = {
    "Nuevas (quincena actual)": QUINCENAL_SCOPE_CREATED_CURRENT,
    "Nuevas (quincena previa)": QUINCENAL_SCOPE_CREATED_PREVIOUS,
    "Nuevas (acumulado)": QUINCENAL_SCOPE_CREATED_MONTH,
    "Cerradas (quincena actual)": QUINCENAL_SCOPE_CLOSED_CURRENT,
    "Resolución (cerradas ahora)": QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
    "Otras abiertas": QUINCENAL_SCOPE_OTHERS_OPEN,
    "Incidencias con criticidad alta abiertas": QUINCENAL_SCOPE_CRITICAL_HIGH_OPEN,
}


def normalize_quincenal_scope_label(value: object) -> str:
    raw = str(value or "").strip() or QUINCENAL_SCOPE_ALL
    return _LEGACY_LABEL_TO_CANONICAL.get(raw, raw)


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
    maestras = max(int(maestras_total or 0), 0)
    others = max(int(others_total or 0), 0)
    open_total_safe = max(int(open_total or 0), 0)
    return not (maestras == 0 and others == open_total_safe)


def quincenal_scope_options(
    df: pd.DataFrame,
    *,
    settings: Settings | None,
    country: str = "",
    source_ids: Sequence[str] | None = None,
    reference_day: pd.Timestamp | None = None,
) -> Dict[str, List[str]]:
    """Return quincenal issue subsets for a resolved country/source scope."""
    if settings is None or df is None or df.empty:
        return {QUINCENAL_SCOPE_ALL: []}

    resolved_country = str(country or "").strip()
    if not resolved_country and "country" in df.columns:
        resolved_country = str(df["country"].fillna("").astype(str).iloc[0]).strip()

    resolved_source_ids = [str(source_id or "").strip() for source_id in list(source_ids or [])]
    resolved_source_ids = [token for token in resolved_source_ids if token]
    if not resolved_source_ids and "source_id" in df.columns:
        resolved_source_ids = sorted(
            {sid for sid in df["source_id"].fillna("").astype(str).tolist() if sid}
        )

    labels = source_label_map(settings, country=resolved_country, source_ids=resolved_source_ids)
    result = build_country_quincenal_result(
        df=df,
        settings=settings,
        country=resolved_country,
        source_ids=resolved_source_ids,
        source_label_by_id=labels,
        reference_day=reference_day,
    )
    groups = result.aggregate.groups
    summary = result.aggregate.summary
    focus_label = str(summary.open_focus_label or open_issue_grouping(settings).focus_scope_label)
    other_label = str(summary.open_other_label or open_issue_grouping(settings).other_scope_label)
    open_total_df = pd.concat([groups.open_focus, groups.open_other], ignore_index=True).copy(
        deep=False
    )
    show_open_split = should_show_open_split(
        maestras_total=int(summary.open_focus_total),
        others_total=int(summary.open_other_total),
        open_total=int(summary.open_total),
    )
    options: Dict[str, List[str]] = {
        QUINCENAL_SCOPE_ALL: [],
        QUINCENAL_SCOPE_CREATED_CURRENT: _issue_keys(groups.new_now),
        QUINCENAL_SCOPE_CREATED_PREVIOUS: _issue_keys(groups.new_before),
        QUINCENAL_SCOPE_CREATED_MONTH: _issue_keys(groups.new_accumulated),
        QUINCENAL_SCOPE_CLOSED_CURRENT: _issue_keys(groups.closed_now),
        QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT: _issue_keys(groups.resolved_now),
        QUINCENAL_SCOPE_OPEN_TOTAL: _issue_keys(open_total_df),
    }
    if show_open_split:
        options[focus_label] = _issue_keys(groups.open_focus)
        options[other_label] = _issue_keys(groups.open_other)
    return {label: keys for label, keys in options.items() if label == QUINCENAL_SCOPE_ALL or keys}


def apply_issue_key_scope(df: pd.DataFrame, *, keys: Sequence[str]) -> pd.DataFrame:
    """Apply a key subset filter (uppercase-normalized) over issue dataframe."""
    if df is None or df.empty or not keys or "key" not in df.columns:
        return pd.DataFrame() if df is None else df
    allowed = {str(key or "").strip().upper() for key in list(keys or []) if str(key or "").strip()}
    if not allowed:
        return df
    mask = df["key"].fillna("").astype(str).str.strip().str.upper().isin(allowed)
    return df.loc[mask].copy(deep=False)
