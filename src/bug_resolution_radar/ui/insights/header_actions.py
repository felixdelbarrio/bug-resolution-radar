"""Shared header row helpers for Insights tabs."""

from __future__ import annotations

from typing import Callable

import streamlit as st


def render_insights_header_row(
    *,
    left_render: Callable[[], None] | None,
    right_render: Callable[[], None],
) -> None:
    """Render a single-row header with optional left control and right actions."""
    if left_render is None:
        right_render()
        return

    left_col, right_col = st.columns([5.6, 1.2], gap="small")
    with left_col:
        left_render()
    with right_col:
        right_render()
