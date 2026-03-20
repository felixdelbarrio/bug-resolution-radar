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
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

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
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.0f}%"


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


def _set_shape_text(slide: Any, index_1_based: int, text: str) -> None:
    shape = _shape_or_none(slide, index_1_based)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    shape.text = str(text or "")


def _set_run_text(
    slide: Any,
    *,
    shape_index: int,
    paragraph_index: int,
    run_index: int,
    text: str,
) -> None:
    shape = _shape_or_none(slide, shape_index)
    if shape is None or not getattr(shape, "has_text_frame", False):
        return
    paragraphs = list(shape.text_frame.paragraphs)
    if paragraph_index >= len(paragraphs):
        return
    runs = list(paragraphs[paragraph_index].runs)
    if run_index >= len(runs):
        return
    runs[run_index].text = str(text or "")


def _overlay_picture(slide: Any, *, anchor_shape_index: int, payload: bytes) -> None:
    anchor = _shape_or_none(slide, anchor_shape_index)
    if anchor is None:
        return
    if not payload:
        return
    slide.shapes.add_picture(
        BytesIO(payload),
        anchor.left,
        anchor.top,
        width=anchor.width,
        height=anchor.height,
    )


def _blank_shape_area(slide: Any, *, anchor_shape_index: int) -> None:
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


def _chart_png(
    settings: Settings, *, dff: pd.DataFrame, open_df: pd.DataFrame, chart_id: str
) -> bytes:
    registry = build_trends_registry()
    spec = registry.get(chart_id)
    if spec is None:
        return b""

    kpis = compute_kpis(dff, settings=settings, include_timeseries_chart=False)
    fig = spec.render(ChartContext(dff=dff, open_df=open_df, kpis=kpis))
    if fig is None:
        return b""
    payload = _fig_to_png(fig)
    return payload or b""


def _populate_summary_slide(slide: Any, *, title: str, scope_result: QuincenalScopeResult) -> None:
    summary = scope_result.summary
    _set_shape_text(slide, 3, title)

    _set_run_text(
        slide, shape_index=4, paragraph_index=0, run_index=0, text=str(summary.open_total)
    )
    _set_run_text(
        slide,
        shape_index=5,
        paragraph_index=0,
        run_index=0,
        text=str(summary.maestras_total),
    )
    _set_run_text(
        slide,
        shape_index=6,
        paragraph_index=0,
        run_index=0,
        text=f"{summary.others_total} ",
    )

    _set_run_text(
        slide,
        shape_index=9,
        paragraph_index=0,
        run_index=0,
        text=f"{summary.closed_now} ",
    )
    closed_label = "INCIDENCIA CERRADA" if int(summary.closed_now) == 1 else "INCIDENCIAS CERRADAS"
    _set_run_text(slide, shape_index=9, paragraph_index=0, run_index=1, text=closed_label)
    _set_shape_text(slide, 10, _fmt_delta_pct(summary.closed_delta_pct))

    days_now = _fmt_days(summary.resolution_days_now)
    _set_run_text(slide, shape_index=12, paragraph_index=0, run_index=0, text=f"{days_now} ")
    day_label = "DÍA DE RESOLUCIÓN " if days_now == 1 else "DÍAS DE RESOLUCIÓN "
    _set_run_text(slide, shape_index=12, paragraph_index=0, run_index=1, text=day_label)
    _set_shape_text(slide, 13, _fmt_delta_pct(summary.resolution_delta_pct))

    _set_run_text(
        slide,
        shape_index=15,
        paragraph_index=0,
        run_index=0,
        text=f"{summary.new_now} ",
    )
    new_label = "NUEVA INCIDENCIA" if int(summary.new_now) == 1 else "NUEVAS INCIDENCIAS"
    _set_run_text(slide, shape_index=15, paragraph_index=0, run_index=1, text=new_label)
    _set_run_text(
        slide,
        shape_index=16,
        paragraph_index=0,
        run_index=1,
        text=f": {summary.new_before}",
    )
    _set_run_text(
        slide,
        shape_index=16,
        paragraph_index=1,
        run_index=1,
        text=f": {summary.new_now}            ",
    )
    _set_run_text(
        slide,
        shape_index=16,
        paragraph_index=2,
        run_index=1,
        text=f": {summary.new_accumulated}",
    )
    _set_shape_text(slide, 19, _fmt_delta_pct(summary.new_delta_pct))


def _populate_evolution_slide(
    slide: Any,
    *,
    title: str,
    backlog_png: bytes,
    resolution_png: bytes,
    priority_png: bytes,
) -> None:
    _set_shape_text(slide, 2, title)
    _overlay_picture(slide, anchor_shape_index=7, payload=backlog_png)
    _overlay_picture(slide, anchor_shape_index=4, payload=resolution_png)
    _overlay_picture(slide, anchor_shape_index=9, payload=priority_png)

    # Requested: do not include client-type chart for now.
    _set_shape_text(slide, 6, "")
    _blank_shape_area(slide, anchor_shape_index=6)
    _blank_shape_area(slide, anchor_shape_index=8)


def _update_cover_period(slide: Any, *, period_label: str) -> None:
    for shape in slide.shapes:
        if not getattr(shape, "has_text_frame", False):
            continue
        text = str(getattr(shape, "text", "") or "")
        if "Periodo" not in text and "periodo" not in text:
            continue
        shape.text = str(period_label or "").strip()
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

    # Keep only: cover + dashboard header + 3 resumen slides + evolución header + 2 evolución slides.
    _remove_slide(prs, 1)  # Remove explanatory helper slide.
    if len(prs.slides) >= 8:
        _copy_slide_content(prs, source_index=6, target_index=7)
    else:
        _append_slide_clone(prs, source_index=6)
    while len(prs.slides) > 8:
        _remove_slide(prs, 8)

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
        anchor_shape_index=20,
        payload=_chart_png(
            settings, dff=aggregate.dff, open_df=aggregate.open_df, chart_id="open_priority_pie"
        ),
    )
    _overlay_picture(
        prs.slides[3],
        anchor_shape_index=20,
        payload=_chart_png(
            settings, dff=source_a.dff, open_df=source_a.open_df, chart_id="open_priority_pie"
        ),
    )
    _overlay_picture(
        prs.slides[4],
        anchor_shape_index=20,
        payload=_chart_png(
            settings, dff=source_b.dff, open_df=source_b.open_df, chart_id="open_priority_pie"
        ),
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
