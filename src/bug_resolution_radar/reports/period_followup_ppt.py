"""Template-based fortnight follow-up PPT report."""

from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, List, Mapping, Optional, Sequence, cast

import pandas as pd
import plotly.graph_objects as go
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Pt

from bug_resolution_radar.analytics.analysis_window import apply_analysis_depth_filter
from bug_resolution_radar.analytics.insights import (
    build_theme_color_map,
    build_theme_fortnight_trend,
    build_theme_render_order,
    order_theme_labels_by_volume,
)
from bug_resolution_radar.analytics.issues import normalize_text_col, priority_rank
from bug_resolution_radar.analytics.trend_charts import ChartContext, build_trends_registry
from bug_resolution_radar.analytics.trend_insights import build_trend_insight_pack
from bug_resolution_radar.analytics.kpis import compute_kpis
from bug_resolution_radar.analytics.period_functionality_followup import (
    FunctionalityIssueRow,
    FunctionalityTopRow,
    FunctionalityZoomSlide,
    PeriodFunctionalityFollowupSummary,
    build_period_functionality_followup_summary,
)
from bug_resolution_radar.analytics.period_summary import (
    OPEN_ISSUES_FOCUS_MODE_MAESTRAS,
    QuincenalScopeResult,
    build_country_quincenal_result,
    format_window_label,
    scope_country_sources,
    source_label_map,
)
from bug_resolution_radar.analytics.status_semantics import effective_closed_mask
from bug_resolution_radar.config import Settings, resolve_period_ppt_template_path
from bug_resolution_radar.reports.executive_ppt import _fig_to_png, _kaleido_png_bytes
from bug_resolution_radar.repositories.issues_store import load_issues_df

_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_EMU_PER_INCH = 914400.0
_FUNCTIONALITY_TEMPLATE_FILENAME = "Seguimiento de incidencias por funcionalidad.pptx"
_TABLE_RENDER_DPI = 180
_TABLE_HEADER_BG_RGB = (0, 19, 145)
_TABLE_HEADER_FG_RGB = (255, 255, 255)
_TABLE_BODY_BG_RGB = (255, 255, 255)
_TABLE_BODY_FG_RGB = (0, 19, 145)
_TABLE_BORDER_RGB = (211, 216, 225)
_TABLE_LINK_RGB = (0, 81, 241)
_TABLE_PADDING_X_PX = 12
_TABLE_PADDING_Y_PX = 8
_TABLE_LINE_SPACING_PX = 2
_TABLE_BORDER_WIDTH_EMU = 10_160
_ZOOM_TABLE_HEADER_FONT_SIZE_PT = 8.6
_REPORT_FONT_DIR = (
    Path(__file__).resolve().parent.parent / "ui" / "assets" / "fonts" / "bbva"
).resolve()
_REPORT_FONT_BOOK_PATH = _REPORT_FONT_DIR / "BentonSansBBVA-Book.ttf"
_REPORT_FONT_BOLD_PATH = _REPORT_FONT_DIR / "BentonSansBBVA-Bold.ttf"
_ZOOM_TABLE_ROWS_PER_SLIDE = 5
_ZOOM_TABLE_COLUMN_WEIGHTS: tuple[float, ...] = (1.9, 4.9, 2.3, 1.9, 1.5, 1.5)
_FUNCTIONALITY_TABLE_TOP_SHIFT_RATIO = 0.048
_FUNCTIONALITY_TABLE_TOP_GUARD_EMU = 32_000
_FUNCTIONALITY_TABLE_FONT_BOOST_PT = 1.2
_EXEC_BG_RGB = (7, 36, 96)
_EXEC_TEXT_PRIMARY_RGB = (247, 251, 255)
_EXEC_TEXT_SECONDARY_RGB = (170, 191, 226)
_EXEC_ACCENT_BORDER_RGB = (104, 151, 222)
_EXEC_CARD_BG_RGB = (12, 52, 118)
_EXEC_CARD_TITLE_RGB = (186, 226, 252)


@dataclass(frozen=True)
class PeriodFollowupReportResult:
    file_name: str
    content: bytes
    slide_count: int
    total_issues: int
    open_issues: int
    closed_issues: int
    country: str
    source_ids: tuple[str, ...]
    applied_filter_summary: str


def _slide_text_blob(slide: Any) -> str:
    """Collect lower-cased text from all text-capable shapes in a slide."""
    chunks: list[str] = []
    for shape in getattr(slide, "shapes", []):
        if not getattr(shape, "has_text_frame", False):
            continue
        txt = str(getattr(shape, "text", "") or "").strip()
        if txt:
            chunks.append(txt.lower())
    return " ".join(chunks).strip()


def _looks_like_explanatory_helper_slide(slide: Any) -> bool:
    """Heuristic to detect optional helper/instruction slide in position 2."""
    blob = _slide_text_blob(slide)
    if not blob:
        return True

    production_tokens = (
        "dashboard",
        "seguimiento de incidencias",
        "seguimiento de kpis",
        "gráficos de evolución",
        "graficos de evolucion",
    )
    if any(tok in blob for tok in production_tokens):
        return False

    helper_tokens = (
        "instrucci",
        "comentario",
        "comentarios",
        "helper",
        "ayuda",
        "ejemplo",
        "plantilla",
        "template",
        "no editar",
        "borrar",
        "delete",
    )
    return any(tok in blob for tok in helper_tokens)


def _ensure_slide_index(prs: Any, *, index: int, role: str) -> None:
    if int(index) < len(prs.slides):
        return
    raise ValueError(
        "Plantilla de seguimiento inválida: falta la slide "
        f"{int(index) + 1} ({role}). Revisa PERIOD_PPT_TEMPLATE_PATH."
    )


def _normalize_period_template(prs: Any) -> None:
    """
    Normalize user-provided template into the 8-slide structure expected by renderer.

    Target structure:
      1) Portada
      2) Dashboard header
      3) Resumen país
      4) Resumen origen A
      5) Resumen origen B
      6) Header evolución
      7) Evolución origen A
      8) Evolución origen B
    """
    if len(prs.slides) < 7:
        raise ValueError(
            "La plantilla de seguimiento debe tener al menos 7 slides base "
            "(portada, dashboard, 3 resúmenes, cabecera evolución y 1 evolución). "
            f"Slides detectadas: {len(prs.slides)}."
        )

    # Optional helper slide used in earlier corporate templates.
    if len(prs.slides) > 1 and _looks_like_explanatory_helper_slide(prs.slides[1]):
        _remove_slide(prs, 1)

    if len(prs.slides) < 7:
        raise ValueError(
            "La plantilla de seguimiento quedó incompleta tras eliminar la slide de ayuda. "
            f"Slides detectadas: {len(prs.slides)}."
        )

    # Ensure we always have two evolution slides based on the same visual template.
    if len(prs.slides) >= 8:
        _copy_slide_content(prs, source_index=6, target_index=7)
    else:
        _append_slide_clone(prs, source_index=6)

    # Keep exactly 8 slides, preserving canonical order.
    while len(prs.slides) > 8:
        _remove_slide(prs, 8)

    required_roles = {
        0: "Portada",
        2: "Resumen país",
        3: "Resumen origen A",
        4: "Resumen origen B",
        6: "Evolución origen A",
        7: "Evolución origen B",
    }
    for idx, role in required_roles.items():
        _ensure_slide_index(prs, index=idx, role=role)


def _slug(value: str) -> str:
    txt = str(value or "").strip().lower()
    txt = re.sub(r"[^a-z0-9]+", "-", txt).strip("-")
    return txt or "scope"


def _fmt_days(value: float | None) -> int:
    if value is None or pd.isna(value):
        return 0
    return max(0, int(round(float(value))))


def _fmt_delta_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "—"
    pct = float(value) * 100.0
    # Direction is already represented by template arrows/colors; keep compact
    # absolute percentage text to avoid overflow in tiny delta placeholders.
    return f"{abs(pct):.0f}%"


def _clean_source_ids(source_ids: Sequence[str]) -> List[str]:
    out: List[str] = []
    for raw in list(source_ids or []):
        sid = str(raw or "").strip()
        if sid and sid not in out:
            out.append(sid)
    return out


def _resolve_template_path(settings: Settings, explicit_path: str | None = None) -> Path:
    return resolve_period_ppt_template_path(settings, explicit_path=explicit_path)


def _resolve_functionality_template_path() -> Path:
    path = (
        Path(__file__).resolve().parent / "templates" / _FUNCTIONALITY_TEMPLATE_FILENAME
    ).resolve()
    if path.exists() and path.is_file():
        return path
    raise FileNotFoundError(
        f"No se encontró la plantilla de seguimiento por funcionalidad. Ruta esperada: {path}"
    )


def _remove_slide(prs: Any, index: int) -> None:
    sld_id = prs.slides._sldIdLst[index]
    prs.part.drop_rel(sld_id.rId)
    del prs.slides._sldIdLst[index]


def _copy_slide_content(prs: Any, *, source_index: int, target_index: int) -> None:
    source = prs.slides[source_index]
    target = prs.slides[target_index]

    for shape in list(target.shapes):
        sp = shape.element
        sp.getparent().remove(sp)

    for rel in list(target.part.rels.values()):
        if "slideLayout" in rel.reltype or "notesSlide" in rel.reltype or "comments" in rel.reltype:
            continue
        target.part.drop_rel(rel.rId)

    rid_map: dict[str, str] = {}
    for rel in source.part.rels.values():
        if "slideLayout" in rel.reltype or "notesSlide" in rel.reltype or "comments" in rel.reltype:
            continue
        rel_target = rel.target_ref if rel.is_external else rel._target
        rid_map[rel.rId] = target.part.rels._add_relationship(
            rel.reltype,
            rel_target,
            rel.is_external,
        )

    for shape in source.shapes:
        clone = deepcopy(shape.element)
        for node in clone.iter():
            for attr_name, attr_value in list(node.attrib.items()):
                if attr_name.startswith(_REL_NS) and attr_value in rid_map:
                    node.set(attr_name, rid_map[attr_value])
        target.shapes._spTree.insert_element_before(clone, "p:extLst")


def _append_slide_clone(prs: Any, *, source_index: int) -> None:
    source = prs.slides[source_index]
    dest = prs.slides.add_slide(source.slide_layout)

    for shape in list(dest.shapes):
        sp = shape.element
        sp.getparent().remove(sp)

    rid_map: dict[str, str] = {}
    for rel in source.part.rels.values():
        if "slideLayout" in rel.reltype or "notesSlide" in rel.reltype or "comments" in rel.reltype:
            continue
        rel_target = rel.target_ref if rel.is_external else rel._target
        rid_map[rel.rId] = dest.part.rels._add_relationship(
            rel.reltype,
            rel_target,
            rel.is_external,
        )

    for shape in source.shapes:
        clone = deepcopy(shape.element)
        for node in clone.iter():
            for attr_name, attr_value in list(node.attrib.items()):
                if attr_name.startswith(_REL_NS) and attr_value in rid_map:
                    node.set(attr_name, rid_map[attr_value])
        dest.shapes._spTree.insert_element_before(clone, "p:extLst")


def _append_slide_clone_from_source(prs: Any, *, source_slide: Any) -> Any:
    dest = prs.slides.add_slide(prs.slide_layouts[6])

    for shape in list(dest.shapes):
        sp = shape.element
        sp.getparent().remove(sp)

    rid_map: dict[str, str] = {}
    for rel in source_slide.part.rels.values():
        if "slideLayout" in rel.reltype or "notesSlide" in rel.reltype or "comments" in rel.reltype:
            continue
        if str(rel.reltype or "").endswith("/image") and not rel.is_external:
            try:
                img_blob = bytes(getattr(rel._target, "blob", b"") or b"")
                if img_blob:
                    _, img_rid = dest.part.get_or_add_image_part(BytesIO(img_blob))
                    rid_map[rel.rId] = img_rid
                    continue
            except Exception:
                pass
        rel_target = rel.target_ref if rel.is_external else rel._target
        rid_map[rel.rId] = dest.part.rels._add_relationship(
            rel.reltype,
            rel_target,
            rel.is_external,
        )

    for shape in source_slide.shapes:
        clone = deepcopy(shape.element)
        for node in clone.iter():
            for attr_name, attr_value in list(node.attrib.items()):
                if attr_name.startswith(_REL_NS) and attr_value in rid_map:
                    node.set(attr_name, rid_map[attr_value])
        dest.shapes._spTree.insert_element_before(clone, "p:extLst")
    _apply_effective_background_from_source(dest_slide=dest, source_slide=source_slide)
    return dest


def _solid_background_rgb(shape_container: Any) -> RGBColor | None:
    if shape_container is None:
        return None
    try:
        fill = shape_container.background.fill
    except Exception:
        return None
    try:
        if int(fill.type or 0) != 1:  # SOLID
            return None
    except Exception:
        return None
    try:
        rgb = getattr(fill.fore_color, "rgb", None)
    except Exception:
        rgb = None
    if rgb is None:
        return None
    return cast(RGBColor, rgb)


def _effective_background_rgb(source_slide: Any) -> RGBColor:
    for container in (
        source_slide,
        getattr(source_slide, "slide_layout", None),
        getattr(getattr(source_slide, "slide_layout", None), "slide_master", None),
    ):
        rgb = _solid_background_rgb(container)
        if rgb is not None:
            return rgb
    return RGBColor(247, 248, 248)


def _apply_effective_background_from_source(*, dest_slide: Any, source_slide: Any) -> None:
    rgb = _effective_background_rgb(source_slide)
    try:
        fill = dest_slide.background.fill
        fill.solid()
        fill.fore_color.rgb = rgb
    except Exception:
        return


def _shape_or_none(slide: Any, index_1_based: int) -> Any | None:
    idx = int(index_1_based) - 1
    if idx < 0 or idx >= len(slide.shapes):
        return None
    return slide.shapes[idx]


