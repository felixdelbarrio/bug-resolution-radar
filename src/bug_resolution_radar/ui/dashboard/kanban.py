from __future__ import annotations

import html
from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import normalize_text_col, priority_rank


def _kanban_set_status_filter(st_name: str) -> None:
    # sincroniza con filtros/matriz: status = [st_name]
    st.session_state["filter_status"] = [st_name]


# Orden canónico (el mismo que “Issues” / matriz)
_CANONICAL_STATUS_ORDER: List[str] = [
    "New",
    "Analysing",
    "Blocked",
    "En progreso",
    "To Rework",
    "Test",
    "Ready To Verify",
    "Accepted",
    "Ready to Deploy",
]


def _order_statuses_canonical(statuses: List[str]) -> List[str]:
    """Ordena según el orden canónico. Los no contemplados van al final manteniendo su orden de entrada."""
    idx = {s.lower(): i for i, s in enumerate(_CANONICAL_STATUS_ORDER)}

    # estable: para los no contemplados respetamos orden original
    def key_fn(pair):
        i, s = pair
        return (idx.get((s or "").strip().lower(), 10_000), i)

    return [s for _, s in sorted(list(enumerate(statuses)), key=key_fn)]


def render_kanban_tab(*, open_df: pd.DataFrame) -> None:
    """
    Kanban siempre desplegado.
    - Columnas = estados (sincronizados con filter_status si hay selección)
    - Header clickable: alinea completamente el filtro de estado
    - SIN slider: siempre muestra todas las issues de cada columna
    - Maquetado dentro de un contenedor
    - Orden de columnas: SIEMPRE el canónico (el mismo que en Issues)
    """
    with st.container(border=True):
        st.markdown("### Kanban (abiertas por Estado)")

        if open_df is None or open_df.empty:
            st.info("No hay incidencias abiertas para mostrar.")
            return

        kan = open_df.copy()
        kan["status"] = normalize_text_col(kan["status"], "(sin estado)")

        status_counts = kan["status"].value_counts()
        all_statuses: List[str] = status_counts.index.tolist()

        # si hay filtro de estado activo => mostrar esos estados
        selected_statuses = list(st.session_state.get("filter_status") or [])
        selected_statuses = [s for s in selected_statuses if s in all_statuses]

        if selected_statuses:
            # respetar orden canónico (NO alfabético)
            selected_statuses = _order_statuses_canonical(selected_statuses)
        else:
            # sin filtro => top 6 por volumen (máx 8) + orden canónico
            selected_statuses = all_statuses[:6]
            selected_statuses = _order_statuses_canonical(selected_statuses)

        selected_statuses = selected_statuses[:8]

        if not selected_statuses:
            st.info("No hay estados disponibles para mostrar.")
            return

        cols = st.columns(len(selected_statuses))

        for col, st_name in zip(cols, selected_statuses):
            sub = kan[kan["status"] == st_name].copy()

            # Orden: prioridad (rank) y luego updated desc si existe
            sub["_prio_rank"] = sub["priority"].astype(str).map(priority_rank) if "priority" in sub.columns else 99
            sort_cols = ["_prio_rank"]
            sort_asc = [True]
            if "updated" in sub.columns:
                sort_cols.append("updated")
                sort_asc.append(False)
            sub = sub.sort_values(by=sort_cols, ascending=sort_asc)

            with col:
                # Header clickable -> fija el filtro de estado
                st.button(
                    f"{st_name}",
                    key=f"kanban_hdr::{st_name}",
                    use_container_width=True,
                    on_click=_kanban_set_status_filter,
                    args=(st_name,),
                )
                st.caption(f"{len(sub)} issues")

                for _, r in sub.iterrows():
                    key = html.escape(str(r.get("key", "") or ""))
                    url = html.escape(str(r.get("url", "") or ""))
                    summ = html.escape(str(r.get("summary", "") or ""))
                    if len(summ) > 80:
                        summ = summ[:77] + "..."

                    st.markdown(
                        f'<div style="margin: 8px 0 10px 0;">'
                        f'<div><a href="{url}" target="_blank" rel="noopener noreferrer">{key}</a></div>'
                        f'<div style="opacity:0.85; font-size:0.85rem; line-height:1.1rem;">{summ}</div>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )