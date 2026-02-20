"""Session state keys and helper containers for dashboard UI state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import streamlit as st

from bug_resolution_radar.config import Settings, save_settings
from bug_resolution_radar.ui.common import open_issues_only

# Canonical keys shared across dashboard modules/components.
FILTER_STATUS_KEY = "filter_status"
FILTER_PRIORITY_KEY = "filter_priority"
FILTER_ASSIGNEE_KEY = "filter_assignee"
FILTERS_BOOTSTRAPPED_KEY = "__filters_bootstrapped_from_env"

FILTER_STATUS_ENV_KEY = "DASHBOARD_FILTER_STATUS_JSON"
FILTER_PRIORITY_ENV_KEY = "DASHBOARD_FILTER_PRIORITY_JSON"
FILTER_ASSIGNEE_ENV_KEY = "DASHBOARD_FILTER_ASSIGNEE_JSON"


# -------------------------
# Types
# -------------------------
@dataclass(frozen=True)
class FilterState:
    status: List[str]
    priority: List[str]
    assignee: List[str]


def _normalize_filter_tokens(values: List[str]) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in list(values or []):
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _parse_filter_env_list(raw: object) -> List[str]:
    txt = str(raw or "").strip()
    if not txt:
        return []
    try:
        payload = json.loads(txt)
    except Exception:
        payload = None
    if isinstance(payload, list):
        return _normalize_filter_tokens([str(x) for x in payload])
    return _normalize_filter_tokens([part.strip() for part in txt.split(",") if part.strip()])


def _encode_filter_env_list(values: List[str]) -> str:
    return json.dumps(
        _normalize_filter_tokens(list(values or [])),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def filters_from_settings(settings: Settings) -> FilterState:
    return FilterState(
        status=_parse_filter_env_list(getattr(settings, FILTER_STATUS_ENV_KEY, "[]")),
        priority=_parse_filter_env_list(getattr(settings, FILTER_PRIORITY_ENV_KEY, "[]")),
        assignee=_parse_filter_env_list(getattr(settings, FILTER_ASSIGNEE_ENV_KEY, "[]")),
    )


def bootstrap_filters_from_env(settings: Settings) -> None:
    """Hydrate canonical filter session keys from persisted .env once per session."""
    if bool(st.session_state.get(FILTERS_BOOTSTRAPPED_KEY, False)):
        return

    persisted = filters_from_settings(settings)
    if FILTER_STATUS_KEY not in st.session_state:
        st.session_state[FILTER_STATUS_KEY] = list(persisted.status)
    else:
        st.session_state[FILTER_STATUS_KEY] = _normalize_filter_tokens(
            list(st.session_state.get(FILTER_STATUS_KEY) or [])
        )

    if FILTER_PRIORITY_KEY not in st.session_state:
        st.session_state[FILTER_PRIORITY_KEY] = list(persisted.priority)
    else:
        st.session_state[FILTER_PRIORITY_KEY] = _normalize_filter_tokens(
            list(st.session_state.get(FILTER_PRIORITY_KEY) or [])
        )

    if FILTER_ASSIGNEE_KEY not in st.session_state:
        st.session_state[FILTER_ASSIGNEE_KEY] = list(persisted.assignee)
    else:
        st.session_state[FILTER_ASSIGNEE_KEY] = _normalize_filter_tokens(
            list(st.session_state.get(FILTER_ASSIGNEE_KEY) or [])
        )

    st.session_state[FILTERS_BOOTSTRAPPED_KEY] = True


def persist_filters_in_env(settings: Settings) -> bool:
    """Persist canonical filter state into .env when it changes."""
    current = get_filter_state()
    persisted = filters_from_settings(settings)
    if current == persisted:
        return False

    save_settings(
        settings.model_copy(
            update={
                FILTER_STATUS_ENV_KEY: _encode_filter_env_list(current.status),
                FILTER_PRIORITY_ENV_KEY: _encode_filter_env_list(current.priority),
                FILTER_ASSIGNEE_ENV_KEY: _encode_filter_env_list(current.assignee),
            }
        )
    )
    return True


# -------------------------
# Filter state (session_state)
# -------------------------
def get_filter_state() -> FilterState:
    """
    Lee el estado de filtros desde st.session_state.
    NO renderiza widgets (eso lo hace render_filters en components/filters.py).
    """
    return FilterState(
        status=_normalize_filter_tokens(list(st.session_state.get(FILTER_STATUS_KEY) or [])),
        priority=_normalize_filter_tokens(list(st.session_state.get(FILTER_PRIORITY_KEY) or [])),
        assignee=_normalize_filter_tokens(list(st.session_state.get(FILTER_ASSIGNEE_KEY) or [])),
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
