"""Chip styling and HTML builders used by insights sections."""

from __future__ import annotations

import html
from typing import Mapping, Optional, Tuple

import pandas as pd
import streamlit as st

from bug_resolution_radar.analytics.topic_expandable_summary import infer_root_cause_label
from bug_resolution_radar.theme.design_tokens import BBVA_NEUTRAL_SOFT
from bug_resolution_radar.ui.common import (
    chip_style_from_color,
    neutral_chip_style,
    priority_color,
    status_color,
)

_NEUTRAL_TOKEN = BBVA_NEUTRAL_SOFT.upper()


def inject_insights_chip_css() -> None:
    st.markdown(
        """
        <style>
          .ins-card {
            border: 1px solid var(--bbva-border);
            border-radius: 12px;
            background: var(--bbva-surface-soft);
            padding: 0.50rem 0.62rem;
            margin: 0.34rem 0;
            transition: border-color 120ms ease, box-shadow 120ms ease;
          }
          .ins-card:hover {
            border-color: var(--bbva-border-strong);
            box-shadow: 0 2px 10px color-mix(in srgb, var(--bbva-text) 10%, transparent);
          }
          .ins-main {
            display: flex;
            align-items: center;
            gap: 0.38rem;
            flex-wrap: wrap;
            min-width: 0;
          }
          .ins-card .ins-main + .ins-main {
            margin-top: 0.30rem;
          }
          .ins-key-link,
          .ins-key-text {
            font-weight: 800;
            font-size: 0.98rem;
            line-height: 1.25;
          }
          .ins-key-link {
            color: var(--bbva-action-link) !important;
            font-family: var(--bbva-font-sans) !important;
            text-decoration: none;
          }
          .ins-key-link:hover {
            color: var(--bbva-action-link-hover) !important;
            text-decoration: underline;
          }
          .ins-chip {
            display: inline-flex;
            align-items: center;
            white-space: nowrap;
            max-width: 100%;
          }
          .ins-summary {
            color: color-mix(in srgb, var(--bbva-text) 96%, transparent);
            line-height: 1.28;
          }
          .ins-meta-row {
            display: flex;
            align-items: center;
            gap: 0.35rem;
            flex-wrap: wrap;
            margin-bottom: 0.35rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _safe_text(value: object, *, fallback: str) -> str:
    txt = str(value or "").strip()
    return txt if txt else fallback


def _chip_style(value: str, *, is_priority: bool) -> str:
    color = priority_color(value) if is_priority else status_color(value)
    if color.upper() == _NEUTRAL_TOKEN:
        return neutral_chip_style()
    return chip_style_from_color(color)


def _chip_html(value: object, *, is_priority: bool, fallback: str) -> str:
    txt = _safe_text(value, fallback=fallback)
    return f'<span class="ins-chip" style="{_chip_style(txt, is_priority=is_priority)}">{html.escape(txt)}</span>'


def status_chip_html(value: object) -> str:
    return _chip_html(value, is_priority=False, fallback="(sin estado)")


def priority_chip_html(value: object) -> str:
    return _chip_html(value, is_priority=True, fallback="(sin priority)")


def neutral_chip_html(text: object) -> str:
    txt = _safe_text(text, fallback="—")
    return f'<span class="ins-chip" style="{neutral_chip_style()}">{html.escape(txt)}</span>'


def key_html(key: object, url: str) -> str:
    k = _safe_text(key, fallback="")
    if not k:
        return ""
    if url:
        return (
            f'<a class="ins-key-link" href="{html.escape(url)}" target="_blank" '
            f'rel="noopener noreferrer">{html.escape(k)}</a>'
        )
    return f'<span class="ins-key-text">{html.escape(k)}</span>'


def render_issue_bullet(
    *,
    key: object,
    url: str,
    status: object,
    priority: object,
    summary: Optional[str] = None,
    age_days: Optional[float] = None,
    assignee: Optional[str] = None,
) -> None:
    card = issue_card_html(
        key=key,
        url=url,
        status=status,
        priority=priority,
        summary=summary,
        age_days=age_days,
        assignee=assignee,
    )
    if card:
        st.markdown(card, unsafe_allow_html=True)


def issue_card_html(
    *,
    key: object,
    url: str,
    status: object,
    priority: object,
    summary: Optional[str] = None,
    age_days: Optional[float] = None,
    assignee: Optional[str] = None,
    source: Optional[str] = None,
    root_cause: Optional[str] = None,
) -> str:
    k_html = key_html(key, url)
    if not k_html:
        return ""

    bits = [k_html]
    if age_days is not None:
        bits.append(neutral_chip_html(f"{age_days:.0f}d"))
    if assignee:
        bits.append(neutral_chip_html(f"Asignado: {assignee}"))
    if source:
        bits.append(neutral_chip_html(f"Origen: {source}"))
    bits.append(status_chip_html(status))
    bits.append(priority_chip_html(priority))
    if root_cause:
        bits.append(neutral_chip_html(f"Causa raíz: {root_cause}"))
    summary_html = f'<span class="ins-summary">{html.escape(summary)}</span>' if summary else ""
    return (
        '<div class="ins-card">'
        f'<div class="ins-main">{" ".join(bits)}</div>'
        f'<div class="ins-main">{summary_html}</div>'
        "</div>"
    )


def issue_cards_html_from_df(
    df: pd.DataFrame,
    *,
    key_to_url: Mapping[str, str],
    key_to_meta: Mapping[str, Tuple[str, str, str]],
    summary_col: str = "summary",
    assignee_col: str = "assignee",
    age_days_col: str | None = None,
    source_col: str | None = None,
    include_root_cause: bool = False,
    summary_max_chars: int = 160,
    limit: int | None = None,
) -> str:
    """Build issue cards HTML from a dataframe using the same visual style across insights."""
    if not isinstance(df, pd.DataFrame) or df.empty or "key" not in df.columns:
        return ""

    view = df if limit is None else df.head(max(0, int(limit)))
    cards: list[str] = []
    for _, row in view.iterrows():
        issue_key = str(row.get("key", "") or "").strip()
        if not issue_key:
            continue

        status, prio, fallback_summary = key_to_meta.get(
            issue_key,
            ("(sin estado)", "(sin priority)", ""),
        )
        issue_url = str(key_to_url.get(issue_key, "") or "").strip()

        age_days: float | None = None
        if age_days_col and age_days_col in view.columns:
            age_raw = row.get(age_days_col, pd.NA)
            if pd.notna(age_raw):
                try:
                    age_days = float(age_raw)
                except Exception:
                    age_days = None

        assignee = ""
        if assignee_col in view.columns:
            assignee = str(row.get(assignee_col, "") or "").strip()
        assignee = assignee or "(sin asignar)"

        source = ""
        if source_col and source_col in view.columns:
            source = str(row.get(source_col, "") or "").strip()

        summary_text = ""
        if summary_col in view.columns:
            summary_text = str(row.get(summary_col, "") or "").strip()
        if not summary_text:
            summary_text = str(fallback_summary or "").strip()
        if summary_max_chars > 0 and len(summary_text) > summary_max_chars:
            summary_text = summary_text[: max(0, summary_max_chars - 3)] + "..."

        root_cause = ""
        if include_root_cause:
            root_cause = infer_root_cause_label(summary_text)

        card_html = issue_card_html(
            key=issue_key,
            url=issue_url,
            status=status,
            priority=prio,
            summary=summary_text,
            age_days=age_days,
            assignee=assignee,
            source=source,
            root_cause=root_cause,
        )
        if card_html:
            cards.append(card_html)
    return "".join(cards)
