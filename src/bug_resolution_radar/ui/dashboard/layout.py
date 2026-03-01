"""Shared layout helpers for dashboard sections."""

from __future__ import annotations

from pathlib import Path

import streamlit as st


def _page_favicon() -> str:
    icon_path = (
        Path(__file__).resolve().parents[1]
        / "assets"
        / "icons"
        / "bbva"
        / "spherica-behavioural-economics.svg"
    )
    return str(icon_path) if icon_path.exists() else "📡"


def apply_dashboard_layout(*, title: str = "Cuadro de mando de incidencias") -> None:
    """
    Configura el layout global del dashboard (page config + estilos).
    Debe llamarse una sola vez al inicio del render de la página.
    """
    try:
        st.set_page_config(
            page_title=title,
            page_icon=_page_favicon(),
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except Exception:
        pass

    st.markdown(
        """
        <style>
          /* Contenedor general: respiración vertical */
          .block-container { padding-top: 1.25rem; padding-bottom: 2.5rem; }

          /* Títulos más compactos */
          h1, h2, h3 { letter-spacing: -0.02em; }

          /* Cards/containers: look limpio */
          .br-card {
            background: var(--bbva-surface-soft);
            border: 1px solid var(--bbva-border);
            border-radius: 14px;
            padding: 18px 18px;
            box-shadow: 0 6px 18px color-mix(in srgb, var(--bbva-text) 7%, transparent);
          }

          .br-card + .br-card { margin-top: 14px; }

          /* Ajustes suaves de captions */
          .stCaption { opacity: 0.82; }

          /* Botones: un pelín más redondos */
          button[kind="secondary"], button[kind="primary"] { border-radius: 12px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def card_open() -> None:
    """Abre un contenedor tipo 'card'."""
    st.markdown('<div class="br-card">', unsafe_allow_html=True)


def card_close() -> None:
    """Cierra un contenedor tipo 'card'."""
    st.markdown("</div>", unsafe_allow_html=True)
