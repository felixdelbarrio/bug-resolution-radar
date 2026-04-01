"""Template-based fortnight follow-up PPT report."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, List, Sequence

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE, MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Pt

from bug_resolution_radar.analytics.analysis_window import apply_analysis_depth_filter
from bug_resolution_radar.analytics.kpis import compute_kpis
from bug_resolution_radar.analytics.period_summary import (
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
_FIRST_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


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


def _set_first_number(slide: Any, *, shape_index: int, value: int) -> None:
    shape = _shape_or_none(slide, shape_index)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    replacement = str(int(value))
    for paragraph in list(shape.text_frame.paragraphs):
        for run in list(paragraph.runs):
            src = str(getattr(run, "text", "") or "")
            if not _FIRST_NUMBER_RE.search(src):
                continue
            run.text = _FIRST_NUMBER_RE.sub(replacement, src, count=1)
            _set_shape_text_fit(shape)
            return
    source = str(getattr(shape, "text", "") or "")
    if _FIRST_NUMBER_RE.search(source):
        _set_shape_text_by_shape(shape, _FIRST_NUMBER_RE.sub(replacement, source, count=1))


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


def _set_label_run(slide: Any, *, shape_index: int, paragraph_index: int, text: str) -> None:
    shape = _shape_or_none(slide, shape_index)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    paragraphs = list(shape.text_frame.paragraphs)
    if paragraph_index >= len(paragraphs):
        return
    paragraph = paragraphs[paragraph_index]
    runs = list(paragraph.runs)
    if len(runs) < 2:
        _set_shape_text_by_shape(shape, str(text or ""))
        return
    label_txt = str(text or "")
    if len(runs) >= 3 and not str(getattr(runs[1], "text", "") or "").strip():
        runs[1].text = " "
        runs[2].text = label_txt
        for run in runs[3:]:
            run.text = ""
    else:
        runs[1].text = label_txt
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
    payload = _fig_to_png(fig)
    return payload or b""


def _populate_summary_slide(slide: Any, *, title: str, scope_result: QuincenalScopeResult) -> None:
    summary = scope_result.summary
    _set_shape_text(slide, 3, title)
    _set_first_number(slide, shape_index=4, value=int(summary.open_total))
    _set_first_number(slide, shape_index=5, value=int(summary.open_focus_total))
    _set_first_number(slide, shape_index=6, value=int(summary.open_other_total))
    _set_label_run(
        slide,
        shape_index=5,
        paragraph_index=0,
        text=str(summary.open_focus_report_label),
    )
    _set_label_run(
        slide,
        shape_index=6,
        paragraph_index=0,
        text=str(summary.open_other_report_label),
    )
    _set_first_number(slide, shape_index=9, value=int(summary.closed_now))
    _set_first_number(slide, shape_index=12, value=_fmt_days(summary.resolution_days_now))
    _set_first_number(slide, shape_index=15, value=int(summary.new_now))
    _set_label_run(
        slide,
        shape_index=9,
        paragraph_index=0,
        text="INCIDENCIA CERRADA" if int(summary.closed_now) == 1 else "INCIDENCIAS CERRADAS",
    )
    _set_label_run(
        slide,
        shape_index=15,
        paragraph_index=0,
        text="NUEVA INCIDENCIA" if int(summary.new_now) == 1 else "NUEVAS INCIDENCIAS",
    )
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
    _set_shape_font_size(slide, shape_index=10, font_size_pt=14.0, bold=True)
    _set_shape_font_size(slide, shape_index=13, font_size_pt=14.0, bold=True)
    _set_shape_font_size(slide, shape_index=19, font_size_pt=14.0, bold=True)


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
