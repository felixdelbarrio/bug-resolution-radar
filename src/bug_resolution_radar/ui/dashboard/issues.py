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

    dff_show = _sorted_for_display(dff)

    # CSV export always uses the "table-like" dataframe
    export_df = make_table_export_df(dff_show)

    # Compact toolbar: CSV + count + view mode (same visual language as top tabs)
    view_key = f"{key_prefix}::view_mode"
    if view_key not in st.session_state:
        st.session_state[view_key] = "Cards"

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
            use_container_width=False,
        )
    with center:
        n = 0 if export_df is None else int(len(export_df))
        st.caption(f"{n:,} issues filtradas")
    with right:
        picked = st.segmented_control(
            "Vista",
            options=["Cards", "Tabla"],
            selection_mode="single",
            key=view_key,
            label_visibility="collapsed",
            width="stretch",
        )
        view = str(picked or st.session_state.get(view_key) or "Cards")

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
