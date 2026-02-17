"""Issue cards/table renderers and visual formatting helpers."""

from __future__ import annotations

import html
import re
from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import (
    chip_style_from_color,
    priority_color,
    priority_rank,
    status_color,
)

_JIRA_KEY_RE = re.compile(r"/browse/([^/?#]+)")
MAX_TABLE_HTML_ROWS = 1200


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


def _render_issue_table_html(display_df: pd.DataFrame, show_cols: List[str]) -> None:
    title_by_col = {
        "jira": "Jira",
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
    records = display_df[show_cols].to_dict(orient="records")
    for idx, row in zip(display_df.index.tolist(), records):
        row_cells = [f'<td class="issue-table-index">{html.escape(str(idx))}</td>']
        for col in show_cols:
            if col == "jira":
                url = str(row.get("jira") or row.get("url") or "").strip()
                label = _jira_label_from_row(row)
                if url:
                    row_cells.append(
                        "<td>"
                        f'<a class="issue-table-jira" href="{html.escape(url)}" '
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
            border: 1px solid rgba(17,25,45,0.12);
            border-radius: 14px;
            overflow: hidden;
            background: #ffffff;
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
            color: rgba(17,25,45,0.60);
            background: #F6F8FB;
            border-bottom: 1px solid rgba(17,25,45,0.12);
            padding: 0.60rem 0.72rem;
            white-space: nowrap;
          }}
          .issue-table td {{
            border-top: 1px solid rgba(17,25,45,0.10);
            padding: 0.50rem 0.72rem;
            vertical-align: middle;
            color: #11192D;
            white-space: nowrap;
          }}
          .issue-table-index {{
            width: 54px;
            text-align: right !important;
            color: rgba(17,25,45,0.52) !important;
            font-variant-numeric: tabular-nums;
            background: #FBFCFE;
          }}
          .issue-table-summary {{
            min-width: 480px;
            max-width: 680px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }}
          .issue-table-jira {{
            color: #0051F1 !important;
            font-weight: 700;
            text-decoration: none;
          }}
          .issue-table-jira:hover {{
            text-decoration: underline;
          }}
          .issue-table-chip {{
            display: inline-flex;
            align-items: center;
            max-width: 100%;
          }}
          .issue-table-chip-neutral {{
            color: #44546B;
            border: 1px solid rgba(17,25,45,0.16);
            background: #F4F6F9;
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


def render_issue_cards(dff: pd.DataFrame, *, max_cards: int, title: str) -> None:
    """Render issues as BBVA-styled cards (open issues prioritized)."""
    if title:
        st.markdown(f"### {title}")

    if dff is None or dff.empty:
        st.info("No hay issues para mostrar con los filtros actuales.")
        return

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

    now = pd.Timestamp.utcnow()
    open_df = (
        safe_df[safe_df["resolved"].isna()].copy(deep=False)
        if "resolved" in safe_df.columns
        else safe_df.copy(deep=False)
    )

    if "created" in open_df.columns:
        open_df["open_age_days"] = ((now - open_df["created"]).dt.total_seconds() / 86400.0).fillna(
            0.0
        )
    else:
        open_df["open_age_days"] = 0.0

    # Sort: priority, then updated desc.
    open_df["_prio_rank"] = (
        open_df["priority"].astype(str).map(priority_rank) if "priority" in open_df.columns else 99
    )
    sort_cols = ["_prio_rank"]
    asc = [True]
    if "updated" in open_df.columns:
        sort_cols.append("updated")
        asc.append(False)

    open_df = open_df.sort_values(by=sort_cols, ascending=asc).head(max_cards)

    cards: List[str] = []
    for row in open_df.itertuples(index=False):
        key = html.escape(str(getattr(row, "key", "") or ""))
        url = html.escape(str(getattr(row, "url", "") or ""))
        summary = html.escape(str(getattr(row, "summary", "") or ""))
        status = html.escape(str(getattr(row, "status", "") or ""))
        prio = html.escape(str(getattr(row, "priority", "") or ""))
        assignee = html.escape(str(getattr(row, "assignee", "") or ""))
        age = float(getattr(row, "open_age_days", 0.0) or 0.0)

        badges: List[str] = []
        if prio:
            p_style = chip_style_from_color(priority_color(prio))
            badges.append(
                f'<span class="badge badge-priority" style="{p_style}">Priority: {prio}</span>'
            )
        if status:
            s_style = chip_style_from_color(status_color(status))
            badges.append(
                f'<span class="badge badge-status" style="{s_style}">Status: {status}</span>'
            )
        if assignee:
            badges.append(f'<span class="badge">Assignee: {assignee}</span>')
        badges.append(f'<span class="badge badge-age">Open age: {age:.0f}d</span>')

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

    # Make a clickable Jira link using stored URL
    if "url" in display_df.columns:
        display_df["jira"] = display_df["url"]

    show_cols = [
        "jira",
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
            f"Tabla optimizada: mostrando {MAX_TABLE_HTML_ROWS}/{len(display_df)} filas. "
            "Usa CSV para el dataset completo."
        )
        display_df = display_df.head(MAX_TABLE_HTML_ROWS).copy(deep=False)

    _render_issue_table_html(display_df, show_cols)