def _shape_area_in2(shape: Any) -> float:
    return float(shape.width) * float(shape.height) / (_EMU_PER_INCH * _EMU_PER_INCH)


def _shape_center(shape: Any) -> tuple[float, float]:
    cx = float(shape.left) + (float(shape.width) / 2.0)
    cy = float(shape.top) + (float(shape.height) / 2.0)
    return cx, cy


def _picture_candidates(slide: Any, *, min_area_in2: float = 1.0) -> List[Any]:
    out: List[Any] = []
    for shape in slide.shapes:
        try:
            if getattr(shape, "shape_type", None) != MSO_SHAPE_TYPE.PICTURE:
                continue
        except Exception:
            continue
        if _shape_area_in2(shape) < float(min_area_in2):
            continue
        out.append(shape)
    return out


def _remove_shape(shape: Any) -> None:
    try:
        node = shape.element
        node.getparent().remove(node)
    except Exception:
        return


def _set_shape_text_fit(shape: Any) -> None:
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    tf = shape.text_frame
    try:
        tf.word_wrap = True
    except Exception:
        pass
    try:
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except Exception:
        pass


def _set_shape_text(slide: Any, index_1_based: int, text: str) -> None:
    shape = _shape_or_none(slide, index_1_based)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    _set_shape_text_by_shape(shape, text)


def _set_shape_text_by_shape(shape: Any, text: str) -> None:
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    target_lines = str(text or "").splitlines() or [""]
    tf = shape.text_frame
    paragraphs = list(tf.paragraphs)
    while len(paragraphs) < len(target_lines):
        tf.add_paragraph()
        paragraphs = list(tf.paragraphs)

    for idx, line in enumerate(target_lines):
        p = paragraphs[idx]
        runs = list(p.runs)
        if not runs:
            p.add_run()
            runs = list(p.runs)
        runs[0].text = str(line)
        for run in runs[1:]:
            run.text = ""

    for idx in range(len(target_lines), len(paragraphs)):
        p = paragraphs[idx]
        runs = list(p.runs)
        if not runs:
            p.add_run()
            runs = list(p.runs)
        runs[0].text = ""
        for run in runs[1:]:
            run.text = ""

    _set_shape_text_fit(shape)


def _set_shape_text_strict(slide: Any, index_1_based: int, text: str) -> None:
    shape = _shape_or_none(slide, index_1_based)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    tf = shape.text_frame
    sample_run = None
    try:
        sample_run = tf.paragraphs[0].runs[0]
    except Exception:
        sample_run = None

    tf.clear()
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = str(text or "")
    if sample_run is not None:
        try:
            run.font.bold = sample_run.font.bold
        except Exception:
            pass
        try:
            run.font.italic = sample_run.font.italic
        except Exception:
            pass
        try:
            run.font.size = sample_run.font.size
        except Exception:
            pass
        try:
            run.font.name = sample_run.font.name
        except Exception:
            pass
        try:
            rgb = getattr(getattr(sample_run.font, "color", None), "rgb", None)
            if rgb is not None:
                run.font.color.rgb = rgb
        except Exception:
            pass
    _set_shape_text_fit(shape)


def _shape_table_or_none(slide: Any, index_1_based: int) -> Any | None:
    shape = _shape_or_none(slide, index_1_based)
    if shape is not None and getattr(shape, "has_table", False):
        return shape
    table_shapes = [item for item in slide.shapes if getattr(item, "has_table", False)]
    if not table_shapes:
        return None
    return max(table_shapes, key=_shape_area_in2)


def _normalize_column_widths(
    widths: Sequence[int | float],
    *,
    total_width: int,
) -> list[int]:
    safe_total = max(int(total_width or 0), 1)
    raw = [max(int(round(float(value or 0))), 1) for value in list(widths or [])]
    if not raw:
        return []
    raw_sum = sum(raw)
    if raw_sum <= 0:
        even = max(int(round(safe_total / len(raw))), 1)
        out = [even for _ in raw]
    else:
        out = [max(int(round((value / raw_sum) * safe_total)), 1) for value in raw]
    out[-1] += safe_total - sum(out)
    return out


def _rebuild_table_shape_with_rows(
    slide: Any,
    *,
    table_shape: Any,
    target_rows: int,
) -> Any:
    table = table_shape.table
    col_count = len(table.columns)
    needed_rows = max(int(target_rows or 0), 2)
    if col_count <= 0:
        return table_shape
    if len(table.rows) == needed_rows:
        return table_shape

    left = int(table_shape.left)
    top = int(table_shape.top)
    width = int(table_shape.width)
    height = int(table_shape.height)

    old_widths = [int(getattr(col, "width", 0) or 0) for col in table.columns]
    header_texts = [str(table.cell(0, cidx).text or "") for cidx in range(col_count)]
    header_h = int(
        getattr(table.rows[0], "height", 0) or max(int(height / max(len(table.rows), 1)), 1)
    )

    new_shape = slide.shapes.add_table(needed_rows, col_count, left, top, width, height)
    new_table = new_shape.table
    normalized_widths = _normalize_column_widths(old_widths, total_width=width)
    if len(normalized_widths) == col_count:
        for col, col_width in zip(new_table.columns, normalized_widths):
            try:
                col.width = int(col_width)
            except Exception:
                continue

    body_rows = max(needed_rows - 1, 1)
    remaining_h = max(int(height) - int(header_h), 1)
    body_h = max(int(round(remaining_h / body_rows)), 1)
    try:
        new_table.rows[0].height = int(header_h)
    except Exception:
        pass
    for ridx in range(1, needed_rows):
        try:
            new_table.rows[ridx].height = int(body_h)
        except Exception:
            continue

    for cidx, header in enumerate(header_texts):
        _set_table_cell_text(new_table.cell(0, cidx), header, align=PP_ALIGN.LEFT)

    _remove_shape(table_shape)
    return new_shape


def _trim_text(value: object, *, max_chars: int) -> str:
    txt = str(value or "").strip()
    if max_chars <= 0 or len(txt) <= max_chars:
        return txt
    return txt[: max(0, max_chars - 3)].rstrip() + "..."


def _emu_to_px(value: int | float, *, dpi: int = _TABLE_RENDER_DPI) -> int:
    inches = max(float(value or 0) / _EMU_PER_INCH, 0.0)
    return max(int(round(inches * float(dpi))), 1)


def _load_report_font(*, size_px: int, bold: bool) -> Any:
    preferred = [_REPORT_FONT_BOLD_PATH] if bold else [_REPORT_FONT_BOOK_PATH]
    fallback = [_REPORT_FONT_BOOK_PATH] if bold else [_REPORT_FONT_BOLD_PATH]
    for candidate in preferred + fallback:
        try:
            if candidate.exists():
                return ImageFont.truetype(str(candidate), max(int(size_px), 1))
        except Exception:
            continue
    return ImageFont.load_default()


def _measure_text(draw: Any, text: str, font: Any) -> tuple[int, int]:
    if not str(text or ""):
        return 0, 0
    left, top, right, bottom = draw.textbbox((0, 0), str(text), font=font)
    return max(int(right - left), 0), max(int(bottom - top), 0)


def _shorten_to_width(draw: Any, text: str, font: Any, *, max_width: int) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if _measure_text(draw, raw, font)[0] <= max_width:
        return raw

    probe = raw
    while probe:
        probe = probe[:-1].rstrip()
        candidate = f"{probe}..."
        if _measure_text(draw, candidate, font)[0] <= max_width:
            return candidate
    return "..."


def _wrap_text_to_width(draw: Any, text: str, font: Any, *, max_width: int) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return [""]

    lines: list[str] = []
    for block in raw.splitlines() or [""]:
        words = block.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if _measure_text(draw, candidate, font)[0] <= max_width:
                current = candidate
                continue
            lines.append(current)
            current = word
        lines.append(current)

    return lines or [""]


def _fit_lines_in_cell(
    draw: Any,
    text: str,
    font: Any,
    *,
    max_width: int,
    max_height: int,
) -> list[str]:
    lines = _wrap_text_to_width(draw, text, font, max_width=max_width)
    line_h = max(_measure_text(draw, "Ag", font)[1], 1)
    capacity = max(
        int((max_height + _TABLE_LINE_SPACING_PX) / (line_h + _TABLE_LINE_SPACING_PX)),
        1,
    )
    if len(lines) <= capacity:
        return lines
    if capacity == 1:
        return [_shorten_to_width(draw, " ".join(lines), font, max_width=max_width)]
    tail = " ".join(lines[capacity - 1 :])
    return lines[: capacity - 1] + [_shorten_to_width(draw, tail, font, max_width=max_width)]


def _draw_table_cell_text(
    draw: Any,
    *,
    text: str,
    font: Any,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    align: str,
) -> None:
    x0, y0, x1, y1 = box
    inner_w = max((x1 - x0) - (_TABLE_PADDING_X_PX * 2), 1)
    inner_h = max((y1 - y0) - (_TABLE_PADDING_Y_PX * 2), 1)
    lines = _fit_lines_in_cell(draw, text, font, max_width=inner_w, max_height=inner_h)
    line_h = max(_measure_text(draw, "Ag", font)[1], 1)
    total_h = (line_h * len(lines)) + (_TABLE_LINE_SPACING_PX * max(len(lines) - 1, 0))
    start_y = y0 + max(int(((y1 - y0) - total_h) / 2), _TABLE_PADDING_Y_PX)

    for idx, line in enumerate(lines):
        line_w, _ = _measure_text(draw, line, font)
        if align == "center":
            tx = x0 + max(int(((x1 - x0) - line_w) / 2), _TABLE_PADDING_X_PX)
        else:
            tx = x0 + _TABLE_PADDING_X_PX
        ty = start_y + idx * (line_h + _TABLE_LINE_SPACING_PX)
        draw.text((tx, ty), line, font=font, fill=fill)


def _set_table_cell_text(
    cell: Any,
    text: str,
    *,
    hyperlink: str = "",
    align: PP_ALIGN | None = None,
    bold: bool | None = None,
    color_rgb: RGBColor | None = None,
    font_size_pt: float | None = None,
) -> None:
    if cell is None:
        return
    tf = getattr(cell, "text_frame", None)
    if tf is None:
        return

    paragraphs = list(tf.paragraphs)
    if not paragraphs:
        tf.add_paragraph()
        paragraphs = list(tf.paragraphs)
    p0 = paragraphs[0]
    if align is not None:
        try:
            p0.alignment = align
        except Exception:
            pass
    runs = list(p0.runs)
    if not runs:
        p0.add_run()
        runs = list(p0.runs)
    run = runs[0]
    run.text = str(text or "")
    if bold is not None:
        try:
            run.font.bold = bool(bold)
        except Exception:
            pass
    if color_rgb is not None:
        try:
            run.font.color.rgb = color_rgb
        except Exception:
            pass
    if font_size_pt is not None:
        try:
            run.font.size = Pt(float(font_size_pt))
        except Exception:
            pass
    try:
        if hyperlink:
            run.hyperlink.address = str(hyperlink)
            try:
                run.font.color.rgb = RGBColor(*_TABLE_LINK_RGB)
            except Exception:
                pass
            try:
                run.font.underline = True
            except Exception:
                pass
        elif getattr(run, "hyperlink", None) is not None:
            run.hyperlink.address = None
    except Exception:
        pass
    for extra in runs[1:]:
        extra.text = ""

    for extra_paragraph in paragraphs[1:]:
        if align is not None:
            try:
                extra_paragraph.alignment = align
            except Exception:
                pass
        extra_runs = list(extra_paragraph.runs)
        if not extra_runs:
            extra_paragraph.add_run()
            extra_runs = list(extra_paragraph.runs)
        extra_runs[0].text = ""
        for extra in extra_runs[1:]:
            extra.text = ""

    try:
        tf.word_wrap = True
    except Exception:
        pass
    try:
        cell.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    except Exception:
        pass
    try:
        tf.margin_left = Pt(4.0)
        tf.margin_right = Pt(3.0)
        tf.margin_top = Pt(1.0)
        tf.margin_bottom = Pt(1.0)
    except Exception:
        pass


def _set_table_rows(
    slide: Any,
    *,
    table_shape_index: int,
    rows: Sequence[Sequence[str]],
    hyperlink_by_row: Mapping[int, str] | None = None,
    left_align_cols: Sequence[int] = (),
    min_row_height_emu: int | None = None,
) -> None:
    shape = _shape_table_or_none(slide, table_shape_index)
    if shape is None:
        return

    needed_rows = max(len(list(rows or [])) + 1, 2)
    shape = _rebuild_table_shape_with_rows(slide, table_shape=shape, target_rows=needed_rows)
    table = shape.table
    col_count = len(table.columns)
    normalized_rows = [list(row)[:col_count] for row in list(rows or [])]
    if not normalized_rows:
        normalized_rows = [[""] * col_count]
    normalized_rows = [row + ([""] * (col_count - len(row))) for row in normalized_rows]

    # Compact rows so all issues fit in the visual container.
    total_rows = len(normalized_rows) + 1  # header + data
    if total_rows > 1:
        header_h = int(table.rows[0].height or max(int(shape.height / total_rows), 1))
        remaining_h = max(int(shape.height) - header_h, 1)
        min_row_h = max(int(min_row_height_emu or 1), 1)
        row_h = max(int(remaining_h / max(len(normalized_rows), 1)), min_row_h)
        for ridx in range(1, len(table.rows)):
            try:
                table.rows[ridx].height = row_h
            except Exception:
                continue

    # Enforce a portable, explicit visual style to maximize compatibility
    # across Keynote/PowerPoint/document viewers.
    for cidx in range(col_count):
        header_cell = table.cell(0, cidx)
        try:
            header_cell.fill.solid()
            header_cell.fill.fore_color.rgb = RGBColor(*_TABLE_HEADER_BG_RGB)
        except Exception:
            pass
        _set_table_cell_text(
            header_cell,
            str(header_cell.text or ""),
            align=PP_ALIGN.LEFT,
            bold=True,
            color_rgb=RGBColor(*_TABLE_HEADER_FG_RGB),
            font_size_pt=_ZOOM_TABLE_HEADER_FONT_SIZE_PT,
        )
        _set_table_cell_border(
            header_cell,
            color_rgb=RGBColor(*_TABLE_BORDER_RGB),
            width_emu=_TABLE_BORDER_WIDTH_EMU,
        )

    hyperlinks = dict(hyperlink_by_row or {})
    for ridx, row_values in enumerate(normalized_rows, start=1):
        row_link = str(hyperlinks.get(ridx - 1, "") or "").strip()
        for cidx, value in enumerate(row_values):
            body_cell = table.cell(ridx, cidx)
            try:
                body_cell.fill.solid()
                body_cell.fill.fore_color.rgb = RGBColor(*_TABLE_BODY_BG_RGB)
            except Exception:
                pass
            _set_table_cell_text(
                body_cell,
                str(value or ""),
                hyperlink=row_link if cidx == 0 else "",
                align=PP_ALIGN.LEFT,
                bold=False,
                color_rgb=RGBColor(*_TABLE_BODY_FG_RGB),
            )
            _set_table_cell_border(
                body_cell,
                color_rgb=RGBColor(*_TABLE_BORDER_RGB),
                width_emu=_TABLE_BORDER_WIDTH_EMU,
            )


