"""Data preparation context objects used by dashboard sections."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd

from bug_resolution_radar.config import Settings
from bug_resolution_radar.kpis import compute_kpis
from bug_resolution_radar.ui.components.filters import apply_filters
from bug_resolution_radar.ui.dashboard.state import FilterState, get_filter_state, open_only


@dataclass(frozen=True)
class DashboardDataContext:
    df_all: pd.DataFrame
    dff: pd.DataFrame
    open_df: pd.DataFrame
    fs: FilterState
    kpis: Dict[str, Any]


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def build_dashboard_data_context(
    *,
    df_all: pd.DataFrame,
    settings: Settings,
    include_kpis: bool = True,
) -> DashboardDataContext:
    """
    Build the canonical dashboard data context once per rerun.

    Every tab consumes the same filtered dataframe/open subset/KPIs to avoid
    duplicated computations and data divergence across widgets.
    """
    safe_all = _safe_df(df_all)
    fs = get_filter_state()
    dff = apply_filters(safe_all, fs)
    open_df = open_only(dff)
    kpis = compute_kpis(dff, settings=settings) if include_kpis else {}
    return DashboardDataContext(df_all=safe_all, dff=dff, open_df=open_df, fs=fs, kpis=kpis)
