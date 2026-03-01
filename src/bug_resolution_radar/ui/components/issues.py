"""Issue cards/table renderers and visual formatting helpers."""

from __future__ import annotations

import html
import re
from typing import List, Tuple
from urllib.parse import quote, unquote

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.status_semantics import effective_closed_mask
from bug_resolution_radar.config import Settings
from bug_resolution_radar.ingest.browser_runtime import open_url_in_configured_browser
from bug_resolution_radar.theme.design_tokens import BBVA_NEUTRAL_SOFT
from bug_resolution_radar.ui.common import (
    chip_palette_for_color,
    chip_style_from_color,
    priority_color,
    priority_rank,
    status_color,
)

_JIRA_KEY_RE = re.compile(r"/browse/([^/?#]+)")
_SUMMARY_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_SOURCE_TYPE_TOKENS = {"jira": "Jira", "helix": "Helix"}
_ISSUE_OPEN_URL_QP = "br_open_issue_url"
_ISSUE_OPEN_SOURCE_QP = "br_open_issue_source"
_ISSUE_OPEN_KEY_QP = "br_open_issue_key"
_SUMMARY_SPLIT_TOKENS = (" - ", " — ", " – ", ": ")
MAX_TABLE_HTML_ROWS = 3000
MAX_TABLE_NATIVE_ROWS = 2500
_NEUTRAL_TOKEN = BBVA_NEUTRAL_SOFT.upper()
_NEUTRAL_BORDER = chip_palette_for_color(BBVA_NEUTRAL_SOFT)[1]
_NEUTRAL_BG = chip_palette_for_color(BBVA_NEUTRAL_SOFT)[2]


def _normalize_source_type(value: object) -> str:
    token = str(value or "").strip().lower()
    return token if token in _SOURCE_TYPE_TOKENS else "jira"


def _browser_for_source_type(settings: Settings | None, source_type: str) -> str:
    source = _normalize_source_type(source_type)
    if source == "helix":
        raw = str(getattr(settings, "HELIX_BROWSER", "chrome") or "chrome").strip()
    else:
        raw = str(getattr(settings, "JIRA_BROWSER", "chrome") or "chrome").strip()
    return raw.lower() or "chrome"


def _extract_query_text(value: object) -> str:
    if isinstance(value, list):
        if not value:
            return ""
        value = value[0]
    return str(value or "").strip()


def build_issue_open_href(url: str, source_type: str, *, key_label: str = "") -> str:
    target = str(url or "").strip()
    if not target:
        return "#"
    source = _normalize_source_type(source_type)
    parts: List[str] = []
    key_txt = str(key_label or "").strip()
    if key_txt:
        parts.append(f"{_ISSUE_OPEN_KEY_QP}={quote(key_txt, safe='')}")
    parts.extend(
        [
            f"{_ISSUE_OPEN_URL_QP}={quote(target, safe='')}",
            f"{_ISSUE_OPEN_SOURCE_QP}={quote(source, safe='')}",
        ]
    )
    return "?" + "&".join(parts)


def handle_issue_link_open_request(*, settings: Settings | None) -> None:
    qp = st.query_params
    raw_url = _extract_query_text(qp.get(_ISSUE_OPEN_URL_QP))
    if not raw_url:
        return
    raw_source = _extract_query_text(qp.get(_ISSUE_OPEN_SOURCE_QP))
    target_url = unquote(raw_url)
    source_type = _normalize_source_type(unquote(raw_source))
    browser = _browser_for_source_type(settings, source_type)
    opened = open_url_in_configured_browser(
        target_url,
        browser,
        allow_system_default_fallback=False,
    )
    if not opened:
        st.warning(
            f"No se pudo abrir la incidencia en el navegador configurado ({browser}). "
            "Revisa la configuración de navegador."
        )
    for key in (_ISSUE_OPEN_URL_QP, _ISSUE_OPEN_SOURCE_QP, _ISSUE_OPEN_KEY_QP):
        try:
            del qp[key]
        except Exception:
            pass
    st.rerun()