def _set_table_cell_border(
    cell: Any,
    *,
    color_rgb: RGBColor,
    width_emu: int,
) -> None:
    if cell is None:
        return
    tc = getattr(cell, "_tc", None)
    if tc is None:
        return
    tc_pr = tc.get_or_add_tcPr()
    color_hex = f"{int(color_rgb[0]):02X}{int(color_rgb[1]):02X}{int(color_rgb[2]):02X}"
    for side in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        existing = tc_pr.find(qn(side))
        if existing is not None:
            tc_pr.remove(existing)
        ln = OxmlElement(side)
        ln.set("w", str(max(int(width_emu or 0), 1)))
        ln.set("cap", "flat")
        ln.set("cmpd", "sng")
        ln.set("algn", "ctr")

        solid = OxmlElement("a:solidFill")
        srgb = OxmlElement("a:srgbClr")
        srgb.set("val", color_hex)
        solid.append(srgb)
        ln.append(solid)

        dash = OxmlElement("a:prstDash")
        dash.set("val", "solid")
        ln.append(dash)

        head = OxmlElement("a:headEnd")
        head.set("type", "none")
        head.set("w", "med")
        head.set("len", "med")
        ln.append(head)

        tail = OxmlElement("a:tailEnd")
        tail.set("type", "none")
        tail.set("w", "med")
        tail.set("len", "med")
        ln.append(tail)
        tc_pr.append(ln)


def _table_body_font_size_pt(data_rows: int) -> float:
    rows = max(int(data_rows or 0), 1)
    if rows <= 6:
        return 10.0
    if rows <= 10:
        return 9.0
    if rows <= 16:
        return 8.0
    return 7.2


def _tune_table_font(
    slide: Any,
    *,
    table_shape_index: int,
    data_rows: int,
    description_col_index: int | None = None,
) -> None:
    shape = _shape_table_or_none(slide, table_shape_index)
    if shape is None:
        return
    table = shape.table
    base_size = _table_body_font_size_pt(data_rows)

    for ridx in range(1, len(table.rows)):
        for cidx in range(len(table.columns)):
            cell = table.cell(ridx, cidx)
            tf = getattr(cell, "text_frame", None)
            if tf is None:
                continue
            for paragraph in list(tf.paragraphs):
                for run in list(paragraph.runs):
                    size = base_size
                    if description_col_index is not None and cidx == int(description_col_index):
                        size = max(base_size - 0.4, 7.0)
                    run.font.size = Pt(float(size))
            try:
                tf.word_wrap = True
            except Exception:
                pass


def _table_picture_payload(
    table_shape: Any,
    *,
    rows: Sequence[Sequence[str]],
    description_col_index: int | None = None,
    left_align_cols: Sequence[int] = (),
    hyperlink_by_row: Mapping[int, str] | None = None,
    font_boost_pt: float = 0.0,
) -> bytes:
    table = table_shape.table
    col_count = len(table.columns)
    if col_count <= 0:
        return b""

    normalized_rows = [list(row)[:col_count] for row in list(rows or [])]
    if not normalized_rows:
        normalized_rows = [[""] * col_count]
    normalized_rows = [row + ([""] * (col_count - len(row))) for row in normalized_rows]

    width_px = _emu_to_px(int(table_shape.width))
    height_px = _emu_to_px(int(table_shape.height))
    image = Image.new("RGB", (width_px, height_px), _TABLE_BODY_BG_RGB)
    draw = ImageDraw.Draw(image)

    raw_col_widths = [int(getattr(col, "width", 0) or 0) for col in table.columns]
    total_col_width = sum(width for width in raw_col_widths if width > 0)
    if total_col_width <= 0:
        raw_col_widths = [1] * col_count
        total_col_width = col_count
    col_widths_px = [
        max(int(round((float(width) / float(total_col_width)) * float(width_px))), 1)
        for width in raw_col_widths
    ]
    col_widths_px[-1] += width_px - sum(col_widths_px)

    header_h_emu = int(
        table.rows[0].height or max(int(table_shape.height / (len(normalized_rows) + 1)), 1)
    )
    remaining_h_emu = max(int(table_shape.height) - header_h_emu, 1)
    body_row_h_emu = max(int(remaining_h_emu / max(len(normalized_rows), 1)), 1)
    header_h_px = _emu_to_px(header_h_emu)
    body_row_h_px = max(
        int(round(float(height_px - header_h_px) / max(len(normalized_rows), 1))), 1
    )
    body_row_h_px = max(body_row_h_px, _emu_to_px(body_row_h_emu))
    header_h_px = max(height_px - (body_row_h_px * len(normalized_rows)), 1)

    safe_font_boost = max(float(font_boost_pt or 0.0), 0.0)
    base_font_pt = _table_body_font_size_pt(len(normalized_rows)) + safe_font_boost
    header_font = _load_report_font(
        size_px=max(_emu_to_px(Pt(base_font_pt + 0.8)), 12),
        bold=True,
    )

    left_cols = {int(idx) for idx in left_align_cols}
    headers = [str(table.cell(0, cidx).text or "").strip() for cidx in range(col_count)]
    hyperlinks = {
        int(k): str(v).strip() for k, v in dict(hyperlink_by_row or {}).items() if str(v).strip()
    }

    x = 0
    for cidx, cell_w in enumerate(col_widths_px):
        box = (x, 0, x + cell_w, header_h_px)
        draw.rectangle(box, fill=_TABLE_HEADER_BG_RGB, outline=_TABLE_BORDER_RGB, width=2)
        _draw_table_cell_text(
            draw,
            text=headers[cidx],
            font=header_font,
            box=box,
            fill=_TABLE_HEADER_FG_RGB,
            align="left",
        )
        x += cell_w

    y = header_h_px
    for ridx, row_values in enumerate(normalized_rows):
        x = 0
        row_link = hyperlinks.get(ridx, "")
        for cidx, value in enumerate(row_values):
            box = (x, y, x + col_widths_px[cidx], y + body_row_h_px)
            draw.rectangle(box, fill=_TABLE_BODY_BG_RGB, outline=_TABLE_BORDER_RGB, width=2)
            cell_font_pt = base_font_pt
            if description_col_index is not None and cidx == int(description_col_index):
                cell_font_pt = max(base_font_pt - 0.25, 7.0)
            cell_font = _load_report_font(
                size_px=max(_emu_to_px(Pt(cell_font_pt)), 10),
                bold=False,
            )
            _draw_table_cell_text(
                draw,
                text=str(value or ""),
                font=cell_font,
                box=box,
                fill=_TABLE_LINK_RGB if cidx == 0 and row_link else _TABLE_BODY_FG_RGB,
                align="left" if cidx in left_cols else "center",
            )
            x += col_widths_px[cidx]
        y += body_row_h_px

    payload = BytesIO()
    image.save(payload, format="PNG")
    return payload.getvalue()


def _replace_table_with_picture(
    slide: Any,
    *,
    table_shape_index: int,
    rows: Sequence[Sequence[str]],
    description_col_index: int | None = None,
    left_align_cols: Sequence[int] = (),
    hyperlink_by_row: Mapping[int, str] | None = None,
    target_geometry: tuple[int, int, int, int] | None = None,
    font_boost_pt: float = 0.0,
) -> None:
    shape = _shape_table_or_none(slide, table_shape_index)
    if shape is None:
        return

    payload = _table_picture_payload(
        shape,
        rows=rows,
        description_col_index=description_col_index,
        left_align_cols=left_align_cols,
        hyperlink_by_row=hyperlink_by_row,
        font_boost_pt=font_boost_pt,
    )
    if not payload:
        _set_table_rows(
            slide,
            table_shape_index=table_shape_index,
            rows=rows,
            hyperlink_by_row=hyperlink_by_row,
        )
        _tune_table_font(
            slide,
            table_shape_index=table_shape_index,
            data_rows=len(list(rows or [])),
            description_col_index=description_col_index,
        )
        return

    left = int(shape.left)
    top = int(shape.top)
    width = int(shape.width)
    height = int(shape.height)
    if target_geometry is not None:
        try:
            g_left, g_top, g_width, g_height = target_geometry
            if int(g_width) > 0 and int(g_height) > 0:
                left = int(g_left)
                top = int(g_top)
                width = int(g_width)
                height = int(g_height)
        except Exception:
            pass

    slide.shapes.add_picture(
        BytesIO(payload),
        left,
        top,
        width=width,
        height=height,
    )
    _remove_shape(shape)


def _set_paragraph_value_after_colon(
    slide: Any, *, shape_index: int, paragraph_index: int, value: int
) -> None:
    shape = _shape_or_none(slide, shape_index)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    paragraphs = list(shape.text_frame.paragraphs)
    if paragraph_index >= len(paragraphs):
        return
    paragraph = paragraphs[paragraph_index]
    runs = list(paragraph.runs)
    if not runs:
        paragraph.add_run()
        runs = list(paragraph.runs)
    target = runs[1] if len(runs) > 1 else runs[0]
    src = str(getattr(target, "text", "") or "")
    trail_match = re.search(r"\s+$", src)
    trailing = trail_match.group(0) if trail_match is not None else ""
    target.text = f": {int(value)}{trailing}"
    for run in runs[2:]:
        run.text = ""
    _set_shape_text_fit(shape)


def _set_shape_font_size(
    slide: Any,
    *,
    shape_index: int,
    font_size_pt: float,
    bold: bool | None = None,
    disable_autofit: bool = False,
) -> None:
    shape = _shape_or_none(slide, shape_index)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    tf = shape.text_frame
    if disable_autofit:
        try:
            tf.auto_size = MSO_AUTO_SIZE.NONE
        except Exception:
            pass
        try:
            tf.word_wrap = False
        except Exception:
            pass
    for paragraph in list(tf.paragraphs):
        for run in list(paragraph.runs):
            run.font.size = Pt(float(font_size_pt))
            if bold is not None:
                run.font.bold = bool(bold)


def _set_shape_font_color(
    slide: Any,
    *,
    shape_index: int,
    color_rgb: RGBColor,
) -> None:
    shape = _shape_or_none(slide, shape_index)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    tf = shape.text_frame
    for paragraph in list(tf.paragraphs):
        runs = list(paragraph.runs)
        if not runs:
            run = paragraph.add_run()
            runs = [run]
        for run in runs:
            try:
                run.font.color.rgb = color_rgb
            except Exception:
                continue


def _set_table_column_widths(shape: Any, *, weights: Sequence[float]) -> None:
    if shape is None or not getattr(shape, "has_table", False):
        return
    table = shape.table
    cols = list(table.columns)
    if not cols:
        return
    raw_weights = [float(w) for w in list(weights or [])]
    if len(raw_weights) != len(cols) or not any(w > 0 for w in raw_weights):
        return
    total_width = sum(int(getattr(col, "width", 0) or 0) for col in cols)
    if total_width <= 0:
        total_width = int(getattr(shape, "width", 0) or 0)
    if total_width <= 0:
        return
    weight_total = sum(raw_weights)
    col_widths = [
        max(int(round((weight / weight_total) * float(total_width))), 1) for weight in raw_weights
    ]
    col_widths[-1] += int(total_width) - sum(col_widths)
    for col, width in zip(cols, col_widths):
        try:
            col.width = int(width)
        except Exception:
            continue


def _configure_zoom_table_layout(
    slide: Any,
    *,
    table_shape_index: int,
    caption_shape_index: int,
) -> None:
    table_shape = _shape_table_or_none(slide, table_shape_index)
    caption_shape = _shape_or_none(slide, caption_shape_index)
    if table_shape is None:
        return
    if caption_shape is not None:
        try:
            table_shape.left = int(caption_shape.left)
            table_shape.width = int(caption_shape.width)
        except Exception:
            pass
    _set_table_column_widths(table_shape, weights=_ZOOM_TABLE_COLUMN_WEIGHTS)


def _to_roman(value: int) -> str:
    num = max(int(value or 0), 0)
    if num <= 0:
        return ""
    pairs = (
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    )
    out: list[str] = []
    rem = num
    for arabic, roman in pairs:
        while rem >= arabic:
            out.append(roman)
            rem -= arabic
    return "".join(out)


def _chunk_zoom_issues(
    issues: Sequence[FunctionalityIssueRow],
    *,
    rows_per_slide: int,
) -> list[tuple[FunctionalityIssueRow, ...]]:
    size = max(int(rows_per_slide or 0), 1)
    items = list(issues or [])
    if not items:
        return [tuple()]
    chunks: list[tuple[FunctionalityIssueRow, ...]] = []
    for start in range(0, len(items), size):
        chunks.append(tuple(items[start : start + size]))
    return chunks


