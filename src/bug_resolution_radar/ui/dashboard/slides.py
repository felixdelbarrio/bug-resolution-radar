# bug_resolution_radar/ui/dashboard/slides.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import streamlit as st


# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class SlideSpec:
    chart_id: str
    title: str
    subtitle: str = ""


# Renderer signature:
# - Must render the chart AND its insights (or return them for a second pass).
# - We keep it flexible: pass chart_id and let renderer decide.
SlideRenderer = Callable[[str], None]


# ---------------------------------------------------------------------
# CSS (premium "one chart per screen" feel)
# ---------------------------------------------------------------------
def inject_slides_css() -> None:
    css = """
    <style>
      /* Container that feels like a "slide" */
      .bbva-slide {
        border: 1px solid rgba(49, 60, 68, 0.15);
        background: rgba(255,255,255,0.85);
        border-radius: 18px;
        padding: 18px 18px 14px 18px;
        box-shadow: 0 10px 28px rgba(0,0,0,0.06);
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
        background: linear-gradient(90deg, rgba(49,60,68,0.00), rgba(49,60,68,0.18), rgba(49,60,68,0.00));
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


# ---------------------------------------------------------------------
# State helpers (local to slides)
# ---------------------------------------------------------------------
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


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def render_slides(
    *,
    slide_specs: Sequence[SlideSpec],
    selected_ids: Sequence[str],
    renderer: SlideRenderer,
    state_key: str = "trend_slide_idx",
    show_selector: bool = True,
) -> None:
    """
    "One chart per screen" slide deck.

    Parameters
    ----------
    slide_specs:
        Ordered list of all available slides (id + display metadata).
    selected_ids:
        Subset of slide_specs.chart_id that should be included in the deck (in that order).
        Usually this comes from your settings (TREND_SELECTED_CHARTS) or UI selection.
    renderer:
        Function that takes chart_id and renders: title is handled here; renderer draws plot + insights.
    state_key:
        session_state key that stores current slide index.
    show_selector:
        If True, shows a selectbox to jump to a chart.
    """
    inject_slides_css()

    # Build deck in display order, filtered by selection
    specs_by_id: Dict[str, SlideSpec] = {s.chart_id: s for s in slide_specs}
    deck: List[SlideSpec] = [specs_by_id[cid] for cid in selected_ids if cid in specs_by_id]

    if not deck:
        st.info("Selecciona al menos un gráfico para mostrar en Tendencias.")
        return

    idx = _get_slide_index(state_key, default=0)
    idx = _clamp(idx, 0, len(deck) - 1)
    _set_slide_index(state_key, idx)

    # --- Toolbar (prev/next + jump) ---
    left, mid, right = st.columns([2, 6, 2], vertical_alignment="center")

    with left:
        c_prev, c_next = st.columns(2)
        with c_prev:
            if st.button("◀︎", key=f"{state_key}__prev", use_container_width=True, disabled=(idx == 0)):
                _set_slide_index(state_key, idx - 1)
                st.rerun()
        with c_next:
            if st.button("▶︎", key=f"{state_key}__next", use_container_width=True, disabled=(idx >= len(deck) - 1)):
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
        # Optional: fullscreen hint / micro-help
        st.caption("Tip: usa ◀︎ ▶︎ para navegar")

    # --- Slide container ---
    spec = deck[idx]
    with st.container():
        st.markdown('<div class="bbva-slide">', unsafe_allow_html=True)

        st.markdown(f"<h2>{spec.title}</h2>", unsafe_allow_html=True)
        if spec.subtitle:
            st.markdown(f'<div class="subtitle">{spec.subtitle}</div>', unsafe_allow_html=True)

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

        # Render the chart + insights
        st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
        renderer(spec.chart_id)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------
# Convenience builders
# ---------------------------------------------------------------------
def build_default_slide_specs() -> List[SlideSpec]:
    """
    Centralized titles/subtitles for the trend deck.
    Keep this in sync with your registry chart ids.
    """
    return [
        SlideSpec("timeseries", "Evolución del backlog (últimos 90 días)", "Entrada vs salida diaria y tendencia de carga."),
        SlideSpec("age_buckets", "Antigüedad de abiertas", "Dónde se está quedando el trabajo (cola larga y riesgo)."),
        SlideSpec("resolution_hist", "Tiempos de resolución", "Distribución de lead time (cerradas) y fricción del flujo."),
        SlideSpec("open_priority_pie", "Backlog por prioridad", "Señal de concentración: dónde se está acumulando el riesgo."),
        SlideSpec("open_status_bar", "Backlog por estado", "Cuellos de botella por fase del proceso."),
    ]