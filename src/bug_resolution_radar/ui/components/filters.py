# bug_resolution_radar/ui/components/filters.py
from __future__ import annotations

import html
from typing import List, Optional

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import normalize_text_col, priority_rank
from bug_resolution_radar.ui.dashboard.constants import canonical_status_rank_map
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
    FilterState,
)


def _order_statuses_canonical(statuses: List[str]) -> List[str]:
    """Order statuses by canonical flow. Unknown ones keep stable order and go last."""
    idx = canonical_status_rank_map()

    def key_fn(pair: tuple[int, str]) -> tuple[int, int]:
        orig_i, s = pair
        k = (s or "").strip().lower()
        return (idx.get(k, 10_000), orig_i)

    return [s for _, s in sorted(list(enumerate(statuses)), key=key_fn)]


# ---------------------------------------------------------------------
# Internal: canonical keys + namespaced UI keys
# ---------------------------------------------------------------------
def _ui_key(prefix: str, name: str) -> str:
    p = (prefix or "").strip()
    return f"{p}::{name}" if p else name


def _sync_from_ui_to_canonical(ui_status_key: str, ui_prio_key: str, ui_assignee_key: str) -> None:
    """Copy UI widget state (namespaced keys) into canonical shared keys."""
    st.session_state[FILTER_STATUS_KEY] = list(st.session_state.get(ui_status_key) or [])
    st.session_state[FILTER_PRIORITY_KEY] = list(st.session_state.get(ui_prio_key) or [])
    st.session_state[FILTER_ASSIGNEE_KEY] = list(st.session_state.get(ui_assignee_key) or [])


def _mirror_canonical_to_ui(ui_status_key: str, ui_prio_key: str, ui_assignee_key: str) -> None:
    """Before creating widgets, ensure their state reflects canonical keys (for cross-component sync)."""
    st.session_state[ui_status_key] = list(st.session_state.get(FILTER_STATUS_KEY) or [])
    st.session_state[ui_prio_key] = list(st.session_state.get(FILTER_PRIORITY_KEY) or [])
    st.session_state[ui_assignee_key] = list(st.session_state.get(FILTER_ASSIGNEE_KEY) or [])