def _shape_text_frame(
    slide: Any,
    *,
    shape_index: int,
) -> Any | None:
    shape = _shape_or_none(slide, shape_index)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return None
    tf = shape.text_frame
    try:
        tf.auto_size = MSO_AUTO_SIZE.NONE
    except Exception:
        pass
    try:
        tf.word_wrap = True
    except Exception:
        pass
    return tf


def _set_paragraph_single_run(
    paragraph: Any,
    *,
    text: str,
    size_pt: float,
    bold: bool = True,
    italic: bool = False,
    space_before_pt: float = 0.0,
    color_rgb: RGBColor | None = None,
) -> None:
    paragraph.clear()
    run = paragraph.add_run()
    run.text = str(text or "")
    run.font.size = Pt(float(size_pt))
    run.font.bold = bool(bold)
    run.font.italic = bool(italic)
    if color_rgb is not None:
        run.font.color.rgb = color_rgb
    paragraph.space_before = Pt(float(space_before_pt))
    paragraph.space_after = Pt(0)


def _set_paragraph_value_label(
    paragraph: Any,
    *,
    value_text: str,
    label_text: str,
    value_size_pt: float,
    label_size_pt: float,
    color_rgb: RGBColor | None = None,
) -> None:
    paragraph.clear()
    value_run = paragraph.add_run()
    value_run.text = f"{str(value_text)} "
    value_run.font.size = Pt(float(value_size_pt))
    value_run.font.bold = True
    if color_rgb is not None:
        value_run.font.color.rgb = color_rgb
    label_run = paragraph.add_run()
    label_run.text = str(label_text or "")
    label_run.font.size = Pt(float(label_size_pt))
    label_run.font.bold = True
    if color_rgb is not None:
        label_run.font.color.rgb = color_rgb
    paragraph.space_before = Pt(0)
    paragraph.space_after = Pt(0)


def _first_run_color_rgb(shape: Any) -> RGBColor | None:
    if shape is None or not getattr(shape, "has_text_frame", False):
        return None
    for paragraph in list(shape.text_frame.paragraphs):
        for run in list(paragraph.runs):
            color = getattr(getattr(run, "font", None), "color", None)
            rgb = getattr(color, "rgb", None)
            if rgb is not None:
                return cast(RGBColor, rgb)
    return None


def _write_open_criticity_card(
    slide: Any,
    *,
    shape_index: int,
    value: int,
    label: str,
    color_rgb: RGBColor | None = None,
) -> None:
    shape = _shape_or_none(slide, shape_index)
    base_color = color_rgb or _first_run_color_rgb(shape)
    tf = _shape_text_frame(slide, shape_index=shape_index)
    if tf is None:
        return
    tf.clear()
    p0 = tf.paragraphs[0]
    _set_paragraph_single_run(
        p0,
        text=str(int(value)),
        size_pt=35.0,
        bold=True,
        color_rgb=base_color,
    )
    p1 = tf.add_paragraph()
    _set_paragraph_single_run(
        p1,
        text=str(label or "").strip(),
        size_pt=9.5,
        bold=True,
        space_before_pt=0.6,
        color_rgb=base_color,
    )


def _write_metric_card(
    slide: Any,
    *,
    shape_index: int,
    value_text: str,
    label_text: str,
    extra_lines: Sequence[tuple[str, float, bool, bool, float]] | None = None,
    value_size_pt: float = 25.0,
    label_size_pt: float = 12.0,
    text_color_rgb: RGBColor | None = None,
) -> None:
    base_color = text_color_rgb if text_color_rgb is not None else RGBColor(0, 0, 0)
    tf = _shape_text_frame(slide, shape_index=shape_index)
    if tf is None:
        return
    tf.clear()
    p0 = tf.paragraphs[0]
    _set_paragraph_value_label(
        p0,
        value_text=str(value_text or ""),
        label_text=str(label_text or ""),
        value_size_pt=float(value_size_pt),
        label_size_pt=float(label_size_pt),
        color_rgb=base_color,
    )

    for text, size_pt, bold, italic, space_before in list(extra_lines or []):
        p = tf.add_paragraph()
        _set_paragraph_single_run(
            p,
            text=str(text or ""),
            size_pt=float(size_pt),
            bold=bool(bold),
            italic=bool(italic),
            space_before_pt=float(space_before),
            color_rgb=base_color,
        )


def _add_metric_split_column(
    slide: Any,
    *,
    card_shape_index: int,
    top_label: str,
    top_value: int,
    bottom_label: str,
    bottom_value: int,
    value_suffix: str = "",
    text_color_rgb: RGBColor | None = None,
) -> None:
    card = _shape_or_none(slide, card_shape_index)
    if card is None:
        return

    base_color = (
        text_color_rgb
        if text_color_rgb is not None
        else (_first_run_color_rgb(_shape_or_none(slide, 16)) or RGBColor(4, 19, 139))
    )

    left = int(card.left)
    top = int(card.top)
    width = int(card.width)
    height = int(card.height)
    if width <= 0 or height <= 0:
        return

    # Mirror the visual geometry of the "NUEVAS INCIDENCIAS" right column.
    divider_left = left + int(width * 0.636)
    divider_top = top + int(height * 0.094)
    divider_height = int(height * 0.811)
    divider_width = max(int(width * 0.0018), 1)

    divider = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        divider_left,
        divider_top,
        divider_width,
        divider_height,
    )
    divider.fill.solid()
    divider.fill.fore_color.rgb = base_color
    divider.line.fill.background()

    text_left = divider_left + int(width * 0.012)
    text_top = top + int(height * 0.078)
    text_width = max((left + width) - text_left - int(width * 0.040), 1)
    text_height = int(height * 0.845)
    split_box = slide.shapes.add_textbox(text_left, text_top, text_width, text_height)
    tf = split_box.text_frame
    try:
        tf.auto_size = MSO_AUTO_SIZE.NONE
    except Exception:
        pass
    try:
        tf.word_wrap = True
    except Exception:
        pass
    try:
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0
    except Exception:
        pass
    tf.clear()

    p0 = tf.paragraphs[0]
    _set_paragraph_single_run(
        p0,
        text=f"{str(top_label).strip()}: {int(top_value)}{str(value_suffix or '')}",
        size_pt=12.0,
        bold=True,
        color_rgb=base_color,
    )
    p1 = tf.add_paragraph()
    _set_paragraph_single_run(
        p1,
        text=f"{str(bottom_label).strip()}: {int(bottom_value)}{str(value_suffix or '')}",
        size_pt=12.0,
        bold=True,
        color_rgb=base_color,
        space_before_pt=0.3,
    )


def _align_delta_badges_with_new_card(slide: Any) -> None:
    ref_card = _shape_or_none(slide, 15)
    ref_delta = _shape_or_none(slide, 19)
    ref_marker = _shape_or_none(slide, 18)
    if ref_card is None or ref_delta is None or ref_marker is None:
        return
    delta_dx = int(ref_delta.left) - int(ref_card.left)
    delta_dy = int(ref_delta.top) - int(ref_card.top)
    marker_dx = int(ref_marker.left) - int(ref_card.left)
    marker_dy = int(ref_marker.top) - int(ref_card.top)

    for card_idx, delta_idx, marker_idx in ((9, 10, 11), (12, 13, 14)):
        card = _shape_or_none(slide, card_idx)
        delta = _shape_or_none(slide, delta_idx)
        marker = _shape_or_none(slide, marker_idx)
        if card is not None and delta is not None:
            delta.left = int(card.left) + delta_dx
            delta.top = int(card.top) + delta_dy
        if card is not None and marker is not None:
            marker.left = int(card.left) + marker_dx
            marker.top = int(card.top) + marker_dy


def _set_paragraph_level(
    slide: Any,
    *,
    shape_index: int,
    paragraph_index: int,
    level: int,
) -> None:
    shape = _shape_or_none(slide, shape_index)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    paragraphs = list(shape.text_frame.paragraphs)
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        return
    try:
        paragraphs[paragraph_index].level = max(0, int(level))
    except Exception:
        return


def _overlay_picture(
    slide: Any,
    *,
    payload: bytes,
    anchor_shape: Any | None = None,
    anchor_shape_index: int | None = None,
    replace_anchor: bool = False,
) -> Any | None:
    anchor = anchor_shape
    if anchor is None and anchor_shape_index is not None:
        anchor = _shape_or_none(slide, anchor_shape_index)
    if anchor is None:
        return None
    if not payload:
        return None
    rendered = slide.shapes.add_picture(
        BytesIO(payload),
        anchor.left,
        anchor.top,
        width=anchor.width,
        height=anchor.height,
    )
    if replace_anchor:
        _remove_shape(anchor)
    return rendered


def _blank_shape_area(
    slide: Any,
    *,
    anchor_shape: Any | None = None,
    anchor_shape_index: int | None = None,
    replace_anchor: bool = False,
) -> None:
    anchor = anchor_shape
    if anchor is None and anchor_shape_index is not None:
        anchor = _shape_or_none(slide, anchor_shape_index)
    if anchor is None:
        return
    blank = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        anchor.left,
        anchor.top,
        anchor.width,
        anchor.height,
    )
    blank.fill.solid()
    blank.fill.fore_color.rgb = RGBColor(255, 255, 255)
    blank.line.fill.background()
    if replace_anchor:
        _remove_shape(anchor)


def _resolve_summary_chart_anchor(slide: Any) -> Any | None:
    # Prefer the main chart placeholder (largest picture in summary slide).
    picture_shapes = _picture_candidates(slide, min_area_in2=1.0)
    if picture_shapes:
        return max(picture_shapes, key=_shape_area_in2)
    # Backward compatibility with canonical corporate template.
    return _shape_or_none(slide, 20)


def _resolve_evolution_chart_anchors(
    slide: Any,
) -> tuple[Any | None, Any | None, Any | None, List[Any]]:
    """
    Resolve anchors for (backlog, resolution, priority, extras) robustly.

    Uses geometric placement so the renderer does not depend on mutable shape indexes.
    """
    picture_shapes = _picture_candidates(slide, min_area_in2=1.0)
    if len(picture_shapes) >= 3:
        priority_shape = max(picture_shapes, key=lambda s: _shape_center(s)[0])
        remaining = [s for s in picture_shapes if s is not priority_shape]
        backlog_shape = min(remaining, key=lambda s: _shape_center(s)[1]) if remaining else None
        resolution_shape = max(remaining, key=lambda s: _shape_center(s)[1]) if remaining else None
        used = {id(x) for x in (backlog_shape, resolution_shape, priority_shape) if x is not None}
        extras = [shape for shape in picture_shapes if id(shape) not in used]
        return backlog_shape, resolution_shape, priority_shape, extras

    # Fallback to legacy index mapping.
    backlog_shape = _shape_or_none(slide, 7)
    resolution_shape = _shape_or_none(slide, 4)
    priority_shape = _shape_or_none(slide, 9)
    return backlog_shape, resolution_shape, priority_shape, []


def _chart_png(
    settings: Settings, *, dff: pd.DataFrame, open_df: pd.DataFrame, chart_id: str
) -> bytes:
    registry = build_trends_registry()
    spec = registry.get(chart_id)
    if spec is None:
        return b""

    kpis = compute_kpis(dff, settings=settings, include_timeseries_chart=(chart_id == "timeseries"))
    fig = spec.render(ChartContext(dff=dff, open_df=open_df, kpis=kpis))
    if fig is None:
        return b""
    if chart_id == "timeseries":
        margin = getattr(getattr(fig, "layout", None), "margin", None)
        left = int(getattr(margin, "l", 16) or 16)
        right = int(getattr(margin, "r", 16) or 16)
        top = int(getattr(margin, "t", 48) or 48)
        bottom = max(int(getattr(margin, "b", 92) or 92), 144)
        fig.update_layout(
            legend=dict(font=dict(size=18)),
            margin=dict(l=left, r=right, t=top, b=bottom),
        )
    payload = _fig_to_png_exact(fig, width=3400, height=760)
    return payload or b""


def _normalize_lookup_token(value: object) -> str:
    txt = str(value or "").strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r"[^a-z0-9]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _boardroom_snippet(text: str, *, max_chars: int) -> str:
    clean = re.sub(r"\s+", " ", str(text or "").strip())
    if not clean:
        return ""
    first = clean.split(". ")[0].strip()
    if first and len(first) <= max_chars:
        return first if first.endswith(".") else f"{first}."
    return _trim_text(clean, max_chars=max_chars)


def _priority_order_key(value: object) -> tuple[int, str]:
    label = str(value or "").strip()
    return (int(priority_rank(label)), label.lower())


