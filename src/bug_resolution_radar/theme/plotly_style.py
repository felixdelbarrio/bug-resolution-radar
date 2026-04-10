"""Pure Plotly styling helpers shared by backend and UI."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from bug_resolution_radar.theme.design_tokens import (
    BBVA_DARK,
    BBVA_FONT_SANS,
    BBVA_LIGHT,
    hex_to_rgba,
)
from bug_resolution_radar.theme.semantic_colors import flow_signal_color_map


@lru_cache(maxsize=2)
def plotly_template_without_scattermapbox(*, dark_mode: bool) -> Any:
    """
    Return a Plotly base template with deprecated `scattermapbox` defaults removed.
    """
    template_name = "plotly_dark" if dark_mode else "plotly_white"
    try:
        import plotly.io as pio

        template_payload: dict[str, Any] = dict(pio.templates[template_name].to_plotly_json())
    except Exception:
        return template_name

    data_payload = template_payload.get("data")
    if not isinstance(data_payload, dict):
        return template_payload

    if "scattermapbox" not in data_payload:
        return template_payload

    cleaned_data = dict(data_payload)
    cleaned_data.pop("scattermapbox", None)
    template_payload["data"] = cleaned_data
    return template_payload


def apply_plotly_bbva(fig: Any, *, showlegend: bool = False, dark_mode: bool = False) -> Any:
    """Apply a consistent Plotly style aligned with app design tokens."""
    palette = BBVA_DARK if dark_mode else BBVA_LIGHT
    text_color = palette.ink
    grid_color = hex_to_rgba(
        palette.ink,
        0.14 if dark_mode else 0.10,
        fallback=BBVA_LIGHT.ink,
    )
    legend_bg = hex_to_rgba(
        palette.midnight if dark_mode else palette.white,
        0.72 if dark_mode else 0.65,
        fallback=BBVA_LIGHT.midnight,
    )
    legend_border = hex_to_rgba(
        palette.ink,
        0.20 if dark_mode else 0.12,
        fallback=BBVA_LIGHT.ink,
    )
    transparent_bg = hex_to_rgba(palette.ink, 0.0, fallback=BBVA_LIGHT.ink)
    legend_bottom_space = 92 if showlegend else 16
    undefined_tokens = {"undefined", "none", "nan", "null"}
    es_label_map = {
        "count": "Incidencias",
        "value": "Valor",
        "date": "Fecha",
        "status": "Estado",
        "priority": "Prioridad",
        "bucket": "Rango",
        "created": "Creadas",
        "closed": "Cerradas",
        "open_backlog_proxy": "Backlog abierto",
        "resolution_days": "Días de resolución",
    }

    def _clean_txt(value: object) -> str:
        txt = str(value or "").strip()
        return "" if txt.lower() in undefined_tokens else txt

    def _localize(text: object) -> str:
        clean = _clean_txt(text)
        if not clean:
            return ""
        return es_label_map.get(clean.strip().lower(), clean)

    fig.update_layout(
        template=plotly_template_without_scattermapbox(dark_mode=dark_mode),
        paper_bgcolor=transparent_bg,
        plot_bgcolor=transparent_bg,
        font=dict(family=BBVA_FONT_SANS, color=text_color),
        colorway=[
            palette.electric_blue,
            palette.core_blue,
            palette.royal_blue,
            palette.serene_dark_blue,
            palette.serene_blue,
            palette.aqua,
            palette.midnight,
        ],
        showlegend=showlegend,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.22,
            xanchor="right",
            x=1.0,
            bgcolor=legend_bg,
            bordercolor=legend_border,
            borderwidth=1,
            font=dict(size=11, color=text_color),
            title=dict(font=dict(color=text_color), text=""),
        ),
        hoverlabel=dict(
            bgcolor=legend_bg,
            bordercolor=legend_border,
            font=dict(color=text_color),
        ),
        margin=dict(l=16, r=16, t=48, b=legend_bottom_space),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=grid_color,
        zeroline=False,
        tickfont=dict(color=text_color),
        title_font=dict(color=text_color),
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=grid_color,
        zeroline=False,
        tickfont=dict(color=text_color),
        title_font=dict(color=text_color),
    )

    for series_name, color in flow_signal_color_map().items():
        fig.update_traces(
            line=dict(color=color),
            marker=dict(color=color),
            selector={"name": series_name},
        )

    try:
        title_obj = getattr(fig.layout, "title", None)
        title_text = _localize(getattr(title_obj, "text", ""))
        fig.update_layout(title_text=title_text)
    except Exception:
        pass

    try:
        x_axis = getattr(fig.layout, "xaxis", None)
        y_axis = getattr(fig.layout, "yaxis", None)
        x_title = _localize(getattr(getattr(x_axis, "title", None), "text", ""))
        y_title = _localize(getattr(getattr(y_axis, "title", None), "text", ""))
        fig.update_xaxes(title_text=x_title)
        fig.update_yaxes(title_text=y_title)
    except Exception:
        pass

    try:
        for annotation in list(getattr(fig.layout, "annotations", []) or []):
            annotation.text = _localize(getattr(annotation, "text", ""))
            annotation.font = dict(color=text_color)
    except Exception:
        pass

    for trace in getattr(fig, "data", []):
        try:
            trace.name = _localize(getattr(trace, "name", ""))
            trace_type = str(getattr(trace, "type", "") or "").strip().lower()
            if trace_type == "pie":
                trace.showlegend = bool(showlegend)
            else:
                trace.showlegend = bool(showlegend and trace.name)
            if hasattr(trace, "textfont"):
                trace.textfont = dict(color=text_color)
            if hasattr(trace, "legendgrouptitle"):
                trace.legendgrouptitle = dict(font=dict(color=text_color))
        except Exception:
            pass

        try:
            hovertemplate = getattr(trace, "hovertemplate", None)
            if isinstance(hovertemplate, str):
                cleaned = hovertemplate
                cleaned = cleaned.replace("%{fullData.name}", "")
                cleaned = cleaned.replace("undefined", "")
                cleaned = cleaned.replace("Undefined", "")
                trace.hovertemplate = cleaned
        except Exception:
            pass
    return fig