def _title_and_description_from_row(
    row: dict[str, object] | pd.Series,
) -> Tuple[str, str]:
    summary = _safe_cell_text(row.get("summary"))
    description = ""
    for col in (
        "description",
        "details",
        "detailed_description",
        "detailed_decription",
    ):
        txt = _safe_cell_text(row.get(col))
        if txt != "—":
            description = txt
            break
    if summary == "—":
        summary = ""
    if description:
        return (summary or "Sin título"), description
    txt = summary or "Sin título"
    for token in _SUMMARY_SPLIT_TOKENS:
        if token not in txt:
            continue
        head, tail = txt.split(token, 1)
        if head.strip() and tail.strip():
            return head.strip(), tail.strip()
    if len(txt) > 110:
        head = txt[:110]
        if " " in head:
            head = head.rsplit(" ", 1)[0]
        tail = txt[len(head) :].strip(" -–—:;,.")
        if head.strip() and tail:
            return head.strip(), tail
    return txt, ""


def _safe_cell_text(value: object) -> str:
    null_tokens = {"nan", "none", "nat", "undefined", "null", ""}

    if value is None:
        return "—"

    # Handle list-like values first (labels/components can arrive as arrays).
    if isinstance(value, (list, tuple, set)):
        parts: List[str] = []
        for x in value:
            txt = str(x).strip()
            if txt.lower() in null_tokens:
                continue
            parts.append(txt)
        return ", ".join(parts) if parts else "—"

    to_list = getattr(value, "tolist", None)
    if callable(to_list) and not isinstance(value, (str, bytes, bytearray, dict)):
        try:
            as_list = to_list()
        except Exception:
            as_list = None
        if isinstance(as_list, (list, tuple, set)):
            parts = [str(x).strip() for x in as_list if str(x).strip()]
            parts = [p for p in parts if p.lower() not in null_tokens]
            return ", ".join(parts) if parts else "—"

    # Avoid ambiguous truth values from array-like pd.isna outputs.
    try:
        na_value = pd.isna(value)
    except Exception:
        na_value = False
    if isinstance(na_value, bool) and na_value:
        return "—"

    txt = str(value).strip()
    if txt.lower() in null_tokens:
        return "—"
    return txt


def _origin_link_header(df: pd.DataFrame) -> str:
    if df is None or df.empty or "source_type" not in df.columns:
        return "Origen"
    types: list[str] = [
        str(x).strip().lower()
        for x in df["source_type"].fillna("").astype(str).tolist()
        if str(x).strip()
    ]
    uniq = {t for t in types if t}
    if len(uniq) == 1:
        token = next(iter(uniq))
        return _SOURCE_TYPE_TOKENS.get(token, token.upper())
    return "Origen"


def _jira_label_from_row(row: dict[str, object] | pd.Series) -> str:
    key = _safe_cell_text(row.get("key"))
    if key != "—":
        return key
    for alt_col in ("issue_key", "ticket", "incident", "id"):
        alt = _safe_cell_text(row.get(alt_col))
        if alt != "—":
            mm_alt = _SUMMARY_KEY_RE.search(alt)
            if mm_alt:
                return mm_alt.group(1)
            return alt
    url = str(row.get("jira") or row.get("url") or "").strip()
    m = _JIRA_KEY_RE.search(url)
    if m:
        return m.group(1)
    m_url = _SUMMARY_KEY_RE.search(url)
    if m_url:
        return m_url.group(1)
    summary = _safe_cell_text(row.get("summary"))
    if summary != "—":
        mm = _SUMMARY_KEY_RE.search(summary)
        if mm:
            return mm.group(1)
    source = _normalize_source_type(row.get("source_type"))
    return _SOURCE_TYPE_TOKENS.get(source, "Issue")


def _chip_html(value: object, *, for_priority: bool) -> str:
    txt = _safe_cell_text(value)
    if txt == "—":
        return '<span class="issue-table-chip issue-table-chip-neutral">—</span>'
    color = priority_color(txt) if for_priority else status_color(txt)
    if color.upper() == _NEUTRAL_TOKEN:
        return f'<span class="issue-table-chip issue-table-chip-neutral">{html.escape(txt)}</span>'
    style = chip_style_from_color(color)
    return f'<span class="issue-table-chip" style="{style}">{html.escape(txt)}</span>'


