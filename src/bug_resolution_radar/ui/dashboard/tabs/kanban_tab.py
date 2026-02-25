"""Kanban rendering utilities and grouped issue presentation."""

from __future__ import annotations

import html
import re
from typing import List

import pandas as pd
import streamlit as st

from bug_resolution_radar.ui.common import (
    chip_style_from_color,
    normalize_text_col,
    priority_color,
    priority_rank,
    status_color,
)
from bug_resolution_radar.ui.dashboard.constants import canonical_status_rank_map
from bug_resolution_radar.ui.dashboard.exports.downloads import render_minimal_export_actions
from bug_resolution_radar.ui.dashboard.state import FILTER_STATUS_KEY

MAX_KANBAN_ITEMS_PER_COLUMN = 220
MAX_KANBAN_TOTAL_ITEMS = 1200


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
        return f"rgba(127,146,178,{alpha:.3f})"
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
          .kan-items { display: grid; gap: 10px; }
          .kan-item {
            margin: 2px 0;
            border: 1px solid var(--bbva-border);
            border-radius: 12px;
            background: var(--bbva-surface-soft);
            padding: 0.50rem 0.58rem;
            max-width: 100%;
            overflow: hidden;
          }
          .kan-item:hover {
            border-color: var(--bbva-border-strong);
            box-shadow: 0 2px 10px color-mix(in srgb, var(--bbva-text) 10%, transparent);
          }
          .kan-item-key a {
            display: block;
            font-weight: 800;
            text-decoration: none;
            max-width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .kan-item-meta {
            display: flex;
            gap: 0.30rem;
            flex-wrap: wrap;
            margin-top: 0.34rem;
            min-width: 0;
          }
          .kan-chip {
            display: inline-flex;
            align-items: center;
            max-width: 100%;
            min-width: 0;
          }
          .kan-chip-text {
            display: block;
            min-width: 0;
            max-width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          .kan-chip-assignee {
            flex: 1 1 10rem;
            min-width: 0;
            max-width: 100%;
          }
          .kan-item-summary {
            margin-top: 0.30rem;
            color: color-mix(in srgb, var(--bbva-text) 90%, transparent);
            font-size: 0.90rem;
            line-height: 1.26rem;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
            word-break: break-word;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _neutral_chip_style() -> str:
    return (
        "color:var(--bbva-text-muted); border:1px solid var(--bbva-border-strong); "
        "background:color-mix(in srgb, var(--bbva-surface) 86%, var(--bbva-surface-2)); "
        "border-radius:999px; padding:2px 10px; font-weight:700; font-size:0.78rem;"
    )


def _chip_html(label: str, style: str) -> str:
    return '<span class="kan-chip" style="{}"><span class="kan-chip-text">{}</span></span>'.format(
        style, html.escape(label)
    )


def _assignee_chip_html(label: str) -> str:
    return '<span class="kan-chip kan-chip-assignee" style="{}"><span class="kan-chip-text">{}</span></span>'.format(
        _neutral_chip_style(),
        html.escape(label),
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
    with st.container(border=True, key="kanban_shell"):
        if open_df is None or open_df.empty:
            st.info("No hay incidencias abiertas para mostrar.")
            return
        if "status" not in open_df.columns:
            st.info("No hay columna 'status' para construir el tablero Kanban.")
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
        now = pd.Timestamp.utcnow().tz_localize(None)
        if "created" in kan.columns:
            created_naive = pd.to_datetime(
                kan["created"], errors="coerce", utc=True
            ).dt.tz_localize(None)
            kan["age_days"] = ((now - created_naive).dt.total_seconds() / 86400.0).clip(lower=0.0)
        else:
            kan["age_days"] = pd.NA

        max_items_per_col = max(
            60,
            min(
                MAX_KANBAN_ITEMS_PER_COLUMN,
                MAX_KANBAN_TOTAL_ITEMS // max(len(selected_statuses), 1),
            ),
        )

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
            total_in_col = len(sub)
            if total_in_col > max_items_per_col:
                sub = sub.head(max_items_per_col).copy(deep=False)

            with col:
                # Header clickable -> fija el filtro de estado
                with st.container(key=f"kanban_chip_{slug}"):
                    st.button(
                        f"{st_name}",
                        key=f"kanban_hdr__{slug}",
                        width="stretch",
                        on_click=_kanban_set_status_filter,
                        args=(st_name,),
                    )
                if total_in_col > max_items_per_col:
                    st.caption(f"{len(sub)}/{total_in_col} issues (cap de rendimiento por columna)")
                else:
                    st.caption(f"{total_in_col} issues")
                cards_html: List[str] = []
                for r in sub.itertuples(index=False):
                    key = html.escape(str(getattr(r, "key", "") or ""))
                    url = html.escape(str(getattr(r, "url", "") or ""))
                    summ = html.escape(str(getattr(r, "summary", "") or ""))
                    if len(summ) > 120:
                        summ = summ[:117] + "..."
                    status = str(getattr(r, "status", "") or "").strip() or "(sin estado)"
                    prio = str(getattr(r, "priority", "") or "").strip() or "(sin priority)"
                    assignee = str(getattr(r, "assignee", "") or "").strip()
                    age_raw = getattr(r, "age_days", pd.NA)
                    age_days = float(age_raw) if pd.notna(age_raw) else None

                    key_html = (
                        f'<a href="{url}" target="_blank" rel="noopener noreferrer">{key}</a>'
                        if url
                        else key
                    )
                    chips: List[str] = [
                        _chip_html(status, chip_style_from_color(status_color(status))),
                        _chip_html(prio, chip_style_from_color(priority_color(prio))),
                    ]
                    if assignee:
                        chips.append(_assignee_chip_html(assignee))
                    if age_days is not None:
                        chips.append(_chip_html(f"{age_days:.0f}d", _neutral_chip_style()))

                    cards_html.append(
                        '<article class="kan-item">'
                        f'<div class="kan-item-key">{key_html}</div>'
                        f'<div class="kan-item-meta">{"".join(chips)}</div>'
                        f'<div class="kan-item-summary">{summ}</div>'
                        "</article>"
                    )

                if cards_html:
                    st.markdown(
                        f'<div class="kan-items">{"".join(cards_html)}</div>',
                        unsafe_allow_html=True,
                    )