def _format_quincena_boardroom(start_value: object, end_value: object) -> str:
    start = pd.to_datetime(start_value, errors="coerce")
    end = pd.to_datetime(end_value, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return str(start_value or "")
    month_names = (
        "ene",
        "feb",
        "mar",
        "abr",
        "may",
        "jun",
        "jul",
        "ago",
        "sep",
        "oct",
        "nov",
        "dic",
    )
    month = month_names[max(min(int(start.month) - 1, 11), 0)]
    return f"{month} {int(start.day):02d}-{int(end.day):02d}"


def _format_quincena_axis_ym(start_value: object, end_value: object) -> str:
    start = pd.to_datetime(start_value, errors="coerce")
    end = pd.to_datetime(end_value, errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return str(start_value or "")
    return f"{int(start.month):02d} | {int(start.day)}-{int(end.day)}"


def _clear_slide_shapes(slide: Any) -> None:
    for shape in list(getattr(slide, "shapes", [])):
        _remove_shape(shape)


def _fig_to_png_exact(fig: Optional[go.Figure], *, width: int, height: int) -> bytes:
    if fig is None:
        return b""
    try:
        return _kaleido_png_bytes(
            fig_obj=fig,
            scale=2.0,
            export_width=max(int(width), 640),
            export_height=max(int(height), 360),
        )
    except Exception:
        payload = _fig_to_png(fig)
        return payload or b""


def _overlay_picture_contain(
    slide: Any,
    *,
    payload: bytes,
    frame_left: int,
    frame_top: int,
    frame_width: int,
    frame_height: int,
) -> None:
    if not payload:
        return
    try:
        img = Image.open(BytesIO(payload))
        src_w = float(max(int(getattr(img, "width", 1) or 1), 1))
        src_h = float(max(int(getattr(img, "height", 1) or 1), 1))
    except Exception:
        src_w, src_h = 16.0, 9.0

    frame_w = float(max(int(frame_width or 1), 1))
    frame_h = float(max(int(frame_height or 1), 1))
    src_ratio = src_w / src_h
    frame_ratio = frame_w / frame_h

    if frame_ratio >= src_ratio:
        pic_h = frame_h
        pic_w = pic_h * src_ratio
    else:
        pic_w = frame_w
        pic_h = pic_w / src_ratio

    left = int(round(float(frame_left) + (frame_w - pic_w) / 2.0))
    top = int(round(float(frame_top) + (frame_h - pic_h) / 2.0))
    slide.shapes.add_picture(
        BytesIO(payload),
        left,
        top,
        width=int(round(pic_w)),
        height=int(round(pic_h)),
    )


def _add_exec_textbox(
    slide: Any,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    text: str,
    font_size_pt: float,
    color_rgb: RGBColor,
    bold: bool = False,
    align: PP_ALIGN = PP_ALIGN.LEFT,
) -> Any:
    box = slide.shapes.add_textbox(int(left), int(top), int(width), int(height))
    tf = box.text_frame
    tf.clear()
    try:
        tf.auto_size = MSO_AUTO_SIZE.NONE
    except Exception:
        pass
    try:
        tf.word_wrap = True
        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.TOP
        tf.margin_left = 0
        tf.margin_right = 0
        tf.margin_top = 0
        tf.margin_bottom = 0
    except Exception:
        pass
    p = tf.paragraphs[0]
    p.alignment = align
    p.space_before = Pt(0)
    p.space_after = Pt(0)
    run = p.add_run()
    run.text = str(text or "")
    run.font.size = Pt(float(font_size_pt))
    run.font.bold = bool(bold)
    run.font.color.rgb = color_rgb
    return box


def _write_exec_metric_block(
    slide: Any,
    *,
    left: int,
    top: int,
    width: int,
    kicker: str,
    value: str,
) -> None:
    _add_exec_textbox(
        slide,
        left=left,
        top=top,
        width=width,
        height=200_000,
        text=str(kicker or "").upper(),
        font_size_pt=11.4,
        color_rgb=RGBColor(*_EXEC_TEXT_SECONDARY_RGB),
        bold=True,
    )
    _add_exec_textbox(
        slide,
        left=left,
        top=top + 150_000,
        width=width,
        height=290_000,
        text=str(value or "—"),
        font_size_pt=32.0,
        color_rgb=RGBColor(*_EXEC_TEXT_PRIMARY_RGB),
        bold=True,
    )


def _extract_resolution_story_values(
    dff: pd.DataFrame, open_df: pd.DataFrame
) -> tuple[str, str, str]:
    pack = build_trend_insight_pack("resolution_hist", dff=dff, open_df=open_df)
    metric_by_label = {
        _normalize_lookup_token(getattr(metric, "label", "")): str(getattr(metric, "value", "—"))
        for metric in list(getattr(pack, "metrics", []) or [])
    }
    habitual = metric_by_label.get(_normalize_lookup_token("Antigüedad habitual"), "—")
    stalled = metric_by_label.get(_normalize_lookup_token("Casos más atascados"), "—")
    over_30 = metric_by_label.get(_normalize_lookup_token(">30d abiertas"), "—")
    return habitual, stalled, over_30


def _resolution_cards_by_title(dff: pd.DataFrame, open_df: pd.DataFrame) -> Mapping[str, str]:
    pack = build_trend_insight_pack("resolution_hist", dff=dff, open_df=open_df)
    cards = list(getattr(pack, "cards", []) or [])
    cards_by_token: dict[str, str] = {
        _normalize_lookup_token(getattr(card, "title", "")): str(getattr(card, "body", "")).strip()
        for card in cards
    }
    ordered_titles = (
        "Incidencias críticas envejecidas",
        "Brecha por prioridad",
        "Riesgo real de envejecimiento",
        "Cola extrema de antigüedad",
    )
    resolved: dict[str, str] = {}
    for title in ordered_titles:
        token = _normalize_lookup_token(title)
        body = str(cards_by_token.get(token, "") or "").strip()
        if body:
            resolved[title] = body
            continue
        fallback = next(
            (
                str(getattr(card, "body", "") or "").strip()
                for card in cards
                if str(getattr(card, "body", "") or "").strip()
                and str(getattr(card, "title", "") or "").strip() not in resolved
            ),
            "",
        )
        resolved[title] = (
            fallback or "Sin datos suficientes para este insight en el scope seleccionado."
        )
    return resolved


def _resolution_chart_png_executive(
    settings: Settings,
    *,
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
) -> bytes:
    registry = build_trends_registry()
    spec = registry.get("resolution_hist")
    if spec is None:
        return b""
    kpis = compute_kpis(dff, settings=settings, include_timeseries_chart=False)
    fig = spec.render(ChartContext(dff=dff, open_df=open_df, kpis=kpis, dark_mode=False))
    if fig is None:
        return b""

    fig.update_layout(
        width=3200,
        height=620,
        xaxis_title="Rango en días",
        yaxis_title="Incidencias abiertas",
        xaxis=dict(
            tickfont=dict(size=17, color="#1E2C46"),
            title=dict(font=dict(size=20, color="#17253F")),
            gridcolor="rgba(155, 169, 196, 0.22)",
        ),
        yaxis=dict(
            tickfont=dict(size=17, color="#1E2C46"),
            title=dict(font=dict(size=19, color="#17253F")),
            gridcolor="rgba(155, 169, 196, 0.22)",
        ),
        legend=dict(
            title_text="",
            orientation="h",
            xanchor="right",
            x=1.0,
            yanchor="top",
            y=-0.11,
            font=dict(size=16, color="#1A2740"),
            bgcolor="rgba(255,255,255,0.96)",
            bordercolor="rgba(188,198,216,0.95)",
            borderwidth=1,
        ),
        margin=dict(l=48, r=30, t=18, b=86),
        bargap=0.14,
        plot_bgcolor="#F6F8FC",
        paper_bgcolor="#F6F8FC",
    )
    fig.update_traces(
        textposition="inside",
        textfont=dict(size=19, color="#FFFFFF"),
        marker_line_color="#0A2E72",
        marker_line_width=1,
        cliponaxis=False,
    )
    payload = _fig_to_png_exact(fig, width=3600, height=700)
    return payload or b""


def _add_exec_insight_card(
    slide: Any,
    *,
    left: int,
    top: int,
    width: int,
    height: int,
    title: str,
    body: str,
    title_font_size_pt: float = 17.0,
    body_font_size_pt: float = 12.8,
) -> None:
    card = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        int(left),
        int(top),
        int(width),
        int(height),
    )
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(*_EXEC_CARD_BG_RGB)
    card.line.color.rgb = RGBColor(*_EXEC_ACCENT_BORDER_RGB)
    card.line.width = Pt(1.0)

    tf = card.text_frame
    tf.clear()
    try:
        tf.auto_size = MSO_AUTO_SIZE.NONE
    except Exception:
        pass
    try:
        tf.word_wrap = True
        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.TOP
        tf.margin_left = 82_000
        tf.margin_right = 78_000
        tf.margin_top = 48_000
        tf.margin_bottom = 42_000
    except Exception:
        pass

    p0 = tf.paragraphs[0]
    p0.alignment = PP_ALIGN.LEFT
    p0.space_before = Pt(0)
    p0.space_after = Pt(0)
    title_run = p0.add_run()
    title_run.text = f"{str(title or '').strip()} ↗"
    title_run.font.size = Pt(float(title_font_size_pt))
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(*_EXEC_CARD_TITLE_RGB)

    p1 = tf.add_paragraph()
    p1.alignment = PP_ALIGN.LEFT
    p1.space_before = Pt(2.2)
    p1.space_after = Pt(0)
    body_run = p1.add_run()
    body_run.text = str(body or "").strip()
    body_run.font.size = Pt(float(body_font_size_pt))
    body_run.font.bold = False
    body_run.font.color.rgb = RGBColor(*_EXEC_TEXT_PRIMARY_RGB)
    try:
        p1.line_spacing = 1.14
    except Exception:
        pass


def _populate_open_aging_executive_slide(
    slide: Any,
    *,
    settings: Settings,
    scope_result: QuincenalScopeResult,
    slide_width: int,
    slide_height: int,
) -> None:
    _clear_slide_shapes(slide)

    try:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(*_EXEC_BG_RGB)
    except Exception:
        pass

    slide_w = int(slide_width or 9_144_000)
    slide_h = int(slide_height or 5_143_500)
    margin_x = int(slide_w * 0.044)
    content_w = max(slide_w - (2 * margin_x), 1)

    _add_exec_textbox(
        slide,
        left=margin_x,
        top=int(slide_h * 0.036),
        width=content_w,
        height=int(slide_h * 0.103),
        text="Visión agregada de incidencias abiertas : rango de días por prioridad",
        font_size_pt=22.0,
        color_rgb=RGBColor(*_EXEC_TEXT_PRIMARY_RGB),
        bold=True,
    )

    habitual, stalled, over_30 = _extract_resolution_story_values(
        scope_result.dff,
        scope_result.open_df,
    )

    metric_top = int(slide_h * 0.183)
    metric_gap = int(slide_w * 0.018)
    metric_w = int((content_w - (2 * metric_gap)) / 3)
    _write_exec_metric_block(
        slide,
        left=margin_x,
        top=metric_top,
        width=metric_w,
        kicker="Antigüedad habitual",
        value=habitual,
    )
    _write_exec_metric_block(
        slide,
        left=margin_x + metric_w + metric_gap,
        top=metric_top,
        width=metric_w,
        kicker="Casos más atascados",
        value=stalled,
    )
    _write_exec_metric_block(
        slide,
        left=margin_x + (2 * (metric_w + metric_gap)),
        top=metric_top,
        width=metric_w,
        kicker=">30d abiertas",
        value=over_30,
    )

    chart_frame_left = margin_x
    chart_frame_top = int(slide_h * 0.305)
    chart_frame_width = content_w
    chart_frame_height = int(slide_h * 0.322)
    chart_frame = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        chart_frame_left,
        chart_frame_top,
        chart_frame_width,
        chart_frame_height,
    )
    chart_frame.fill.solid()
    chart_frame.fill.fore_color.rgb = RGBColor(247, 248, 252)
    chart_frame.line.color.rgb = RGBColor(*_EXEC_ACCENT_BORDER_RGB)
    chart_frame.line.width = Pt(1.2)

    chart_png = _resolution_chart_png_executive(
        settings,
        dff=scope_result.dff,
        open_df=scope_result.open_df,
    )
    if chart_png:
        _overlay_picture_contain(
            slide,
            payload=chart_png,
            frame_left=chart_frame_left + 190_000,
            frame_top=chart_frame_top + 26_000,
            frame_width=chart_frame_width - 380_000,
            frame_height=chart_frame_height - 52_000,
        )
    else:
        _add_exec_textbox(
            slide,
            left=chart_frame_left + 55_000,
            top=chart_frame_top + int(chart_frame_height * 0.42),
            width=chart_frame_width - 110_000,
            height=300_000,
            text="No hay datos suficientes para renderizar el gráfico de antigüedad por prioridad.",
            font_size_pt=17.0,
            color_rgb=RGBColor(*_EXEC_TEXT_PRIMARY_RGB),
            bold=False,
            align=PP_ALIGN.CENTER,
        )

    insight_text = _resolution_cards_by_title(scope_result.dff, scope_result.open_df)
    cards = [
        (
            "Incidencias críticas envejecidas",
            insight_text.get("Incidencias críticas envejecidas", ""),
        ),
        ("Brecha por prioridad", insight_text.get("Brecha por prioridad", "")),
        ("Riesgo real de envejecimiento", insight_text.get("Riesgo real de envejecimiento", "")),
        ("Cola extrema de antigüedad", insight_text.get("Cola extrema de antigüedad", "")),
    ]

    cards_top = int(slide_h * 0.643)
    cards_gap_x = int(slide_w * 0.021)
    cards_gap_y = int(slide_h * 0.017)
    card_w = int((content_w - cards_gap_x) / 2)
    card_h = int((slide_h - cards_top - cards_gap_y - int(slide_h * 0.018)) / 2)
    card_h = max(card_h, int(slide_h * 0.13))
    coords = [
        (margin_x, cards_top),
        (margin_x + card_w + cards_gap_x, cards_top),
        (margin_x, cards_top + card_h + cards_gap_y),
        (margin_x + card_w + cards_gap_x, cards_top + card_h + cards_gap_y),
    ]
    for (left, top), (title, body) in zip(coords, cards):
        _add_exec_insight_card(
            slide,
            left=left,
            top=top,
            width=card_w,
            height=card_h,
            title=title,
            body=_boardroom_snippet(body, max_chars=118),
            title_font_size_pt=12.6,
            body_font_size_pt=9.6,
        )


def _extract_priority_story_values(
    dff: pd.DataFrame, open_df: pd.DataFrame
) -> tuple[str, str, str]:
    pack = build_trend_insight_pack("open_priority_pie", dff=dff, open_df=open_df)
    metric_by_label = {
        _normalize_lookup_token(getattr(metric, "label", "")): str(getattr(metric, "value", "—"))
        for metric in list(getattr(pack, "metrics", []) or [])
    }
    total = metric_by_label.get(_normalize_lookup_token("Total abiertas"), "—")
    dominant = metric_by_label.get(_normalize_lookup_token("Prioridad dominante"), "—")
    weighted = metric_by_label.get(_normalize_lookup_token("Riesgo ponderado"), "—")
    return total, dominant, weighted


