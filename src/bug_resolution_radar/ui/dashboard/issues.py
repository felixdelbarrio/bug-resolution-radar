from __future__ import annotations

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.components.issues import render_issue_cards, render_issue_table
from bug_resolution_radar.ui.dashboard.downloads import make_table_export_df, render_download_bar


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
    - Always shows ALL filtered issues (no 'max issues' slider)
    - CSV download always enabled (both Cards & Table), using the Table export format
    """
    st.markdown(f"### {title}")

    dff_show = _sorted_for_display(dff)

    # CSV export always uses the "table-like" dataframe
    export_df = make_table_export_df(dff_show)

    # Top bar: download + count (visible in both views)
    render_download_bar(
        export_df,
        key_prefix=key_prefix,
        filename_prefix="issues_filtradas",
        suffix="issues",
    )

    # Default view: Cards
    view = st.radio(
        "Vista",
        options=["Cards", "Tabla"],
        horizontal=True,
        index=0,
        label_visibility="collapsed",
        key=f"{key_prefix}::view_mode",
    )

    if dff_show.empty:
        st.info("No hay issues para mostrar con los filtros actuales.")
        return

    if view == "Cards":
        render_issue_cards(
            dff_show,
            max_cards=int(len(dff_show)),
            title="Issues (prioridad + última actualización)",
        )
        return

    st.markdown("#### Tabla (filtrada)")
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
    st.markdown("## 🧾 Issues")

    dff_filtered = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    if dff_filtered.empty:
        st.info("No hay datos para mostrar.")
        return

    # Render sección (export + cards/tabla)
    render_issues_section(dff_filtered, title="Issues (filtradas)", key_prefix=key_prefix)
