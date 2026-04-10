"""Shared age-buckets chart helpers (issue-level + aggregated distributions)."""

from __future__ import annotations

from typing import Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from bug_resolution_radar.analytics.age_buckets_chart import (
    AGE_BUCKET_LABELS_DAYS,
    AGE_BUCKET_ORDER,
    build_age_bucket_points,
    build_age_bucket_priority_distribution,
    build_age_buckets_issue_distribution as _build_age_buckets_issue_distribution,
    build_age_buckets_open_priority_stacked as _build_age_buckets_open_priority_stacked,
)


def _workspace_dark_mode_enabled() -> bool:
    try:
        return bool(st.session_state.get("workspace_dark_mode", False))
    except Exception:
        return False


def build_age_buckets_issue_distribution(
    *,
    issues: pd.DataFrame,
    status_order: Sequence[str],
    bucket_order: Sequence[str] = AGE_BUCKET_ORDER,
) -> go.Figure:
    return _build_age_buckets_issue_distribution(
        issues=issues,
        status_order=status_order,
        bucket_order=bucket_order,
        dark_mode=_workspace_dark_mode_enabled(),
    )


def build_age_buckets_open_priority_stacked(
    *,
    grouped: pd.DataFrame,
    bucket_order: Sequence[str] = AGE_BUCKET_ORDER,
) -> go.Figure:
    return _build_age_buckets_open_priority_stacked(
        grouped=grouped,
        bucket_order=bucket_order,
        dark_mode=_workspace_dark_mode_enabled(),
    )