def _priority_cards_by_title(dff: pd.DataFrame, open_df: pd.DataFrame) -> Mapping[str, str]:
    pack = build_trend_insight_pack("open_priority_pie", dff=dff, open_df=open_df)
    cards = list(getattr(pack, "cards", []) or [])
    cards_by_token: dict[str, str] = {
        _normalize_lookup_token(getattr(card, "title", "")): str(getattr(card, "body", "")).strip()
        for card in cards
    }
    ordered_titles = (
        "Inflación de prioridades altas",
        "Concentración de prioridad",
        "Incidencias de mayor impacto con antigüedad elevada",
        "Incidencias de mayor impacto sin arrancar",
        "Incidencias de mayor impacto sin movimiento reciente",
    )
    resolved: dict[str, str] = {}
    for title in ordered_titles:
        token = _normalize_lookup_token(title)
        body = str(cards_by_token.get(token, "") or "").strip()
        if body:
            resolved[title] = body
            continue
        fallback = next(
            (
                str(getattr(card, "body", "") or "").strip()
                for card in cards
                if str(getattr(card, "body", "") or "").strip()
                and str(getattr(card, "title", "") or "").strip() not in resolved
            ),
            "",
        )
        resolved[title] = (
            fallback or "Sin datos suficientes para este insight en el scope seleccionado."
        )
    return resolved


def _priority_chart_png_executive(
    settings: Settings,
    *,
    dff: pd.DataFrame,
    open_df: pd.DataFrame,
) -> bytes:
    _ = settings
    safe_open = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    if safe_open.empty:
        safe_open = dff if isinstance(dff, pd.DataFrame) else pd.DataFrame()
    if safe_open.empty:
        return b""

    if "priority" not in safe_open.columns:
        return b""

    work = safe_open.copy(deep=False)
    work["priority"] = normalize_text_col(work["priority"], "(sin priority)")
    counts = work["priority"].value_counts(dropna=False)
    if counts.empty:
        return b""
    labels = sorted([str(x) for x in counts.index.tolist()], key=_priority_order_key)
    values = [int(counts.get(label, 0)) for label in labels]
    total = max(sum(values), 1)
    color_map = {
        "supone un impedimento": "#8B0000",
        "highest": "#B51F29",
        "high": "#D64C4C",
        "medium": "#F2A529",
        "low": "#2FA84F",
        "lowest": "#1E8C45",
        "(sin priority)": "#7E8EA7",
    }
    fig = go.Figure()
    percentages: list[float] = []
    for label, value in zip(labels, values):
        color = color_map.get(str(label).strip().lower(), "#4A7BD1")
        pct = (value / total) * 100.0 if total else 0.0
        percentages.append(pct)
        fig.add_trace(
            go.Bar(
                x=[label],
                y=[value],
                marker=dict(color=color, line=dict(color="#0A2E72", width=1)),
                text=[str(value) if value > 0 else ""],
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(size=26, color="#FFFFFF"),
                cliponaxis=False,
                hovertemplate="Prioridad: %{x}<br>Incidencias: %{y}<extra></extra>",
                name=str(label),
                showlegend=False,
            )
        )
    max_value = max(values) if values else 1
    top_offset = max(max_value * 0.075, 2.2)
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=[float(v) + top_offset for v in values],
            mode="text",
            text=[f"{pct:.1f}%" if val > 0 else "" for pct, val in zip(percentages, values)],
            textposition="top center",
            textfont=dict(size=28, color="#0C376E"),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.update_layout(
        width=3200,
        height=620,
        xaxis=dict(
            tickfont=dict(size=18, color="#1E2C46"),
            gridcolor="rgba(155, 169, 196, 0.22)",
            categoryorder="array",
            categoryarray=labels,
            title="",
        ),
        yaxis=dict(
            tickfont=dict(size=18, color="#1E2C46"),
            gridcolor="rgba(155, 169, 196, 0.22)",
            range=[0, (max_value + top_offset) * 1.12 if values else 1.0],
            title="",
        ),
        uniformtext=dict(minsize=20, mode="show"),
        bargap=0.38,
        showlegend=False,
        margin=dict(l=36, r=24, t=28, b=58),
        plot_bgcolor="#F6F8FC",
        paper_bgcolor="#F6F8FC",
    )
    payload = _fig_to_png_exact(fig, width=3400, height=760)
    return payload or b""


def _populate_open_priority_executive_slide(
    slide: Any,
    *,
    settings: Settings,
    scope_result: QuincenalScopeResult,
    slide_width: int,
    slide_height: int,
) -> None:
    _clear_slide_shapes(slide)
    try:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(*_EXEC_BG_RGB)
    except Exception:
        pass

    slide_w = int(slide_width or 9_144_000)
    slide_h = int(slide_height or 5_143_500)
    margin_x = int(slide_w * 0.044)
    content_w = max(slide_w - (2 * margin_x), 1)

    _add_exec_textbox(
        slide,
        left=margin_x,
        top=int(slide_h * 0.031),
        width=content_w,
        height=int(slide_h * 0.068),
        text="Visión agregada de incidencias abiertas por prioridad",
        font_size_pt=24.0,
        color_rgb=RGBColor(*_EXEC_TEXT_PRIMARY_RGB),
        bold=True,
    )

    chart_frame_left = margin_x
    chart_frame_top = int(slide_h * 0.105)
    chart_frame_width = content_w
    chart_frame_height = int(slide_h * 0.43)
    chart_frame = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        chart_frame_left,
        chart_frame_top,
        chart_frame_width,
        chart_frame_height,
    )
    chart_frame.fill.solid()
    chart_frame.fill.fore_color.rgb = RGBColor(247, 248, 252)
    chart_frame.line.color.rgb = RGBColor(*_EXEC_ACCENT_BORDER_RGB)
    chart_frame.line.width = Pt(1.2)

    chart_png = _priority_chart_png_executive(
        settings,
        dff=scope_result.dff,
        open_df=scope_result.open_df,
    )
    if chart_png:
        _overlay_picture_contain(
            slide,
            payload=chart_png,
            frame_left=chart_frame_left + 190_000,
            frame_top=chart_frame_top + 26_000,
            frame_width=chart_frame_width - 380_000,
            frame_height=chart_frame_height - 52_000,
        )
    else:
        _add_exec_textbox(
            slide,
            left=chart_frame_left + 55_000,
            top=chart_frame_top + int(chart_frame_height * 0.42),
            width=chart_frame_width - 110_000,
            height=300_000,
            text="No hay datos suficientes para renderizar la distribución de prioridad.",
            font_size_pt=17.0,
            color_rgb=RGBColor(*_EXEC_TEXT_PRIMARY_RGB),
            bold=False,
            align=PP_ALIGN.CENTER,
        )

    insight_text = _priority_cards_by_title(scope_result.dff, scope_result.open_df)
    cards = [
        ("Inflación de prioridades altas", insight_text.get("Inflación de prioridades altas", "")),
        ("Concentración de prioridad", insight_text.get("Concentración de prioridad", "")),
        (
            "Incidencias de mayor impacto con antigüedad elevada",
            insight_text.get("Incidencias de mayor impacto con antigüedad elevada", ""),
        ),
        (
            "Incidencias de mayor impacto sin movimiento reciente",
            insight_text.get("Incidencias de mayor impacto sin movimiento reciente", ""),
        ),
        (
            "Incidencias de mayor impacto sin arrancar",
            insight_text.get("Incidencias de mayor impacto sin arrancar", ""),
        ),
    ]

    cards_top = int(slide_h * 0.547)
    cards_gap_x = int(slide_w * 0.021)
    cards_gap_y = int(slide_h * 0.010)
    card_w = int((content_w - cards_gap_x) / 2)
    card_h = int(slide_h * 0.135)
    _add_exec_insight_card(
        slide,
        left=margin_x,
        top=cards_top,
        width=card_w,
        height=card_h,
        title=cards[0][0],
        body=re.sub(r"\s+", " ", str(cards[0][1] or "").strip()),
        title_font_size_pt=12.0,
        body_font_size_pt=8.35,
    )
    _add_exec_insight_card(
        slide,
        left=margin_x + card_w + cards_gap_x,
        top=cards_top,
        width=card_w,
        height=card_h,
        title=cards[2][0],
        body=re.sub(r"\s+", " ", str(cards[2][1] or "").strip()),
        title_font_size_pt=11.8,
        body_font_size_pt=8.2,
    )
    _add_exec_insight_card(
        slide,
        left=margin_x,
        top=cards_top + card_h + cards_gap_y,
        width=card_w,
        height=card_h,
        title=cards[1][0],
        body=re.sub(r"\s+", " ", str(cards[1][1] or "").strip()),
        title_font_size_pt=12.0,
        body_font_size_pt=8.35,
    )
    _add_exec_insight_card(
        slide,
        left=margin_x + card_w + cards_gap_x,
        top=cards_top + card_h + cards_gap_y,
        width=card_w,
        height=card_h,
        title=cards[3][0],
        body=re.sub(r"\s+", " ", str(cards[3][1] or "").strip()),
        title_font_size_pt=11.8,
        body_font_size_pt=8.2,
    )
    full_card_top = cards_top + (2 * (card_h + cards_gap_y))
    full_card_h = max(slide_h - full_card_top - int(slide_h * 0.022), int(slide_h * 0.075))
    _add_exec_insight_card(
        slide,
        left=margin_x,
        top=full_card_top,
        width=content_w,
        height=full_card_h,
        title=cards[4][0],
        body=re.sub(r"\s+", " ", str(cards[4][1] or "").strip()),
        title_font_size_pt=12.0,
        body_font_size_pt=8.35,
    )


def _populate_summary_slide(slide: Any, *, title: str, scope_result: QuincenalScopeResult) -> None:
    summary = scope_result.summary
    _set_shape_text(slide, 3, title)
    _set_paragraph_value_after_colon(
        slide, shape_index=16, paragraph_index=0, value=int(summary.new_before)
    )
    _set_paragraph_value_after_colon(
        slide, shape_index=16, paragraph_index=1, value=int(summary.new_now)
    )
    _set_paragraph_value_after_colon(
        slide, shape_index=16, paragraph_index=2, value=int(summary.new_accumulated)
    )
    _set_shape_text(slide, 10, _fmt_delta_pct(summary.closed_delta_pct))
    _set_shape_text(slide, 13, _fmt_delta_pct(summary.resolution_delta_pct))
    _set_shape_text(slide, 19, _fmt_delta_pct(summary.new_delta_pct))
    focus_split_label = (
        "MAESTRAS"
        if str(summary.open_group_mode or "").strip() == OPEN_ISSUES_FOCUS_MODE_MAESTRAS
        else "ALTAS"
    )
    _write_open_criticity_card(
        slide,
        shape_index=4,
        value=int(summary.open_total),
        label="INCIDENCIAS ABIERTAS EN TOTAL",
        color_rgb=RGBColor(255, 255, 255),
    )
    _write_open_criticity_card(
        slide,
        shape_index=5,
        value=int(summary.open_focus_total),
        label=str(summary.open_focus_report_label),
    )
    _write_open_criticity_card(
        slide,
        shape_index=6,
        value=int(summary.open_other_total),
        label=str(summary.open_other_report_label),
    )

    _write_metric_card(
        slide,
        shape_index=15,
        value_text=str(int(summary.new_now)),
        label_text="NUEVA INCIDENCIA" if int(summary.new_now) == 1 else "NUEVAS INCIDENCIAS",
    )
    _write_metric_card(
        slide,
        shape_index=9,
        value_text=str(int(summary.closed_now)),
        label_text="INCIDENCIA CERRADA" if int(summary.closed_now) == 1 else "INCIDENCIAS CERRADAS",
    )
    _add_metric_split_column(
        slide,
        card_shape_index=9,
        top_label=str(focus_split_label),
        top_value=int(summary.closed_focus_now),
        bottom_label="RESTO",
        bottom_value=int(summary.closed_other_now),
    )
    _write_metric_card(
        slide,
        shape_index=12,
        value_text=str(_fmt_days(summary.resolution_days_now)),
        label_text="DÍAS DE RESOLUCIÓN",
        extra_lines=[
            ("(EN PROMEDIO)", 9.5, True, True, 0.6),
        ],
    )
    _set_paragraph_level(slide, shape_index=12, paragraph_index=1, level=1)
    _add_metric_split_column(
        slide,
        card_shape_index=12,
        top_label="MAX",
        top_value=int(_fmt_days(summary.resolution_days_max_now)),
        bottom_label="MIN",
        bottom_value=int(_fmt_days(summary.resolution_days_min_now)),
        value_suffix=" días",
    )

    _set_shape_font_size(slide, shape_index=10, font_size_pt=14.0, bold=True)
    _set_shape_font_size(slide, shape_index=13, font_size_pt=14.0, bold=True)
    _set_shape_font_size(slide, shape_index=19, font_size_pt=14.0, bold=True)
    _align_delta_badges_with_new_card(slide)


def _populate_evolution_slide(
    slide: Any,
    *,
    title: str,
    backlog_png: bytes,
    resolution_png: bytes,
    priority_png: bytes,
) -> None:
    _set_shape_text(slide, 2, title)
    backlog_anchor, resolution_anchor, priority_anchor, extra_anchors = (
        _resolve_evolution_chart_anchors(slide)
    )
    _overlay_picture(slide, anchor_shape=backlog_anchor, payload=backlog_png, replace_anchor=True)
    _overlay_picture(
        slide, anchor_shape=resolution_anchor, payload=resolution_png, replace_anchor=True
    )
    _overlay_picture(slide, anchor_shape=priority_anchor, payload=priority_png, replace_anchor=True)

    # If template includes extra chart slots, blank them for now.
    for extra in extra_anchors:
        _blank_shape_area(slide, anchor_shape=extra, replace_anchor=True)


