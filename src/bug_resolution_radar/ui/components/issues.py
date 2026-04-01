"""Issue cards/table renderers and visual formatting helpers."""

from __future__ import annotations

import html
import re
from functools import lru_cache
from typing import Iterable, List, Tuple
from urllib.parse import quote, unquote

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.status_semantics import effective_closed_mask
from bug_resolution_radar.config import Settings
from bug_resolution_radar.ingest.browser_runtime import open_url_in_configured_browser
from bug_resolution_radar.theme.design_tokens import BBVA_DARK, BBVA_LIGHT, BBVA_NEUTRAL_SOFT
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
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_MD_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
MAX_TABLE_HTML_ROWS = 3000
MAX_TABLE_NATIVE_ROWS = 2500
# Keep styled rendering for the full native table range shown to users.
# Fast path remains only as an emergency fallback for oversized direct calls.
MAX_TABLE_STYLED_ROWS = MAX_TABLE_NATIVE_ROWS
MAX_CARD_TITLE_CHARS = 220
MAX_CARD_DESCRIPTION_CHARS = 420
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
    qp = getattr(st, "query_params", None)
    if qp is None:
        return
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
    summary = _normalize_issue_card_text(_safe_cell_text(row.get("summary")))
    description = ""
    for col in (
        "description",
        "details",
        "detailed_description",
        "detailed_decription",
    ):
        txt = _normalize_issue_card_text(_safe_cell_text(row.get(col)))
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


def _issue_key_link_html(*, url: str, source_type: str, key_label: str) -> str:
    label = html.escape(str(key_label or "").strip() or "—")
    target_url = str(url or "").strip()
    if not target_url:
        return f'<span class="issue-key-anchor issue-key-anchor-disabled">{label}</span>'
    href = html.escape(
        build_issue_open_href(target_url, source_type, key_label=key_label),
        quote=True,
    )
    return f'<a class="issue-key-anchor" href="{href}">{label}</a>'


def _truncate_issue_card_text(value: str, *, max_chars: int) -> str:
    txt = str(value or "").strip()
    if not txt or txt == "—" or len(txt) <= max_chars:
        return txt
    trimmed = txt[: max_chars + 1]
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    return trimmed.rstrip(" -–—:;,.") + "…"


@lru_cache(maxsize=4096)
def _normalize_issue_card_text(value: str) -> str:
    txt = str(value or "").strip()
    if not txt or txt == "—":
        return txt or "—"

    txt = html.unescape(txt)
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    txt = _MD_CODE_FENCE_RE.sub(" ", txt)
    txt = _MD_IMAGE_RE.sub(r"\1", txt)
    txt = _MD_LINK_RE.sub(r"\1", txt)
    txt = _HTML_TAG_RE.sub(" ", txt)

    clean_lines: List[str] = []
    for raw in txt.split("\n"):
        line = str(raw or "").strip()
        if not line:
            continue
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        line = re.sub(r"^\s*>\s*", "", line)
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        line = re.sub(r"[*_~`]+", "", line)
        line = line.strip()
        if line:
            clean_lines.append(line)

    normalized = " ".join(clean_lines) if clean_lines else txt
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or "—"


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


def _safe_display_series(series: pd.Series) -> pd.Series:
    if series is None:
        return pd.Series([], dtype=str)
    values = [_safe_cell_text(v) for v in series.tolist()]
    out = pd.Series(values, index=series.index, dtype=object)
    return out.fillna("—").astype(str)


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


def _native_link_cell_style(value: object, *, dark_mode: bool = False) -> str:
    txt = _safe_cell_text(value)
    if txt == "—":
        muted = BBVA_DARK.ink_muted if dark_mode else BBVA_LIGHT.ink_muted
        return f"color: {muted};"
    link_color = BBVA_DARK.serene_blue if dark_mode else BBVA_LIGHT.electric_blue
    return f"color: {link_color}; text-decoration: underline; font-weight: 800; cursor: pointer;"


def _row_to_record_dict(row: pd.Series) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in row.items():
        out[str(key)] = value
    return out


