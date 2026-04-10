"""Shared helpers for quincenal issue scopes across filters and Issues tab."""

from __future__ import annotations

from typing import Dict, List

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.quincenal_scope import (
    QUINCENAL_SCOPE_ALL,
    QUINCENAL_SCOPE_CLOSED_CURRENT,
    QUINCENAL_SCOPE_CREATED_CURRENT,
    QUINCENAL_SCOPE_CREATED_MONTH,
    QUINCENAL_SCOPE_CREATED_PREVIOUS,
    QUINCENAL_SCOPE_CRITICAL_HIGH_OPEN,
    QUINCENAL_SCOPE_MAESTRAS_OPEN,
    QUINCENAL_SCOPE_OPEN_TOTAL,
    QUINCENAL_SCOPE_OTHERS_OPEN,
    QUINCENAL_SCOPE_RESOLUTION_CLOSED_CURRENT,
    apply_issue_key_scope,
    normalize_quincenal_scope_label,
    quincenal_scope_options as _quincenal_scope_options,
    should_show_open_split,
)
from bug_resolution_radar.config import Settings


def quincenal_scope_options(
    df: pd.DataFrame,
    *,
    settings: Settings | None,
    reference_day: pd.Timestamp | None = None,
) -> Dict[str, List[str]]:
    country = str(st.session_state.get("workspace_country") or "").strip()
    source_ids: List[str] = []
    mode = str(st.session_state.get("workspace_scope_mode") or "source").strip().lower()
    if mode == "source":
        selected_source = str(st.session_state.get("workspace_source_id") or "").strip()
        if selected_source:
            source_ids = [selected_source]

    return _quincenal_scope_options(
        df,
        settings=settings,
        country=country,
        source_ids=source_ids,
        reference_day=reference_day,
    )