def _native_signal_cell_style(value: object, *, for_priority: bool) -> str:
    txt = _safe_cell_text(value)
    if txt == "—":
        return (
            f"color: var(--bbva-text-muted); font-weight: 700; background-color: {_NEUTRAL_BG}; "
            f"border: 1px solid {_NEUTRAL_BORDER}; border-radius: 999px; "
            "padding-left: 10px; padding-right: 10px; text-align: center;"
        )

    color = priority_color(txt) if for_priority else status_color(txt)
    if color.upper() == _NEUTRAL_TOKEN:
        return (
            f"color: var(--bbva-text-muted); font-weight: 700; background-color: {_NEUTRAL_BG}; "
            f"border: 1px solid {_NEUTRAL_BORDER}; border-radius: 999px; "
            "padding-left: 10px; padding-right: 10px; text-align: center;"
        )

    txt_color, border, bg = chip_palette_for_color(color)
    return (
        f"color: {txt_color}; background-color: {bg}; border: 1px solid {border}; "
        "border-radius: 999px; font-weight: 700; padding-left: 10px; padding-right: 10px; "
        "text-align: center;"
    )


def _native_key_cell_style(value: object) -> str:
    txt = _safe_cell_text(value)
    if txt == "—":
        return ""
    return (
        "color: var(--bbva-action-link) !important; text-decoration: underline !important; "
        "font-weight: 800 !important; opacity: 1 !important; white-space: nowrap;"
    )


