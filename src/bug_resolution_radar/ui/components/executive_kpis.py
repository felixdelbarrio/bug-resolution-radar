"""Shared executive KPI cards used across dashboard and insights views."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Sequence

import streamlit as st


@dataclass(frozen=True)
class ExecutiveKpiItem:
    label: str
    value: str
    hint: str = ""
    tone: str = "neutral"


def _inject_exec_kpi_css() -> None:
    st.markdown(
        """
        <style>
          .exec-wrap {
            border: 1px solid var(--bbva-border);
            border-radius: 16px;
            background: var(--bbva-surface-elevated);
            padding: 0.46rem 0.62rem;
          }
          .exec-kpi-grid {
            display: grid;
            gap: 0.42rem;
            margin-bottom: 0.40rem;
          }
          .exec-kpi {
            border: 1px solid var(--bbva-border);
            border-radius: 12px;
            background: color-mix(in srgb, var(--bbva-surface) 92%, var(--bbva-surface-2));
            padding: 0.40rem 0.52rem;
          }
          .exec-kpi.exec-kpi--red {
            border-color: color-mix(in srgb, var(--bbva-signal-red) 52%, var(--bbva-border));
            background: color-mix(in srgb, var(--bbva-signal-red-soft) 28%, var(--bbva-surface) 72%);
          }
          .exec-kpi.exec-kpi--green {
            border-color: color-mix(in srgb, var(--bbva-signal-green) 50%, var(--bbva-border));
            background: color-mix(in srgb, var(--bbva-signal-green) 20%, var(--bbva-surface) 80%);
          }
          .exec-kpi.exec-kpi--amber {
            border-color: color-mix(in srgb, var(--bbva-signal-yellow) 58%, var(--bbva-border));
            background: color-mix(in srgb, var(--bbva-signal-yellow) 22%, var(--bbva-surface) 78%);
          }
          .exec-kpi-lbl {
            color: var(--bbva-text-muted);
            font-size: 0.76rem;
            font-weight: 700;
            line-height: 1.15;
          }
          .exec-kpi-val {
            margin-top: 0.08rem;
            color: var(--bbva-text);
            font-size: 1.44rem;
            font-weight: 800;
            line-height: 1.04;
          }
          .exec-kpi-hint {
            margin-top: 0.14rem;
            color: var(--bbva-text-muted);
            font-size: 0.72rem;
            line-height: 1.1;
          }
          .exec-kpi.exec-kpi--red .exec-kpi-val { color: var(--bbva-signal-red-strong); }
          .exec-kpi.exec-kpi--green .exec-kpi-val { color: var(--bbva-goal-green); }
          .exec-kpi.exec-kpi--amber .exec-kpi-val { color: color-mix(in srgb, var(--bbva-signal-yellow) 86%, var(--bbva-midnight) 14%); }
          @media (max-width: 1020px) {
            .exec-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
          }
          @media (max-width: 680px) {
            .exec-kpi-grid { grid-template-columns: 1fr !important; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_executive_kpi_grid(
    items: Sequence[ExecutiveKpiItem],
    *,
    columns: int = 4,
) -> None:
    """Render executive KPI cards with the same visual treatment as dashboard overview."""
    if not items:
        return
    _inject_exec_kpi_css()
    cols = max(1, int(columns))
    cards_html = []
    allowed_tones = {"neutral", "red", "green", "amber"}
    for item in items:
        tone = str(getattr(item, "tone", "neutral") or "neutral").strip().lower()
        if tone not in allowed_tones:
            tone = "neutral"
        cards_html.append(
            (
                f'<article class="exec-kpi exec-kpi--{tone}">'
                f'<div class="exec-kpi-lbl">{html.escape(str(item.label))}</div>'
                f'<div class="exec-kpi-val">{html.escape(str(item.value))}</div>'
                f'<div class="exec-kpi-hint">{html.escape(str(item.hint or ""))}</div>'
                "</article>"
            )
        )
    st.markdown(
        (
            '<section class="exec-wrap">'
            f'<div class="exec-kpi-grid" style="grid-template-columns: repeat({cols}, minmax(0, 1fr));">'
            f"{''.join(cards_html)}"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )
