from __future__ import annotations

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.components.filters import apply_filters, render_filters
from bug_resolution_radar.ui.components.issues import render_issue_cards, render_issue_table
from bug_resolution_radar.ui.dashboard.downloads import make_table_export_df, render_download_bar
from bug_resolution_radar.ui.dashboard.state import get_filter_state


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
    df_all: pd.DataFrame | None = None,
    key_prefix: str = "issues_tab",
) -> None:
    """
    Issues tab:
    - Mismos filtros que en Tendencias (widgets reutilizados)
    - Sin matriz (ahora está en Resumen)
    - Renderiza Cards/Tabla sobre el dataframe filtrado por esos filtros

    IMPORTANT:
    - Para no “encoger” opciones de filtros, renderiza widgets sobre df_all (dataset completo).
      Si no se proporciona df_all, cae a dff (compatibilidad con llamadas antiguas).
    - render_filters usa key_prefix namespaced y sincroniza a keys canónicas:
        filter_status / filter_priority / filter_assignee
      para que get_filter_state() funcione y otros módulos (matriz/kanban) puedan escribir ahí.
    """
    st.markdown("## 🧾 Issues")

    base_df = (
        df_all
        if isinstance(df_all, pd.DataFrame)
        else (dff if isinstance(dff, pd.DataFrame) else pd.DataFrame())
    )
    if base_df.empty:
        st.info("No hay datos para mostrar.")
        return

    # 1) Filtros (mismo componente que Tendencias), con keys namespaced para evitar duplicados
    render_filters(base_df, key_prefix="issues")

    st.markdown("---")

    # 2) Aplicar filtros actuales (estado global canónico en session_state)
    fs = get_filter_state()
    dff_filtered = apply_filters(base_df, fs)

    # 3) Render sección (export + cards/tabla)
    render_issues_section(dff_filtered, title="Issues (filtradas)", key_prefix=key_prefix)