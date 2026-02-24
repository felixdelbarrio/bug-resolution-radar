"""Issue cards/table renderers and visual formatting helpers."""

from __future__ import annotations

import html
import re
from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.status_semantics import effective_closed_mask
from bug_resolution_radar.ui.common import (
    chip_palette_for_color,
    chip_style_from_color,
    priority_color,
    priority_rank,
    status_color,
)

_JIRA_KEY_RE = re.compile(r"/browse/([^/?#]+)")
_SOURCE_TYPE_TOKENS = {"jira": "Jira", "helix": "Helix"}
MAX_TABLE_HTML_ROWS = 3000
MAX_TABLE_NATIVE_ROWS = 2500


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) != 6:
        return f"rgba(127,146,178,{alpha:.3f})"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3f})"


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
    url = str(row.get("jira") or row.get("url") or "").strip()
    m = _JIRA_KEY_RE.search(url)
    return m.group(1) if m else "Jira"


def _chip_html(value: object, *, for_priority: bool) -> str:
    txt = _safe_cell_text(value)
    if txt == "—":
        return '<span class="issue-table-chip issue-table-chip-neutral">—</span>'
    color = priority_color(txt) if for_priority else status_color(txt)
    if color.upper() == "#E2E6EE":
        return (
            '<span class="issue-table-chip issue-table-chip-neutral">'
            f"{html.escape(txt)}"
            "</span>"
        )
    style = chip_style_from_color(color)
    return f'<span class="issue-table-chip" style="{style}">{html.escape(txt)}</span>'


def _native_signal_cell_style(value: object, *, for_priority: bool) -> str:
    txt = _safe_cell_text(value)
    if txt == "—":
        return (
            "color: var(--bbva-text-muted) !important; "
            "font-weight: 700 !important; "
            "background: color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2)) !important; "
            "border: 1px solid var(--bbva-border) !important; "
            "border-radius: 999px !important;"
        )

    color = priority_color(txt) if for_priority else status_color(txt)
    if color.upper() == "#E2E6EE":
        return (
            "color: var(--bbva-text) !important; "
            "font-weight: 700 !important; "
            "background: color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2)) !important; "
            "border: 1px solid var(--bbva-border) !important; "
            "border-radius: 999px !important;"
        )

    txt_color, border, bg = chip_palette_for_color(color)
    return (
        f"color: {txt_color} !important; "
        f"background: {bg} !important; "
        f"border: 1px solid {border} !important; "
        "border-radius: 999px !important; "
        "font-weight: 700 !important;"
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
                label = _safe_cell_text(row.get("key"))
                if label == "—":
                    label = _jira_label_from_row(row)
                if url:
                    row_cells.append(
                        "<td>"
                        f'<a class="issue-table-origin" href="{html.escape(url)}" '
                        f'target="_blank" rel="noopener noreferrer">{html.escape(label)}</a>'
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
              <thead><tr>{''.join(header_cells)}</tr></thead>
              <tbody>{''.join(rows_html)}</tbody>
            </table>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_issue_table_native(display_df: pd.DataFrame, show_cols: List[str]) -> None:
    """Render large datasets with Streamlit's virtualized table to reduce DOM pressure."""
    df_show = display_df[show_cols].copy(deep=False)
    col_cfg = {}
    origin_header = _origin_link_header(display_df)
    if "key" in df_show.columns:
        col_cfg["key"] = st.column_config.TextColumn(origin_header, width="small")
    if "url" in df_show.columns:
        col_cfg["url"] = st.column_config.LinkColumn("Abrir", display_text="Abrir")
    if "summary" in df_show.columns:
        col_cfg["summary"] = st.column_config.TextColumn("summary", width="large")
    if "status" in df_show.columns:
        col_cfg["status"] = st.column_config.TextColumn("status", width="medium")
    if "priority" in df_show.columns:
        col_cfg["priority"] = st.column_config.TextColumn("priority", width="small")

    styler = df_show.style
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

    st.dataframe(
        styler,
        width="stretch",
        hide_index=False,
        column_config=col_cfg or None,
    )


def prepare_issue_cards_df(dff: pd.DataFrame, *, max_cards: int) -> pd.DataFrame:
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

    cards: List[str] = []
    for row in cards_df.to_dict(orient="records"):
        key_txt = _safe_cell_text(row.get("key"))
        key = html.escape(key_txt if key_txt != "—" else _jira_label_from_row(row))
        url_raw = str(row.get("url") or "").strip()
        url = html.escape(url_raw)
        summary = html.escape(_safe_cell_text(row.get("summary")))
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
            badges.append(f'<span class="badge badge-age">Resolved in: {cycle_days:.0f}d</span>')

        cards.append(
            (
                '<article class="issue-card">'
                '<div class="issue-top">'
                f'<div class="issue-key"><a href="{url}" target="_blank" rel="noopener noreferrer">{key}</a></div>'
                "</div>"
                f'<div class="issue-summary">{summary}</div>'
                f'<div class="badges">{"".join(badges)}</div>'
                "</article>"
            )
        )
    st.markdown(
        f"""
        <style>
          .issue-cards-stack {{
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            gap: 12px;
          }}
        </style>
        <div class="issue-cards-stack">{''.join(cards)}</div>
        """,
        unsafe_allow_html=True,
    )


def render_issue_table(dff: pd.DataFrame) -> None:
    """Render issues in a custom HTML table with chip-style status/priority cells."""
    if dff is None or dff.empty:
        st.info("No hay issues para mostrar con los filtros actuales.")
        return

    display_df = dff.copy(deep=False)

    show_cols = [
        "key",
        "summary",
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

    sort_by = "updated" if "updated" in display_df.columns else None
    if sort_by:
        display_df = display_df.sort_values(by=sort_by, ascending=False)

    if len(display_df) > MAX_TABLE_HTML_ROWS:
        st.caption(
            f"Tabla optimizada: vista virtualizada para {len(display_df)} filas "
            "(mejor rendimiento y menor consumo de memoria)."
        )
        if len(display_df) > MAX_TABLE_NATIVE_ROWS:
            st.caption(
                f"Mostrando {MAX_TABLE_NATIVE_ROWS}/{len(display_df)} filas en pantalla. "
                "Usa CSV para el dataset completo."
            )
            display_df = display_df.head(MAX_TABLE_NATIVE_ROWS).copy(deep=False)
        native_cols = list(show_cols)
        if "url" in display_df.columns and "url" not in native_cols:
            native_cols.insert(1 if "key" in native_cols else 0, "url")
        _render_issue_table_native(display_df, native_cols)
        return

    _render_issue_table_html(display_df, show_cols)