def _render_issue_table_html(display_df: pd.DataFrame, show_cols: List[str]) -> None:
    origin_header = _origin_link_header(display_df)
    title_by_col = {
        "key": origin_header,
        "summary": "summary",
        "status": "status",
        "type": "type",
        "priority": "priority",
        "created": "created",
        "updated": "updated",
        "resolved": "resolved",
        "assignee": "assignee",
        "components": "components",
        "labels": "labels",
    }

    header_cells = ['<th class="issue-table-index"></th>']
    header_cells.extend([f"<th>{html.escape(title_by_col.get(c, c))}</th>" for c in show_cols])

    rows_html: List[str] = []
    records = display_df.to_dict(orient="records")
    for idx, row in zip(display_df.index.tolist(), records):
        row_cells = [f'<td class="issue-table-index">{html.escape(str(idx))}</td>']
        for col in show_cols:
            if col == "key":
                url = str(row.get("url") or "").strip()
                source_type = _normalize_source_type(row.get("source_type"))
                label = _safe_cell_text(row.get("key"))
                if label == "—":
                    label = _jira_label_from_row(row)
                if url:
                    href = html.escape(build_issue_open_href(url, source_type))
                    row_cells.append(
                        "<td>"
                        f'<a class="issue-table-origin" href="{href}" '
                        'target="_self" '
                        f'rel="noopener noreferrer">{html.escape(label)}</a>'
                        "</td>"
                    )
                else:
                    row_cells.append(f"<td>{html.escape(label)}</td>")
                continue

            if col == "status":
                row_cells.append(f"<td>{_chip_html(row.get(col), for_priority=False)}</td>")
                continue

            if col == "priority":
                row_cells.append(f"<td>{_chip_html(row.get(col), for_priority=True)}</td>")
                continue

            text = _safe_cell_text(row.get(col))
            css_class = "issue-table-summary" if col == "summary" else ""
            row_cells.append(f'<td class="{css_class}">{html.escape(text)}</td>')

        rows_html.append(f"<tr>{''.join(row_cells)}</tr>")

    st.markdown(
        f"""
        <style>
          .issue-table-shell {{
            border: 1px solid var(--bbva-border);
            border-radius: 14px;
            overflow: hidden;
            background: var(--bbva-surface);
          }}
          .issue-table-scroll {{
            max-height: 600px;
            overflow: auto;
          }}
          .issue-table {{
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 0.96rem;
            line-height: 1.35;
          }}
          .issue-table thead th {{
            position: sticky;
            top: 0;
            z-index: 2;
            text-align: left;
            font-weight: 700;
            color: var(--bbva-text-muted);
            background: color-mix(in srgb, var(--bbva-surface) 82%, var(--bbva-surface-2));
            border-bottom: 1px solid var(--bbva-border);
            padding: 0.60rem 0.72rem;
            white-space: nowrap;
          }}
          .issue-table td {{
            border-top: 1px solid var(--bbva-border);
            padding: 0.50rem 0.72rem;
            vertical-align: middle;
            color: var(--bbva-text);
            white-space: nowrap;
          }}
          .issue-table-index {{
            width: 54px;
            text-align: right !important;
            color: var(--bbva-text-muted) !important;
            font-variant-numeric: tabular-nums;
            background: color-mix(in srgb, var(--bbva-surface) 72%, var(--bbva-surface-2));
          }}
          .issue-table-summary {{
            min-width: 480px;
            max-width: 680px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}
          .issue-table-jira {{
            color: var(--bbva-primary) !important;
            font-weight: 700;
            text-decoration: none;
          }}
          .issue-table-jira:hover,
          .issue-table-origin:hover {{
            text-decoration: underline;
          }}
          .issue-table-origin {{
            color: var(--bbva-primary) !important;
            font-weight: 800;
            text-decoration: none;
          }}
          .issue-table-chip {{
            display: inline-flex;
            align-items: center;
            max-width: 100%;
          }}
          .issue-table-chip-neutral {{
            color: var(--bbva-text-muted);
            border: 1px solid var(--bbva-border-strong);
            background: color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2));
            border-radius: 999px;
            padding: 2px 10px;
            font-weight: 700;
            font-size: 0.80rem;
          }}
        </style>
        <div class="issue-table-shell">
          <div class="issue-table-scroll">
            <table class="issue-table">
              <thead><tr>{"".join(header_cells)}</tr></thead>
              <tbody>{"".join(rows_html)}</tbody>
            </table>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _selection_payload(event: object) -> dict[str, object]:
    if event is None:
        return {}
    sel = getattr(event, "selection", None)
    if sel is None and isinstance(event, dict):
        sel = event.get("selection")
    if sel is None:
        return {}
    if isinstance(sel, dict):
        return sel
    rows = getattr(sel, "rows", None)
    cols = getattr(sel, "columns", None)
    cells = getattr(sel, "cells", None)
    out: dict[str, object] = {}
    if rows is not None:
        out["rows"] = rows
    if cols is not None:
        out["columns"] = cols
    if cells is not None:
        out["cells"] = cells
    return out


def _selected_cell_from_event(event: object) -> Tuple[object | None, str | None]:
    payload = _selection_payload(event)
    cells = payload.get("cells")
    if isinstance(cells, list) and cells:
        cell = cells[0]
        if isinstance(cell, dict):
            return cell.get("row"), str(cell.get("column") or "")
        if isinstance(cell, (list, tuple)) and len(cell) >= 2:
            return cell[0], str(cell[1] or "")

    rows = payload.get("rows")
    cols = payload.get("columns")
    row_value = rows[0] if isinstance(rows, list) and rows else None
    col_value = str(cols[0] or "") if isinstance(cols, list) and cols else None
    return row_value, col_value


def _row_record_from_selection(
    display_df: pd.DataFrame,
    records: List[dict[str, object]],
    row_value: object,
) -> dict[str, object] | None:
    if isinstance(row_value, int):
        if 0 <= row_value < len(records):
            return records[row_value]
    try:
        if row_value in display_df.index:
            maybe = display_df.loc[row_value]
            if isinstance(maybe, pd.DataFrame):
                if maybe.empty:
                    return None
                return maybe.iloc[0].to_dict()
            return maybe.to_dict()
    except Exception:
        return None
    return None


def _render_issue_table_native(
    display_df: pd.DataFrame,
    show_cols: List[str],
    *,
    settings: Settings | None,
    table_key: str,
    sort_state_prefix: str | None = None,
) -> None:
    """Render large datasets with Streamlit's virtualized table to reduce DOM pressure."""
    df_show = display_df[show_cols].copy(deep=False).copy().reset_index(drop=True)
    col_cfg = {}
    origin_header = _origin_link_header(display_df)

    records = display_df.to_dict(orient="records")
    if "key" in df_show.columns:
        key_values: List[str] = []
        for row in records:
            label = _jira_label_from_row(row)
            key_values.append(label)
        df_show["key"] = key_values
        col_cfg["key"] = st.column_config.TextColumn(
            origin_header,
            width="medium",
        )
    if "status" in df_show.columns:
        df_show["status"] = display_df["status"].map(_safe_cell_text)
    if "priority" in df_show.columns:
        df_show["priority"] = display_df["priority"].map(_safe_cell_text)
    if "summary" in df_show.columns:
        col_cfg["summary"] = st.column_config.TextColumn("summary", width="large")
    if "description" in df_show.columns:
        df_show["description"] = display_df["description"].map(_safe_cell_text)
        col_cfg["description"] = st.column_config.TextColumn("description", width="large")
    if "status" in df_show.columns:
        col_cfg["status"] = st.column_config.TextColumn("status", width="small")
    if "priority" in df_show.columns:
        col_cfg["priority"] = st.column_config.TextColumn("priority", width="small")

    styler = df_show.style
    try:
        styler = styler.hide(axis="index")
    except Exception:
        pass
    if "key" in df_show.columns:
        styler = styler.map(_native_key_cell_style, subset=["key"])
    if "status" in df_show.columns:
        styler = styler.map(
            lambda x: _native_signal_cell_style(x, for_priority=False),
            subset=["status"],
        )
    if "priority" in df_show.columns:
        styler = styler.map(
            lambda x: _native_signal_cell_style(x, for_priority=True),
            subset=["priority"],
        )

    event = st.dataframe(
        styler,
        width="stretch",
        hide_index=True,
        column_config=col_cfg or None,
        on_select="rerun",
        selection_mode=("single-cell", "single-column"),
        key=table_key,
    )

    row_value, col_value = _selected_cell_from_event(event)
    if row_value is None and col_value:
        col_token = str(col_value or "").strip()
        col_token_lower = col_token.lower()
        origin_lower = str(origin_header or "").strip().lower()
        sortable_map = {str(c).strip().lower(): str(c) for c in df_show.columns}
        if col_token_lower == origin_lower:
            col_token_lower = "key"
        selected_sort_col = sortable_map.get(col_token_lower)
        if selected_sort_col and sort_state_prefix:
            sort_col_key = f"{sort_state_prefix}::sort_col"
            sort_asc_key = f"{sort_state_prefix}::sort_asc"
            current_col = str(st.session_state.get(sort_col_key) or "")
            current_asc = bool(st.session_state.get(sort_asc_key, False))
            default_asc = selected_sort_col not in {"updated", "created", "resolved"}
            if current_col == selected_sort_col:
                st.session_state[sort_asc_key] = not current_asc
            else:
                st.session_state[sort_col_key] = selected_sort_col
                st.session_state[sort_asc_key] = default_asc
            st.rerun()
        return

    last_open_key = f"{table_key}::last_open_token"
    col_token = str(col_value or "").strip().lower()
    if col_token not in {"key", str(origin_header or "").strip().lower()} or row_value is None:
        st.session_state[last_open_key] = ""
        return

    selected = _row_record_from_selection(display_df, records, row_value)
    if not selected:
        return
    target_url = str(selected.get("url") or "").strip()
    if not target_url:
        return
    source_type = _normalize_source_type(selected.get("source_type"))
    browser = _browser_for_source_type(settings, source_type)
    open_token = (
        f"{str(selected.get('source_id') or '').strip().lower()}::"
        f"{str(selected.get('key') or '').strip().upper()}::"
        f"{target_url}"
    )
    if str(st.session_state.get(last_open_key) or "") == open_token:
        return

    opened = open_url_in_configured_browser(
        target_url,
        browser,
        allow_system_default_fallback=False,
    )
    if not opened:
        st.warning(
            f"No se pudo abrir la incidencia en el navegador configurado ({browser}). "
            "Revisa la configuración de navegador."
        )
    st.session_state[last_open_key] = open_token
    st.rerun()


def prepare_issue_cards_df(
    dff: pd.DataFrame, *, max_cards: int, preserve_order: bool = False
) -> pd.DataFrame:
    """Prepare card rows with consistent ordering over the full filtered dataset."""
    if dff is None or dff.empty:
        return pd.DataFrame()

    cols = [
        "key",
        "summary",
        "status",
        "priority",
        "assignee",
        "created",
        "updated",
        "resolved",
        "url",
    ]
    safe_df = dff.copy(deep=False)
    for c in cols:
        if c not in safe_df.columns:
            safe_df[c] = None

    now = pd.Timestamp.now(tz="UTC")
    created = (
        pd.to_datetime(safe_df["created"], errors="coerce", utc=True)
        if "created" in safe_df.columns
        else pd.Series([pd.NaT] * len(safe_df), index=safe_df.index)
    )
    resolved = (
        pd.to_datetime(safe_df["resolved"], errors="coerce", utc=True)
        if "resolved" in safe_df.columns
        else pd.Series([pd.NaT] * len(safe_df), index=safe_df.index)
    )

    card_df = safe_df.copy(deep=False)
    card_df["__is_open"] = ~effective_closed_mask(card_df)
    card_df["__open_age_days"] = (
        ((now - created).dt.total_seconds() / 86400.0).clip(lower=0.0).fillna(0.0)
    )
    card_df["__cycle_days"] = (
        ((resolved - created).dt.total_seconds() / 86400.0).clip(lower=0.0).fillna(0.0)
    )
    card_df["__prio_rank"] = (
        card_df["priority"].astype(str).map(priority_rank) if "priority" in card_df.columns else 99
    )

    if preserve_order:
        return card_df.head(max_cards)

    sort_cols = ["__is_open", "__prio_rank"]
    asc = [False, True]
    if "updated" in card_df.columns:
        sort_cols.append("updated")
        asc.append(False)
    return card_df.sort_values(by=sort_cols, ascending=asc).head(max_cards)


def render_issue_cards(
    dff: pd.DataFrame,
    *,
    max_cards: int,
    title: str,
    settings: Settings | None = None,
    prepared_df: pd.DataFrame | None = None,
) -> None:
    """Render issues as BBVA-styled cards over the full filtered set (open first)."""
    if title:
        st.markdown(f"### {title}")

    if dff is None or dff.empty:
        st.info("No hay issues para mostrar con los filtros actuales.")
        return

    cards_df = (
        prepared_df
        if isinstance(prepared_df, pd.DataFrame)
        else prepare_issue_cards_df(dff, max_cards=max_cards)
    )

    st.markdown(
        """
        <style>
          .st-key-issues_tab_issues_shell [class*="st-key-issue_card_shell_"] {
            border: 1px solid var(--bbva-issue-card-border) !important;
            border-radius: var(--bbva-radius-xl) !important;
            padding: 14px 16px 12px 16px !important;
            margin: 0 0 12px 0 !important;
            background: linear-gradient(
              180deg,
              var(--bbva-issue-card-bg-start) 0%,
              var(--bbva-issue-card-bg-end) 100%
            ) !important;
            box-shadow: var(--bbva-issue-card-shadow),
                        inset 0 0 0 1px var(--bbva-issue-card-inset) !important;
            overflow: visible !important;
          }
          .st-key-issues_tab_issues_shell [class*="st-key-issue_card_shell_"]:hover {
            border-color: var(--bbva-issue-card-border-hover) !important;
            box-shadow: var(--bbva-issue-card-shadow-hover),
                        inset 0 0 0 1px var(--bbva-issue-card-inset-hover) !important;
          }
          .st-key-issues_tab_issues_shell [class*="st-key-issue_card_shell_"] [data-testid="stVerticalBlock"] {
            gap: 0 !important;
          }
          [class*="st-key-issue_card_shell_"] [data-testid="stHorizontalBlock"] {
            align-items: baseline !important;
          }
          [class*="st-key-issue_card_shell_"] [data-testid="stVerticalBlock"] > [data-testid="element-container"] {
            margin-bottom: 0.22rem !important;
          }
          [class*="st-key-issue_card_shell_"] [data-testid="stVerticalBlock"] > [data-testid="element-container"]:last-child {
            margin-bottom: 0 !important;
          }
          [class*="st-key-issue_open_btn_"] [data-testid="stButton"] {
            margin: 0 !important;
          }
          [class*="st-key-issue_open_btn_"] button {
            border: 0 !important;
            background: transparent !important;
            color: var(--bbva-action-link) !important;
            text-decoration: underline !important;
            font-weight: 800 !important;
            padding: 0 !important;
            margin: 0 !important;
            min-height: auto !important;
            height: auto !important;
            line-height: 1.08 !important;
            white-space: nowrap !important;
            box-shadow: none !important;
            width: auto !important;
            min-width: 0 !important;
            border-radius: 0 !important;
          }
          [class*="st-key-issue_open_btn_"] button:hover {
            color: var(--bbva-action-link-hover) !important;
            background: transparent !important;
          }
          [class*="st-key-issue_open_btn_"] button:focus,
          [class*="st-key-issue_open_btn_"] button:focus-visible {
            outline: none !important;
            box-shadow: none !important;
          }
          [class*="st-key-issue_open_btn_"] button > div,
          [class*="st-key-issue_open_btn_"] button > div > p {
            margin: 0 !important;
            padding: 0 !important;
            line-height: 1.08 !important;
          }
          .issue-title-inline {
            font-weight: 700;
            color: var(--bbva-text);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-top: 1px;
          }
          .issue-card-badges {
            margin-top: 11px !important;
            margin-bottom: 2px !important;
            padding-bottom: 8px !important;
            row-gap: 8px !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        for idx_card, row in enumerate(cards_df.to_dict(orient="records")):
            key_txt = _safe_cell_text(row.get("key"))
            key_label = key_txt if key_txt != "—" else _jira_label_from_row(row)
            url_raw = str(row.get("url") or "").strip()
            source_type = _normalize_source_type(row.get("source_type"))
            title_txt, desc_txt = _title_and_description_from_row(row)
            issue_title = html.escape(title_txt)
            issue_desc = html.escape(desc_txt)
            issue_desc_html = (
                f'<div class="issue-description">{issue_desc}</div>' if issue_desc else ""
            )
            status_txt = _safe_cell_text(row.get("status"))
            prio_txt = _safe_cell_text(row.get("priority"))
            assignee_txt = _safe_cell_text(row.get("assignee"))
            is_open = bool(row.get("__is_open", True))
            open_age = float(row.get("__open_age_days", 0.0) or 0.0)
            cycle_days = float(row.get("__cycle_days", 0.0) or 0.0)

            badges: List[str] = []
            if prio_txt != "—":
                p_style = chip_style_from_color(priority_color(prio_txt))
                badges.append(
                    f'<span class="badge badge-priority" style="{p_style}">Priority: {html.escape(prio_txt)}</span>'
                )
            if status_txt != "—":
                s_style = chip_style_from_color(status_color(status_txt))
                badges.append(
                    f'<span class="badge badge-status" style="{s_style}">Status: {html.escape(status_txt)}</span>'
                )
            if assignee_txt != "—":
                badges.append(f'<span class="badge">Assignee: {html.escape(assignee_txt)}</span>')
            if is_open:
                badges.append(f'<span class="badge badge-age">Open age: {open_age:.0f}d</span>')
            else:
                badges.append(
                    f'<span class="badge badge-age">Resolved in: {cycle_days:.0f}d</span>'
                )

            with st.container(key=f"issue_card_shell_{idx_card}"):
                c_key, c_title = st.columns([1.8, 10.2], gap="small")
                with c_key:
                    if st.button(
                        key_label,
                        key=f"issue_open_btn_{idx_card}",
                        type="tertiary",
                        width="content",
                    ):
                        browser = _browser_for_source_type(settings, source_type)
                        opened = open_url_in_configured_browser(
                            url_raw,
                            browser,
                            allow_system_default_fallback=False,
                        )
                        if not opened:
                            st.warning(
                                f"No se pudo abrir la incidencia en el navegador configurado ({browser}). "
                                "Revisa la configuración de navegador."
                            )
                with c_title:
                    st.markdown(
                        f'<div class="issue-title-inline">{issue_title}</div>',
                        unsafe_allow_html=True,
                    )
                if issue_desc_html:
                    st.markdown(issue_desc_html, unsafe_allow_html=True)
                st.markdown(
                    f'<div class="badges issue-card-badges">{"".join(badges)}</div>',
                    unsafe_allow_html=True,
                )


def render_issue_table(
    dff: pd.DataFrame,
    *,
    settings: Settings | None = None,
    table_key: str = "issues_table_grid",
    preserve_order: bool = False,
    sort_state_prefix: str | None = None,
) -> None:
    """Render issues in an interactive table with sortable headers."""
    if dff is None or dff.empty:
        st.info("No hay issues para mostrar con los filtros actuales.")
        return

    display_df = dff.copy(deep=False)

    show_cols = [
        "key",
        "summary",
        "description",
        "status",
        "type",
        "priority",
        "created",
        "updated",
        "resolved",
        "assignee",
        "components",
        "labels",
    ]
    show_cols = [c for c in show_cols if c in display_df.columns]

    sort_by = "updated" if ("updated" in display_df.columns and not preserve_order) else None
    if sort_by:
        display_df = display_df.sort_values(by=sort_by, ascending=False)

    if len(display_df) > MAX_TABLE_NATIVE_ROWS:
        st.caption(
            f"Mostrando {MAX_TABLE_NATIVE_ROWS}/{len(display_df)} filas en pantalla. "
            "Usa Excel para el dataset completo."
        )
        display_df = display_df.head(MAX_TABLE_NATIVE_ROWS).copy(deep=False)

    _render_issue_table_native(
        display_df,
        list(show_cols),
        settings=settings,
        table_key=table_key,
        sort_state_prefix=sort_state_prefix,
    )
