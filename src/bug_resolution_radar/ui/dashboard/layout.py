from __future__ import annotations

import streamlit as st


def apply_dashboard_layout(*, title: str = "Bug Resolution Radar") -> None:
    """
    Configura el layout global del dashboard (page config + estilos).
    Debe llamarse una sola vez al inicio del render de la página.
    """
    # Page config (solo 1 vez por app; Streamlit lo ignora si se repite)
    try:
        st.set_page_config(
            page_title=title,
            page_icon="📡",
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except Exception:
        # En algunos contextos (tests / reruns raros) puede fallar; no rompemos la app.
        pass

    # CSS “premium” y consistente con el look actual (sin tocar tus variables BBVA)
    st.markdown(
        """
        <style>
          /* Contenedor general: respiración vertical */
          .block-container { padding-top: 1.25rem; padding-bottom: 2.5rem; }

          /* Títulos más compactos */
          h1, h2, h3 { letter-spacing: -0.02em; }

          /* Cards/containers: look limpio */
          .br-card {
            background: rgba(255,255,255,0.6);
            border: 1px solid rgba(0,0,0,0.06);
            border-radius: 14px;
            padding: 18px 18px;
            box-shadow: 0 8px 28px rgba(0,0,0,0.05);
            backdrop-filter: blur(6px);
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