def _iter_df_records(df: pd.DataFrame) -> Iterable[dict[str, object]]:
    columns = [str(col) for col in df.columns.tolist()]
    for values in df.itertuples(index=False, name=None):
        yield {columns[idx]: value for idx, value in enumerate(values)}


def _df_records(df: pd.DataFrame) -> List[dict[str, object]]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    return list(_iter_df_records(df))


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
                return _row_to_record_dict(maybe.iloc[0])
            if isinstance(maybe, pd.Series):
                return _row_to_record_dict(maybe)
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
    df_show = display_df[show_cols].copy(deep=False).reset_index(drop=True)
    col_cfg = {}
    origin_header = _origin_link_header(display_df)
    key_display_col = "__jira_key_display__"

    records = _df_records(display_df)
    if "key" in df_show.columns:
        key_values: List[str] = []
        for row in records:
            label = _jira_label_from_row(row)
            key_values.append(label)
        # Avoid using a visible column literally named "key" in the canvas grid.
        # Streamlit/Glide can treat it specially and end up hiding its text.
        df_show.insert(0, key_display_col, key_values)
        df_show = df_show.drop(columns=["key"], errors="ignore")
        col_cfg[key_display_col] = st.column_config.TextColumn(origin_header, width="medium")
    if "status" in df_show.columns:
        df_show["status"] = _safe_display_series(df_show["status"])
    if "priority" in df_show.columns:
        df_show["priority"] = _safe_display_series(df_show["priority"])
    if "summary" in df_show.columns:
        col_cfg["summary"] = st.column_config.TextColumn("summary", width="large")
    if "description" in df_show.columns:
        df_show["description"] = _safe_display_series(df_show["description"])
        col_cfg["description"] = st.column_config.TextColumn("description", width="large")
    if "status" in df_show.columns:
        col_cfg["status"] = st.column_config.TextColumn("status", width="small")
    if "priority" in df_show.columns:
        col_cfg["priority"] = st.column_config.TextColumn("priority", width="small")

    render_payload: object = df_show
    use_styler = len(df_show) <= MAX_TABLE_STYLED_ROWS
    if use_styler:
        styler = df_show.style
        try:
            styler = styler.hide(axis="index")
        except Exception:
            pass
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
        if key_display_col in df_show.columns:
            dark_mode = bool(st.session_state.get("workspace_dark_mode", False))
            styler = styler.map(
                lambda value: _native_link_cell_style(value, dark_mode=dark_mode),
                subset=[key_display_col],
            )
        render_payload = styler

    event = st.dataframe(
        render_payload,
        width="stretch",
        hide_index=True,
        column_config=col_cfg or None,
        on_select="rerun",
        # Keep sorting controlled in backend (shared with cards/export) and retain cell-click actions.
        selection_mode=["single-cell", "single-column"],
        key=table_key,
    )

    row_value, col_value = _selected_cell_from_event(event)
    if row_value is None:
        return

    last_open_key = f"{table_key}::last_open_token"
    col_token = str(col_value or "").strip().lower()
    if col_token not in {key_display_col.lower(), str(origin_header or "").strip().lower()}:
        st.session_state[last_open_key] = ""
        return
    if row_value is None:
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
    records = _df_records(cards_df)

    with st.container():
        for idx_card, row in enumerate(records):
            key_txt = _safe_cell_text(row.get("key"))
            key_label = key_txt if key_txt != "—" else _jira_label_from_row(row)
            url_raw = str(row.get("url") or "").strip()
            source_type = _normalize_source_type(row.get("source_type"))
            title_txt, desc_txt = _title_and_description_from_row(row)
            issue_title = html.escape(
                _truncate_issue_card_text(title_txt, max_chars=MAX_CARD_TITLE_CHARS)
            )
            issue_desc = html.escape(
                _truncate_issue_card_text(desc_txt, max_chars=MAX_CARD_DESCRIPTION_CHARS)
            )
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
                    st.markdown(
                        _issue_key_link_html(
                            url=url_raw,
                            source_type=source_type,
                            key_label=key_label,
                        ),
                        unsafe_allow_html=True,
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