# ---------------------------------------------------------------------
# Filters UI
# ---------------------------------------------------------------------
def render_filters(df: pd.DataFrame, *, key_prefix: str = "") -> FilterState:
    """Render filter widgets and return the selected filter state.

    IMPORTANT:
    - Widgets use NAMESPACED keys (by key_prefix) to avoid StreamlitDuplicateElementKey
      when the same filters are rendered in multiple tabs.
    - Canonical shared state remains in:
        filter_status, filter_priority, filter_assignee
      so matrix/kanban/insights can still sync by writing those keys.
    """
    st.markdown("### Filtros")

    # Normalize empty values so filters + matrix can round-trip selections.
    status_col = (
        normalize_text_col(df["status"], "(sin estado)")
        if "status" in df.columns
        else pd.Series([], dtype=str)
    )
    priority_col = (
        normalize_text_col(df["priority"], "(sin priority)")
        if "priority" in df.columns
        else pd.Series([], dtype=str)
    )

    # Namespaced widget keys (avoid duplicates across tabs)
    ui_status_key = _ui_key(key_prefix, "filter_status_ui")
    ui_prio_key = _ui_key(key_prefix, "filter_priority_ui")
    ui_assignee_key = _ui_key(key_prefix, "filter_assignee_ui")

    # Mirror canonical -> ui before widget creation (so matrix clicks reflect in widgets)
    _mirror_canonical_to_ui(ui_status_key, ui_prio_key, ui_assignee_key)

    # Layout: Estado | Priority | Asignado  (Tipo eliminado)
    f1, f2, f3 = st.columns(3)

    with f1:
        status_opts_raw = status_col.astype(str).unique().tolist()
        status_opts = _order_statuses_canonical(status_opts_raw)

        # pills no siempre soporta "default" en todas las versiones, pero sí key/state.
        # Usamos session_state como fuente de verdad, y on_change para sincronizar canónico.
        st.pills(
            "Estado",
            options=status_opts,
            selection_mode="multi",
            default=list(st.session_state.get(ui_status_key) or []),
            key=ui_status_key,
            on_change=_sync_from_ui_to_canonical,
            args=(ui_status_key, ui_prio_key, ui_assignee_key),
        )

    with f2:
        if "priority" in df.columns:
            prio_opts = sorted(
                priority_col.astype(str).unique().tolist(),
                key=lambda p: (priority_rank(p), p),
            )
            st.multiselect(
                "Priority",
                prio_opts,
                default=list(st.session_state.get(ui_prio_key) or []),
                key=ui_prio_key,
                on_change=_sync_from_ui_to_canonical,
                args=(ui_status_key, ui_prio_key, ui_assignee_key),
            )
        else:
            # keep ui key consistent
            st.session_state[ui_prio_key] = []
            st.session_state[FILTER_PRIORITY_KEY] = []

    with f3:
        if "assignee" in df.columns:
            assignee_opts = sorted(df["assignee"].dropna().astype(str).unique().tolist())
            st.multiselect(
                "Asignado",
                assignee_opts,
                default=list(st.session_state.get(ui_assignee_key) or []),
                key=ui_assignee_key,
                on_change=_sync_from_ui_to_canonical,
                args=(ui_status_key, ui_prio_key, ui_assignee_key),
            )
        else:
            st.session_state[ui_assignee_key] = []
            st.session_state[FILTER_ASSIGNEE_KEY] = []

    # Return canonical state (single source of truth)
    return FilterState(
        status=list(st.session_state.get(FILTER_STATUS_KEY) or []),
        priority=list(st.session_state.get(FILTER_PRIORITY_KEY) or []),
        assignee=list(st.session_state.get(FILTER_ASSIGNEE_KEY) or []),
    )


def apply_filters(df: pd.DataFrame, fs: FilterState) -> pd.DataFrame:
    """Apply FilterState to dataframe and return a filtered copy.

    Also normalizes status/priority to keep UI consistent.
    """
    dff = df.copy()

    if "status" in dff.columns:
        dff["status"] = normalize_text_col(dff["status"], "(sin estado)")
    if "priority" in dff.columns:
        dff["priority"] = normalize_text_col(dff["priority"], "(sin priority)")

    if fs.status and "status" in dff.columns:
        dff = dff[dff["status"].isin(fs.status)]
    if fs.priority and "priority" in dff.columns:
        dff = dff[dff["priority"].isin(fs.priority)]
    if fs.assignee and "assignee" in dff.columns:
        dff = dff[dff["assignee"].isin(fs.assignee)]

    # IMPORTANTE: no filtramos por "type" (se muestra todo lo que entra por ingesta)
    return dff


# ---------------------------------------------------------------------
# Matrix (Estado x Priority)
# ---------------------------------------------------------------------
def _matrix_set_filters(st_name: str, prio: str) -> None:
    # Canonical keys (shared across tabs)
    st.session_state[FILTER_STATUS_KEY] = [st_name]
    st.session_state[FILTER_PRIORITY_KEY] = [prio]


def _matrix_clear_filters() -> None:
    st.session_state[FILTER_STATUS_KEY] = []
    st.session_state[FILTER_PRIORITY_KEY] = []
    st.session_state[FILTER_ASSIGNEE_KEY] = []


def _any_filter_active(fs: Optional[FilterState]) -> bool:
    if fs is None:
        return False
    return bool(fs.status or fs.priority or fs.assignee)


