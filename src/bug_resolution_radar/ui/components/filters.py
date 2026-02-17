"""Dashboard filters, matrix interactions and synchronized filter state helpers."""

from __future__ import annotations

import html
from typing import List, Optional

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import (
    normalize_text_col,
    priority_color,
    priority_rank,
    status_color,
)
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


def _status_combo_label(status: str) -> str:
    return status


def _priority_combo_label(priority: str) -> str:
    return priority


def _hex_with_alpha(hex_color: str, alpha: int) -> str:
    h = (hex_color or "").strip()
    if bool(st.session_state.get("workspace_dark_mode", False)):
        if alpha <= 40:
            alpha = 52
        elif alpha <= 130:
            alpha = 178
    if len(h) == 7 and h.startswith("#"):
        return f"{h}{alpha:02X}"
    return h


def _inject_filters_panel_css() -> None:
    st.markdown(
        """
        <style>
          [data-testid="stMultiSelect"] > label {
            margin-bottom: 0.1rem !important;
          }
          [data-testid="stMultiSelect"] [data-baseweb="select"] > div {
            min-height: 2.28rem !important;
          }
          /* Base chips style (neutral / assignee-like); status & priority overrides are injected later */
          [data-testid="stMultiSelect"] [data-baseweb="tag"] {
            background: color-mix(in srgb, var(--bbva-surface) 88%, var(--bbva-surface-2)) !important;
            border: 1px solid var(--bbva-border) !important;
            color: var(--bbva-text) !important;
          }
          [data-testid="stMultiSelect"] [data-baseweb="tag"] * {
            color: var(--bbva-text) !important;
          }
          [data-testid="stMultiSelect"] [data-baseweb="tag"] svg {
            fill: var(--bbva-text-muted) !important;
          }
          [data-testid="stMultiSelect"] [role="listbox"] {
            background: var(--bbva-surface) !important;
            border: 1px solid var(--bbva-border) !important;
          }
          [data-testid="stMultiSelect"] [role="option"] {
            color: var(--bbva-text) !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _css_attr_value(txt: str) -> str:
    return (txt or "").replace("\\", "\\\\").replace('"', '\\"')


def _inject_colored_multiselect_css(
    *, status_labels: List[str], priority_labels: List[str]
) -> None:
    rules: List[str] = []

    for label in status_labels:
        raw = (label or "").strip()
        c = status_color(raw)
        bg = _hex_with_alpha(c, 24)
        border = _hex_with_alpha(c, 120)
        v = _css_attr_value(label)
        rules.append(
            f"""
            [role="option"][aria-label="{v}"] {{
              background: {bg} !important;
              border-left: 3px solid {c} !important;
              position: relative;
              padding-left: 1.72rem !important;
              background-image: radial-gradient(circle at 0.68rem 50%, {c} 0 0.30rem, transparent 0.31rem) !important;
              background-repeat: no-repeat !important;
            }}
            [role="option"][aria-label="{v}"]::before {{
              content: "";
              width: 0.56rem;
              height: 0.56rem;
              border-radius: 999px;
              background: {c};
              position: absolute;
              left: 0.60rem;
              top: 50%;
              transform: translateY(-50%);
            }}
            [data-baseweb="tag"][title="{v}"] {{
              background: {bg} !important;
              border: 1px solid {border} !important;
              color: {c} !important;
              background-image: none !important;
            }}
            [role="option"]:has(span[title="{v}"]),
            [role="option"]:has(div[title="{v}"]),
            [role="option"]:has(span:only-child):has(span[title="{v}"]) {{
              background: {bg} !important;
              border-left: 3px solid {c} !important;
              position: relative;
              padding-left: 1.72rem !important;
              background-image: radial-gradient(circle at 0.68rem 50%, {c} 0 0.30rem, transparent 0.31rem) !important;
              background-repeat: no-repeat !important;
            }}
            [role="option"]:has(span[title="{v}"])::before,
            [role="option"]:has(div[title="{v}"])::before {{
              content: "";
              width: 0.56rem;
              height: 0.56rem;
              border-radius: 999px;
              background: {c};
              position: absolute;
              left: 0.60rem;
              top: 50%;
              transform: translateY(-50%);
            }}
            [data-baseweb="tag"]:has(span[title="{v}"]),
            [data-baseweb="tag"]:has(div[title="{v}"]) {{
              background: {bg} !important;
              border: 1px solid {border} !important;
              color: {c} !important;
              background-image: none !important;
            }}
            [data-baseweb="tag"]:has(span[title="{v}"]) * ,
            [data-baseweb="tag"]:has(div[title="{v}"]) * {{
              color: {c} !important;
            }}
            """
        )

    for label in priority_labels:
        raw = (label or "").strip()
        c = priority_color(raw)
        bg = _hex_with_alpha(c, 24)
        border = _hex_with_alpha(c, 120)
        v = _css_attr_value(label)
        rules.append(
            f"""
            [role="option"][aria-label="{v}"] {{
              background: {bg} !important;
              border-left: 3px solid {c} !important;
              position: relative;
              padding-left: 1.72rem !important;
              background-image: radial-gradient(circle at 0.68rem 50%, {c} 0 0.30rem, transparent 0.31rem) !important;
              background-repeat: no-repeat !important;
            }}
            [role="option"][aria-label="{v}"]::before {{
              content: "";
              width: 0.56rem;
              height: 0.56rem;
              border-radius: 999px;
              background: {c};
              position: absolute;
              left: 0.60rem;
              top: 50%;
              transform: translateY(-50%);
            }}
            [data-baseweb="tag"][title="{v}"] {{
              background: {bg} !important;
              border: 1px solid {border} !important;
              color: {c} !important;
              background-image: none !important;
            }}
            [role="option"]:has(span[title="{v}"]),
            [role="option"]:has(div[title="{v}"]),
            [role="option"]:has(span:only-child):has(span[title="{v}"]) {{
              background: {bg} !important;
              border-left: 3px solid {c} !important;
              position: relative;
              padding-left: 1.72rem !important;
              background-image: radial-gradient(circle at 0.68rem 50%, {c} 0 0.30rem, transparent 0.31rem) !important;
              background-repeat: no-repeat !important;
            }}
            [role="option"]:has(span[title="{v}"])::before,
            [role="option"]:has(div[title="{v}"])::before {{
              content: "";
              width: 0.56rem;
              height: 0.56rem;
              border-radius: 999px;
              background: {c};
              position: absolute;
              left: 0.60rem;
              top: 50%;
              transform: translateY(-50%);
            }}
            [data-baseweb="tag"]:has(span[title="{v}"]),
            [data-baseweb="tag"]:has(div[title="{v}"]) {{
              background: {bg} !important;
              border: 1px solid {border} !important;
              color: {c} !important;
              background-image: none !important;
            }}
            [data-baseweb="tag"]:has(span[title="{v}"]) * ,
            [data-baseweb="tag"]:has(div[title="{v}"]) * {{
              color: {c} !important;
            }}
            """
        )

    if rules:
        st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)


def _mirror_canonical_to_ui(ui_status_key: str, ui_prio_key: str, ui_assignee_key: str) -> None:
    """Before creating widgets, ensure their state reflects canonical keys (for cross-component sync)."""
    st.session_state[ui_status_key] = [
        _status_combo_label(x) for x in list(st.session_state.get(FILTER_STATUS_KEY) or [])
    ]
    st.session_state[ui_prio_key] = [
        _priority_combo_label(x) for x in list(st.session_state.get(FILTER_PRIORITY_KEY) or [])
    ]
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
    _inject_filters_panel_css()

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

    status_opts_raw = status_col.astype(str).unique().tolist()
    status_opts_raw = _order_statuses_canonical(status_opts_raw)
    status_opts_ui = [_status_combo_label(s) for s in status_opts_raw]

    prio_opts_ui: List[str] = []
    if "priority" in df.columns:
        prio_opts = sorted(
            priority_col.astype(str).unique().tolist(),
            key=lambda p: (priority_rank(p), p),
        )
        prio_opts_ui = [_priority_combo_label(p) for p in prio_opts]

    # Inject option/tag color styles once to avoid per-column layout jitter.
    _inject_colored_multiselect_css(status_labels=status_opts_ui, priority_labels=prio_opts_ui)

    with st.container(border=True):
        c_status, c_prio, c_assignee = st.columns([1.35, 1.0, 1.0], gap="small")

        with c_status:
            selected_ui_status = list(st.session_state.get(ui_status_key) or [])
            st.session_state[ui_status_key] = [x for x in selected_ui_status if x in status_opts_ui]
            st.multiselect(
                "Estado",
                status_opts_ui,
                default=list(st.session_state.get(ui_status_key) or []),
                key=ui_status_key,
                on_change=_sync_from_ui_to_canonical,
                args=(ui_status_key, ui_prio_key, ui_assignee_key),
                placeholder="Estado",
            )

        with c_prio:
            if "priority" in df.columns:
                selected_ui_prio = list(st.session_state.get(ui_prio_key) or [])
                st.session_state[ui_prio_key] = [x for x in selected_ui_prio if x in prio_opts_ui]
                st.multiselect(
                    "Priority",
                    prio_opts_ui,
                    default=list(st.session_state.get(ui_prio_key) or []),
                    key=ui_prio_key,
                    on_change=_sync_from_ui_to_canonical,
                    args=(ui_status_key, ui_prio_key, ui_assignee_key),
                    placeholder="Priority",
                )
            else:
                st.session_state[ui_prio_key] = []
                st.session_state[FILTER_PRIORITY_KEY] = []

        with c_assignee:
            if "assignee" in df.columns:
                assignee_opts = sorted(df["assignee"].dropna().astype(str).unique().tolist())
                st.multiselect(
                    "Asignado",
                    assignee_opts,
                    default=list(st.session_state.get(ui_assignee_key) or []),
                    key=ui_assignee_key,
                    on_change=_sync_from_ui_to_canonical,
                    args=(ui_status_key, ui_prio_key, ui_assignee_key),
                    placeholder="Asignado",
                )
            else:
                st.session_state[ui_assignee_key] = []
                st.session_state[FILTER_ASSIGNEE_KEY] = []

    # Return canonical state (single source of truth)
    fs = FilterState(
        status=list(st.session_state.get(FILTER_STATUS_KEY) or []),
        priority=list(st.session_state.get(FILTER_PRIORITY_KEY) or []),
        assignee=list(st.session_state.get(FILTER_ASSIGNEE_KEY) or []),
    )
    return fs


def apply_filters(df: pd.DataFrame, fs: FilterState) -> pd.DataFrame:
    """Apply FilterState to dataframe and return a filtered copy.

    Also normalizes status/priority to keep UI consistent.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    mask = pd.Series(True, index=df.index)

    status_norm: pd.Series | None = None
    if "status" in df.columns:
        status_norm = normalize_text_col(df["status"], "(sin estado)")
        if fs.status:
            mask &= status_norm.isin(fs.status)

    priority_norm: pd.Series | None = None
    if "priority" in df.columns:
        priority_norm = normalize_text_col(df["priority"], "(sin priority)")
        if fs.priority:
            mask &= priority_norm.isin(fs.priority)

    if fs.assignee and "assignee" in df.columns:
        mask &= df["assignee"].isin(fs.assignee)

    dff = df.loc[mask].copy(deep=False)

    if status_norm is not None:
        dff["status"] = status_norm.loc[mask].to_numpy()
    if priority_norm is not None:
        dff["priority"] = priority_norm.loc[mask].to_numpy()

    # IMPORTANTE: no filtramos por "type" (se muestra todo lo que entra por ingesta)
    return dff


# ---------------------------------------------------------------------
# Matrix (Estado x Priority)
# ---------------------------------------------------------------------
def _matrix_set_filters(st_name: str, prio: str) -> None:
    # Multi-status selection with single priority focus from the clicked cell.
    statuses = list(st.session_state.get(FILTER_STATUS_KEY) or [])
    if st_name in statuses:
        statuses = [s for s in statuses if s != st_name]
    else:
        statuses.append(st_name)
    st.session_state[FILTER_STATUS_KEY] = statuses
    st.session_state[FILTER_PRIORITY_KEY] = [prio] if statuses else []


def _matrix_clear_filters() -> None:
    st.session_state[FILTER_STATUS_KEY] = []
    st.session_state[FILTER_PRIORITY_KEY] = []
    st.session_state[FILTER_ASSIGNEE_KEY] = []


def _any_filter_active(fs: Optional[FilterState]) -> bool:
    if fs is None:
        return False
    return bool(fs.status or fs.priority or fs.assignee)


def _matrix_chip_style(hex_color: str, *, selected: bool = False) -> str:
    color = (hex_color or "#8EA2C4").strip()
    border = _hex_with_alpha(color, 150 if selected else 110)
    bg = _hex_with_alpha(color, 48 if selected else 24)
    fw = "800" if selected else "700"
    return (
        f"display:block; width:100%; text-align:center; padding:0.42rem 0.54rem; "
        f"border-radius:11px; border:1px solid {border}; background:{bg}; "
        f"color:{color}; font-weight:{fw}; font-size:0.92rem; line-height:1.18;"
    )


def _inject_matrix_compact_css(scope_key: str) -> None:
    st.markdown(
        f"""
        <style>
          .st-key-{scope_key} div[data-testid="stButton"] > button {{
            min-height: 2.15rem !important;
            padding: 0.18rem 0.42rem !important;
            border-radius: 11px !important;
            font-size: 0.95rem !important;
            font-weight: 650 !important;
          }}
          .st-key-{scope_key} div[data-testid="stMarkdownContainer"] p {{
            margin-bottom: 0.16rem !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


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

    # current selection from canonical session_state (multi-status enabled)
    selected_statuses = list(st.session_state.get(FILTER_STATUS_KEY) or [])
    selected_priorities = list(st.session_state.get(FILTER_PRIORITY_KEY) or [])

    has_matrix_sel = bool(selected_statuses or selected_priorities)
    has_any_filter = _any_filter_active(fs)

    cA, cB = st.columns([3, 1])
    with cA:
        if has_matrix_sel:
            status_txt = ", ".join(selected_statuses) if selected_statuses else "(todos)"
            prio_txt = ", ".join(selected_priorities) if selected_priorities else "(todas)"
            st.caption(f"Seleccionado: Estado={status_txt} · Priority={prio_txt}")
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
    total_open = int(sum(row_totals.values()))

    matrix_scope_key = f"{(key_prefix or 'mx')}_matrix_panel"
    _inject_matrix_compact_css(matrix_scope_key)

    with st.container(border=True, key=matrix_scope_key):
        # Header row (con totales por columna)
        hdr = st.columns(len(priorities) + 1)
        hdr[0].markdown(f"**Estado ({total_open:,})**")
        for i, p in enumerate(priorities):
            label = f"{p} ({col_totals.get(p, 0)})"
            p_color = priority_color(p)
            hdr[i + 1].markdown(
                f'<div style="{_matrix_chip_style(p_color, selected=p in selected_priorities)}">'
                f"{html.escape(label)}</div>",
                unsafe_allow_html=True,
            )

        # Rows (con total por estado)
        for st_name in statuses:
            total_row = int(row_totals.get(st_name, 0))
            row = st.columns(len(priorities) + 1)

            row_label = f"{st_name} ({total_row})"
            st_color = status_color(st_name)
            row[0].markdown(
                f'<div style="{_matrix_chip_style(st_color, selected=st_name in selected_statuses)}">'
                f"{html.escape(row_label)}</div>",
                unsafe_allow_html=True,
            )

            for i, p in enumerate(priorities):
                cnt = (
                    int(counts.at[st_name, p])
                    if (st_name in counts.index and p in counts.columns)
                    else 0
                )
                is_selected = bool(st_name in selected_statuses and p in selected_priorities)
                row[i + 1].button(
                    str(cnt),
                    key=f"{key_prefix}::cell::{st_name}::{p}",
                    disabled=(cnt == 0),
                    type="primary" if is_selected else "secondary",
                    use_container_width=True,
                    on_click=_matrix_set_filters,
                    args=(st_name, p),
                )