def _update_cover_period(slide: Any, *, period_label: str) -> None:
    candidates: list[tuple[int, Any]] = []
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        text = str(getattr(shape, "text", "") or "")
        lower = text.lower()
        if "periodo" not in lower:
            continue

        score = 0
        # Main template placeholder: "Periodo dd/mm - dd/mm yyyy".
        if "dd/mm" in lower:
            score += 100
        if lower.strip().startswith("periodo"):
            score += 20

        # Corporate cover period ribbon is yellow and sits in lower area.
        try:
            fill = shape.fill
            if int(fill.type or 0) == 1:
                rgb = getattr(fill.fore_color, "rgb", None)
                if rgb is not None:
                    score += 40 if int(getattr(rgb, "blue", 255)) < 170 else 0
        except Exception:
            pass
        try:
            score += int(int(shape.top) / 100000)
        except Exception:
            pass

        # Avoid replacing explanatory subtitle "...análisis del periodo".
        if "kpi" in lower or "análisis" in lower or "analisis" in lower:
            score -= 30
        candidates.append((score, shape))

    if not candidates:
        return
    target = max(candidates, key=lambda item: item[0])[1]
    if not getattr(target, "has_text_frame", False):
        return

    tf = target.text_frame
    sample_run = None
    try:
        sample_run = tf.paragraphs[0].runs[0]
    except Exception:
        sample_run = None

    tf.clear()
    paragraph = tf.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = str(period_label or "").strip()

    if sample_run is not None:
        try:
            run.font.bold = sample_run.font.bold
        except Exception:
            pass
        try:
            run.font.italic = sample_run.font.italic
        except Exception:
            pass
        try:
            run.font.name = sample_run.font.name
        except Exception:
            pass
        try:
            rgb = getattr(getattr(sample_run.font, "color", None), "rgb", None)
            if rgb is not None:
                run.font.color.rgb = rgb
        except Exception:
            pass

    # Keep the period text readable and centered inside the yellow ribbon.
    run.font.size = Pt(15.0)
    try:
        tf.vertical_anchor = MSO_VERTICAL_ANCHOR.MIDDLE
    except Exception:
        pass
    try:
        tf.word_wrap = False
    except Exception:
        pass
    try:
        tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    except Exception:
        pass


def _fmt_avg_days(value: float) -> str:
    if pd.isna(value):
        return "0"
    safe = max(float(value or 0.0), 0.0)
    return str(int(round(safe)))


def _top_row_line(row: FunctionalityTopRow) -> str:
    count = int(row.new_count or 0)
    count_txt = "incidencia nueva" if count == 1 else "incidencias nuevas"
    line = (
        f"{count} {count_txt} en {str(row.functionality or '').strip()} "
        f"(acumuladas {int(row.open_total or 0)})"
    )
    return _trim_text(line, max_chars=72)


def _root_cause_caption(zoom: FunctionalityZoomSlide, *, critical_wording: bool) -> str:
    issue_count = int(zoom.current_open_critical_count or 0)
    if issue_count <= 0:
        if critical_wording:
            return "Sin incidencias críticas abiertas de la quincena para esta funcionalidad."
        return "Sin incidencias abiertas de la quincena para esta funcionalidad."

    roots = [
        item
        for item in list(zoom.root_causes or [])
        if str(getattr(item, "label", "") or "").strip().lower() != "sin detalle suficiente"
    ]
    if not roots:
        return f"{issue_count} incidencias sin señal suficiente de causa raíz predominante."

    if len(roots) == 1:
        item = roots[0]
        cause = str(getattr(item, "label", "") or "").strip() or "Sin detalle"
        qty = int(getattr(item, "count", 0) or 0)
        noun = "incidencia" if qty == 1 else "incidencias"
        verb = "fue causada" if qty == 1 else "fueron causadas"
        return f"{qty} {noun} {verb} por {cause}."

    chunks: list[str] = []
    for item in roots:
        count = int(getattr(item, "count", 0) or 0)
        cause = str(getattr(item, "label", "") or "").strip() or "Sin detalle"
        chunks.append(f"{count} por {cause}")
    if len(chunks) == 2:
        detail = f"{chunks[0]} y {chunks[1]}"
    else:
        detail = ", ".join(chunks[:-1]) + f" y {chunks[-1]}"
    return f"Causas raíz detectadas: {detail}."


def _functionality_dashboard_table_target_geometry(
    slide: Any,
    *,
    table_shape_index: int,
) -> tuple[int, int, int, int] | None:
    table_shape = _shape_table_or_none(slide, table_shape_index)
    if table_shape is None:
        return None

    left = int(table_shape.left)
    top = int(table_shape.top)
    width = int(table_shape.width)
    height = int(table_shape.height)
    if width <= 0 or height <= 0:
        return None

    top_anchor_indexes = (2, 4, 5, 6, 8, 10)
    top_anchor_bottom = 0
    for idx in top_anchor_indexes:
        anchor = _shape_or_none(slide, idx)
        if anchor is None:
            continue
        top_anchor_bottom = max(top_anchor_bottom, int(anchor.top) + int(anchor.height))

    guard_top = max(top_anchor_bottom + _FUNCTIONALITY_TABLE_TOP_GUARD_EMU, 0)
    proposed_top = top - max(int(round(height * _FUNCTIONALITY_TABLE_TOP_SHIFT_RATIO)), 1)
    new_top = max(proposed_top, guard_top)
    if new_top >= top:
        return None
    delta = top - new_top
    return (left, new_top, width, height + delta)


def _populate_functionality_dashboard_slide(
    slide: Any,
    *,
    summary: PeriodFunctionalityFollowupSummary,
) -> None:
    critical_wording = bool(getattr(summary, "is_critical_focus", False))
    table_rows: list[list[str]] = []
    for row in list(summary.tail_rows or []):
        table_rows.append(
            [
                str(int(row.rank)),
                str(row.functionality or ""),
                str(int(row.new_count or 0)),
                str(int(row.open_total or 0)),
            ]
        )

    _set_shape_text(
        slide,
        2,
        (
            "Top tres de las incidencias por funcionalidad identificadas en la "
            f"{str(summary.period_label or '').replace('Quincena ', 'quincena ')}"
        ),
    )
    _set_shape_text_strict(
        slide,
        5,
        (
            f"{int(summary.total_open_critical)} INCIDENCIAS CRÍTICAS\nABIERTAS"
            if critical_wording
            else f"{int(summary.total_open_critical)} INCIDENCIAS\nABIERTAS"
        ),
    )
    _set_shape_font_color(slide, shape_index=5, color_rgb=RGBColor(255, 255, 255))

    top_rows = list(summary.top_rows or [])
    top_shapes = (6, 8, 10)
    for idx, shape_idx in enumerate(top_shapes):
        if idx < len(top_rows):
            _set_shape_text(slide, shape_idx, _top_row_line(top_rows[idx]))
        else:
            _set_shape_text(slide, shape_idx, "Sin incidencias nuevas para esta posición.")

    _set_shape_text_strict(
        slide,
        13,
        (
            "Incidencias en la quincena en ready to verify: "
            f"{int(summary.mitigation_ready_to_verify.count)} / "
            f"{_fmt_avg_days(summary.mitigation_ready_to_verify.avg_open_days)} días promedio"
        ),
    )
    _set_shape_text_strict(
        slide,
        19,
        (
            "Incidencias en New: "
            f"{int(summary.mitigation_new.count)} / "
            f"{_fmt_avg_days(summary.mitigation_new.avg_open_days)} días promedio"
        ),
    )
    _set_shape_text_strict(
        slide,
        20,
        (
            (
                "Incidencias críticas bloqueadas: "
                if critical_wording
                else "Incidencias bloqueadas: "
            )
            + f"{int(summary.mitigation_blocked.count)} / "
            f"{_fmt_avg_days(summary.mitigation_blocked.avg_open_days)} días promedio"
        ),
    )
    _set_shape_text_strict(
        slide,
        21,
        (
            "Resto de incidencias: "
            f"{int(summary.mitigation_non_critical.count)} / "
            f"{_fmt_avg_days(summary.mitigation_non_critical.avg_open_days)} días promedio"
        ),
    )
    _set_shape_font_color(slide, shape_index=18, color_rgb=RGBColor(255, 255, 255))
    table_target_geometry = _functionality_dashboard_table_target_geometry(
        slide,
        table_shape_index=1,
    )
    _replace_table_with_picture(
        slide,
        table_shape_index=1,
        rows=table_rows,
        description_col_index=1,
        left_align_cols=(1,),
        target_geometry=table_target_geometry,
        font_boost_pt=_FUNCTIONALITY_TABLE_FONT_BOOST_PT,
    )


def _populate_functionality_zoom_slide(
    slide: Any,
    *,
    zoom: FunctionalityZoomSlide,
    critical_wording: bool,
    issues_page: Sequence[FunctionalityIssueRow] | None = None,
    page_number: int = 1,
    total_pages: int = 1,
) -> None:
    functionality = str(zoom.functionality or "").strip() or "Sin funcionalidad"
    page_suffix = ""
    if int(total_pages or 0) > 1:
        roman = _to_roman(int(page_number or 1))
        page_suffix = f" ({roman})" if roman else f" ({int(page_number or 1)})"
    _set_shape_text(
        slide,
        1,
        f"Incidencias, en {functionality}, abiertas en la quincena{page_suffix}",
    )
    _set_shape_text(
        slide,
        3,
        _trim_text(_root_cause_caption(zoom, critical_wording=critical_wording), max_chars=200),
    )
    _set_shape_font_color(slide, shape_index=3, color_rgb=RGBColor(*_TABLE_BODY_FG_RGB))
    _set_shape_text(
        slide,
        4,
        "Zoom de incidencias críticas del periodo:"
        if critical_wording
        else "Zoom de incidencias del periodo:",
    )

    _configure_zoom_table_layout(slide, table_shape_index=2, caption_shape_index=3)

    page_issues = list(issues_page if issues_page is not None else zoom.issues or [])
    rows: list[list[str]] = []
    row_links: dict[int, str] = {}
    for idx, issue in enumerate(page_issues):
        rows.append(
            [
                str(issue.key or ""),
                _trim_text(str(issue.summary or "").replace("/", " / "), max_chars=260),
                _trim_text(str(issue.root_cause or "").replace("/", " / "), max_chars=120),
                _trim_text(str(issue.status or ""), max_chars=48),
                _trim_text(str(issue.priority or ""), max_chars=28),
                f"{int(issue.open_days or 0)} días",
            ]
        )
        if str(issue.url or "").strip():
            row_links[idx] = str(issue.url).strip()
    _set_table_rows(
        slide,
        table_shape_index=2,
        rows=rows,
        hyperlink_by_row=row_links,
        left_align_cols=(0, 1, 2),
        min_row_height_emu=300_000,
    )
    _tune_table_font(
        slide,
        table_shape_index=2,
        data_rows=len(rows),
        description_col_index=1,
    )


def _functionality_fortnight_trend_png(*, open_df: pd.DataFrame) -> bytes:
    safe_open = open_df if isinstance(open_df, pd.DataFrame) else pd.DataFrame()
    if safe_open.empty:
        return b""

    trend = build_theme_fortnight_trend(safe_open, cumulative=True)
    if not isinstance(trend, pd.DataFrame) or trend.empty:
        return b""

    raw_axis_labels = trend["quincena_label"].dropna().astype(str).drop_duplicates().tolist()
    if not raw_axis_labels:
        return b""
    axis_meta = (
        trend.loc[:, ["quincena_label", "quincena_start", "quincena_end"]]
        .drop_duplicates(subset=["quincena_label"])
        .copy(deep=False)
    )
    axis_meta["axis_label"] = [
        _format_quincena_axis_ym(start, end)
        for start, end in zip(axis_meta["quincena_start"], axis_meta["quincena_end"])
    ]
    axis_label_map = {
        str(raw): str(lbl) for raw, lbl in zip(axis_meta["quincena_label"], axis_meta["axis_label"])
    }
    axis_labels = [axis_label_map.get(lbl, lbl) for lbl in raw_axis_labels]

    theme_totals = (
        trend.groupby("tema", dropna=False)["issues_value"]
        .max()
        .sort_values(ascending=False)
        .fillna(0)
    )
    ordered_themes = order_theme_labels_by_volume(
        theme_totals.index.tolist(),
        counts_by_label=theme_totals,
        others_last=True,
    )
    ordering = build_theme_render_order(
        ordered_themes,
        counts_by_label=theme_totals,
        others_last=True,
        others_at_x_axis=True,
    )
    legend_order = list(ordering.display_order)
    stack_order = list(ordering.stack_order_bottom_to_top)
    if not legend_order or not stack_order:
        return b""
    theme_color_map = build_theme_color_map(theme_order=legend_order, dark_mode=False)

    trend_local = trend.copy(deep=False)
    trend_local["axis_label"] = [
        axis_label_map.get(str(lbl), str(lbl)) for lbl in trend_local["quincena_label"].tolist()
    ]
    totals = (
        trend_local.groupby("axis_label", dropna=False)["issues_value"]
        .sum()
        .reindex(axis_labels)
        .fillna(0)
        .astype(int)
    )
    fig = go.Figure()
    legend_rank = {theme: idx for idx, theme in enumerate(legend_order)}
    for theme in stack_order:
        sub = trend_local.loc[trend_local["tema"].eq(theme)].copy(deep=False)
        values_series = (
            pd.to_numeric(sub.get("issues_value"), errors="coerce")
            .fillna(0.0)
            .groupby(sub.get("axis_label"))
            .sum()
            .reindex(axis_labels)
            .fillna(0.0)
        )
        values = values_series.astype(float).tolist()
        value_text = [str(int(v)) if float(v) >= 4 else "" for v in values]
        color_hex = str(theme_color_map.get(theme) or "#7784A0")
        text_color = "#FFFFFF"
        if _normalize_lookup_token(theme) in {
            _normalize_lookup_token("Monetarias"),
            _normalize_lookup_token("Transferencias"),
            _normalize_lookup_token("Softoken"),
        }:
            text_color = "#0B1F3B"
        fig.add_trace(
            go.Bar(
                x=axis_labels,
                y=values,
                name=str(theme),
                marker=dict(color=color_hex, line=dict(color="#F2F5FA", width=0.8)),
                text=value_text,
                textposition="inside",
                textfont=dict(size=13.5, color=text_color),
                legendrank=int(legend_rank.get(theme, len(legend_rank))),
                customdata=[[int(totals.get(lbl, 0))] for lbl in axis_labels],
                hovertemplate=(
                    "Tema: %{fullData.name}<br>Quincena: %{x}<br>"
                    "Incidencias abiertas acumuladas: %{y}<br>"
                    "Total columna: %{customdata[0]}<extra></extra>"
                ),
            )
        )

    max_total = float(totals.max()) if not totals.empty else 0.0
    total_offset = max(max_total * 0.062, 0.20)
    fig.add_trace(
        go.Scatter(
            x=axis_labels,
            y=[float(v) + total_offset for v in totals.tolist()],
            mode="text",
            text=[str(int(v)) for v in totals.tolist()],
            textposition="top center",
            textfont=dict(size=19, color="#0B3E76"),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        width=1980,
        height=940,
        barmode="stack",
        bargap=0.19,
        margin=dict(l=52, r=42, t=24, b=172),
        xaxis_title="Quincena",
        yaxis_title="Incidencias abiertas acumuladas",
        hovermode="x",
        uniformtext=dict(minsize=11, mode="hide"),
        plot_bgcolor="#F6F8FC",
        paper_bgcolor="#F6F8FC",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.30,
            xanchor="center",
            x=0.5,
            title=dict(text=""),
            bgcolor="rgba(255,255,255,0.96)",
            bordercolor="rgba(188,198,216,0.95)",
            borderwidth=1,
            font=dict(size=15, color="#1A2740"),
            traceorder="normal",
        ),
    )
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=axis_labels,
        tickangle=0,
        tickfont=dict(size=11.2, color="#1E2C46"),
        automargin=True,
        gridcolor="rgba(155, 169, 196, 0.22)",
    )
    fig.update_yaxes(
        range=[0, max_total + (total_offset * 2.5) if max_total > 0 else 1.0],
        tickfont=dict(size=14, color="#1E2C46"),
        title_font=dict(size=20, color="#17253F"),
        gridcolor="rgba(155, 169, 196, 0.24)",
    )

    payload = _fig_to_png(fig)
    return payload or b""


