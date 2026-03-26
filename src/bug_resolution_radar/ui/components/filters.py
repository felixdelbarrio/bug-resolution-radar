"""Dashboard filters, matrix interactions and synchronized filter state helpers."""

from __future__ import annotations

import json
import re
from typing import List, Optional

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as components_html

from bug_resolution_radar.config import Settings
from bug_resolution_radar.theme.design_tokens import hex_with_alpha
from bug_resolution_radar.ui.common import (
    normalize_text_col,
    priority_color,
    priority_rank,
    status_color,
)
from bug_resolution_radar.ui.dashboard.constants import order_statuses_canonical
from bug_resolution_radar.ui.dashboard.quincenal_scope import quincenal_scope_options
from bug_resolution_radar.ui.dashboard.state import (
    FILTER_ASSIGNEE_KEY,
    FILTER_PRIORITY_KEY,
    FILTER_STATUS_KEY,
    ISSUES_QUINCENAL_SCOPE_KEY,
    FilterState,
)

FILTER_ACTION_CONTEXT_KEY = "__filters_action_context"


# ---------------------------------------------------------------------
# Internal: canonical keys + namespaced UI keys
# ---------------------------------------------------------------------
def _ui_key(prefix: str, name: str) -> str:
    p = (prefix or "").strip()
    return f"{p}::{name}" if p else name


def _sync_from_ui_to_canonical(
    ui_status_key: str,
    ui_prio_key: str,
    ui_assignee_key: str,
    ui_quincenal_key: str | None = None,
) -> None:
    """Copy UI widget state (namespaced keys) into canonical shared keys."""
    st.session_state[FILTER_STATUS_KEY] = list(st.session_state.get(ui_status_key) or [])
    st.session_state[FILTER_PRIORITY_KEY] = list(st.session_state.get(ui_prio_key) or [])
    st.session_state[FILTER_ASSIGNEE_KEY] = list(st.session_state.get(ui_assignee_key) or [])
    if ui_quincenal_key:
        selected = str(st.session_state.get(ui_quincenal_key) or "Todas").strip() or "Todas"
        st.session_state[ISSUES_QUINCENAL_SCOPE_KEY] = selected


def _status_combo_label(status: str) -> str:
    return status


def _priority_combo_label(priority: str) -> str:
    return priority


def _theme_alpha(alpha: int) -> int:
    alpha_i = int(alpha)
    if bool(st.session_state.get("workspace_dark_mode", False)):
        if alpha_i <= 40:
            return 52
        if alpha_i <= 130:
            return 178
    return alpha_i


def _inject_filters_panel_css() -> None:
    chip_border = "var(--bbva-flt-action-chip-border)"
    chip_bg = "var(--bbva-flt-action-chip-bg)"
    chip_text = "var(--bbva-flt-action-chip-text)"
    chip_lbl = "var(--bbva-flt-action-chip-label)"
    css = """
        <style>
          .flt-action-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.34rem;
            border-radius: 999px;
            padding: 0.13rem 0.58rem;
            border: 1px solid __CHIP_BORDER__;
            background: __CHIP_BG__;
            color: __CHIP_TEXT__;
            font-size: 0.74rem;
            font-weight: 780;
            letter-spacing: 0.01em;
            margin-bottom: 0.34rem;
          }
          .flt-action-chip-lbl {
            color: __CHIP_LABEL__;
            opacity: 0.92;
            text-transform: uppercase;
            letter-spacing: 0.04em;
          }
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
    """
    css = (
        css.replace("__CHIP_BORDER__", chip_border)
        .replace("__CHIP_BG__", chip_bg)
        .replace("__CHIP_TEXT__", chip_text)
        .replace("__CHIP_LABEL__", chip_lbl)
    )
    st.markdown(css, unsafe_allow_html=True)


def _normalize_semantic_label(label: str) -> str:
    return re.sub(r"\s+", " ", str(label or "").strip().lower()).strip()


