"""Slide-style chart navigation helpers for trends-like pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Sequence

import streamlit as st


@dataclass(frozen=True)
class SlideSpec:
    chart_id: str
    title: str
    subtitle: str = ""


SlideRenderer = Callable[[str], None]


def inject_slides_css() -> None:
    """Inject compact card-like CSS used by slide navigation UI."""
    css = """
    <style>
      /* Container that feels like a "slide" */
      .bbva-slide {
        border: 1px solid var(--bbva-border);
        background: var(--bbva-surface-elevated);
        border-radius: 18px;
        padding: 18px 18px 14px 18px;
        box-shadow: 0 10px 28px color-mix(in srgb, var(--bbva-text) 10%, transparent);
      }

      /* Header: title + subtitle */
      .bbva-slide h2 {
        margin: 0;
        padding: 0;
        font-size: 1.25rem;
        font-weight: 750;
        letter-spacing: -0.01em;
      }
      .bbva-slide .subtitle {
        margin-top: 4px;
        opacity: 0.75;
        font-size: 0.92rem;
        line-height: 1.2rem;
      }

      /* Divider line inside the slide */
      .bbva-slide .divider {
        height: 1px;
        margin: 12px 0 14px 0;
        background: linear-gradient(90deg, transparent, var(--bbva-border-strong), transparent);
      }

      /* The plotly chart container spacing */
      .bbva-slide .chart-wrap {
        margin-top: 6px;
      }

      /* Compact toolbar */
      .bbva-slide-toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin: 10px 0 12px 0;
      }
      .bbva-slide-toolbar .meta {
        opacity: 0.75;
        font-size: 0.9rem;
        white-space: nowrap;
      }

      /* Make expander look more "cardy" */
      .bbva-insights .streamlit-expanderHeader {
        font-weight: 650;
      }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def _get_slide_index(key: str, *, default: int = 0) -> int:
    v = st.session_state.get(key, default)
    try:
        v = int(v)
    except Exception:
        v = default
    return v


def _set_slide_index(key: str, idx: int) -> None:
    st.session_state[key] = int(idx)


def _clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def render_slides(
    *,
    slide_specs: Sequence[SlideSpec],
    selected_ids: Sequence[str],
    renderer: SlideRenderer,
    state_key: str = "trend_slide_idx",
    show_selector: bool = True,
) -> None:
    """Render a one-chart-per-screen deck with prev/next controls and optional jump selector."""
    inject_slides_css()

    specs_by_id: Dict[str, SlideSpec] = {s.chart_id: s for s in slide_specs}
    deck: List[SlideSpec] = [specs_by_id[cid] for cid in selected_ids if cid in specs_by_id]

    if not deck:
        st.info("Selecciona al menos un gráfico para mostrar en Tendencias.")
        return

    idx = _get_slide_index(state_key, default=0)
    idx = _clamp(idx, 0, len(deck) - 1)
    _set_slide_index(state_key, idx)

    left, mid, right = st.columns([2, 6, 2], vertical_alignment="center")

    with left:
        c_prev, c_next = st.columns(2)
        with c_prev:
            if st.button("◀︎", key=f"{state_key}__prev", width="stretch", disabled=(idx == 0)):
                _set_slide_index(state_key, idx - 1)
                st.rerun()
        with c_next:
            if st.button(
                "▶︎",
                key=f"{state_key}__next",
                width="stretch",
                disabled=(idx >= len(deck) - 1),
            ):
                _set_slide_index(state_key, idx + 1)
                st.rerun()

    with mid:
        st.markdown(
            f'<div class="bbva-slide-toolbar"><div class="meta">Gráfico {idx+1} / {len(deck)}</div></div>',
            unsafe_allow_html=True,
        )

        if show_selector and len(deck) > 1:
            labels = [s.title for s in deck]
            # Keep selectbox in sync with slide index
            sel = st.selectbox(
                "Ir a…",
                options=list(range(len(deck))),
                index=idx,
                format_func=lambda i: labels[i],
                label_visibility="collapsed",
                key=f"{state_key}__jump",
            )
            if int(sel) != idx:
                _set_slide_index(state_key, int(sel))
                st.rerun()

    with right:
        st.caption("Tip: usa ◀︎ ▶︎ para navegar")

    spec = deck[idx]
    with st.container():
        st.markdown('<div class="bbva-slide">', unsafe_allow_html=True)

        st.markdown(f"<h2>{spec.title}</h2>", unsafe_allow_html=True)
        if spec.subtitle:
            st.markdown(f'<div class="subtitle">{spec.subtitle}</div>', unsafe_allow_html=True)

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        renderer(spec.chart_id)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


def build_default_slide_specs() -> List[SlideSpec]:
    """
    Centralized titles/subtitles for the trend deck.
    Keep this in sync with your registry chart ids.
    """
    return [
        SlideSpec(
            "timeseries",
            "Evolución del backlog (últimos 90 días)",
            "Entrada vs salida diaria y tendencia de carga.",
        ),
        SlideSpec(
            "age_buckets",
            "Antigüedad de abiertas",
            "Dónde se está quedando el trabajo (cola larga y riesgo).",
        ),
        SlideSpec(
            "resolution_hist",
            "Tiempos de resolución",
            "Distribución de lead time (cerradas) y fricción del flujo.",
        ),
        SlideSpec(
            "open_priority_pie",
            "Backlog por prioridad",
            "Señal de concentración: dónde se está acumulando el riesgo.",
        ),
        SlideSpec(
            "open_status_bar", "Backlog por estado", "Cuellos de botella por fase del proceso."
        ),
    ]
