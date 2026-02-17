"""Issues tab orchestration and view mode selection."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.components.issues import render_issue_cards, render_issue_table
from bug_resolution_radar.ui.dashboard.downloads import (
    CsvDownloadSpec,
    download_button_for_df,
    make_table_export_df,
)

MAX_CARDS_RENDER = 250


def _sorted_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    if "updated" in df.columns:
        return df.sort_values(by="updated", ascending=False)
    return df.copy()


def _set_issues_view(view_key: str, value: str) -> None:
    st.session_state[view_key] = value


def _inject_issues_view_toggle_css(*, scope_key: str) -> None:
    """Scoped style for Issues Cards/Tabla toggle buttons."""
    st.markdown(
        f"""
        <style>
          .st-key-{scope_key} .stButton > button {{
            min-height: 2.15rem !important;
            padding: 0.35rem 0.78rem !important;
            border-radius: 10px !important;
            font-weight: 700 !important;
            border: 1px solid var(--bbva-tab-soft-border) !important;
            background: var(--bbva-tab-soft-bg) !important;
            color: var(--bbva-tab-soft-text) !important;
          }}
          .st-key-{scope_key} .stButton > button[kind="primary"] {{
            border-color: var(--bbva-tab-active-border) !important;
            background: var(--bbva-tab-active-bg) !important;
            color: var(--bbva-tab-active-text) !important;
          }}
          .st-key-{scope_key} .stButton > button * {{
            color: inherit !important;
            fill: currentColor !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_issues_section(
    dff: pd.DataFrame,
    *,
    title: str = "Issues",
    key_prefix: str = "issues",
) -> None:
    """Render the Issues section with:
    - Default view: Cards
    - Table always includes all filtered issues
    - Cards are capped for render performance on large datasets
    - CSV download always enabled (both Cards & Table), using the Table export format
    """
    if title:
        st.markdown(f"### {title}")

    with st.container(border=True, key=f"{key_prefix}_issues_shell"):
        dff_show = _sorted_for_display(dff)

        # CSV export always uses the "table-like" dataframe
        export_df = make_table_export_df(dff_show)

        # Compact toolbar: CSV + count + view mode (same visual language as top tabs)
        view_key = f"{key_prefix}::view_mode"
        if str(st.session_state.get(view_key) or "").strip() not in {"Cards", "Tabla"}:
            st.session_state[view_key] = "Cards"
        view = str(st.session_state.get(view_key) or "Cards")

        # Keep same grid as filters (Estado | Priority | Asignado) for strict visual alignment.
        left, center, right = st.columns([1.35, 1.0, 1.0], gap="small")
        with left:
            download_button_for_df(
                export_df,
                label="⬇ CSV",
                key=f"{key_prefix}::download_csv",
                spec=CsvDownloadSpec(filename_prefix="issues_filtradas"),
                suffix="issues",
                disabled=export_df is None or export_df.empty,
                width="content",
            )
        with center:
            n = 0 if export_df is None else int(len(export_df))
            st.caption(f"{n:,} issues filtradas")
        with right:
            toggle_scope = f"{key_prefix}_view_toggle"
            _inject_issues_view_toggle_css(scope_key=toggle_scope)
            with st.container(key=toggle_scope):
                c_cards, c_table = st.columns(2, gap="small")
                c_cards.button(
                    "Cards",
                    key=f"{view_key}::cards_btn",
                    type="primary" if view == "Cards" else "secondary",
                    width="stretch",
                    on_click=_set_issues_view,
                    args=(view_key, "Cards"),
                )
                c_table.button(
                    "Tabla",
                    key=f"{view_key}::table_btn",
                    type="primary" if view == "Tabla" else "secondary",
                    width="stretch",
                    on_click=_set_issues_view,
                    args=(view_key, "Tabla"),
                )

        if dff_show.empty:
            st.info("No hay issues para mostrar con los filtros actuales.")
            return

        if view == "Cards":
            max_cards = min(int(len(dff_show)), MAX_CARDS_RENDER)
            if len(dff_show) > MAX_CARDS_RENDER:
                st.caption(
                    f"Vista Cards mostrando {max_cards}/{len(dff_show)}. "
                    "Usa Tabla para ver todos los resultados."
                )
            render_issue_cards(
                dff_show,
                max_cards=max_cards,
                title="",
            )
            return

        render_issue_table(export_df)


def render_issues_tab(
    dff: pd.DataFrame | None = None,
    *,
    key_prefix: str = "issues_tab",
) -> None:
    """
    Issues tab:
    - Consume el dataframe ya filtrado por el dashboard (single source of truth).
    - Sin filtros locales para evitar doble cómputo/incoherencias entre tabs.
    """
    dff_filtered = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    if dff_filtered.empty:
        st.info("No hay datos para mostrar.")
        return

    # Render sección (export + cards/tabla)
    render_issues_section(dff_filtered, title="", key_prefix=key_prefix)
