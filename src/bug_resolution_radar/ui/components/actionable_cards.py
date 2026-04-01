"""Reusable actionable cards with semantic accent, metric and inline CTA."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import streamlit as st


@dataclass(frozen=True)
class ActionableCardItem:
    card_id: str
    kicker: str
    metric: str
    detail: str
    link_label: str = ""
    tone: str = "neutral"
    on_click: Callable[..., None] | None = None
    click_args: tuple[Any, ...] = ()
    click_kwargs: Mapping[str, Any] = field(default_factory=dict)
    disabled: bool = False


def tone_color_css(tone: str) -> str:
    """Return canonical dashboard/insights tone color using shared semantic tokens."""
    tone_key = str(tone or "").strip().lower()
    return {
        "risk": "var(--bbva-focus-tone-risk)",
        "warning": "var(--bbva-focus-tone-warning)",
        "flow": "var(--bbva-focus-tone-flow)",
        "quality": "var(--bbva-focus-tone-quality)",
        "opportunity": "var(--bbva-focus-tone-opportunity)",
    }.get(tone_key, "var(--bbva-primary)")


def _inject_actionable_cards_css(key_prefix: str) -> None:
    token = str(key_prefix or "actionable_cards").strip()
    st.markdown(
        f"""
        <style>
          [class*="st-key-{token}_card_"] {{
            border: 1px solid var(--bbva-border) !important;
            border-radius: 12px !important;
            background: color-mix(in srgb, var(--bbva-surface) 92%, var(--bbva-surface-2)) !important;
            box-shadow: none !important;
            padding: 0.54rem 0.64rem !important;
          }}
          [class*="st-key-{token}_card_"] [data-testid="stVerticalBlock"] {{
            gap: 0.45rem !important;
          }}
          [class*="st-key-{token}_card_"] [data-testid="stVerticalBlockBorderWrapper"] {{
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
          }}
          [class*="st-key-{token}_card_"] [data-testid="stVerticalBlockBorderWrapper"] > div {{
            padding-top: 0 !important;
          }}
          [class*="st-key-{token}_link_"] div[data-testid="stButton"] > button {{
            justify-content: flex-start !important;
            width: 100% !important;
            min-height: 1.66rem !important;
            padding: 0 !important;
            border: 0 !important;
            background: transparent !important;
            color: var(--bbva-action-link) !important;
            font-family: var(--bbva-font-sans) !important;
            font-size: 0.98rem !important;
            font-weight: 760 !important;
            letter-spacing: 0 !important;
            border-radius: 8px !important;
            text-align: left !important;
            box-shadow: none !important;
          }}
          [class*="st-key-{token}_link_"] div[data-testid="stButton"] > button *,
          [class*="st-key-{token}_link_"] div[data-testid="stButton"] > button svg {{
            color: inherit !important;
            fill: currentColor !important;
          }}
          [class*="st-key-{token}_link_"] div[data-testid="stButton"] > button:hover {{
            color: var(--bbva-action-link-hover) !important;
            transform: translateX(1px);
          }}
          [class*="st-key-{token}_link_"] div[data-testid="stButton"] > button:focus-visible {{
            outline: none !important;
            box-shadow: 0 0 0 2px color-mix(in srgb, var(--bbva-primary) 34%, transparent) !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_actionable_card_grid(
    items: Sequence[ActionableCardItem],
    *,
    columns: int = 4,
    key_prefix: str = "actionable_cards",
) -> None:
    """Render cards in a responsive grid with focus-style visuals and CTA links."""
    cards = list(items or [])
    if not cards:
        return

    _inject_actionable_cards_css(key_prefix)
    col_count = max(1, int(columns))

    for start in range(0, len(cards), col_count):
        row_cards = cards[start : start + col_count]
        cols = st.columns(col_count, gap="small")
        for idx, card in enumerate(row_cards):
            with cols[idx]:
                tone = tone_color_css(card.tone)
                with st.container(key=f"{key_prefix}_card_{card.card_id}"):
                    st.markdown(
                        (
                            '<div style="width:4.20rem;height:0.22rem;border-radius:999px;'
                            f'margin-bottom:0.10rem;background:color-mix(in srgb, {tone} 82%, var(--bbva-primary) 18%);"></div>'
                            '<div style="font-size:0.70rem;font-weight:800;line-height:1.1;'
                            f'text-transform:uppercase;letter-spacing:0.05em;color:color-mix(in srgb, {tone} 76%, var(--bbva-text-muted) 24%);">'
                            f"{html.escape(str(card.kicker or ''))}"
                            "</div>"
                            '<div style="font-size:2.02rem;font-weight:800;line-height:1.02;letter-spacing:-0.02em;'
                            f'color:color-mix(in srgb, {tone} 62%, var(--bbva-text) 38%);">'
                            f"{html.escape(str(card.metric or ''))}"
                            "</div>"
                            '<div style="color:var(--bbva-text-muted);font-size:0.92rem;line-height:1.3;'
                            'min-height:2.34rem;">'
                            f"{html.escape(str(card.detail or ''))}"
                            "</div>"
                        ),
                        unsafe_allow_html=True,
                    )
                    if str(card.link_label or "").strip():
                        with st.container(key=f"{key_prefix}_link_{card.card_id}"):
                            st.button(
                                str(card.link_label),
                                key=f"{key_prefix}_btn_{card.card_id}",
                                width="stretch",
                                on_click=card.on_click,
                                args=tuple(card.click_args or ()),
                                kwargs=dict(card.click_kwargs or {}),
                                disabled=bool(card.disabled),
                            )
