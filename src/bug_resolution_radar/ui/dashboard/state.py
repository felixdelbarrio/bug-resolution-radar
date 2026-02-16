from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import streamlit as st


# -------------------------
# Types
# -------------------------
@dataclass(frozen=True)
class FilterState:
    status: List[str]
    priority: List[str]
    itype: List[str]
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
        status=list(st.session_state.get("filter_status") or []),
        priority=list(st.session_state.get("filter_priority") or []),
        itype=list(st.session_state.get("filter_type") or []),
        assignee=list(st.session_state.get("filter_assignee") or []),
    )


def has_any_filter_active(fs: Optional[FilterState] = None) -> bool:
    """
    True si hay cualquier filtro activo (status/priority/type/assignee).
    Si fs no se pasa, lo lee de session_state.
    """
    if fs is None:
        fs = get_filter_state()
    return bool(fs.status or fs.priority or fs.itype or fs.assignee)


def clear_all_filters() -> None:
    """Limpia TODOS los filtros globales (session_state)."""
    st.session_state["filter_status"] = []
    st.session_state["filter_priority"] = []
    st.session_state["filter_type"] = []
    st.session_state["filter_assignee"] = []


# -------------------------
# Data helpers
# -------------------------
def open_only(df: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve solo abiertas si existe columna 'resolved' (resolved isna()).
    Si no existe, devuelve copia del df.
    """
    if df is None:
        return df
    if "resolved" in df.columns:
        return df[df["resolved"].isna()].copy()
    return df.copy()