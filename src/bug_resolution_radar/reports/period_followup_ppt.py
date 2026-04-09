"""Template-based fortnight follow-up PPT report."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, List, Mapping, Sequence, cast

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Pt

from bug_resolution_radar.analytics.analysis_window import apply_analysis_depth_filter
from bug_resolution_radar.analytics.kpis import compute_kpis
from bug_resolution_radar.analytics.period_functionality_followup import (
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
from bug_resolution_radar.reports.executive_ppt import _fig_to_png
from bug_resolution_radar.ui.common import load_issues_df
from bug_resolution_radar.ui.dashboard.registry import ChartContext, build_trends_registry

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
_REPORT_FONT_DIR = (
    Path(__file__).resolve().parent.parent / "ui" / "assets" / "fonts" / "bbva"
).resolve()
_REPORT_FONT_BOOK_PATH = _REPORT_FONT_DIR / "BentonSansBBVA-Book.ttf"
_REPORT_FONT_BOLD_PATH = _REPORT_FONT_DIR / "BentonSansBBVA-Bold.ttf"


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
    if shape is None or not getattr(shape, "has_table", False):
        return None
    return shape


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


def _set_table_cell_text(cell: Any, text: str, *, hyperlink: str = "") -> None:
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
    runs = list(p0.runs)
    if not runs:
        p0.add_run()
        runs = list(p0.runs)
    run = runs[0]
    run.text = str(text or "")
    try:
        if hyperlink:
            run.hyperlink.address = str(hyperlink)
        elif getattr(run, "hyperlink", None) is not None:
            run.hyperlink.address = None
    except Exception:
        pass
    for extra in runs[1:]:
        extra.text = ""

    for extra_paragraph in paragraphs[1:]:
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


def _set_table_rows(
    slide: Any,
    *,
    table_shape_index: int,
    rows: Sequence[Sequence[str]],
    hyperlink_by_row: Mapping[int, str] | None = None,
) -> None:
    shape = _shape_table_or_none(slide, table_shape_index)
    if shape is None:
        return

    table = shape.table
    col_count = len(table.columns)
    normalized_rows = [list(row)[:col_count] for row in list(rows or [])]
    if not normalized_rows:
        normalized_rows = [[""] * col_count]
    normalized_rows = [row + ([""] * (col_count - len(row))) for row in normalized_rows]

    tbl_xml = table._tbl
    tr_elements = list(getattr(tbl_xml, "tr_lst", []))
    if len(tr_elements) < 2:
        return
    template_tr = deepcopy(tr_elements[1])
    for tr in tr_elements[1:]:
        tbl_xml.remove(tr)

    for _ in normalized_rows:
        tbl_xml.append(deepcopy(template_tr))

    # Compact rows so all issues fit in the visual container.
    total_rows = len(normalized_rows) + 1  # header + data
    if total_rows > 1:
        header_h = int(table.rows[0].height or max(int(shape.height / total_rows), 1))
        remaining_h = max(int(shape.height) - header_h, 1)
        row_h = max(int(remaining_h / max(len(normalized_rows), 1)), 1)
        for ridx in range(1, len(table.rows)):
            try:
                table.rows[ridx].height = row_h
            except Exception:
                continue

    hyperlinks = dict(hyperlink_by_row or {})
    for ridx, row_values in enumerate(normalized_rows, start=1):
        row_link = str(hyperlinks.get(ridx - 1, "") or "").strip()
        for cidx, value in enumerate(row_values):
            _set_table_cell_text(
                table.cell(ridx, cidx),
                str(value or ""),
                hyperlink=row_link if cidx == 0 else "",
            )


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

    base_font_pt = _table_body_font_size_pt(len(normalized_rows))
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
                cell_font_pt = max(base_font_pt - 0.4, 7.0)
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
        text=f"{str(top_label).strip()}: {int(top_value)}",
        size_pt=12.0,
        bold=True,
        color_rgb=base_color,
    )
    p1 = tf.add_paragraph()
    _set_paragraph_single_run(
        p1,
        text=f"{str(bottom_label).strip()}: {int(bottom_value)}",
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
    payload = _fig_to_png(fig)
    return payload or b""


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
        top_label=str(focus_split_label),
        top_value=int(summary.resolved_focus_now),
        bottom_label="RESTO",
        bottom_value=int(summary.resolved_other_now),
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
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        text = str(getattr(shape, "text", "") or "")
        if "Periodo" not in text and "periodo" not in text:
            continue
        _set_shape_text_by_shape(shape, str(period_label or "").strip())
        return


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
            f"{int(summary.total_open_critical)} INCIDENCIAS CRÍTICAS  | ABIERTAS"
            if critical_wording
            else f"{int(summary.total_open_critical)} INCIDENCIAS  | ABIERTAS"
        ),
    )

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
    _replace_table_with_picture(
        slide,
        table_shape_index=1,
        rows=table_rows,
        description_col_index=1,
        left_align_cols=(1,),
    )


def _populate_functionality_zoom_slide(
    slide: Any,
    *,
    zoom: FunctionalityZoomSlide,
    critical_wording: bool,
) -> None:
    functionality = str(zoom.functionality or "").strip() or "Sin funcionalidad"
    _set_shape_text(
        slide,
        1,
        f"Incidencias, en {functionality}, abiertas en la quincena",
    )
    _set_shape_text(
        slide,
        3,
        _trim_text(_root_cause_caption(zoom, critical_wording=critical_wording), max_chars=200),
    )
    _set_shape_text(
        slide,
        4,
        "Zoom de incidencias críticas del periodo:"
        if critical_wording
        else "Zoom de incidencias del periodo:",
    )

    rows: list[list[str]] = []
    row_links: dict[int, str] = {}
    for idx, issue in enumerate(list(zoom.issues or [])):
        rows.append(
            [
                str(issue.key or ""),
                _trim_text(issue.summary, max_chars=120),
                _trim_text(issue.root_cause, max_chars=42),
                _trim_text(issue.status, max_chars=20),
                _trim_text(issue.priority, max_chars=14),
                f"{int(issue.open_days or 0)} días",
            ]
        )
        if str(issue.url or "").strip():
            row_links[idx] = str(issue.url).strip()

    table_shape = _shape_table_or_none(slide, 2)
    caption_shape = _shape_or_none(slide, 3)
    target_geometry: tuple[int, int, int, int] | None = None
    if table_shape is not None and caption_shape is not None:
        try:
            target_geometry = (
                int(caption_shape.left),
                int(table_shape.top),
                int(caption_shape.width),
                int(table_shape.height),
            )
        except Exception:
            target_geometry = None

    _replace_table_with_picture(
        slide,
        table_shape_index=2,
        rows=rows,
        description_col_index=1,
        left_align_cols=(0, 1, 2),
        hyperlink_by_row=row_links,
        target_geometry=target_geometry,
    )


def _append_functionality_followup_slides(
    prs: Any,
    *,
    summary: PeriodFunctionalityFollowupSummary,
    period_label: str,
) -> None:
    critical_wording = bool(getattr(summary, "is_critical_focus", False))
    template_path = _resolve_functionality_template_path()
    template_prs = Presentation(str(template_path))
    if len(template_prs.slides) < 5:
        raise ValueError(
            "La plantilla de funcionalidad debe contener 5 slides (cabecera + dashboard + 3 zoom)."
        )

    appended: list[Any] = []
    for source_slide in template_prs.slides:
        appended.append(_append_slide_clone_from_source(prs, source_slide=source_slide))

    # Slide 1 (cabecera funcionalidad)
    _set_shape_text(appended[0], 3, str(period_label or "").strip())
    _set_shape_text(
        appended[0],
        2,
        (
            "Detalle, de las incidencias críticas, abiertas por funcionalidad"
            if critical_wording
            else "Detalle, de las incidencias, abiertas por funcionalidad"
        ),
    )

    # Slide 2 (dashboard funcionalidad)
    _set_shape_text(
        appended[1],
        3,
        (
            "Seguimiento de KPIs - Incidencias críticas por funcionalidad"
            if critical_wording
            else "Seguimiento de KPIs - Incidencias por funcionalidad"
        ),
    )
    _populate_functionality_dashboard_slide(appended[1], summary=summary)

    # Slides 3-5 (zoom top 3)
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
    for idx in range(3):
        _populate_functionality_zoom_slide(
            appended[idx + 2],
            zoom=zooms[idx],
            critical_wording=critical_wording,
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
        title=f"Seguimiento de incidencias - {country_txt.upper()}",
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

    _populate_evolution_slide(
        prs.slides[6],
        title=f"Seguimiento de KPIs - {source_a_label.split('·')[0].strip().upper()}",
        backlog_png=_chart_png(
            settings,
            dff=source_a.dff,
            open_df=source_a.open_df,
            chart_id="age_buckets",
        ),
        resolution_png=_chart_png(
            settings,
            dff=source_a.dff,
            open_df=source_a.open_df,
            chart_id="resolution_hist",
        ),
        priority_png=_chart_png(
            settings,
            dff=source_a.dff,
            open_df=source_a.open_df,
            chart_id="open_priority_pie",
        ),
    )
    _populate_evolution_slide(
        prs.slides[7],
        title=f"Seguimiento de KPIs - {source_b_label.split('·')[0].strip().upper()}",
        backlog_png=_chart_png(
            settings,
            dff=source_b.dff,
            open_df=source_b.open_df,
            chart_id="age_buckets",
        ),
        resolution_png=_chart_png(
            settings,
            dff=source_b.dff,
            open_df=source_b.open_df,
            chart_id="resolution_hist",
        ),
        priority_png=_chart_png(
            settings,
            dff=source_b.dff,
            open_df=source_b.open_df,
            chart_id="open_priority_pie",
        ),
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