def _css_attr_value(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _semantic_label_tone_map(
    *, status_labels: List[str], priority_labels: List[str]
) -> dict[str, dict[str, str]]:
    tones: dict[str, dict[str, str]] = {}
    for label in list(status_labels or []):
        color = status_color(label)
        tones[_normalize_semantic_label(label)] = {
            "color": color,
            "bg": hex_with_alpha(color, _theme_alpha(24), fallback=status_color("")),
            "border": hex_with_alpha(color, _theme_alpha(120), fallback=status_color("")),
        }
    for label in list(priority_labels or []):
        color = priority_color(label)
        tones[_normalize_semantic_label(label)] = {
            "color": color,
            "bg": hex_with_alpha(color, _theme_alpha(24), fallback=priority_color("")),
            "border": hex_with_alpha(color, _theme_alpha(120), fallback=priority_color("")),
        }
    return tones


def _semantic_tag_css_rules(*, status_labels: List[str], priority_labels: List[str]) -> str:
    tones = _semantic_label_tone_map(status_labels=status_labels, priority_labels=priority_labels)
    if not tones:
        return ""

    rules: List[str] = []
    seen_labels: set[str] = set()
    for label in [*list(status_labels or []), *list(priority_labels or [])]:
        raw = str(label or "").strip()
        if not raw:
            continue
        norm = _normalize_semantic_label(raw)
        if norm in seen_labels:
            continue
        seen_labels.add(norm)
        tone = tones.get(norm)
        if not tone:
            continue
        escaped = _css_attr_value(raw)
        selector = f'[data-baseweb="tag"][aria-label^="{escaped}" i]'
        rules.append(
            (
                f"{selector} {{"
                f" background: {tone['bg']} !important;"
                f" border: 1px solid {tone['border']} !important;"
                f" color: {tone['color']} !important;"
                "}"
                f"{selector} * {{ color: {tone['color']} !important; }}"
            )
        )
    return "".join(rules)


def _inject_semantic_tag_css(*, status_labels: List[str], priority_labels: List[str]) -> None:
    rules = _semantic_tag_css_rules(status_labels=status_labels, priority_labels=priority_labels)
    if not rules:
        return
    st.markdown(f"<style>{rules}</style>", unsafe_allow_html=True)


def _inject_semantic_option_runtime_bridge(
    *, status_labels: List[str], priority_labels: List[str]
) -> None:
    tones = _semantic_label_tone_map(status_labels=status_labels, priority_labels=priority_labels)
    if not tones:
        return
    payload = json.dumps(tones, ensure_ascii=False)
    components_html(
        f"""
        <script>
          (function () {{
            const toneMap = {payload};
            const parentWin = window.parent || window;
            let parentDoc = document;
            try {{
              if (parentWin && parentWin.document) {{
                parentDoc = parentWin.document;
              }}
            }} catch (e) {{
              parentDoc = document;
            }}

            const normalize = (txt) =>
              String(txt || "")
                .toLowerCase()
                .replace(/[\\u00d7\\u2715\\u2716]/g, "")
                .replace(/[_-]+/g, " ")
                .replace(/\\s+/g, " ")
                .trim();

            const optionLabel = (opt) => {{
              const aria = String(opt.getAttribute("aria-label") || "").trim();
              if (aria) return aria;
              const titled = opt.querySelector("[title]");
              if (titled && titled.getAttribute("title")) return titled.getAttribute("title");
              return String(opt.textContent || "");
            }};

            const applyTones = () => {{
              const tones = parentWin.__bbvaSemanticTones || toneMap;
              parentDoc.querySelectorAll('div[data-baseweb="popover"] [role="option"]').forEach((opt) => {{
                const toneKey = normalize(optionLabel(opt));
                const tone = tones[toneKey];
                if (!tone) {{
                  opt.removeAttribute("data-bbva-semantic");
                  opt.removeAttribute("data-bbva-semantic-key");
                  opt.style.removeProperty("--bbva-opt-dot");
                  return;
                }}
                opt.setAttribute("data-bbva-semantic", "1");
                opt.setAttribute("data-bbva-semantic-key", toneKey);
                opt.style.setProperty("--bbva-opt-dot", tone.color);
              }});
            }};

            const scheduleApply = () => {{
              if (parentWin.__bbvaSemanticToneRAF) return;
              const run = () => {{
                parentWin.__bbvaSemanticToneRAF = 0;
                applyTones();
              }};
              try {{
                parentWin.__bbvaSemanticToneRAF = parentWin.requestAnimationFrame(run);
              }} catch (e) {{
                setTimeout(run, 30);
              }}
            }};

            parentWin.__bbvaSemanticTones = toneMap;
            applyTones();
            setTimeout(() => applyTones(), 40);

            const shouldRescan = (node) => {{
              if (!node || node.nodeType !== 1) return false;
              if (node.matches && node.matches('div[data-baseweb="popover"], [role="option"]')) {{
                return true;
              }}
              try {{
                return Boolean(
                  node.querySelector &&
                  node.querySelector('div[data-baseweb="popover"], [role="option"]')
                );
              }} catch (e) {{
                return false;
              }};
            }};

            if (!parentWin.__bbvaSemanticToneObserver && parentDoc && parentDoc.body) {{
              const observer = new MutationObserver((mutations) => {{
                for (const mutation of mutations) {{
                  if (mutation.type !== "childList") continue;
                  for (const node of mutation.addedNodes || []) {{
                    if (shouldRescan(node)) {{
                      scheduleApply();
                      return;
                    }}
                  }}
                }}
              }});
              observer.observe(parentDoc.body, {{ childList: true, subtree: true }});
              parentWin.__bbvaSemanticToneObserver = observer;
            }}
          }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _mirror_canonical_to_ui(
    ui_status_key: str,
    ui_prio_key: str,
    ui_assignee_key: str,
    ui_quincenal_key: str | None = None,
) -> None:
    """Before creating widgets, ensure their state reflects canonical keys (for cross-component sync)."""
    st.session_state[ui_status_key] = [
        _status_combo_label(x) for x in list(st.session_state.get(FILTER_STATUS_KEY) or [])
    ]
    st.session_state[ui_prio_key] = [
        _priority_combo_label(x) for x in list(st.session_state.get(FILTER_PRIORITY_KEY) or [])
    ]
    st.session_state[ui_assignee_key] = list(st.session_state.get(FILTER_ASSIGNEE_KEY) or [])
    if ui_quincenal_key:
        st.session_state[ui_quincenal_key] = (
            str(st.session_state.get(ISSUES_QUINCENAL_SCOPE_KEY) or "Todas").strip() or "Todas"
        )


def _normalize_filter_values(values: List[str]) -> List[str]:
    out = sorted({str(x).strip().lower() for x in list(values or []) if str(x).strip()})
    return list(out)


def _active_context_label(
    context_raw: object,
    *,
    status: List[str],
    priority: List[str],
    assignee: List[str],
) -> str | None:
    context = context_raw if isinstance(context_raw, dict) else {}
    label = str(context.get("label") or "").strip()
    if not label:
        return None
    ctx_status = list(context.get("status") or [])
    ctx_priority = list(context.get("priority") or [])
    ctx_assignee = list(context.get("assignee") or [])
    if _normalize_filter_values(ctx_status) != _normalize_filter_values(status):
        return None
    if _normalize_filter_values(ctx_priority) != _normalize_filter_values(priority):
        return None
    if _normalize_filter_values(ctx_assignee) != _normalize_filter_values(assignee):
        return None
    return label


# ---------------------------------------------------------------------
# Filters UI
# ---------------------------------------------------------------------
def render_filters(
    df: pd.DataFrame,
    *,
    key_prefix: str = "",
    settings: Settings | None = None,
    include_quincenal: bool = False,
) -> FilterState:
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
    ui_quincenal_key = _ui_key(key_prefix, "filter_quincenal_ui")

    # Mirror canonical -> ui before widget creation (so matrix clicks reflect in widgets)
    _mirror_canonical_to_ui(
        ui_status_key,
        ui_prio_key,
        ui_assignee_key,
        ui_quincenal_key if include_quincenal else None,
    )

    ctx_label = _active_context_label(
        st.session_state.get(FILTER_ACTION_CONTEXT_KEY),
        status=list(st.session_state.get(FILTER_STATUS_KEY) or []),
        priority=list(st.session_state.get(FILTER_PRIORITY_KEY) or []),
        assignee=list(st.session_state.get(FILTER_ASSIGNEE_KEY) or []),
    )
    if ctx_label is None:
        st.session_state.pop(FILTER_ACTION_CONTEXT_KEY, None)

    status_opts_raw = status_col.astype(str).unique().tolist()
    status_opts_raw = order_statuses_canonical(status_opts_raw)
    status_opts_ui = [_status_combo_label(s) for s in status_opts_raw]

    prio_opts_ui: List[str] = []
    if "priority" in df.columns:
        prio_opts = sorted(
            priority_col.astype(str).unique().tolist(),
            key=lambda p: (priority_rank(p), p),
        )
        prio_opts_ui = [_priority_combo_label(p) for p in prio_opts]
    quincenal_options = {"Todas": []}
    quincenal_labels = ["Todas"]
    if include_quincenal:
        quincenal_options = quincenal_scope_options(df, settings=settings)
        quincenal_labels = list(quincenal_options.keys()) if quincenal_options else ["Todas"]
        selected_quincenal = (
            str(st.session_state.get(ui_quincenal_key) or "Todas").strip() or "Todas"
        )
        if selected_quincenal not in quincenal_labels:
            selected_quincenal = "Todas"
        st.session_state[ui_quincenal_key] = selected_quincenal
        st.session_state[ISSUES_QUINCENAL_SCOPE_KEY] = selected_quincenal

    # Tags use stable aria-label selectors (color only, no dot) from centralized token map.
    _inject_semantic_tag_css(
        status_labels=status_opts_ui,
        priority_labels=prio_opts_ui,
    )

    with st.container(border=True, key=f"{(key_prefix or 'dashboard')}_filters_panel"):
        if ctx_label:
            st.markdown(
                (
                    '<div class="flt-action-chip">'
                    '<span class="flt-action-chip-lbl">Investigando</span>'
                    f"<span>{ctx_label}</span>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )
        sync_args = (
            ui_status_key,
            ui_prio_key,
            ui_assignee_key,
            ui_quincenal_key if include_quincenal else None,
        )
        if include_quincenal:
            c_status, c_prio, c_assignee, c_quincenal = st.columns(
                [1.25, 0.96, 0.96, 1.06], gap="small"
            )
        else:
            c_status, c_prio, c_assignee = st.columns([1.35, 1.0, 1.0], gap="small")

        with c_status:
            selected_ui_status = list(st.session_state.get(ui_status_key) or [])
            st.session_state[ui_status_key] = [x for x in selected_ui_status if x in status_opts_ui]
            st.multiselect(
                "Estado",
                status_opts_ui,
                key=ui_status_key,
                on_change=_sync_from_ui_to_canonical,
                args=sync_args,
                placeholder="Estado",
            )

        with c_prio:
            if "priority" in df.columns:
                selected_ui_prio = list(st.session_state.get(ui_prio_key) or [])
                st.session_state[ui_prio_key] = [x for x in selected_ui_prio if x in prio_opts_ui]
                st.multiselect(
                    "Priority",
                    prio_opts_ui,
                    key=ui_prio_key,
                    on_change=_sync_from_ui_to_canonical,
                    args=sync_args,
                    placeholder="Priority",
                )
            else:
                st.session_state[ui_prio_key] = []
                st.session_state[FILTER_PRIORITY_KEY] = []

        with c_assignee:
            if "assignee" in df.columns:
                assignee_opts = sorted(
                    normalize_text_col(df["assignee"], "(sin asignar)")
                    .astype(str)
                    .unique()
                    .tolist()
                )
                selected_ui_assignee = list(st.session_state.get(ui_assignee_key) or [])
                st.session_state[ui_assignee_key] = [
                    x for x in selected_ui_assignee if x in assignee_opts
                ]
                st.multiselect(
                    "Asignado",
                    assignee_opts,
                    key=ui_assignee_key,
                    on_change=_sync_from_ui_to_canonical,
                    args=sync_args,
                    placeholder="Asignado",
                )
            else:
                st.session_state[ui_assignee_key] = []
                st.session_state[FILTER_ASSIGNEE_KEY] = []

        if include_quincenal:
            with c_quincenal:
                st.selectbox(
                    "Quincenal",
                    options=quincenal_labels,
                    key=ui_quincenal_key,
                    on_change=_sync_from_ui_to_canonical,
                    args=sync_args,
                    help=(
                        "Filtro quincenal operativo para visualizar bloques de "
                        "nuevas/cerradas/maestras/otras."
                    ),
                )
                st.session_state[ISSUES_QUINCENAL_SCOPE_KEY] = (
                    str(st.session_state.get(ui_quincenal_key) or "Todas").strip() or "Todas"
                )

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
        assignee_norm = normalize_text_col(df["assignee"], "(sin asignar)")
        mask &= assignee_norm.isin(fs.assignee)

    needs_status_write = False
    if status_norm is not None:
        needs_status_write = bool(fs.status)
        if not needs_status_write and bool(df["status"].isna().any()):
            needs_status_write = True
        if not needs_status_write:
            try:
                needs_status_write = bool((df["status"] == "").any())
            except Exception:
                needs_status_write = False

    needs_priority_write = False
    if priority_norm is not None:
        needs_priority_write = bool(fs.priority)
        if not needs_priority_write and bool(df["priority"].isna().any()):
            needs_priority_write = True
        if not needs_priority_write:
            try:
                needs_priority_write = bool((df["priority"] == "").any())
            except Exception:
                needs_priority_write = False

    if bool(mask.all()) and not (needs_status_write or needs_priority_write):
        # Fast path: avoid extra frame materialization when no filter narrows results.
        return df.copy(deep=False)

    dff = df.loc[mask].copy(deep=False)
    if needs_status_write and status_norm is not None:
        dff["status"] = status_norm.loc[mask].to_numpy()
    if needs_priority_write and priority_norm is not None:
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


def _matrix_toggle_status_filter(st_name: str) -> None:
    statuses = list(st.session_state.get(FILTER_STATUS_KEY) or [])
    if st_name in statuses:
        statuses = [s for s in statuses if s != st_name]
    else:
        statuses.append(st_name)
    st.session_state[FILTER_STATUS_KEY] = statuses


def _matrix_toggle_priority_filter(prio: str) -> None:
    priorities = list(st.session_state.get(FILTER_PRIORITY_KEY) or [])
    st.session_state[FILTER_PRIORITY_KEY] = [] if priorities == [prio] else [prio]


def _matrix_priority_label(priority: str) -> str:
    p = str(priority or "").strip()
    if p.lower() == "supone un impedimento":
        return "Impedimento"
    return p


def _matrix_safe_token(value: str) -> str:
    tok = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return tok or "na"


def _matrix_header_button_css(hex_color: str, *, selected: bool) -> str:
    color = (hex_color or status_color("")).strip()
    deployed_color = status_color("Deployed").strip().upper()
    if color.strip().upper() == deployed_color:
        border = hex_with_alpha(color, _theme_alpha(145), fallback=status_color(""))
        bg = "var(--bbva-goal-green-bg)"
        hover_bg = "color-mix(in srgb, var(--bbva-goal-green-bg) 78%, var(--bbva-goal-green) 22%)"
        fw = "800" if selected else "700"
        return (
            f"border:1px solid {border} !important;"
            f"background:{bg} !important;"
            f"color:{color} !important;"
            f"font-weight:{fw} !important;"
            "border-radius:11px !important;"
            "min-height:2.18rem !important;"
            "padding:0.22rem 0.46rem !important;"
            "line-height:1.16 !important;"
            "white-space:normal !important;"
            "word-break:break-word !important;"
            f"box-shadow:{'0 0 0 2px var(--bbva-focus-ring)' if selected else 'none'} !important;"
            f"--mx-hover-bg:{hover_bg};"
            "--mx-focus-ring:var(--bbva-focus-ring);"
        )
    border = hex_with_alpha(color, _theme_alpha(125), fallback=status_color(""))
    bg = hex_with_alpha(color, _theme_alpha(28), fallback=status_color(""))
    hover_bg = hex_with_alpha(color, _theme_alpha(42), fallback=status_color(""))
    fw = "800" if selected else "700"
    return (
        f"border:1px solid {border} !important;"
        f"background:{bg} !important;"
        f"color:{color} !important;"
        f"font-weight:{fw} !important;"
        "border-radius:11px !important;"
        "min-height:2.18rem !important;"
        "padding:0.22rem 0.46rem !important;"
        "line-height:1.16 !important;"
        "white-space:normal !important;"
        "word-break:break-word !important;"
        f"box-shadow:{'0 0 0 2px var(--bbva-focus-ring)' if selected else 'none'} !important;"
        f"--mx-hover-bg:{hover_bg};"
        "--mx-focus-ring:var(--bbva-focus-ring);"
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
          .st-key-{scope_key} div[data-testid="stButton"] > button[kind="primary"] {{
            border-color: color-mix(in srgb, var(--bbva-primary) 56%, var(--bbva-border-strong)) !important;
            background: color-mix(in srgb, var(--bbva-primary) 18%, var(--bbva-surface)) !important;
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--bbva-primary) 30%, transparent) !important;
            font-weight: 790 !important;
          }}
          .st-key-{scope_key} div[data-testid="stButton"] > button[kind="secondary"] {{
            opacity: 0.98 !important;
          }}
          .st-key-{scope_key} div[data-testid="stMarkdownContainer"] p {{
            margin-bottom: 0.16rem !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inject_matrix_header_signal_css(
    *,
    row_specs: List[tuple[str, str, bool]],
    col_specs: List[tuple[str, str, bool]],
) -> None:
    rules: List[str] = []
    for btn_key, color, is_selected in row_specs + col_specs:
        style = _matrix_header_button_css(color, selected=is_selected)
        rules.append(
            f"""
            .st-key-{btn_key} div[data-testid="stButton"] > button {{
              {style}
            }}
            .st-key-{btn_key} div[data-testid="stButton"] > button:hover {{
              background: var(--mx-hover-bg) !important;
              border-color: color-mix(in srgb, {color} 78%, transparent) !important;
            }}
            .st-key-{btn_key} div[data-testid="stButton"] > button:focus-visible {{
              outline: none !important;
              box-shadow: 0 0 0 3px var(--mx-focus-ring) !important;
            }}
            .st-key-{btn_key} div[data-testid="stButton"] > button * {{
              color: inherit !important;
              fill: currentColor !important;
            }}
            """
        )
    if rules:
        st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)


def render_status_priority_matrix(
    scoped_df: pd.DataFrame,
    fs: Optional[FilterState] = None,
    *,
    key_prefix: str = "mx",
) -> None:
    """Render a clickable matrix Estado x Priority for filtered issues.

    IMPORTANT: If you render this matrix more than once on the same page (e.g. in multiple tabs),
    you MUST pass different key_prefix values to avoid StreamlitDuplicateElementId.
    """
    if scoped_df is None or scoped_df.empty:
        return
    if "status" not in scoped_df.columns or "priority" not in scoped_df.columns:
        return

    st.markdown("### Matriz Estado x Priority (filtradas)")

    mx = scoped_df.assign(
        status=normalize_text_col(scoped_df["status"], "(sin estado)"),
        priority=normalize_text_col(scoped_df["priority"], "(sin priority)"),
    )

    # Orden filas: CANÓNICO
    statuses = order_statuses_canonical(mx["status"].value_counts().index.tolist())

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
    if has_matrix_sel:
        status_txt = ", ".join(selected_statuses) if selected_statuses else "(todos)"
        prio_txt = (
            ", ".join(_matrix_priority_label(p) for p in selected_priorities)
            if selected_priorities
            else "(todas)"
        )
        st.caption(f"Seleccionado: Estado={status_txt} · Priority={prio_txt}")
    else:
        st.caption("Click en cabeceras o celdas para filtrar. Repite click para desmarcar.")

    counts = pd.crosstab(mx["status"], mx["priority"])

    # Totales: columnas + filas
    col_totals = {p: int(counts[p].sum()) if p in counts.columns else 0 for p in priorities}
    row_totals = counts.sum(axis=1).to_dict()
    total_issues = int(sum(row_totals.values()))

    matrix_scope_key = f"{(key_prefix or 'mx')}_matrix_panel"
    _inject_matrix_compact_css(matrix_scope_key)

    row_btn_specs: List[tuple[str, str, bool]] = []
    col_btn_specs: List[tuple[str, str, bool]] = []
    for st_name in statuses:
        row_key = f"{key_prefix}__mx_row__{_matrix_safe_token(st_name)}"
        row_btn_specs.append((row_key, status_color(st_name), st_name in selected_statuses))
    for p in priorities:
        col_key = f"{key_prefix}__mx_col__{_matrix_safe_token(p)}"
        col_btn_specs.append((col_key, priority_color(p), p in selected_priorities))
    _inject_matrix_header_signal_css(row_specs=row_btn_specs, col_specs=col_btn_specs)

    with st.container(border=True, key=matrix_scope_key):
        # Header row (con totales por columna)
        hdr = st.columns(len(priorities) + 1)
        hdr[0].markdown(f"**Estado ({total_issues:,})**")
        for i, p in enumerate(priorities):
            label = f"{_matrix_priority_label(p)} ({col_totals.get(p, 0)})"
            col_key = f"{key_prefix}__mx_col__{_matrix_safe_token(p)}"
            hdr[i + 1].button(
                label,
                key=col_key,
                type="primary" if p in selected_priorities else "secondary",
                width="stretch",
                disabled=(col_totals.get(p, 0) == 0),
                on_click=_matrix_toggle_priority_filter,
                args=(p,),
            )

        # Rows (con total por estado)
        for st_name in statuses:
            total_row = int(row_totals.get(st_name, 0))
            row = st.columns(len(priorities) + 1)

            row_label = f"{st_name} ({total_row})"
            row_key = f"{key_prefix}__mx_row__{_matrix_safe_token(st_name)}"
            row[0].button(
                row_label,
                key=row_key,
                type="primary" if st_name in selected_statuses else "secondary",
                width="stretch",
                disabled=(total_row == 0),
                on_click=_matrix_toggle_status_filter,
                args=(st_name,),
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
                    width="stretch",
                    on_click=_matrix_set_filters,
                    args=(st_name, p),
                )