def _populate_functionality_trend_aggregate_slide(
    slide: Any,
    *,
    open_df: pd.DataFrame,
    slide_width: int,
    slide_height: int,
) -> None:
    _clear_slide_shapes(slide)

    try:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(247, 248, 248)
    except Exception:
        pass

    slide_w = int(slide_width or 9_144_000)
    slide_h = int(slide_height or 5_143_500)
    margin_x = int(slide_w * 0.032)
    content_w = max(slide_w - (2 * margin_x), 1)

    _add_exec_textbox(
        slide,
        left=margin_x,
        top=int(slide_h * 0.03),
        width=content_w,
        height=int(slide_h * 0.065),
        text="Tendencia por funcionalidad : vista agregada",
        font_size_pt=30.0,
        color_rgb=RGBColor(0, 19, 70),
        bold=True,
    )

    frame_left = margin_x
    frame_top = int(slide_h * 0.11)
    frame_width = content_w
    frame_height = max(slide_h - frame_top - int(slide_h * 0.03), int(slide_h * 0.80))
    frame = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        frame_left,
        frame_top,
        frame_width,
        frame_height,
    )
    frame.fill.solid()
    frame.fill.fore_color.rgb = RGBColor(247, 248, 252)
    frame.line.color.rgb = RGBColor(214, 220, 232)
    frame.line.width = Pt(1.0)

    chart_png = _functionality_fortnight_trend_png(open_df=open_df)
    if chart_png:
        _overlay_picture_contain(
            slide,
            payload=chart_png,
            frame_left=frame_left + 34_000,
            frame_top=frame_top + 30_000,
            frame_width=frame_width - 68_000,
            frame_height=frame_height - 56_000,
        )
    else:
        _add_exec_textbox(
            slide,
            left=frame_left + 60_000,
            top=frame_top + 2_450_000,
            width=frame_width - 120_000,
            height=290_000,
            text="No hay datos suficientes para construir la tendencia acumulada por funcionalidad.",
            font_size_pt=16.0,
            color_rgb=RGBColor(56, 67, 92),
            bold=False,
            align=PP_ALIGN.CENTER,
        )


def _append_functionality_followup_slides(
    prs: Any,
    *,
    summary: PeriodFunctionalityFollowupSummary,
    period_label: str,
    open_df: pd.DataFrame,
    slide_width: int,
    slide_height: int,
) -> None:
    critical_wording = bool(getattr(summary, "is_critical_focus", False))
    template_path = _resolve_functionality_template_path()
    template_prs = Presentation(str(template_path))
    if len(template_prs.slides) < 5:
        raise ValueError(
            "La plantilla de funcionalidad debe contener 5 slides (cabecera + dashboard + 3 zoom)."
        )

    header_slide = _append_slide_clone_from_source(prs, source_slide=template_prs.slides[0])
    trend_slide = _append_slide_clone_from_source(prs, source_slide=template_prs.slides[1])
    dashboard_slide = _append_slide_clone_from_source(prs, source_slide=template_prs.slides[1])
    zoom_template_slide = template_prs.slides[2]

    # Slide 1 (cabecera funcionalidad)
    _set_shape_text(header_slide, 3, str(period_label or "").strip())
    _set_shape_text(
        header_slide,
        2,
        (
            "Detalle, de las incidencias críticas, abiertas por funcionalidad"
            if critical_wording
            else "Detalle, de las incidencias, abiertas por funcionalidad"
        ),
    )

    # Slide 2 (tendencia funcionalidad agregada)
    _populate_functionality_trend_aggregate_slide(
        trend_slide,
        open_df=open_df,
        slide_width=slide_width,
        slide_height=slide_height,
    )

    # Slide 3 (dashboard funcionalidad)
    _set_shape_text(
        dashboard_slide,
        3,
        (
            "Seguimiento de KPIs - Incidencias críticas abiertas por funcionalidad"
            if critical_wording
            else "Seguimiento de KPIs - Incidencias abiertas por funcionalidad"
        ),
    )
    _populate_functionality_dashboard_slide(dashboard_slide, summary=summary)

    # Zoom de top 3 funcionalidades con paginado por overflow.
    zooms = list(summary.zoom_slides or [])
    while len(zooms) < 3:
        zooms.append(
            FunctionalityZoomSlide(
                functionality=f"Sin funcionalidad {len(zooms) + 1}",
                current_open_critical_count=0,
                root_causes=(),
                issues=(),
            )
        )
    zooms = zooms[:3]

    zoom_page_specs: list[
        tuple[FunctionalityZoomSlide, tuple[FunctionalityIssueRow, ...], int, int]
    ] = []
    for zoom in zooms:
        pages = _chunk_zoom_issues(
            tuple(getattr(zoom, "issues", ()) or ()),
            rows_per_slide=_ZOOM_TABLE_ROWS_PER_SLIDE,
        )
        total_pages = len(pages)
        for page_idx, page_rows in enumerate(pages, start=1):
            zoom_page_specs.append((zoom, page_rows, page_idx, total_pages))

    zoom_target_slides = [
        _append_slide_clone_from_source(prs, source_slide=zoom_template_slide)
        for _ in zoom_page_specs
    ]
    for target_slide, spec in zip(zoom_target_slides, zoom_page_specs):
        zoom, page_rows, page_idx, total_pages = spec
        _populate_functionality_zoom_slide(
            target_slide,
            zoom=zoom,
            critical_wording=critical_wording,
            issues_page=page_rows,
            page_number=page_idx,
            total_pages=total_pages,
        )


def _load_or_scope_data(
    settings: Settings,
    *,
    country: str,
    source_ids: Sequence[str],
    dff_override: pd.DataFrame | None,
    open_df_override: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if dff_override is not None:
        dff = dff_override.copy(deep=False)
    else:
        base_df = load_issues_df(settings.DATA_PATH)
        scoped = scope_country_sources(base_df, country=country, source_ids=source_ids)
        dff = apply_analysis_depth_filter(scoped, settings=settings)

    if open_df_override is not None:
        open_df = open_df_override.copy(deep=False)
    else:
        closed_mask = effective_closed_mask(dff)
        open_df = dff.loc[~closed_mask].copy(deep=False)
    return dff, open_df


def generate_country_period_followup_ppt(
    settings: Settings,
    *,
    country: str,
    source_ids: Sequence[str],
    dff_override: pd.DataFrame | None = None,
    open_df_override: pd.DataFrame | None = None,
    template_path: str | None = None,
    applied_filter_summary: str = "",
    functionality_status_filters: Sequence[str] | None = None,
    functionality_priority_filters: Sequence[str] | None = None,
    functionality_filters: Sequence[str] | None = None,
) -> PeriodFollowupReportResult:
    clean_source_ids = _clean_source_ids(source_ids)
    if len(clean_source_ids) < 2:
        raise ValueError(
            "El informe de seguimiento requiere dos orígenes configurados para el país seleccionado."
        )
    clean_source_ids = clean_source_ids[:2]

    country_txt = str(country or "").strip()
    dff, open_df = _load_or_scope_data(
        settings,
        country=country_txt,
        source_ids=clean_source_ids,
        dff_override=dff_override,
        open_df_override=open_df_override,
    )
    if dff.empty:
        raise ValueError("No hay incidencias para generar el informe de seguimiento.")

    labels = source_label_map(settings, country=country_txt, source_ids=clean_source_ids)
    quincenal = build_country_quincenal_result(
        df=dff,
        settings=settings,
        country=country_txt,
        source_ids=clean_source_ids,
        source_label_by_id=labels,
    )
    template = _resolve_template_path(settings, explicit_path=template_path)
    prs = Presentation(str(template))

    # Normalize user template into canonical 8-slide structure.
    _normalize_period_template(prs)

    aggregate = quincenal.aggregate
    source_a_id, source_b_id = clean_source_ids[0], clean_source_ids[1]
    source_a = quincenal.by_source[source_a_id]
    source_b = quincenal.by_source[source_b_id]
    source_a_label = labels.get(source_a_id, source_a_id)
    source_b_label = labels.get(source_b_id, source_b_id)

    _update_cover_period(prs.slides[0], period_label=format_window_label(aggregate.summary.window))
    _populate_summary_slide(
        prs.slides[2],
        title=f"Seguimiento de incidencias - {country_txt.upper()} (vista agregada)",
        scope_result=aggregate,
    )
    _populate_summary_slide(
        prs.slides[3],
        title=f"Seguimiento de incidencias - {source_a_label.split('·')[0].strip().upper()}",
        scope_result=source_a,
    )
    _populate_summary_slide(
        prs.slides[4],
        title=f"Seguimiento de incidencias - {source_b_label.split('·')[0].strip().upper()}",
        scope_result=source_b,
    )

    _overlay_picture(
        prs.slides[2],
        anchor_shape=_resolve_summary_chart_anchor(prs.slides[2]),
        payload=_chart_png(
            settings, dff=aggregate.dff, open_df=aggregate.open_df, chart_id="timeseries"
        ),
        replace_anchor=True,
    )
    _overlay_picture(
        prs.slides[3],
        anchor_shape=_resolve_summary_chart_anchor(prs.slides[3]),
        payload=_chart_png(
            settings, dff=source_a.dff, open_df=source_a.open_df, chart_id="timeseries"
        ),
        replace_anchor=True,
    )
    _overlay_picture(
        prs.slides[4],
        anchor_shape=_resolve_summary_chart_anchor(prs.slides[4]),
        payload=_chart_png(
            settings, dff=source_b.dff, open_df=source_b.open_df, chart_id="timeseries"
        ),
        replace_anchor=True,
    )

    _populate_open_aging_executive_slide(
        prs.slides[6],
        settings=settings,
        scope_result=aggregate,
        slide_width=int(prs.slide_width),
        slide_height=int(prs.slide_height),
    )
    _populate_open_priority_executive_slide(
        prs.slides[7],
        settings=settings,
        scope_result=aggregate,
        slide_width=int(prs.slide_width),
        slide_height=int(prs.slide_height),
    )

    functionality_followup = build_period_functionality_followup_summary(
        scope_result=aggregate,
        jira_base_url=str(getattr(settings, "JIRA_BASE_URL", "") or "").strip(),
        status_filters=list(functionality_status_filters or []),
        priority_filters=list(functionality_priority_filters or []),
        functionality_filters=list(functionality_filters or []),
        apply_default_status_when_empty=True,
        top_n=3,
        top_root_causes=3,
    )
    _append_functionality_followup_slides(
        prs,
        summary=functionality_followup,
        period_label=functionality_followup.period_label,
        open_df=aggregate.open_df,
        slide_width=int(prs.slide_width),
        slide_height=int(prs.slide_height),
    )

    buff = BytesIO()
    prs.save(buff)
    content = buff.getvalue()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    file_name = (
        f"seguimiento-{_slug(country_txt)}-{_slug(source_a_id)}-{_slug(source_b_id)}-{stamp}.pptx"
    )
    total_issues = int(len(aggregate.dff))
    open_issues = int(len(aggregate.open_df))
    closed_issues = max(total_issues - open_issues, 0)
    return PeriodFollowupReportResult(
        file_name=file_name,
        content=content,
        slide_count=len(prs.slides),
        total_issues=total_issues,
        open_issues=open_issues,
        closed_issues=closed_issues,
        country=country_txt,
        source_ids=tuple(clean_source_ids),
        applied_filter_summary=str(applied_filter_summary or "").strip(),
    )
