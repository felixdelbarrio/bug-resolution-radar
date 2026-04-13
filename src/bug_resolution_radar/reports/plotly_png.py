"""Browser-free Plotly-to-PNG renderer for report charts."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Sequence, cast

import pandas as pd
import plotly.graph_objects as go
from PIL import Image, ImageColor, ImageDraw, ImageFont

from bug_resolution_radar.theme.design_tokens import BBVA_LIGHT, BBVA_REPORT_LINE, BBVA_REPORT_MIST

_REPORT_FONT_DIR = (
    Path(__file__).resolve().parent.parent / "ui" / "assets" / "fonts" / "bbva"
).resolve()
_REPORT_FONT_BOOK_PATH = _REPORT_FONT_DIR / "BentonSansBBVA-Book.ttf"
_REPORT_FONT_BOLD_PATH = _REPORT_FONT_DIR / "BentonSansBBVA-Bold.ttf"


@dataclass(frozen=True)
class _LegendItem:
    label: str
    color: tuple[int, int, int, int]


@dataclass(frozen=True)
class _AxisSpec:
    kind: str
    ticks: list[tuple[float, str]]
    minimum: float
    maximum: float
    categories: list[str]


def _load_font(size_px: int, *, bold: bool = False) -> Any:
    path = _REPORT_FONT_BOLD_PATH if bold else _REPORT_FONT_BOOK_PATH
    try:
        return ImageFont.truetype(str(path), size=max(8, int(size_px)))
    except Exception:
        try:
            fallback = _REPORT_FONT_BOOK_PATH if path != _REPORT_FONT_BOOK_PATH else path
            return ImageFont.truetype(str(fallback), size=max(8, int(size_px)))
        except Exception:
            return ImageFont.load_default()


def _parse_color(value: object, *, default: str = "#004481") -> tuple[int, int, int, int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        rgb = [int(max(0, min(255, int(float(ch))))) for ch in list(value)[:4]]
        if len(rgb) == 3:
            rgb.append(255)
        return tuple(rgb[:4])  # type: ignore[return-value]

    txt = str(value or "").strip()
    if not txt:
        txt = default

    if txt.lower().startswith("rgba(") and txt.endswith(")"):
        try:
            parts = [part.strip() for part in txt[5:-1].split(",")]
            red = int(float(parts[0]))
            green = int(float(parts[1]))
            blue = int(float(parts[2]))
            alpha = int(round(float(parts[3]) * 255.0)) if len(parts) > 3 else 255
            return (red, green, blue, max(0, min(255, alpha)))
        except Exception:
            txt = default
    if txt.lower().startswith("rgb(") and txt.endswith(")"):
        try:
            parts = [part.strip() for part in txt[4:-1].split(",")]
            return (int(float(parts[0])), int(float(parts[1])), int(float(parts[2])), 255)
        except Exception:
            txt = default

    try:
        return _parse_color(ImageColor.getrgb(txt), default=default)
    except Exception:
        return _parse_color(ImageColor.getrgb(default), default=default)


def _trace_values(trace: object, attr: str) -> list[object]:
    raw = getattr(trace, attr, None)
    if raw is None:
        return []
    try:
        return list(raw)
    except Exception:
        return [raw]


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        out = float(value)
        return None if pd.isna(out) else out
    txt = str(value).strip()
    if not txt:
        return None
    try:
        out = float(txt)
    except Exception:
        return None
    return None if pd.isna(out) else out


def _to_datetime_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=True)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return float(ts.value)


def _stringify_tick(value: object) -> str:
    txt = str(value or "").strip()
    return txt or "—"


def _text_bbox(draw: ImageDraw.ImageDraw, text: str, font: Any) -> tuple[int, int]:
    if not text:
        return (0, 0)
    box = draw.textbbox((0, 0), text, font=font)
    return (max(0, int(box[2] - box[0])), max(0, int(box[3] - box[1])))


def _normalize_text_payload(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, Iterable):
        return [str(item or "") for item in cast(Iterable[object], raw)]
    return [str(raw)]


def _plain_text(value: object) -> str:
    txt = str(value or "").strip()
    if not txt:
        return ""
    return txt.replace("<b>", "").replace("</b>", "")


def _collect_legend_items(fig: go.Figure) -> list[_LegendItem]:
    traces = list(getattr(fig, "data", []) or [])
    if any(str(getattr(trace, "type", "") or "").strip().lower() == "pie" for trace in traces):
        items: list[_LegendItem] = []
        seen: set[str] = set()
        for trace in traces:
            if str(getattr(trace, "type", "") or "").strip().lower() != "pie":
                continue
            labels = [str(label or "").strip() for label in _trace_values(trace, "labels")]
            marker = getattr(trace, "marker", None)
            marker_colors = list(getattr(marker, "colors", []) or [])
            for idx, label in enumerate(labels):
                if not label or label in seen:
                    continue
                seen.add(label)
                color = _parse_color(
                    marker_colors[idx] if idx < len(marker_colors) else BBVA_LIGHT.core_blue
                )
                items.append(_LegendItem(label=label, color=color))
        return items

    items = []
    for trace in traces:
        trace_type = str(getattr(trace, "type", "") or "").strip().lower()
        mode = str(getattr(trace, "mode", "") or "").strip().lower()
        if trace_type == "scatter" and mode == "text":
            continue
        if getattr(trace, "showlegend", True) is False:
            continue
        label = str(getattr(trace, "name", "") or "").strip()
        if not label:
            continue
        color_value = None
        line = getattr(trace, "line", None)
        marker = getattr(trace, "marker", None)
        if line is not None:
            color_value = getattr(line, "color", None)
        if color_value is None and marker is not None:
            color_value = getattr(marker, "color", None)
        if isinstance(color_value, (list, tuple)):
            color_value = color_value[0] if color_value else None
        items.append(_LegendItem(label=label, color=_parse_color(color_value)))
    return items


def _legend_height(
    draw: ImageDraw.ImageDraw,
    items: Sequence[_LegendItem],
    *,
    canvas_width: int,
    font: Any,
    scale: float,
) -> int:
    if not items:
        return int(36 * scale)
    usable_width = max(120, canvas_width - int(120 * scale))
    x_cursor = 0
    rows = 1
    font_height = max(12, _text_bbox(draw, "Hg", font)[1])
    swatch = max(int(14 * scale), int(font_height * 0.78))
    gap = max(int(8 * scale), int(font_height * 0.38))
    item_gap = max(int(14 * scale), int(font_height * 0.84))
    for item in items:
        label_width, label_height = _text_bbox(draw, _plain_text(item.label), font)
        item_width = swatch + gap + label_width + item_gap
        if x_cursor and x_cursor + item_width > usable_width:
            rows += 1
            x_cursor = 0
        x_cursor += item_width
        _ = label_height
    row_height = int(max(20, max(swatch, font_height) + max((8 * scale), font_height * 0.30)))
    return max(int(36 * scale), rows * row_height + int(24 * scale))


def _draw_legend(
    draw: ImageDraw.ImageDraw,
    items: Sequence[_LegendItem],
    *,
    left: int,
    top: int,
    width: int,
    font: Any,
    text_color: tuple[int, int, int, int],
    scale: float,
) -> None:
    if not items:
        return
    font_height = max(12, _text_bbox(draw, "Hg", font)[1])
    swatch = max(int(14 * scale), int(font_height * 0.78))
    gap = max(int(8 * scale), int(font_height * 0.38))
    item_gap = max(int(14 * scale), int(font_height * 0.84))
    row_height = int(max(20, max(swatch, font_height) + max((8 * scale), font_height * 0.30)))
    x_cursor = int(left)
    y_cursor = int(top)
    max_right = int(left + width)
    for item in items:
        label = _plain_text(item.label)
        label_width, label_height = _text_bbox(draw, label, font)
        item_width = swatch + gap + label_width + item_gap
        if x_cursor != left and x_cursor + item_width > max_right:
            x_cursor = int(left)
            y_cursor += row_height
        swatch_top = y_cursor + max(0, (row_height - swatch) // 2)
        draw.rounded_rectangle(
            [x_cursor, swatch_top, x_cursor + swatch, swatch_top + swatch],
            radius=max(2, int(3 * scale)),
            fill=item.color,
        )
        draw.text(
            (x_cursor + swatch + gap, y_cursor + max(0, (row_height - label_height) // 2)),
            label,
            font=font,
            fill=text_color,
        )
        x_cursor += item_width


def _fit_text_to_width(
    draw: ImageDraw.ImageDraw,
    *,
    text: str,
    font: Any,
    max_width: int,
) -> str:
    clean = _plain_text(text)
    if max_width <= 0:
        return ""
    if _text_bbox(draw, clean, font)[0] <= max_width:
        return clean
    ellipsis = "…"
    token = clean
    while token and _text_bbox(draw, f"{token}{ellipsis}", font)[0] > max_width:
        token = token[:-1]
    return f"{token}{ellipsis}" if token else ellipsis


def _draw_legend_vertical(
    draw: ImageDraw.ImageDraw,
    items: Sequence[_LegendItem],
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    font: Any,
    text_color: tuple[int, int, int, int],
    scale: float,
    panel_color: tuple[int, int, int, int],
    border_color: tuple[int, int, int, int],
) -> None:
    if not items or width <= 20 or height <= 20:
        return
    font_height = max(12, _text_bbox(draw, "Hg", font)[1])
    pad = max(int(12 * scale), int(font_height * 0.42))
    swatch = max(int(14 * scale), int(font_height * 0.78))
    gap = max(int(8 * scale), int(font_height * 0.40))
    row_gap = max(int(7 * scale), int(font_height * 0.26))
    row_height = max(swatch, font_height) + row_gap
    panel_left = int(left)
    panel_top = int(top)
    panel_right = int(left + width)
    panel_bottom = int(max(top + height, top + (2 * pad) + row_height))
    draw.rounded_rectangle(
        [panel_left, panel_top, panel_right, panel_bottom],
        radius=max(4, int(8 * scale)),
        fill=panel_color,
        outline=border_color,
        width=max(1, int(1.4 * scale)),
    )

    y_cursor = panel_top + pad
    text_left = panel_left + pad + swatch + gap
    max_label_width = max(24, panel_right - text_left - pad)
    for item in items:
        if y_cursor + row_height > panel_bottom - pad:
            break
        label = _fit_text_to_width(
            draw,
            text=item.label,
            font=font,
            max_width=max_label_width,
        )
        _, label_h = _text_bbox(draw, label, font)
        swatch_top = y_cursor + max(0, (row_height - swatch) // 2)
        draw.rounded_rectangle(
            [panel_left + pad, swatch_top, panel_left + pad + swatch, swatch_top + swatch],
            radius=max(2, int(3 * scale)),
            fill=item.color,
        )
        draw.text(
            (text_left, y_cursor + max(0, (row_height - label_h) // 2)),
            label,
            font=font,
            fill=text_color,
        )
        y_cursor += row_height


def _is_line_dominant_cartesian(traces: Sequence[object]) -> bool:
    scatter_with_lines = 0
    bar_count = 0
    for trace in traces:
        trace_type = str(getattr(trace, "type", "") or "").strip().lower()
        if trace_type == "bar":
            bar_count += 1
            continue
        if trace_type not in {"scatter", "scattergl"}:
            continue
        mode_raw = str(getattr(trace, "mode", "") or "").strip().lower()
        mode_tokens = {token.strip() for token in mode_raw.split("+") if token.strip()}
        if not mode_tokens or "lines" in mode_tokens:
            scatter_with_lines += 1
    return scatter_with_lines >= 2 and bar_count == 0


def _legend_prefers_bottom(fig: go.Figure) -> bool:
    legend = getattr(getattr(fig, "layout", None), "legend", None)
    orientation = str(getattr(legend, "orientation", "") or "").strip().lower()
    if orientation == "h":
        return True
    y_value = getattr(legend, "y", None)
    try:
        if y_value is not None and float(y_value) <= 0:
            return True
    except Exception:
        pass
    return False


def _unique_categories(values: Iterable[object]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _infer_x_axis(fig: go.Figure, traces: Sequence[object]) -> _AxisSpec:
    layout_axis = getattr(getattr(fig, "layout", None), "xaxis", None)
    tickvals = list(getattr(layout_axis, "tickvals", []) or [])
    ticktext = [str(value or "") for value in list(getattr(layout_axis, "ticktext", []) or [])]
    categoryarray = [
        str(value or "") for value in list(getattr(layout_axis, "categoryarray", []) or [])
    ]
    all_x_values: list[object] = []
    for trace in traces:
        if str(getattr(trace, "type", "") or "").strip().lower() == "pie":
            continue
        all_x_values.extend(_trace_values(trace, "x"))

    if tickvals:
        numeric_tickvals = [_to_float(value) for value in tickvals]
        if all(value is not None for value in numeric_tickvals):
            labels = (
                ticktext
                if len(ticktext) == len(tickvals)
                else [_stringify_tick(v) for v in tickvals]
            )
            minimum = min(cast(float, value) for value in numeric_tickvals)
            maximum = max(cast(float, value) for value in numeric_tickvals)
            return _AxisSpec(
                kind="numeric",
                ticks=[
                    (cast(float, numeric_tickvals[idx]), labels[idx]) for idx in range(len(labels))
                ],
                minimum=minimum,
                maximum=maximum if maximum > minimum else minimum + 1.0,
                categories=[],
            )

    dt_values = [_to_datetime_float(value) for value in all_x_values]
    valid_dt = [value for value in dt_values if value is not None]
    if valid_dt and len(valid_dt) >= max(2, len(all_x_values) // 2):
        minimum = min(valid_dt)
        maximum = max(valid_dt)
        if maximum <= minimum:
            maximum = minimum + 86_400_000_000_000.0
        tick_count = 5 if len(valid_dt) >= 5 else max(2, len(valid_dt))
        step = (maximum - minimum) / float(max(1, tick_count - 1))
        ticks: list[tuple[float, str]] = []
        for idx in range(tick_count):
            raw = minimum + (step * idx)
            label = pd.Timestamp(raw, tz="UTC").strftime("%d %b")
            ticks.append((raw, label))
        return _AxisSpec(
            kind="datetime",
            ticks=ticks,
            minimum=minimum,
            maximum=maximum,
            categories=[],
        )

    numeric_values = [_to_float(value) for value in all_x_values]
    valid_numeric = [value for value in numeric_values if value is not None]
    if valid_numeric and len(valid_numeric) >= max(2, len(all_x_values) // 2):
        minimum = min(valid_numeric)
        maximum = max(valid_numeric)
        if maximum <= minimum:
            maximum = minimum + 1.0
        ticks = []
        if tickvals and ticktext and len(tickvals) == len(ticktext):
            for idx, raw in enumerate(tickvals):
                parsed = _to_float(raw)
                if parsed is None:
                    continue
                ticks.append((parsed, ticktext[idx]))
        else:
            tick_count = 5 if len(valid_numeric) >= 5 else max(2, len(valid_numeric))
            step = (maximum - minimum) / float(max(1, tick_count - 1))
            for idx in range(tick_count):
                raw = minimum + (step * idx)
                ticks.append((raw, f"{raw:.0f}"))
        return _AxisSpec(
            kind="numeric",
            ticks=ticks,
            minimum=minimum,
            maximum=maximum,
            categories=[],
        )

    categories = categoryarray or _unique_categories(all_x_values)
    if not categories:
        categories = ["—"]
    return _AxisSpec(
        kind="category",
        ticks=[(float(idx), label) for idx, label in enumerate(categories)],
        minimum=0.0,
        maximum=float(max(1, len(categories) - 1)),
        categories=categories,
    )


def _infer_y_axis(fig: go.Figure, traces: Sequence[object], *, stacked_bars: bool) -> _AxisSpec:
    layout_axis = getattr(getattr(fig, "layout", None), "yaxis", None)
    tickvals = list(getattr(layout_axis, "tickvals", []) or [])
    ticktext = [str(value or "") for value in list(getattr(layout_axis, "ticktext", []) or [])]
    range_values = list(getattr(layout_axis, "range", []) or [])

    if tickvals:
        numeric_tickvals = [_to_float(value) for value in tickvals]
        if all(value is not None for value in numeric_tickvals):
            minimum = min(cast(float, value) for value in numeric_tickvals)
            maximum = max(cast(float, value) for value in numeric_tickvals)
            if len(range_values) >= 2:
                start = _to_float(range_values[0])
                end = _to_float(range_values[1])
                if start is not None and end is not None:
                    minimum = start
                    maximum = end
            if maximum <= minimum:
                maximum = minimum + 1.0
            labels = (
                ticktext
                if len(ticktext) == len(tickvals)
                else [_stringify_tick(v) for v in tickvals]
            )
            return _AxisSpec(
                kind="numeric",
                ticks=[
                    (cast(float, numeric_tickvals[idx]), labels[idx]) for idx in range(len(labels))
                ],
                minimum=minimum,
                maximum=maximum,
                categories=[],
            )

    if len(range_values) >= 2:
        start = _to_float(range_values[0])
        end = _to_float(range_values[1])
        if start is not None and end is not None:
            minimum = min(start, end)
            maximum = max(start, end)
            if maximum <= minimum:
                maximum = minimum + 1.0
            tick_count = 5
            step = (maximum - minimum) / float(max(1, tick_count - 1))
            ticks = [
                (minimum + (step * idx), f"{minimum + (step * idx):.0f}")
                for idx in range(tick_count)
            ]
            return _AxisSpec(
                kind="numeric",
                ticks=ticks,
                minimum=minimum,
                maximum=maximum,
                categories=[],
            )

    values: list[float] = []
    if stacked_bars:
        totals: dict[str, float] = {}
        for trace in traces:
            if str(getattr(trace, "type", "") or "").strip().lower() != "bar":
                continue
            xs = _trace_values(trace, "x")
            ys = _trace_values(trace, "y")
            for idx, raw_y in enumerate(ys):
                y_value = _to_float(raw_y)
                if y_value is None:
                    continue
                x_key = str(xs[idx] if idx < len(xs) else idx)
                totals[x_key] = float(totals.get(x_key, 0.0)) + max(0.0, y_value)
        values.extend(float(total) for total in totals.values())

    for trace in traces:
        if str(getattr(trace, "type", "") or "").strip().lower() == "pie":
            continue
        values.extend(
            [
                cast(float, value)
                for value in [_to_float(item) for item in _trace_values(trace, "y")]
                if value is not None
            ]
        )

    if not values:
        values = [0.0, 1.0]
    minimum = min(0.0, min(values))
    maximum = max(values)
    if maximum <= minimum:
        maximum = minimum + 1.0
    if minimum >= 0:
        minimum = 0.0
    padding = (maximum - minimum) * 0.10
    maximum += padding if padding > 0 else 1.0
    tick_count = 5
    step = (maximum - minimum) / float(max(1, tick_count - 1))
    ticks = [(minimum + (step * idx), f"{minimum + (step * idx):.0f}") for idx in range(tick_count)]
    return _AxisSpec(
        kind="numeric",
        ticks=ticks,
        minimum=minimum,
        maximum=maximum,
        categories=[],
    )


def _map_x(value: object, axis: _AxisSpec, left: int, width: int) -> float | None:
    if axis.kind == "category":
        token = str(value or "").strip()
        if token not in axis.categories:
            return None
        count = max(1, len(axis.categories))
        step = width / float(count)
        idx = axis.categories.index(token)
        return left + (step * (idx + 0.5))

    if axis.kind == "datetime":
        parsed = _to_datetime_float(value)
    else:
        parsed = _to_float(value)
    if parsed is None:
        return None
    span = max(1e-9, axis.maximum - axis.minimum)
    return left + ((parsed - axis.minimum) / span) * width


def _map_y(value: object, axis: _AxisSpec, top: int, height: int) -> float | None:
    parsed = _to_float(value)
    if parsed is None:
        return None
    span = max(1e-9, axis.maximum - axis.minimum)
    normalized = (parsed - axis.minimum) / span
    return top + height - (normalized * height)


def _draw_rotated_text(
    image: Image.Image,
    text: str,
    *,
    position: tuple[int, int],
    font: Any,
    fill: tuple[int, int, int, int],
    angle: int,
) -> None:
    if not text:
        return
    dummy = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy)
    width, height = _text_bbox(dummy_draw, text, font)
    text_layer = Image.new("RGBA", (max(1, width + 4), max(1, height + 4)), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_layer)
    text_draw.text((2, 2), text, font=font, fill=fill)
    rotated = text_layer.rotate(angle, expand=True)
    image.alpha_composite(rotated, dest=position)


def _draw_axes(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    x_axis: _AxisSpec,
    y_axis: _AxisSpec,
    left: int,
    top: int,
    width: int,
    height: int,
    text_color: tuple[int, int, int, int],
    grid_color: tuple[int, int, int, int],
    axis_color: tuple[int, int, int, int],
    x_title: str,
    y_title: str,
    scale: float,
    axis_font_multiplier: float = 1.0,
) -> None:
    safe_multiplier = max(0.8, float(axis_font_multiplier or 1.0))
    axis_font = _load_font(int(16 * scale * safe_multiplier))
    title_font = _load_font(int(18 * scale * max(1.0, safe_multiplier * 0.96)), bold=True)
    draw.line(
        [(left, top + height), (left + width, top + height)],
        fill=axis_color,
        width=max(1, int(2 * scale)),
    )
    draw.line([(left, top), (left, top + height)], fill=axis_color, width=max(1, int(2 * scale)))

    for tick_value, label in y_axis.ticks:
        y_pos = _map_y(tick_value, y_axis, top, height)
        if y_pos is None:
            continue
        draw.line([(left, y_pos), (left + width, y_pos)], fill=grid_color, width=max(1, int(scale)))
        label_w, label_h = _text_bbox(draw, label, axis_font)
        draw.text(
            (left - label_w - int(14 * scale), y_pos - (label_h / 2)),
            label,
            font=axis_font,
            fill=text_color,
        )

    for tick_value, label in x_axis.ticks:
        if x_axis.kind == "category":
            x_pos = _map_x(label, x_axis, left, width)
        else:
            x_pos = _map_x(tick_value, x_axis, left, width)
        if x_pos is None:
            continue
        label_w, label_h = _text_bbox(draw, label, axis_font)
        draw.text(
            (x_pos - (label_w / 2), top + height + int(12 * scale)),
            label,
            font=axis_font,
            fill=text_color,
        )

    if x_title:
        label_w, label_h = _text_bbox(draw, x_title, title_font)
        x_title_offset = int(44 * scale)
        if "quincena" in str(x_title or "").strip().lower():
            x_title_offset += int(30 * scale)
        draw.text(
            (left + (width - label_w) / 2, top + height + x_title_offset),
            x_title,
            font=title_font,
            fill=text_color,
        )
        _ = label_h
    if y_title:
        rotated_x = max(0, int(left - (60 * scale)))
        rotated_y = max(0, int(top + (height / 2)))
        _draw_rotated_text(
            image,
            y_title,
            position=(rotated_x, rotated_y - int(40 * scale)),
            font=title_font,
            fill=text_color,
            angle=90,
        )


def _contrast_text(color: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    luminance = (0.299 * color[0]) + (0.587 * color[1]) + (0.114 * color[2])
    return (17, 25, 45, 255) if luminance > 160 else (255, 255, 255, 255)


def _draw_bar_traces(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    traces: Sequence[object],
    x_axis: _AxisSpec,
    y_axis: _AxisSpec,
    left: int,
    top: int,
    width: int,
    height: int,
    scale: float,
    stacked: bool,
) -> None:
    categories = x_axis.categories if x_axis.categories else [label for _, label in x_axis.ticks]
    if not categories:
        return
    step = width / float(max(1, len(categories)))
    bar_width = step * 0.62
    stacks: dict[str, float] = {category: 0.0 for category in categories}
    label_font = _load_font(int(15 * scale), bold=True)

    for trace in traces:
        if str(getattr(trace, "type", "") or "").strip().lower() != "bar":
            continue
        xs = _trace_values(trace, "x")
        ys = _trace_values(trace, "y")
        text_values = _normalize_text_payload(getattr(trace, "text", None))
        marker = getattr(trace, "marker", None)
        bar_color = _parse_color(getattr(marker, "color", None))
        for idx, raw_y in enumerate(ys):
            y_value = _to_float(raw_y)
            if y_value is None or y_value <= 0:
                continue
            x_raw = xs[idx] if idx < len(xs) else str(idx)
            x_token = str(x_raw or "").strip()
            x_center = _map_x(x_raw, x_axis, left, width)
            if x_center is None:
                continue
            y0_value = stacks.get(x_token, 0.0) if stacked else 0.0
            y1_value = y0_value + y_value
            y0 = _map_y(y0_value, y_axis, top, height)
            y1 = _map_y(y1_value, y_axis, top, height)
            if y0 is None or y1 is None:
                continue
            rect = [
                x_center - (bar_width / 2),
                min(y0, y1),
                x_center + (bar_width / 2),
                max(y0, y1),
            ]
            draw.rounded_rectangle(
                rect,
                radius=max(2, int(4 * scale)),
                fill=bar_color,
            )
            if stacked:
                stacks[x_token] = y1_value
            label = _plain_text(text_values[idx] if idx < len(text_values) else "")
            if label:
                label_w, label_h = _text_bbox(draw, label, label_font)
                rect_height = max(0, rect[3] - rect[1])
                if rect_height >= label_h + (8 * scale):
                    draw.text(
                        (
                            rect[0] + ((bar_width - label_w) / 2),
                            rect[1] + ((rect_height - label_h) / 2),
                        ),
                        label,
                        font=label_font,
                        fill=_contrast_text(bar_color),
                    )


def _draw_scatter_traces(
    draw: ImageDraw.ImageDraw,
    *,
    traces: Sequence[object],
    x_axis: _AxisSpec,
    y_axis: _AxisSpec,
    left: int,
    top: int,
    width: int,
    height: int,
    scale: float,
    line_width_multiplier: float = 1.0,
    marker_size_multiplier: float = 1.0,
) -> None:
    text_font = _load_font(int(16 * scale), bold=True)
    safe_line_multiplier = max(0.8, float(line_width_multiplier or 1.0))
    safe_marker_multiplier = max(0.8, float(marker_size_multiplier or 1.0))
    for trace in traces:
        trace_type = str(getattr(trace, "type", "") or "").strip().lower()
        if trace_type not in {"scatter", "scattergl"}:
            continue
        xs = _trace_values(trace, "x")
        ys = _trace_values(trace, "y")
        mode_raw = str(getattr(trace, "mode", "") or "").strip().lower()
        mode_tokens = {token.strip() for token in mode_raw.split("+") if token.strip()}
        if not mode_tokens:
            mode_tokens = {"lines"}
        line = getattr(trace, "line", None)
        marker = getattr(trace, "marker", None)
        line_color = _parse_color(getattr(line, "color", None))
        marker_color = _parse_color(getattr(marker, "color", None), default="#0051F1")
        marker_size = _to_float(getattr(marker, "size", 6)) or 6.0
        text_values = _normalize_text_payload(getattr(trace, "text", None))

        points: list[tuple[float, float]] = []
        for idx, raw_x in enumerate(xs):
            if idx >= len(ys):
                continue
            x_pos = _map_x(raw_x, x_axis, left, width)
            y_pos = _map_y(ys[idx], y_axis, top, height)
            if x_pos is None or y_pos is None:
                continue
            points.append((x_pos, y_pos))

        if "lines" in mode_tokens and len(points) >= 2:
            base_width = float(getattr(line, "width", 2) or 2)
            line_width_px = int(base_width * scale * safe_line_multiplier)
            draw.line(
                points,
                fill=line_color,
                width=max(int(2 * scale), line_width_px, int(3 * scale * safe_line_multiplier)),
            )

        if "markers" in mode_tokens:
            radius = max(2, int((marker_size / 2.0) * scale * safe_marker_multiplier))
            outline = _parse_color(BBVA_LIGHT.white)
            for x_pos, y_pos in points:
                draw.ellipse(
                    [x_pos - radius, y_pos - radius, x_pos + radius, y_pos + radius],
                    fill=marker_color,
                    outline=outline,
                    width=max(1, int(scale)),
                )

        if "text" in mode_tokens:
            for idx, point in enumerate(points):
                label = _plain_text(text_values[idx] if idx < len(text_values) else "")
                if not label:
                    continue
                label_w, label_h = _text_bbox(draw, label, text_font)
                draw.text(
                    (point[0] - (label_w / 2), point[1] - label_h - int(6 * scale)),
                    label,
                    font=text_font,
                    fill=line_color,
                )


def _render_pie_chart(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    fig: go.Figure,
    width: int,
    height: int,
    legend_items: Sequence[_LegendItem],
    legend_height: int,
    scale: float,
    text_color: tuple[int, int, int, int],
) -> None:
    traces = [
        trace
        for trace in list(getattr(fig, "data", []) or [])
        if str(getattr(trace, "type", "") or "").strip().lower() == "pie"
    ]
    if not traces:
        return
    trace = traces[0]
    values = [float(_to_float(value) or 0.0) for value in _trace_values(trace, "values")]
    colors = list(getattr(getattr(trace, "marker", None), "colors", []) or [])
    hole = max(0.0, min(0.85, float(getattr(trace, "hole", 0.0) or 0.0)))
    total = sum(value for value in values if value > 0)
    if total <= 0:
        return

    top = int(36 * scale)
    bottom = height - legend_height - int(24 * scale)
    diameter = min(width - int(140 * scale), bottom - top)
    diameter = max(int(220 * scale), diameter)
    left = int((width - diameter) / 2)
    pie_top = int(top + max(0, ((bottom - top) - diameter) / 2))
    bbox = [left, pie_top, left + diameter, pie_top + diameter]
    label_font = _load_font(int(18 * scale), bold=True)

    start_angle = -90.0
    for idx, value in enumerate(values):
        if value <= 0:
            continue
        sweep = (value / total) * 360.0
        end_angle = start_angle + sweep
        color = _parse_color(colors[idx] if idx < len(colors) else BBVA_LIGHT.core_blue)
        draw.pieslice(bbox, start=start_angle, end=end_angle, fill=color)

        share = value / total
        label_txt = ""
        if share >= 0.20:
            label_txt = f"{share * 100:.0f}%"
        elif share >= 0.045:
            label_txt = f"{share * 100:.1f}%"
        if label_txt:
            mid_angle = math.radians(start_angle + (sweep / 2.0))
            radius = (diameter / 2.0) * (0.72 if hole > 0 else 0.62)
            inner_radius = (diameter / 2.0) * hole
            text_radius = inner_radius + ((radius - inner_radius) * 0.62)
            center_x = left + (diameter / 2.0)
            center_y = pie_top + (diameter / 2.0)
            x_pos = center_x + (math.cos(mid_angle) * text_radius)
            y_pos = center_y + (math.sin(mid_angle) * text_radius)
            label_w, label_h = _text_bbox(draw, label_txt, label_font)
            draw.text(
                (x_pos - (label_w / 2), y_pos - (label_h / 2)),
                label_txt,
                font=label_font,
                fill=_contrast_text(color),
            )
        start_angle = end_angle

    if hole > 0:
        inner_d = diameter * hole
        inner_left = left + ((diameter - inner_d) / 2.0)
        inner_top = pie_top + ((diameter - inner_d) / 2.0)
        draw.ellipse(
            [inner_left, inner_top, inner_left + inner_d, inner_top + inner_d],
            fill=_parse_color(getattr(getattr(fig, "layout", None), "plot_bgcolor", "#FFFFFF")),
        )

    legend_font = _load_font(int(16 * scale))
    _draw_legend(
        draw,
        legend_items,
        left=int(64 * scale),
        top=height - legend_height + int(10 * scale),
        width=width - int(128 * scale),
        font=legend_font,
        text_color=text_color,
        scale=scale,
    )


def _render_cartesian_chart(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    *,
    fig: go.Figure,
    width: int,
    height: int,
    legend_items: Sequence[_LegendItem],
    legend_height: int,
    scale: float,
    text_color: tuple[int, int, int, int],
    grid_color: tuple[int, int, int, int],
    axis_color: tuple[int, int, int, int],
) -> None:
    traces = [
        trace
        for trace in list(getattr(fig, "data", []) or [])
        if str(getattr(trace, "type", "") or "").strip().lower() != "pie"
    ]
    if not traces:
        return

    line_dominant = _is_line_dominant_cartesian(traces)
    force_bottom_legend = _legend_prefers_bottom(fig)
    use_right_legend = (
        line_dominant
        and len(legend_items) >= 2
        and width >= int(780 * scale)
        and not force_bottom_legend
    )
    axis_font_multiplier = 1.0
    line_width_multiplier = 1.0
    marker_size_multiplier = 1.0
    legend_font_px = int(16 * scale)
    if line_dominant and force_bottom_legend:
        legend_font_px = int(19 * scale)
    legend_font = _load_font(legend_font_px)
    legend_panel_width = 0
    if use_right_legend:
        axis_font_multiplier = 1.18
        line_width_multiplier = 1.55
        marker_size_multiplier = 1.25
        legend_font = _load_font(int(22 * scale), bold=True)
        legend_panel_width = min(
            int(width * 0.31),
            max(int(width * 0.22), int(260 * scale)),
        )

    left = int(104 * scale)
    top = int(42 * scale)
    right = int(44 * scale) + (legend_panel_width if use_right_legend else 0)
    bottom = int(94 * scale) if use_right_legend else legend_height + int(94 * scale)
    plot_width = max(120, width - left - right)
    plot_height = max(120, height - top - bottom)
    barmode = str(getattr(getattr(fig, "layout", None), "barmode", "") or "").strip().lower()
    stacked_bars = barmode in {"stack", "relative"}

    x_axis = _infer_x_axis(fig, traces)
    y_axis = _infer_y_axis(fig, traces, stacked_bars=stacked_bars)

    _draw_axes(
        image,
        draw,
        x_axis=x_axis,
        y_axis=y_axis,
        left=left,
        top=top,
        width=plot_width,
        height=plot_height,
        text_color=text_color,
        grid_color=grid_color,
        axis_color=axis_color,
        x_title=str(
            getattr(getattr(getattr(fig.layout, "xaxis", None), "title", None), "text", "") or ""
        ),
        y_title=str(
            getattr(getattr(getattr(fig.layout, "yaxis", None), "title", None), "text", "") or ""
        ),
        scale=scale,
        axis_font_multiplier=axis_font_multiplier,
    )

    _draw_bar_traces(
        image,
        draw,
        traces=traces,
        x_axis=x_axis,
        y_axis=y_axis,
        left=left,
        top=top,
        width=plot_width,
        height=plot_height,
        scale=scale,
        stacked=stacked_bars,
    )
    _draw_scatter_traces(
        draw,
        traces=traces,
        x_axis=x_axis,
        y_axis=y_axis,
        left=left,
        top=top,
        width=plot_width,
        height=plot_height,
        scale=scale,
        line_width_multiplier=line_width_multiplier,
        marker_size_multiplier=marker_size_multiplier,
    )

    if use_right_legend:
        _draw_legend_vertical(
            draw,
            legend_items,
            left=left + plot_width + int(12 * scale),
            top=top + int(4 * scale),
            width=max(90, legend_panel_width - int(16 * scale)),
            height=max(90, plot_height - int(4 * scale)),
            font=legend_font,
            text_color=text_color,
            scale=scale,
            panel_color=_parse_color(BBVA_REPORT_MIST),
            border_color=_parse_color(BBVA_REPORT_LINE),
        )
    else:
        _draw_legend(
            draw,
            legend_items,
            left=left,
            top=height - legend_height + int(10 * scale),
            width=plot_width,
            font=legend_font,
            text_color=text_color,
            scale=scale,
        )


def render_plotly_figure_png(
    fig: go.Figure,
    *,
    scale: float,
    export_width: int,
    export_height: int,
) -> bytes:
    """Render supported Plotly report figures to PNG without any browser runtime."""

    render_scale = max(1.0, min(float(scale or 1.0), 2.0))
    width = max(320, int(export_width * render_scale))
    height = max(220, int(export_height * render_scale))

    paper_bg = _parse_color(getattr(getattr(fig, "layout", None), "paper_bgcolor", "#FFFFFF"))
    text_color = _parse_color(
        getattr(getattr(getattr(fig, "layout", None), "font", None), "color", BBVA_LIGHT.ink),
        default=BBVA_LIGHT.ink,
    )
    grid_color = _parse_color(
        getattr(getattr(getattr(fig, "layout", None), "xaxis", None), "gridcolor", "#EEF3FB"),
        default="#EEF3FB",
    )
    axis_color = _parse_color(
        getattr(getattr(getattr(fig, "layout", None), "xaxis", None), "linecolor", "#D3D8E1"),
        default="#D3D8E1",
    )

    image = Image.new("RGBA", (width, height), paper_bg)
    draw = ImageDraw.Draw(image)
    legend_items = _collect_legend_items(fig)
    non_pie_traces = [
        trace
        for trace in list(getattr(fig, "data", []) or [])
        if str(getattr(trace, "type", "") or "").strip().lower() != "pie"
    ]
    legend_font_px = int(16 * render_scale)
    if _is_line_dominant_cartesian(non_pie_traces) and _legend_prefers_bottom(fig):
        legend_font_px = int(19 * render_scale)
    legend_font = _load_font(legend_font_px)
    legend_height = _legend_height(
        draw,
        legend_items,
        canvas_width=width,
        font=legend_font,
        scale=render_scale,
    )

    if any(
        str(getattr(trace, "type", "") or "").strip().lower() == "pie"
        for trace in list(getattr(fig, "data", []) or [])
    ):
        _render_pie_chart(
            image,
            draw,
            fig=fig,
            width=width,
            height=height,
            legend_items=legend_items,
            legend_height=legend_height,
            scale=render_scale,
            text_color=text_color,
        )
    else:
        _render_cartesian_chart(
            image,
            draw,
            fig=fig,
            width=width,
            height=height,
            legend_items=legend_items,
            legend_height=legend_height,
            scale=render_scale,
            text_color=text_color,
            grid_color=grid_color,
            axis_color=axis_color,
        )

    payload = BytesIO()
    image.save(payload, format="PNG", optimize=True)
    return payload.getvalue()
