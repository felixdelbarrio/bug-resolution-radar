"""Session state keys and helper containers for dashboard UI state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import open_issues_only

# Canonical keys shared across dashboard modules/components.
FILTER_STATUS_KEY = "filter_status"
FILTER_PRIORITY_KEY = "filter_priority"
FILTER_ASSIGNEE_KEY = "filter_assignee"


# -------------------------
# Types
# -------------------------
@dataclass(frozen=True)
class FilterState:
    status: List[str]
    priority: List[str]
    assignee: List[str]


# -------------------------
# Filter state (session_state)
# -------------------------
def get_filter_state() -> FilterState:
    """
    Lee el estado de filtros desde st.session_state.
    NO renderiza widgets (eso lo hace render_filters en components/filters.py).
    """
    return FilterState(
        status=list(st.session_state.get(FILTER_STATUS_KEY) or []),
        priority=list(st.session_state.get(FILTER_PRIORITY_KEY) or []),
        assignee=list(st.session_state.get(FILTER_ASSIGNEE_KEY) or []),
    )


def has_any_filter_active(fs: Optional[FilterState] = None) -> bool:
    """
    True si hay cualquier filtro activo (status/priority/type/assignee).
    Si fs no se pasa, lo lee de session_state.
    """
    if fs is None:
        fs = get_filter_state()
    return bool(fs.status or fs.priority or fs.assignee)


def clear_all_filters() -> None:
    """Limpia TODOS los filtros globales (session_state)."""
    st.session_state[FILTER_STATUS_KEY] = []
    st.session_state[FILTER_PRIORITY_KEY] = []
    st.session_state[FILTER_ASSIGNEE_KEY] = []


# -------------------------
# Data helpers
# -------------------------
def open_only(df: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve solo abiertas si existe columna 'resolved' (resolved isna()).
    Si no existe, devuelve copia del df.
    """
    return open_issues_only(df)
