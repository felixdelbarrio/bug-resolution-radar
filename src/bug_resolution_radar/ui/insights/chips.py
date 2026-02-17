"""Chip styling and HTML builders used by insights sections."""

from __future__ import annotations

import html
from typing import Optional

import streamlit as st

from bug_resolution_radar.ui.common import (
    chip_style_from_color,
    priority_color,
    status_color,
)

_NEUTRAL_CHIP_STYLE = (
    "color:var(--bbva-text-muted); border:1px solid var(--bbva-border-strong); "
    "background:color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2)); "
    "border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.80rem;"
)


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
            color: var(--bbva-primary) !important;
            text-decoration: none;
          }
          .ins-key-link:hover {
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
    if color.upper() == "#E2E6EE":
        return _NEUTRAL_CHIP_STYLE
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
    return f'<span class="ins-chip" style="{_NEUTRAL_CHIP_STYLE}">{html.escape(txt)}</span>'


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
) -> str:
    k_html = key_html(key, url)
    if not k_html:
        return ""

    bits = [k_html]
    if age_days is not None:
        bits.append(neutral_chip_html(f"{age_days:.0f}d"))
    if assignee:
        bits.append(neutral_chip_html(f"Asignado: {assignee}"))
    bits.append(status_chip_html(status))
    bits.append(priority_chip_html(priority))
    summary_html = f'<span class="ins-summary">{html.escape(summary)}</span>' if summary else ""
    return (
        '<div class="ins-card">'
        f'<div class="ins-main">{" ".join(bits)}</div>'
        f'<div class="ins-main">{summary_html}</div>'
        "</div>"
    )