def render_status_priority_matrix(
    open_df: pd.DataFrame,
    fs: Optional[FilterState] = None,
    *,
    key_prefix: str = "mx",
) -> None:
    """Render a clickable matrix Estado x Priority for open issues.

    IMPORTANT: If you render this matrix more than once on the same page (e.g. in multiple tabs),
    you MUST pass different key_prefix values to avoid StreamlitDuplicateElementId.
    """
    if open_df is None or open_df.empty:
        return
    if "status" not in open_df.columns or "priority" not in open_df.columns:
        return

    st.markdown("### Matriz Estado x Priority (abiertas)")

    mx = open_df.assign(
        status=normalize_text_col(open_df["status"], "(sin estado)"),
        priority=normalize_text_col(open_df["priority"], "(sin priority)"),
    )

    # Orden filas: CANÓNICO
    statuses = _order_statuses_canonical(mx["status"].value_counts().index.tolist())

    # Orden columnas: impedimento primero + resto por rank
    priorities = sorted(
        mx["priority"].dropna().astype(str).unique().tolist(),
        key=lambda p: (priority_rank(p), p),
    )
    if "Supone un impedimento" in priorities:
        priorities = ["Supone un impedimento"] + [
            p for p in priorities if p != "Supone un impedimento"
        ]

    # current selection from canonical session_state (single selection only)
    selected_status = None
    selected_priority = None

    ss = st.session_state.get(FILTER_STATUS_KEY)
    sp = st.session_state.get(FILTER_PRIORITY_KEY)

    if isinstance(ss, list) and len(ss) == 1:
        selected_status = ss[0]
    if isinstance(sp, list) and len(sp) == 1:
        selected_priority = sp[0]

    has_matrix_sel = bool(selected_status and selected_priority)
    has_any_filter = _any_filter_active(fs)

    cA, cB = st.columns([3, 1])
    with cA:
        if has_matrix_sel:
            st.caption(f"Seleccionado: Estado={selected_status} · Priority={selected_priority}")
        else:
            st.caption("Click en una celda: sincroniza Estado/Priority y actualiza la tabla.")
    with cB:
        st.button(
            "Limpiar selección",
            key=f"{key_prefix}::clear",
            disabled=not has_any_filter,
            on_click=_matrix_clear_filters,
        )

    counts = pd.crosstab(mx["status"], mx["priority"])

    # Totales: columnas + filas
    col_totals = {p: int(counts[p].sum()) if p in counts.columns else 0 for p in priorities}
    row_totals = counts.sum(axis=1).to_dict()

    # Header row (con totales por columna)
    hdr = st.columns(len(priorities) + 1)
    hdr[0].markdown("**Estado (total)**")
    for i, p in enumerate(priorities):
        label = f"{p} ({col_totals.get(p, 0)})"
        if selected_priority == p:
            hdr[i + 1].markdown(
                f'<span style="color:var(--bbva-primary); font-weight:800;">{html.escape(label)}</span>',
                unsafe_allow_html=True,
            )
        else:
            hdr[i + 1].markdown(f"**{label}**")

    # Rows (con total por estado)
    for st_name in statuses:
        total_row = int(row_totals.get(st_name, 0))
        row = st.columns(len(priorities) + 1)

        row_label = f"{st_name} ({total_row})"
        if selected_status == st_name:
            row[0].markdown(
                f'<span style="color:var(--bbva-primary); font-weight:800;">{html.escape(row_label)}</span>',
                unsafe_allow_html=True,
            )
        else:
            row[0].markdown(row_label)

        for i, p in enumerate(priorities):
            cnt = (
                int(counts.at[st_name, p])
                if (st_name in counts.index and p in counts.columns)
                else 0
            )
            is_selected = bool(selected_status == st_name and selected_priority == p)
            row[i + 1].button(
                str(cnt),
                key=f"{key_prefix}::cell::{st_name}::{p}",
                disabled=(cnt == 0),
                type="primary" if is_selected else "secondary",
                use_container_width=True,
                on_click=_matrix_set_filters,
                args=(st_name, p),
            )
