from __future__ import annotations

import html
import re
from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import normalize_text_col, priority_rank, status_color
from bug_resolution_radar.ui.dashboard.constants import canonical_status_rank_map
from bug_resolution_radar.ui.dashboard.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.dashboard.state import FILTER_STATUS_KEY


def _kanban_set_status_filter(st_name: str) -> None:
    # sincroniza con filtros/matriz: status = [st_name]
    st.session_state[FILTER_STATUS_KEY] = [st_name]


def _order_statuses_canonical(statuses: List[str]) -> List[str]:
    """Ordena según el orden canónico. Los no contemplados van al final manteniendo su orden de entrada."""
    idx = canonical_status_rank_map()

    # estable: para los no contemplados respetamos orden original
    def key_fn(pair: tuple[int, str]) -> tuple[int, int]:
        i, s = pair
        return (idx.get((s or "").strip().lower(), 10_000), i)

    return [s for _, s in sorted(list(enumerate(statuses)), key=key_fn)]


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) != 6:
        return f"rgba(17,25,45,{alpha:.3f})"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3f})"


def _status_slug(status: str, i: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", (status or "").strip().lower()).strip("_")
    return f"{base or 'status'}_{i}"


def _inject_kanban_header_chip_css(headers: List[tuple[str, str, bool]]) -> None:
    rules: List[str] = []
    for status_name, slug, is_active in headers:
        color = status_color(status_name)
        bg = _hex_to_rgba(color, 0.20 if is_active else 0.12)
        border = _hex_to_rgba(color, 0.72 if is_active else 0.45)
        hover_bg = _hex_to_rgba(color, 0.16 if is_active else 0.14)
        ring = _hex_to_rgba(color, 0.20)

        rules.append(
            f"""
            .st-key-kanban_chip_{slug} div[data-testid="stButton"] > button {{
              background: {bg} !important;
              border: 1px solid {border} !important;
              color: {color} !important;
              border-radius: 999px !important;
              font-weight: 800 !important;
              min-height: 2.60rem !important;
            }}
            .st-key-kanban_chip_{slug} div[data-testid="stButton"] > button:hover {{
              background: {hover_bg} !important;
              border-color: {border} !important;
            }}
            .st-key-kanban_chip_{slug} div[data-testid="stButton"] > button:focus-visible {{
              outline: none !important;
              box-shadow: 0 0 0 3px {ring} !important;
            }}
            """
        )

    if rules:
        st.markdown(f"<style>{''.join(rules)}</style>", unsafe_allow_html=True)


def _inject_kanban_item_css() -> None:
    st.markdown(
        """
        <style>
          .kan-items { display: grid; gap: 8px; }
          .kan-item { margin: 2px 0; }
          .kan-item-key a { font-weight: 700; text-decoration: none; }
          .kan-item-summary {
            opacity: 0.85;
            font-size: 0.85rem;
            line-height: 1.1rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
        if open_df is None or open_df.empty:
            st.info("No hay incidencias abiertas para mostrar.")
            return

        kan = open_df.copy(deep=False)
        export_cols = [
            "key",
            "summary",
            "status",
            "priority",
            "assignee",
            "created",
            "updated",
            "url",
        ]
        export_df = kan[[c for c in export_cols if c in kan.columns]].copy(deep=False)
        render_minimal_export_actions(
            key_prefix="kanban::open",
            filename_prefix="kanban",
            suffix="abiertas",
            csv_df=export_df,
        )
        kan["status"] = normalize_text_col(kan["status"], "(sin estado)")

        status_counts = kan["status"].value_counts()
        all_statuses: List[str] = status_counts.index.tolist()

        # si hay filtro de estado activo => mostrar esos estados
        selected_statuses = list(st.session_state.get(FILTER_STATUS_KEY) or [])
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

        active_filter = {str(s) for s in (st.session_state.get(FILTER_STATUS_KEY) or [])}
        header_meta: List[tuple[str, str, bool]] = []
        for i, st_name in enumerate(selected_statuses):
            slug = _status_slug(st_name, i)
            header_meta.append((st_name, slug, st_name in active_filter))
        _inject_kanban_header_chip_css(header_meta)
        _inject_kanban_item_css()

        cols = st.columns(len(selected_statuses))

        for i, (col, st_name) in enumerate(zip(cols, selected_statuses)):
            sub = kan[kan["status"] == st_name].copy(deep=False)
            slug = _status_slug(st_name, i)

            # Orden: prioridad (rank) y luego updated desc si existe
            sub["_prio_rank"] = (
                sub["priority"].astype(str).map(priority_rank) if "priority" in sub.columns else 99
            )
            sort_cols = ["_prio_rank"]
            sort_asc = [True]
            if "updated" in sub.columns:
                sort_cols.append("updated")
                sort_asc.append(False)
            sub = sub.sort_values(by=sort_cols, ascending=sort_asc)

            with col:
                # Header clickable -> fija el filtro de estado
                with st.container(key=f"kanban_chip_{slug}"):
                    st.button(
                        f"{st_name}",
                        key=f"kanban_hdr__{slug}",
                        use_container_width=True,
                        on_click=_kanban_set_status_filter,
                        args=(st_name,),
                    )
                st.caption(f"{len(sub)} issues")
                cards_html: List[str] = []
                for _, r in sub.iterrows():
                    key = html.escape(str(r.get("key", "") or ""))
                    url = html.escape(str(r.get("url", "") or ""))
                    summ = html.escape(str(r.get("summary", "") or ""))
                    if len(summ) > 80:
                        summ = summ[:77] + "..."

                    key_html = (
                        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{key}</a>'
                        if url
                        else key
                    )
                    cards_html.append(
                        '<article class="kan-item">'
                        f'<div class="kan-item-key">{key_html}</div>'
                        f'<div class="kan-item-summary">{summ}</div>'
                        "</article>"
                    )

                if cards_html:
                    st.markdown(
                        f'<div class="kan-items">{"".join(cards_html)}</div>',
                        unsafe_allow_html=True,
                    )
