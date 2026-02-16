from __future__ import annotations

import html
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import normalize_text_col, priority_rank


@dataclass(frozen=True)
class FilterState:
    status: List[str]
    priority: List[str]
    itype: List[str]
    assignee: List[str]


def render_filters(df: pd.DataFrame) -> FilterState:
    """Render filter widgets and return the selected filter state.

    Uses Streamlit session_state keys so other components (matrix) can update them.
    """
    st.markdown("### Filtros")

    # Normalize empty values so filters + matrix can round-trip selections.
    status_col = normalize_text_col(df["status"], "(sin estado)") if "status" in df.columns else pd.Series([], dtype=str)
    priority_col = (
        normalize_text_col(df["priority"], "(sin priority)") if "priority" in df.columns else pd.Series([], dtype=str)
    )

    f1, f2, f3, f4 = st.columns(4)

    with f1:
        status_opts = sorted(status_col.astype(str).unique().tolist())
        status = st.pills("Estado", options=status_opts, selection_mode="multi", default=[], key="filter_status")

    with f2:
        if "priority" in df.columns:
            prio_opts = sorted(priority_col.astype(str).unique().tolist(), key=lambda p: (priority_rank(p), p))
            priority = st.multiselect("Priority", prio_opts, default=[], key="filter_priority")
        else:
            priority = []

    with f3:
        if "type" in df.columns:
            itype_opts = sorted(df["type"].dropna().astype(str).unique().tolist())
            itype = st.multiselect("Tipo", itype_opts, default=[], key="filter_type")
        else:
            itype = []

    with f4:
        if "assignee" in df.columns:
            assignee_opts = sorted(df["assignee"].dropna().astype(str).unique().tolist())
            assignee = st.multiselect("Asignado", assignee_opts, default=[], key="filter_assignee")
        else:
            assignee = []

    return FilterState(
        status=list(status or []),
        priority=list(priority or []),
        itype=list(itype or []),
        assignee=list(assignee or []),
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
    if fs.itype and "type" in dff.columns:
        dff = dff[dff["type"].isin(fs.itype)]
    if fs.assignee and "assignee" in dff.columns:
        dff = dff[dff["assignee"].isin(fs.assignee)]

    return dff


# ----------------------------
# Matrix (Estado x Priority)
# ----------------------------


def _matrix_set_filters(st_name: str, prio: str) -> None:
    # Callback: runs before the next rerun, so it can safely update widget state.
    st.session_state["filter_status"] = [st_name]
    st.session_state["filter_priority"] = [prio]


def _matrix_clear_filters() -> None:
    # Callback: runs before the next rerun.
    st.session_state["filter_status"] = []
    st.session_state["filter_priority"] = []


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

    status_counts = mx["status"].value_counts()
    statuses = status_counts.index.tolist()

    priorities = sorted(
        mx["priority"].dropna().astype(str).unique().tolist(),
        key=lambda p: (priority_rank(p), p),
    )

    # current selection from session_state (single selection only)
    selected_status = None
    selected_priority = None

    ss = st.session_state.get("filter_status")
    sp = st.session_state.get("filter_priority")

    if isinstance(ss, list) and len(ss) == 1:
        selected_status = ss[0]
    if isinstance(sp, list) and len(sp) == 1:
        selected_priority = sp[0]

    has_matrix_sel = bool(selected_status and selected_priority)

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
            disabled=not has_matrix_sel,
            on_click=_matrix_clear_filters,
        )

    # Header row
    hdr = st.columns(len(priorities) + 1)
    hdr[0].markdown("**Estado**")
    for i, p in enumerate(priorities):
        if selected_priority == p:
            hdr[i + 1].markdown(
                f'<span style="color:var(--bbva-primary); font-weight:800;">{html.escape(p)}</span>',
                unsafe_allow_html=True,
            )
        else:
            hdr[i + 1].markdown(f"**{p}**")

    counts = pd.crosstab(mx["status"], mx["priority"])

    for st_name in statuses[:12]:  # keep it usable; top statuses by count
        row = st.columns(len(priorities) + 1)
        if selected_status == st_name:
            row[0].markdown(
                f'<span style="color:var(--bbva-primary); font-weight:800;">{html.escape(st_name)}</span>',
                unsafe_allow_html=True,
            )
        else:
            row[0].markdown(st_name)

        for i, p in enumerate(priorities):
            cnt = int(counts.at[st_name, p]) if (st_name in counts.index and p in counts.columns) else 0
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