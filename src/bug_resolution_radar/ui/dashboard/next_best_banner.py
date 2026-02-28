"""Premium Next Best Action banner shown above filters in operational sections."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from typing import Callable, List, Tuple

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import (
    chip_style_from_color,
    normalize_text_col,
    priority_color,
    status_color,
)
from bug_resolution_radar.ui.components.filters import (
    FILTER_ACTION_CONTEXT_KEY,
    apply_filters,
)
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
    FilterState,
    get_filter_state,
    open_only,
)
from bug_resolution_radar.ui.insights.copilot import (
    NextBestAction,
    build_operational_snapshot,
    list_next_best_actions,
    resolve_filters_against_open_df,
)

# Intentionally session-only: unresolved actions reappear in future sessions.
NBA_REVIEW_STATE_KEY = "__nba_review_state"
TERMINAL_STATUS_TOKENS = (
    "closed",
    "resolved",
    "done",
    "deployed",
    "accepted",
    "cancelled",
    "canceled",
)


def _safe_df(df: pd.DataFrame | None) -> pd.DataFrame:
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def _norm_token(value: object) -> str:
    txt = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", txt).strip()


def _is_terminal_status(value: object) -> bool:
    token = _norm_token(value)
    if not token:
        return False
    return any(t in token for t in TERMINAL_STATUS_TOKENS)


def _exclude_terminal_statuses(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    if "status" not in df.columns:
        return df.copy(deep=False)
    stx = normalize_text_col(df["status"], "(sin estado)")
    return df.loc[~stx.map(_is_terminal_status)].copy(deep=False)


def _derive_actionable_status_scope(
    *,
    open_df: pd.DataFrame,
    priority_filters: List[str],
    assignee_filters: List[str],
) -> List[str]:
    if not isinstance(open_df, pd.DataFrame) or open_df.empty or "status" not in open_df.columns:
        return []

    mask = pd.Series(True, index=open_df.index)
    if priority_filters and "priority" in open_df.columns:
        mask &= normalize_text_col(open_df["priority"], "(sin priority)").isin(priority_filters)
    if assignee_filters and "assignee" in open_df.columns:
        mask &= normalize_text_col(open_df["assignee"], "(sin asignar)").isin(assignee_filters)

    scoped = open_df.loc[mask]
    if scoped.empty:
        return []
    vals = normalize_text_col(scoped["status"], "(sin estado)").astype(str).value_counts()
    return [str(v) for v in vals.index.tolist() if str(v).strip()]


def _match_count(
    *,
    open_df: pd.DataFrame,
    status_filters: List[str],
    priority_filters: List[str],
    assignee_filters: List[str],
) -> int:
    if not isinstance(open_df, pd.DataFrame) or open_df.empty:
        return 0
    mask = pd.Series(True, index=open_df.index)
    if status_filters and "status" in open_df.columns:
        mask &= normalize_text_col(open_df["status"], "(sin estado)").isin(status_filters)
    if priority_filters and "priority" in open_df.columns:
        mask &= normalize_text_col(open_df["priority"], "(sin priority)").isin(priority_filters)
    if assignee_filters and "assignee" in open_df.columns:
        mask &= normalize_text_col(open_df["assignee"], "(sin asignar)").isin(assignee_filters)
    return int(mask.sum())


def _target_issue_count(
    *,
    df_all: pd.DataFrame,
    status_filters: List[str],
    priority_filters: List[str],
    assignee_filters: List[str],
) -> int:
    """Count exactly as Issues tab will count after applying NBA filters."""
    if not isinstance(df_all, pd.DataFrame) or df_all.empty:
        return 0
    dff_target = apply_filters(
        df_all,
        FilterState(
            status=list(status_filters or []),
            priority=list(priority_filters or []),
            assignee=list(assignee_filters or []),
        ),
    )
    return int(len(dff_target))


def _tone(action_title: str) -> Tuple[str, str, str]:
    t = str(action_title or "").strip().lower()
    if "ownership" in t or "critico" in t:
        return ("PRIORIDAD OPERATIVA", "#8F5C00", "Foco en criticidad")
    if "bloqueo" in t:
        return ("SEÑAL DE BLOQUEO", "#A56A12", "Flujo condicionado")
    if "balance" in t or "entrada" in t:
        return ("SEÑAL DE CAPACIDAD", "#9A6510", "Control semanal")
    if "seguimiento" in t:
        return ("SEGUIMIENTO", "#1A8A5E", "Ritmo estable")
    return ("ACCION RECOMENDADA", "#8F5C00", "Foco recomendado")


def _apply_action(
    *,
    target_section: str,
    status_filters: List[str],
    priority_filters: List[str],
    assignee_filters: List[str],
    scope_key: str,
    action_id: str,
    context_label: str,
) -> None:
    # Only mark reviewed inside current Streamlit session.
    # This ensures unresolved actions can reappear when a new client session starts.
    state = st.session_state.get(NBA_REVIEW_STATE_KEY)
    review_state = state if isinstance(state, dict) else {}
    scope_entry = review_state.get(scope_key)
    scope_data = scope_entry if isinstance(scope_entry, dict) else {}
    reviewed = list(scope_data.get("reviewed_ids") or [])
    if action_id and action_id not in reviewed:
        reviewed.append(action_id)
    scope_data["reviewed_ids"] = reviewed
    review_state[scope_key] = scope_data
    st.session_state[NBA_REVIEW_STATE_KEY] = review_state

    st.session_state[FILTER_STATUS_KEY] = list(status_filters or [])
    st.session_state[FILTER_PRIORITY_KEY] = list(priority_filters or [])
    st.session_state[FILTER_ASSIGNEE_KEY] = list(assignee_filters or [])
    st.session_state[FILTER_ACTION_CONTEXT_KEY] = {
        "label": str(context_label or "").strip(),
        "status": list(status_filters or []),
        "priority": list(priority_filters or []),
        "assignee": list(assignee_filters or []),
        "action_id": str(action_id or ""),
        "scope": str(scope_key or ""),
    }
    st.session_state["__jump_to_tab"] = str(target_section or "issues")


def _chips_html(values: List[str], *, color_fn: Callable[[str], str]) -> str:
    chips: List[str] = []
    for raw in list(values or []):
        txt = str(raw or "").strip()
        if not txt:
            continue
        style = chip_style_from_color(color_fn(txt))
        chips.append(f'<span class="nba-inline-chip" style="{style}">{html.escape(txt)}</span>')
    return "".join(chips)


def _filters_markup(
    *, status_filters: List[str], priority_filters: List[str], assignee_filters: List[str]
) -> str:
    del assignee_filters  # Owner is intentionally omitted: it is already implicit in the insight context.
    status_chips = _chips_html(status_filters, color_fn=status_color)
    priority_chips = _chips_html(priority_filters, color_fn=priority_color)
    if not status_chips and not priority_chips:
        return '<div class="nba-tgt">Sin filtro adicional</div>'
    return (
        '<div class="nba-filters">'
        '<div class="nba-filter-row">'
        '<span class="nba-filter-inline-group">'
        '<span class="nba-filter-label">Status:</span>'
        f'<span class="nba-filter-chips">{status_chips}</span>'
        "</span>"
        '<span class="nba-filter-inline-group">'
        '<span class="nba-filter-label">Priority:</span>'
        f'<span class="nba-filter-chips">{priority_chips}</span>'
        "</span>"
        "</div>"
        "</div>"
    )


def _issues_label(n: int) -> str:
    return "incidencia" if int(n) == 1 else "incidencias"


def _resolved_copy(action: NextBestAction, *, matches: int) -> tuple[str, str]:
    n = max(int(matches), 0)
    t = str(action.title or "").strip().lower()
    if "ownership" in t or "critico" in t:
        body = "Prioridad inmediata: asignar ownership en incidencias criticas sin owner."
        impact = f"Alcance validado en Issues: {n} {_issues_label(n)}."
        return body, impact
    if "bloqueo" in t:
        body = "Prioridad inmediata: desbloquear incidencias activas que frenan el flujo."
        impact = f"Alcance validado en Issues: {n} {_issues_label(n)}."
        return body, impact
    if "balance" in t or "entrada" in t:
        body = "Prioridad inmediata: corregir el desbalance entre entrada y salida."
        impact = f"Alcance validado en Issues: {n} {_issues_label(n)}."
        return body, impact
    if "cola" in t or "envejecida" in t:
        body = "Prioridad inmediata: reducir cola envejecida con gestion dedicada."
        impact = f"Alcance validado en Issues: {n} {_issues_label(n)}."
        return body, impact
    if "duplic" in t:
        body = "Prioridad inmediata: consolidar duplicidades para reducir ruido operativo."
        impact = f"Alcance validado en Issues: {n} {_issues_label(n)}."
        return body, impact
    body = "Prioridad inmediata: ejecutar revision focalizada del conjunto objetivo."
    impact = f"Alcance validado en Issues: {n} {_issues_label(n)}."
    return body, impact


def _context_label_for_action(action: NextBestAction) -> str:
    t = str(action.title or "").strip().lower()
    if "ownership" in t or "critico" in t:
        return "Incidencias criticas sin owner"
    if "bloqueo" in t:
        return "Incidencias bloqueadas"
    if "balance" in t or "entrada" in t:
        return "Desbalance entrada/salida"
    if "cola" in t or "envejecida" in t:
        return "Cola envejecida"
    if "duplic" in t:
        return "Duplicidades operativas"
    title = str(action.title or "").strip()
    return title if title else "Accion prioritaria"


def _scope_key() -> str:
    country = str(st.session_state.get("workspace_country") or "").strip() or "global"
    source = str(st.session_state.get("workspace_source_id") or "").strip() or "all-sources"
    return f"{country}::{source}"


def _reviewed_ids(scope_key: str) -> List[str]:
    state = st.session_state.get(NBA_REVIEW_STATE_KEY)
    review_state = state if isinstance(state, dict) else {}
    scope_entry = review_state.get(scope_key)
    scope_data = scope_entry if isinstance(scope_entry, dict) else {}
    return list(scope_data.get("reviewed_ids") or [])


def _pending_preview_index(scope_key: str) -> int:
    state = st.session_state.get(NBA_REVIEW_STATE_KEY)
    review_state = state if isinstance(state, dict) else {}
    scope_entry = review_state.get(scope_key)
    scope_data = scope_entry if isinstance(scope_entry, dict) else {}
    try:
        return max(int(scope_data.get("preview_index", 0) or 0), 0)
    except Exception:
        return 0


def _advance_pending_preview(scope_key: str) -> None:
    state = st.session_state.get(NBA_REVIEW_STATE_KEY)
    review_state = state if isinstance(state, dict) else {}
    scope_entry = review_state.get(scope_key)
    scope_data = dict(scope_entry) if isinstance(scope_entry, dict) else {}
    current = _pending_preview_index(scope_key)
    scope_data["preview_index"] = current + 1
    review_state[scope_key] = scope_data
    st.session_state[NBA_REVIEW_STATE_KEY] = review_state


def _select_pending_action(
    *,
    actionable_items: List[tuple[str, NextBestAction, List[str], List[str], List[str], int]],
    reviewed: set[str],
    preview_index: int,
) -> tuple[tuple[str, NextBestAction, List[str], List[str], List[str], int] | None, int]:
    pending_items = [x for x in actionable_items if x[0] not in reviewed]
    pending_count = len(pending_items)
    if pending_count <= 0:
        return None, 0
    idx = max(int(preview_index), 0) % pending_count
    return pending_items[idx], pending_count


def _action_id(
    *,
    title: str,
    status_filters: List[str],
    priority_filters: List[str],
    assignee_filters: List[str],
) -> str:
    raw = (
        f"{str(title).strip().lower()}|"
        f"{','.join(sorted([x.lower() for x in status_filters]))}|"
        f"{','.join(sorted([x.lower() for x in priority_filters]))}|"
        f"{','.join(sorted([x.lower() for x in assignee_filters]))}"
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def render_next_best_banner(*, df_all: pd.DataFrame, section: str) -> None:
    safe_all = _safe_df(df_all)
    if safe_all.empty:
        return

    fs = get_filter_state()
    dff = apply_filters(safe_all, fs)
    open_df = _exclude_terminal_statuses(open_only(dff))
    if open_df.empty:
        return
    base_open_df = _exclude_terminal_statuses(open_only(safe_all))
    if base_open_df.empty:
        return

    snapshot = build_operational_snapshot(dff=dff, open_df=open_df)
    section_norm = str(section or "").strip().lower()
    primary_target = "kanban" if section_norm == "kanban" else "issues"
    scope_key = _scope_key()

    actionable_items: List[tuple[str, NextBestAction, List[str], List[str], List[str], int]] = []
    for action in list_next_best_actions(snapshot=snapshot, cards=None):
        status_filters, priority_filters, assignee_filters = resolve_filters_against_open_df(
            open_df=base_open_df,
            status_filters=list(action.status_filters or []),
            priority_filters=list(action.priority_filters or []),
            assignee_filters=list(action.assignee_filters or []),
        )
        if not status_filters:
            status_filters = _derive_actionable_status_scope(
                open_df=base_open_df,
                priority_filters=priority_filters,
                assignee_filters=assignee_filters,
            )
        open_matches = _match_count(
            open_df=base_open_df,
            status_filters=status_filters,
            priority_filters=priority_filters,
            assignee_filters=assignee_filters,
        )
        if open_matches <= 0:
            continue
        matches = _target_issue_count(
            df_all=safe_all,
            status_filters=status_filters,
            priority_filters=priority_filters,
            assignee_filters=assignee_filters,
        )
        if matches <= 0:
            continue
        aid = _action_id(
            title=action.title,
            status_filters=status_filters,
            priority_filters=priority_filters,
            assignee_filters=assignee_filters,
        )
        actionable_items.append(
            (aid, action, status_filters, priority_filters, assignee_filters, matches)
        )

    if not actionable_items:
        return

    reviewed = set(_reviewed_ids(scope_key))
    selected, pending_count = _select_pending_action(
        actionable_items=actionable_items,
        reviewed=reviewed,
        preview_index=_pending_preview_index(scope_key),
    )
    if selected is None:
        return

    action_id, action, status_filters, priority_filters, assignee_filters, matches = selected
    kicker, _, tone = _tone(action.title)
    _, resolved_impact = _resolved_copy(action, matches=matches)
    context_label = _context_label_for_action(action)
    is_dark = bool(st.session_state.get("workspace_dark_mode", False))
    if is_dark:
        # Subtle amber tuned for dark backgrounds (premium + high readability).
        banner_bg = "#CDBB86"
        banner_border = "#9D7A35"
        banner_shadow = "rgba(2, 8, 24, 0.56)"
        ink_primary = "#0F1E37"
        ink_muted = "#263B5E"
        accent_left_a = "#835914"
        accent_left_b = "#B78631"
        kicker_border = "#C63F50"
        kicker_bg = "#F7E9EC"
        kicker_text = "#981B2B"
        action_link_color = "var(--bbva-action-link)"
        link_hover = "var(--bbva-action-link-hover)"
    else:
        banner_bg = "#FFE8A8"
        banner_border = "#C79A3B"
        banner_shadow = "rgba(161, 113, 29, 0.18)"
        ink_primary = "#13233A"
        ink_muted = "#2A3A57"
        accent_left_a = "#9B6F1B"
        accent_left_b = "#D2A44C"
        kicker_border = "#C63F50"
        kicker_bg = "#FDECEE"
        kicker_text = "#9A1E2D"
        action_link_color = "var(--bbva-action-link)"
        link_hover = "var(--bbva-action-link-hover)"

    st.markdown(
        f"""
        <style>
          [class*="st-key-next_best_banner_shell_"] {{
            position: relative;
            overflow: hidden;
            border: 1px solid {banner_border} !important;
            border-radius: 14px;
            background-color: {banner_bg} !important;
            background-image: none !important;
            box-shadow: 0 12px 28px {banner_shadow} !important;
            padding: 0.56rem 0.72rem !important;
          }}
          [class*="st-key-next_best_banner_shell_"] [data-testid="stVerticalBlockBorderWrapper"] {{
            position: relative;
            overflow: hidden;
            border: 1px solid {banner_border} !important;
            background: {banner_bg} !important;
            box-shadow: 0 12px 28px {banner_shadow} !important;
          }}
          [class*="st-key-next_best_banner_shell_"]::before,
          [class*="st-key-next_best_banner_shell_"] [data-testid="stVerticalBlockBorderWrapper"]::before {{
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 4px;
            background: linear-gradient(180deg, {accent_left_a}, {accent_left_b});
          }}
          .nba-kicker {{
            display: inline-flex;
            align-items: center;
            padding: 0.12rem 0.56rem;
            border-radius: 999px;
            border: 1px solid {kicker_border};
            background: {kicker_bg};
            color: {kicker_text};
            font-family: var(--bbva-font-sans);
            font-size: 0.72rem;
            font-weight: 860;
            text-transform: uppercase;
            letter-spacing: 0.05em;
          }}
          .nba-topline {{
            display: flex;
            align-items: center;
            justify-content: flex-start;
            gap: 0.32rem;
            min-height: 1.32rem;
          }}
          .nba-title {{
            margin-top: 0.08rem;
            color: {ink_primary};
            font-size: 0.96rem;
            font-weight: 860;
            letter-spacing: -0.01em;
          }}
          .nba-body {{
            margin-top: 0.12rem;
            color: {ink_primary};
            font-size: 0.98rem;
            font-weight: 720;
          }}
          .nba-sub {{
            color: {ink_muted};
            font-size: 0.79rem;
            margin-top: 0.01rem;
          }}
          .nba-tgt {{
            margin-top: 0.01rem;
            color: {ink_muted};
            font-size: 0.76rem;
            font-weight: 700;
          }}
          .nba-filters {{
            margin-top: 0.04rem;
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            gap: 0.18rem;
          }}
          .nba-filter-row {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.26rem;
          }}
          .nba-filter-inline-group {{
            display: inline-flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.22rem;
          }}
          .nba-filter-label {{
            color: {ink_muted};
            font-size: 0.76rem;
            font-weight: 780;
          }}
          .nba-filter-chips {{
            display: inline-flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.22rem;
          }}
          .nba-inline-chip {{
            display: inline-flex;
            align-items: center;
          }}
          .nba-chip-neutral {{
            border-radius: 999px;
            padding: 2px 10px;
            border: 1px solid var(--bbva-border-strong);
            background: color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2));
            color: {ink_primary};
            font-size: 0.80rem;
            font-weight: 700;
          }}
          .nba-inline-actions-row {{
            margin-top: 0.03rem;
          }}
          [class*="st-key-nba_pending_slot_"] div[data-testid="stButton"],
          [class*="st-key-nba_review_slot_"] div[data-testid="stButton"],
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"],
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] {{
            display: flex !important;
            justify-content: flex-end !important;
            align-items: center !important;
          }}
          [class*="st-key-nba_pending_slot_"] div[data-testid="stButton"] > button,
          [class*="st-key-nba_review_slot_"] div[data-testid="stButton"] > button,
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button {{
            display: inline-flex !important;
            align-items: center !important;
            justify-content: flex-end !important;
            width: 100% !important;
            min-height: 1.16rem !important;
            padding: 0 !important;
            border: 0 !important;
            border-radius: 8px !important;
            background: transparent !important;
            color: {action_link_color} !important;
            font-family: var(--bbva-font-sans) !important;
            font-size: 0.74rem !important;
            font-weight: 700 !important;
            text-transform: none !important;
            letter-spacing: 0 !important;
            line-height: 1.1 !important;
            opacity: 1 !important;
            box-shadow: none !important;
          }}
          [class*="st-key-nba_pending_slot_"] div[data-testid="stButton"] > button *,
          [class*="st-key-nba_review_slot_"] div[data-testid="stButton"] > button *,
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button *,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button *,
          [class*="st-key-nba_pending_slot_"] div[data-testid="stButton"] > button svg,
          [class*="st-key-nba_review_slot_"] div[data-testid="stButton"] > button svg,
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button svg,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button svg {{
            color: inherit !important;
            fill: currentColor !important;
            opacity: 1 !important;
            font-family: inherit !important;
            font-size: inherit !important;
            font-weight: inherit !important;
          }}
          [class*="st-key-nba_pending_slot_"] div[data-testid="stButton"] > button:hover,
          [class*="st-key-nba_review_slot_"] div[data-testid="stButton"] > button:hover,
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button:hover,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button:hover {{
            color: {link_hover} !important;
            transform: translateX(1px);
          }}
          [class*="st-key-next_best_banner_shell_"] div[data-testid="stMarkdownContainer"] p {{
            color: {ink_primary} !important;
          }}
          [class*="st-key-next_best_banner_shell_"] div[data-testid="stMarkdownContainer"] strong {{
            color: {ink_primary} !important;
          }}
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] p,
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] strong,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] p,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button div[data-testid="stMarkdownContainer"] strong {{
            color: {action_link_color} !important;
          }}
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button:hover div[data-testid="stMarkdownContainer"] p,
          [class*="st-key-nba_pending_next_"] div[data-testid="stButton"] > button:hover div[data-testid="stMarkdownContainer"] strong,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button:hover div[data-testid="stMarkdownContainer"] p,
          [class*="st-key-nba_top_review_"] div[data-testid="stButton"] > button:hover div[data-testid="stMarkdownContainer"] strong {{
            color: {link_hover} !important;
          }}
          @media (max-width: 960px) {{
            .nba-title,
            .nba-sub,
            .nba-tgt,
            .nba-filters {{
              max-width: 100%;
            }}
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key=f"next_best_banner_shell_{section_norm}"):
        top_l, top_r = st.columns([0.66, 0.34], gap="small")
        with top_l:
            st.markdown(
                f'<div class="nba-topline"><span class="nba-kicker">{kicker}</span></div>',
                unsafe_allow_html=True,
            )
        with top_r:
            with st.container(key=f"nba_pending_slot_{section_norm}"):
                st.button(
                    f"Pendientes por revisar: {pending_count} ↻",
                    key=f"nba_pending_next_{section_norm}",
                    width="stretch",
                    on_click=_advance_pending_preview,
                    args=(scope_key,),
                )
        st.markdown(f'<div class="nba-title">{action.title}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="nba-sub">{tone} · {resolved_impact}</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="nba-inline-actions-row"></div>', unsafe_allow_html=True)
        bottom_l, bottom_r = st.columns([0.76, 0.24], gap="small")
        with bottom_l:
            st.markdown(
                _filters_markup(
                    status_filters=status_filters,
                    priority_filters=priority_filters,
                    assignee_filters=assignee_filters,
                ),
                unsafe_allow_html=True,
            )
        with bottom_r:
            with st.container(key=f"nba_review_slot_{section_norm}"):
                st.button(
                    "Revisar ↗",
                    key=f"nba_top_review_{section_norm}",
                    width="stretch",
                    on_click=_apply_action,
                    kwargs={
                        "target_section": primary_target,
                        "status_filters": status_filters,
                        "priority_filters": priority_filters,
                        "assignee_filters": assignee_filters,
                        "scope_key": scope_key,
                        "action_id": action_id,
                        "context_label": context_label,
                    },
                )
