from __future__ import annotations

import base64
import re
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn

from bug_resolution_radar.config import Settings, bundled_period_ppt_template_path
from bug_resolution_radar.reports import generate_country_period_followup_ppt
from bug_resolution_radar.reports import period_followup_ppt as period_ppt_mod
from bug_resolution_radar.reports.period_followup_layout import metric_card_typography
from bug_resolution_radar.theme.design_tokens import (
    BBVA_REPORT_AMBER_BG,
    BBVA_REPORT_RED_BG,
    EXEC_CHART_AXIS_FONT_PT,
    EXEC_CHART_EXPORT_HEIGHT,
    EXEC_CHART_EXPORT_WIDTH,
    EXEC_CHART_INSIDE_VALUE_FONT_PT,
    EXEC_CHART_LEGEND_FONT_PT,
    EXEC_CHART_TOTAL_FONT_PT,
    EXEC_CHART_TREND_EXPORT_HEIGHT,
    hex_to_rgb,
)


def _build_minimal_template(path: Path) -> None:
    prs = Presentation()
    for idx in range(9):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        if idx == 0:
            tb = slide.shapes.add_textbox(0, 0, 4_000_000, 600_000)
            tb.text = "Periodo dd/mm - dd/mm 2026"
        else:
            tb = slide.shapes.add_textbox(0, 0, 4_000_000, 600_000)
            tb.text = f"Slide {idx + 1}"
    prs.save(str(path))


def _build_compact_template(path: Path) -> None:
    prs = Presentation()
    for idx in range(7):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        tb = slide.shapes.add_textbox(0, 0, 4_000_000, 600_000)
        if idx == 0:
            tb.text = "Periodo dd/mm - dd/mm 2026"
        elif idx == 1:
            tb.text = "Dashboard de KPIs"
        elif idx in (2, 3, 4):
            tb.text = "Seguimiento de incidencias - Resumen ejecutivo"
        elif idx == 5:
            tb.text = "Gráficos de evolución"
        else:
            tb.text = "Seguimiento de KPIs - Gráficos"
    prs.save(str(path))


def _slide_text(slide: Any) -> str:
    return " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in slide.shapes
        if getattr(shape, "has_text_frame", False)
    )


def _slide_table_text(slide: Any) -> str:
    chunks: list[str] = []
    for shape in slide.shapes:
        if not getattr(shape, "has_table", False):
            continue
        table = shape.table
        for row in table.rows:
            for cell in row.cells:
                chunks.append(str(cell.text or ""))
    return " ".join(chunks)


def _slide_all_text(slide: Any) -> str:
    return f"{_slide_text(slide)} {_slide_table_text(slide)}".strip()


def _find_slide_index(prs: Presentation, needle: str) -> int:
    for idx, slide in enumerate(prs.slides):
        if needle in _slide_all_text(slide):
            return idx
    raise AssertionError(f"No slide contains {needle!r}")


def _native_tables(slide: Any) -> list[Any]:
    return [shape for shape in slide.shapes if getattr(shape, "has_table", False)]


def _table_intersects_picture(slide: Any, table_shape: Any) -> bool:
    table_left = int(getattr(table_shape, "left", 0) or 0)
    table_top = int(getattr(table_shape, "top", 0) or 0)
    table_right = table_left + int(getattr(table_shape, "width", 0) or 0)
    table_bottom = table_top + int(getattr(table_shape, "height", 0) or 0)
    for shape in slide.shapes:
        if getattr(shape, "shape_type", None) != MSO_SHAPE_TYPE.PICTURE:
            continue
        left = int(getattr(shape, "left", 0) or 0)
        top = int(getattr(shape, "top", 0) or 0)
        right = left + int(getattr(shape, "width", 0) or 0)
        bottom = top + int(getattr(shape, "height", 0) or 0)
        if left < table_right and right > table_left and top < table_bottom and bottom > table_top:
            return True
    return False


def _assert_native_table_font_floor(table_shape: Any) -> None:
    table = table_shape.table
    for ridx, row in enumerate(table.rows):
        min_size = 8.0 if ridx == 0 else 9.0
        for cell in row.cells:
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    if not str(getattr(run, "text", "") or "").strip():
                        continue
                    assert run.font.name in {"Arial", "Aptos"}
                    assert run.font.size is not None
                    assert float(run.font.size.pt) >= min_size


def test_generate_country_period_followup_ppt_with_minimal_template(tmp_path: Path) -> None:
    template = tmp_path / "template.pptx"
    _build_minimal_template(template)

    now = pd.Timestamp("2026-03-15T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Issue A",
                "status": "New",
                "priority": "High",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
                "source_type": "jira",
            },
            {
                "key": "B-1",
                "summary": "Issue B",
                "status": "Resolved",
                "priority": "Medium",
                "created": (now - pd.Timedelta(days=10)).isoformat(),
                "updated": now.isoformat(),
                "resolved": (now - pd.Timedelta(days=1)).isoformat(),
                "country": "México",
                "source_id": "jira:mexico:gema",
                "source_type": "jira",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(template))

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )

    assert out.slide_count == 15
    assert out.total_issues == 2
    assert out.open_issues == 1
    assert out.closed_issues == 1
    assert out.content
    prs = Presentation(BytesIO(out.content))
    assert len(prs.slides) == 15
    deck_text = " ".join(_slide_text(slide) for slide in prs.slides)
    assert "Incidencias abiertas por criticidad alta" in deck_text
    assert "Incidencias abiertas con más de 30 días" in deck_text
    dashboard_idx = _find_slide_index(
        prs, "Seguimiento de KPIs - Incidencias abiertas por funcionalidad"
    )
    # Functional follow-up slides must preserve light background from source template.
    bg_fill = prs.slides[dashboard_idx].background.fill
    assert int(bg_fill.type or 0) == 1
    assert bg_fill.fore_color.rgb == RGBColor(247, 248, 248)


def test_generate_country_period_followup_ppt_with_compact_template(tmp_path: Path) -> None:
    template = tmp_path / "compact-template.pptx"
    _build_compact_template(template)

    now = pd.Timestamp("2026-03-15T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Issue A",
                "status": "New",
                "priority": "High",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
                "source_type": "jira",
            },
            {
                "key": "B-1",
                "summary": "Issue B",
                "status": "Resolved",
                "priority": "Medium",
                "created": (now - pd.Timedelta(days=10)).isoformat(),
                "updated": now.isoformat(),
                "resolved": (now - pd.Timedelta(days=1)).isoformat(),
                "country": "México",
                "source_id": "jira:mexico:gema",
                "source_type": "jira",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(template))

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )

    assert out.slide_count == 15
    assert out.total_issues == 2
    assert out.open_issues == 1
    assert out.closed_issues == 1
    assert out.content


def test_generate_country_period_followup_ppt_uses_open_focus_label_from_settings() -> None:
    template = bundled_period_ppt_template_path()
    now = pd.Timestamp("2026-03-15T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Issue A",
                "status": "New",
                "priority": "High",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
                "source_type": "jira",
            },
            {
                "key": "B-1",
                "summary": "Issue B",
                "status": "Resolved",
                "priority": "Medium",
                "created": (now - pd.Timedelta(days=10)).isoformat(),
                "updated": now.isoformat(),
                "resolved": (now - pd.Timedelta(days=1)).isoformat(),
                "country": "México",
                "source_id": "jira:mexico:gema",
                "source_type": "jira",
            },
        ]
    )

    settings_critical = Settings(
        PERIOD_PPT_TEMPLATE_PATH=str(template),
        OPEN_ISSUES_FOCUS_MODE="criticidad_alta",
    )
    out_critical = generate_country_period_followup_ppt(
        settings_critical,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs_critical = Presentation(BytesIO(out_critical.content))
    critical_blob = " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in prs_critical.slides[2].shapes
        if getattr(shape, "has_text_frame", False)
    ).upper()
    assert "CRITICIDAD ALTA" in critical_blob
    assert "ALTAS:" in critical_blob
    assert "RESTO:" in critical_blob

    settings_maestras = Settings(
        PERIOD_PPT_TEMPLATE_PATH=str(template),
        OPEN_ISSUES_FOCUS_MODE="maestras",
    )
    out_maestras = generate_country_period_followup_ppt(
        settings_maestras,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs_maestras = Presentation(BytesIO(out_maestras.content))
    maestras_blob = " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in prs_maestras.slides[2].shapes
        if getattr(shape, "has_text_frame", False)
    ).upper()
    assert "INCIDENCIAS MAESTRAS" in maestras_blob
    assert "MAESTRAS:" in maestras_blob
    assert "RESTO:" in maestras_blob


def test_generate_country_period_followup_ppt_bundled_template_layout_regression() -> None:
    template = bundled_period_ppt_template_path()
    assert template.exists()

    now = pd.Timestamp("2026-03-15T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Issue A",
                "status": "New",
                "priority": "High",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
                "source_type": "jira",
            },
            {
                "key": "A-2",
                "summary": "Issue A2",
                "status": "Resolved",
                "priority": "Low",
                "created": (now - pd.Timedelta(days=8)).isoformat(),
                "updated": now.isoformat(),
                "resolved": (now - pd.Timedelta(days=1)).isoformat(),
                "country": "México",
                "source_id": "jira:mexico:senda",
                "source_type": "jira",
            },
            {
                "key": "B-1",
                "summary": "Issue B",
                "status": "Resolved",
                "priority": "Medium",
                "created": (now - pd.Timedelta(days=10)).isoformat(),
                "updated": now.isoformat(),
                "resolved": (now - pd.Timedelta(days=2)).isoformat(),
                "country": "México",
                "source_id": "jira:mexico:gema",
                "source_type": "jira",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(template))

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )

    prs = Presentation(BytesIO(out.content))

    s3_blob = " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in prs.slides[2].shapes
        if getattr(shape, "has_text_frame", False)
    ).lower()
    assert "seguimiento de incidencias - méxico (vista agregada)" in s3_blob
    for slide_idx in (2, 3, 4):
        summary_slide = prs.slides[slide_idx]
        assert summary_slide.shapes[4].fill.fore_color.rgb == RGBColor(
            *hex_to_rgb(BBVA_REPORT_RED_BG)
        )
        assert summary_slide.shapes[5].fill.fore_color.rgb == RGBColor(
            *hex_to_rgb(BBVA_REPORT_AMBER_BG)
        )

    # Regression guard: redesigned slides 7/8 keep a single hero chart panel.
    for slide_idx in (6, 7):  # slides 7 and 8 (0-based indexes)
        slide = prs.slides[slide_idx]
        pic_shapes = []
        for shape in slide.shapes:
            try:
                _ = shape.image
            except Exception:
                continue
            area_in2 = float(shape.width) * float(shape.height) / (914400.0 * 914400.0)
            if area_in2 >= 1.0:
                pic_shapes.append(shape)
        assert len(pic_shapes) == 1

    s7_blob = " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in prs.slides[6].shapes
        if getattr(shape, "has_text_frame", False)
    ).lower()
    assert "visión agregada de incidencias abiertas : rango de días por prioridad" in s7_blob
    assert "insights accionables" not in s7_blob

    s8_blob = " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in prs.slides[7].shapes
        if getattr(shape, "has_text_frame", False)
    ).lower()
    assert "visión agregada de incidencias abiertas por prioridad" in s8_blob
    assert "total abiertas" not in s8_blob
    assert "prioridad dominante" not in s8_blob
    assert "riesgo ponderado" not in s8_blob
    assert "insights accionables" not in s8_blob

    # Regression guard: summary metrics should not concatenate duplicated labels.
    s4 = prs.slides[3]
    s4_closed = str(s4.shapes[8].text or "").upper().replace(" ", "")
    s4_days = str(s4.shapes[11].text or "").upper().replace(" ", "")
    s4_blob = " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in s4.shapes
        if getattr(shape, "has_text_frame", False)
    ).upper()
    assert "CERRADASINCIDENCIA" not in s4_closed
    assert "RESOLUCIÓNDÍASDERESOLUCIÓN" not in s4_days
    assert s4_blob.count("ALTAS:") == 1
    assert s4_blob.count("RESTO:") == 1
    assert "MAX:" in s4_blob
    assert "MIN:" in s4_blob
    assert "MAX: 7 DÍAS" in s4_blob
    assert "MIN: 7 DÍAS" in s4_blob

    # Long titles should be marked for in-shape fit in PowerPoint.
    s5_title = prs.slides[4].shapes[2]
    assert s5_title.text_frame.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE

    # Cover period must be rendered only in the dedicated period placeholder.
    cover_blob = " || ".join(
        str(getattr(shape, "text", "") or "")
        for shape in prs.slides[0].shapes
        if getattr(shape, "has_text_frame", False)
    )
    cover_blob_lower = cover_blob.lower()
    assert "periodo dd/mm - dd/mm 2026" not in cover_blob_lower
    period_matches = re.findall(
        r"periodo\s+\d{2}/\d{2}\s*-\s*\d{2}/\d{2}/\d{4}",
        cover_blob_lower,
    )
    assert len(period_matches) == 1
    assert "seguimiento incidencias" in cover_blob_lower
    assert "kpis, evolución y análisis del periodo" not in cover_blob_lower

    period_shape = next(
        (
            shape
            for shape in prs.slides[0].shapes
            if getattr(shape, "has_text_frame", False)
            and re.search(
                r"periodo\s+\d{2}/\d{2}\s*-\s*\d{2}/\d{2}/\d{4}",
                str(getattr(shape, "text", "") or "").lower(),
            )
        ),
        None,
    )
    assert period_shape is not None
    period_run_size = None
    for paragraph in period_shape.text_frame.paragraphs:
        for run in paragraph.runs:
            if str(getattr(run, "text", "") or "").strip():
                period_run_size = run.font.size
                break
        if period_run_size is not None:
            break
    assert period_run_size is not None
    assert float(period_run_size.pt) >= 10.5
    assert period_shape.text_frame.auto_size == MSO_AUTO_SIZE.NONE
    assert period_shape.text_frame.word_wrap is False
    assert int(period_shape.text_frame.margin_left) > 0
    assert int(period_shape.text_frame.margin_right) > 0


def test_resolution_chart_uses_executive_fonts_and_column_totals(monkeypatch: Any) -> None:
    now = pd.Timestamp("2026-04-30T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Issue A",
                "status": "New",
                "priority": "High",
                "created": (now - pd.Timedelta(days=1)).isoformat(),
            },
            {
                "key": "A-2",
                "summary": "Issue B",
                "status": "New",
                "priority": "Medium",
                "created": (now - pd.Timedelta(days=1)).isoformat(),
            },
            {
                "key": "A-3",
                "summary": "Issue C",
                "status": "New",
                "priority": "Highest",
                "created": (now - pd.Timedelta(days=45)).isoformat(),
            },
        ]
    )
    captured: dict[str, Any] = {}

    def _capture_fig(fig: Any, *, width: int, height: int, scale: float = 1.0) -> bytes:
        captured["fig"] = fig
        captured["width"] = width
        captured["height"] = height
        captured["scale"] = scale
        return b"png"

    monkeypatch.setattr(period_ppt_mod, "_fig_to_png_exact", _capture_fig)

    payload = period_ppt_mod._resolution_chart_png_executive(
        Settings(),
        dff=dff,
        open_df=dff,
        reference_now=now,
    )

    assert payload == b"png"
    assert captured["width"] == EXEC_CHART_EXPORT_WIDTH
    assert captured["height"] == EXEC_CHART_EXPORT_HEIGHT
    fig = captured["fig"]
    assert int(fig.layout.xaxis.tickfont.size) >= EXEC_CHART_AXIS_FONT_PT
    assert int(fig.layout.yaxis.tickfont.size) >= EXEC_CHART_AXIS_FONT_PT
    assert int(fig.layout.legend.font.size) >= EXEC_CHART_LEGEND_FONT_PT
    bars = [trace for trace in fig.data if str(trace.type) == "bar"]
    assert bars
    assert all(int(trace.textfont.size) >= EXEC_CHART_INSIDE_VALUE_FONT_PT for trace in bars)
    totals_by_x: dict[str, int] = {}
    for trace in bars:
        for x_val, y_val in zip(list(trace.x), list(trace.y)):
            totals_by_x[str(x_val)] = totals_by_x.get(str(x_val), 0) + int(y_val)
    total_trace = [
        trace
        for trace in fig.data
        if str(trace.type) == "scatter" and list(getattr(trace, "text", []) or [])
    ][-1]
    assert int(total_trace.textfont.size) >= EXEC_CHART_TOTAL_FONT_PT
    assert {
        str(x_val): int(text)
        for x_val, text in zip(list(total_trace.x), list(total_trace.text))
        if str(text).strip()
    } == {label: total for label, total in totals_by_x.items() if total > 0}


def test_priority_chart_uses_executive_fonts_and_safe_y_range(monkeypatch: Any) -> None:
    dff = pd.DataFrame(
        [
            {"key": "A-1", "status": "New", "priority": "High"},
            {"key": "A-2", "status": "New", "priority": "High"},
            {"key": "A-3", "status": "New", "priority": "Medium"},
        ]
    )
    captured: dict[str, Any] = {}

    def _capture_fig(fig: Any, *, width: int, height: int, scale: float = 1.0) -> bytes:
        captured["fig"] = fig
        captured["width"] = width
        captured["height"] = height
        return b"png"

    monkeypatch.setattr(period_ppt_mod, "_fig_to_png_exact", _capture_fig)

    payload = period_ppt_mod._priority_chart_png_executive(Settings(), dff=dff, open_df=dff)

    assert payload == b"png"
    assert captured["width"] == EXEC_CHART_EXPORT_WIDTH
    assert captured["height"] == EXEC_CHART_EXPORT_HEIGHT
    fig = captured["fig"]
    bars = [trace for trace in fig.data if str(trace.type) == "bar"]
    assert bars
    assert int(fig.layout.xaxis.tickfont.size) >= EXEC_CHART_AXIS_FONT_PT
    assert int(fig.layout.yaxis.tickfont.size) >= EXEC_CHART_AXIS_FONT_PT
    assert all(int(trace.textfont.size) >= EXEC_CHART_INSIDE_VALUE_FONT_PT for trace in bars)
    pct_trace = [trace for trace in fig.data if str(trace.type) == "scatter"][-1]
    assert int(pct_trace.textfont.size) >= EXEC_CHART_TOTAL_FONT_PT
    max_bar = max(int(trace.y[0]) for trace in bars)
    assert float(fig.layout.yaxis.range[1]) > float(max_bar)


def test_functionality_trend_filters_last_six_months_and_adds_totals(
    monkeypatch: Any,
) -> None:
    rows: list[dict[str, object]] = []
    for idx, created in enumerate(
        [
            "2026-01-05T00:00:00+00:00",
            "2026-02-05T00:00:00+00:00",
            "2026-03-05T00:00:00+00:00",
            "2026-04-05T00:00:00+00:00",
            "2026-05-05T00:00:00+00:00",
            "2026-06-05T00:00:00+00:00",
            "2026-07-05T00:00:00+00:00",
            "2026-08-05T00:00:00+00:00",
        ],
        start=1,
    ):
        rows.append(
            {
                "key": f"A-{idx}",
                "summary": "Pagos no refleja saldo" if idx % 2 else "Login falla",
                "status": "New",
                "priority": "High",
                "created": created,
            }
        )
    captured: dict[str, Any] = {}

    def _capture_fig(fig: Any, *, width: int, height: int, scale: float = 1.0) -> bytes:
        captured["fig"] = fig
        captured["width"] = width
        captured["height"] = height
        return b"png"

    monkeypatch.setattr(period_ppt_mod, "_fig_to_png_exact", _capture_fig)

    payload = period_ppt_mod._functionality_fortnight_trend_png(open_df=pd.DataFrame(rows))

    assert payload == b"png"
    assert captured["width"] == EXEC_CHART_EXPORT_WIDTH
    assert captured["height"] == EXEC_CHART_TREND_EXPORT_HEIGHT
    fig = captured["fig"]
    bars = [trace for trace in fig.data if str(trace.type) == "bar"]
    assert bars
    axis_labels = [str(label) for label in list(bars[0].x)]
    assert all(not label.startswith(("01 |", "02 |")) for label in axis_labels)
    assert any(label.startswith("03 |") for label in axis_labels)
    assert int(fig.layout.xaxis.tickfont.size) >= EXEC_CHART_AXIS_FONT_PT
    assert int(fig.layout.yaxis.tickfont.size) >= EXEC_CHART_AXIS_FONT_PT
    assert int(fig.layout.legend.font.size) >= EXEC_CHART_LEGEND_FONT_PT
    assert all(int(trace.textfont.size) >= EXEC_CHART_INSIDE_VALUE_FONT_PT for trace in bars)
    totals_by_x: dict[str, int] = {}
    for trace in bars:
        for x_val, y_val in zip(list(trace.x), list(trace.y)):
            totals_by_x[str(x_val)] = totals_by_x.get(str(x_val), 0) + int(y_val)
    total_trace = [
        trace
        for trace in fig.data
        if str(trace.type) == "scatter" and list(getattr(trace, "text", []) or [])
    ][-1]
    assert int(total_trace.textfont.size) >= EXEC_CHART_TOTAL_FONT_PT
    assert {
        str(x_val): int(text)
        for x_val, text in zip(list(total_trace.x), list(total_trace.text))
        if str(text).strip()
    } == {label: total for label, total in totals_by_x.items() if total > 0}


def test_filter_last_six_months_trend_keeps_month_window() -> None:
    trend = pd.DataFrame(
        {
            "quincena_start": pd.to_datetime(
                [
                    "2026-01-01",
                    "2026-02-01",
                    "2026-03-01",
                    "2026-04-01",
                    "2026-05-01",
                    "2026-06-01",
                    "2026-07-01",
                    "2026-08-01",
                ]
            ),
            "quincena_end": pd.to_datetime(
                [
                    "2026-01-15",
                    "2026-02-15",
                    "2026-03-15",
                    "2026-04-15",
                    "2026-05-15",
                    "2026-06-15",
                    "2026-07-15",
                    "2026-08-15",
                ]
            ),
            "quincena_label": [f"2026-{month:02d} · 1-15" for month in range(1, 9)],
            "tema": ["Pagos"] * 8,
            "issues": [1] * 8,
            "issues_cumulative": list(range(1, 9)),
            "issues_value": list(range(1, 9)),
        }
    )

    filtered = period_ppt_mod._filter_last_six_months_trend(trend)

    assert filtered["quincena_start"].min() == pd.Timestamp("2026-03-01")
    assert filtered["quincena_start"].max() == pd.Timestamp("2026-08-01")
    assert filtered["quincena_start"].tolist() == sorted(filtered["quincena_start"].tolist())


def test_summary_timeseries_chart_uses_executive_export_tokens(monkeypatch: Any) -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Issue A",
                "status": "New",
                "priority": "High",
                "created": (now - pd.Timedelta(days=20)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
            },
            {
                "key": "A-2",
                "summary": "Issue B",
                "status": "Resolved",
                "priority": "Medium",
                "created": (now - pd.Timedelta(days=18)).isoformat(),
                "updated": now.isoformat(),
                "resolved": (now - pd.Timedelta(days=2)).isoformat(),
            },
            {
                "key": "A-3",
                "summary": "Issue C",
                "status": "New",
                "priority": "Low",
                "created": (now - pd.Timedelta(days=5)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
            },
        ]
    )
    captured: dict[str, Any] = {}

    def _capture_fig(fig: Any, *, width: int, height: int, scale: float = 1.0) -> bytes:
        captured["fig"] = fig
        captured["width"] = width
        captured["height"] = height
        captured["scale"] = scale
        return b"png"

    monkeypatch.setattr(period_ppt_mod, "_fig_to_png_exact", _capture_fig)

    payload = period_ppt_mod._chart_png(
        Settings(),
        dff=dff,
        open_df=dff[dff["resolved"].isna()],
        chart_id="timeseries",
    )

    assert payload == b"png"
    assert captured["width"] == EXEC_CHART_EXPORT_WIDTH
    assert captured["height"] == EXEC_CHART_TREND_EXPORT_HEIGHT
    fig = captured["fig"]
    assert int(fig.layout.xaxis.tickfont.size) >= EXEC_CHART_AXIS_FONT_PT
    assert int(fig.layout.yaxis.tickfont.size) >= EXEC_CHART_AXIS_FONT_PT
    assert int(fig.layout.legend.font.size) >= EXEC_CHART_LEGEND_FONT_PT
    assert int(fig.layout.margin.b) >= 190
    for trace in fig.data:
        if str(getattr(trace, "type", "") or "").lower() in {"scatter", "scattergl"}:
            assert float(trace.marker.size) >= 8.0
            assert float(trace.line.width) >= 4.2


def test_generate_country_period_followup_ppt_uses_timeseries_for_summary(
    monkeypatch: Any,
) -> None:
    now = pd.Timestamp("2026-03-15T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Issue A",
                "status": "New",
                "priority": "High",
                "created": (now - pd.Timedelta(days=2)).isoformat(),
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
                "source_type": "jira",
            },
            {
                "key": "B-1",
                "summary": "Issue B",
                "status": "Resolved",
                "priority": "Medium",
                "created": (now - pd.Timedelta(days=10)).isoformat(),
                "updated": now.isoformat(),
                "resolved": (now - pd.Timedelta(days=1)).isoformat(),
                "country": "México",
                "source_id": "jira:mexico:gema",
                "source_type": "jira",
            },
        ]
    )
    settings = Settings(
        PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()),
        JIRA_BASE_URL="https://jira.example",
        PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED="true",
    )

    called_chart_ids: list[str] = []
    tiny_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5N0nQAAAAASUVORK5CYII="
    )

    def _fake_chart_png(
        _settings: Settings, *, dff: pd.DataFrame, open_df: pd.DataFrame, chart_id: str
    ) -> bytes:
        _ = (dff, open_df)
        called_chart_ids.append(str(chart_id))
        return tiny_png

    monkeypatch.setattr(period_ppt_mod, "_chart_png", _fake_chart_png)

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    assert out.content
    assert called_chart_ids[:3] == ["timeseries", "timeseries", "timeseries"]
    # Redesigned slides 7/8 render with dedicated executive chart builders and
    # no longer call the generic _chart_png pipeline.
    assert called_chart_ids == ["timeseries", "timeseries", "timeseries"]


def test_generate_country_period_followup_ppt_zoom_table_matches_issue_count() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Login falla en acceso de usuario",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-2",
                "summary": "Login falla en acceso biometrico",
                "status": "Ready To Verify",
                "priority": "Highest",
                "created": "2026-04-03T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "B-1",
                "summary": "TAREAS PENDIENTES - No se visualiza dashboard",
                "status": "New",
                "priority": "High",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(
        PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()),
        JIRA_BASE_URL="https://jira.example",
        PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED="true",
    )
    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))
    dashboard_slide = prs.slides[
        _find_slide_index(prs, "Seguimiento de KPIs - Incidencias abiertas por funcionalidad")
    ]
    dashboard_tables = _native_tables(dashboard_slide)
    assert len(dashboard_tables) == 1
    assert "Resto incidencias abiertas" in _slide_table_text(dashboard_slide)
    assert not _table_intersects_picture(dashboard_slide, dashboard_tables[0])
    _assert_native_table_font_floor(dashboard_tables[0])

    first_zoom_idx = _find_slide_index(prs, "Incidencias, en Login y acceso, abiertas")
    for slide_idx in (first_zoom_idx, first_zoom_idx + 1, first_zoom_idx + 2):
        slide = prs.slides[slide_idx]
        zoom_tables = [shape for shape in slide.shapes if getattr(shape, "has_table", False)]
        assert len(zoom_tables) == 1

    zoom_table = [
        shape for shape in prs.slides[first_zoom_idx].shapes if getattr(shape, "has_table", False)
    ][0].table
    first_data_key_cell = zoom_table.cell(1, 0)
    runs = list(first_data_key_cell.text_frame.paragraphs[0].runs)
    assert runs
    assert str(runs[0].hyperlink.address or "").startswith("https://")
    assert first_data_key_cell.text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT
    assert first_data_key_cell.vertical_anchor == MSO_VERTICAL_ANCHOR.MIDDLE
    header_criticity_cell = zoom_table.cell(0, 4)
    header_runs = list(header_criticity_cell.text_frame.paragraphs[0].runs)
    assert header_runs
    assert float(header_runs[0].font.size.pt) >= 8.0
    tc_pr = first_data_key_cell._tc.tcPr
    assert tc_pr.find(qn("a:lnL")) is not None
    assert tc_pr.find(qn("a:lnR")) is not None
    assert tc_pr.find(qn("a:lnT")) is not None
    assert tc_pr.find(qn("a:lnB")) is not None


def test_generate_country_period_followup_ppt_top3_lines_include_avg_days() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Pagos no refleja saldo",
                "status": "New",
                "priority": "High",
                "created": "2026-03-11T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-2",
                "summary": "Pagos timeout intermitente",
                "status": "New",
                "priority": "Medium",
                "created": "2026-03-21T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "B-1",
                "summary": "Transferencias fallan",
                "status": "Ready To Verify",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(
        PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()),
        PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED="true",
    )
    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))
    dashboard_slide = prs.slides[
        _find_slide_index(prs, "Seguimiento de KPIs - Incidencias abiertas por funcionalidad")
    ]
    top_three_blob = _slide_text(dashboard_slide).lower()
    assert "en total" in top_three_blob
    assert "días promedio" in top_three_blob
    assert "acum." not in top_three_blob
    assert "d. p." not in top_three_blob


def test_generate_country_period_followup_ppt_functionality_color_contrast_is_readable() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Pago no refleja movimiento",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-2",
                "summary": "Transferencias en tiempo real fallan",
                "status": "Blocked",
                "priority": "Medium",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(
        PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()),
        PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED="true",
    )

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))

    dashboard_idx = _find_slide_index(
        prs, "Seguimiento de KPIs - Incidencias abiertas por funcionalidad"
    )
    dashboard_blob_shape = next(
        shape
        for shape in prs.slides[dashboard_idx].shapes
        if getattr(shape, "has_text_frame", False)
        and "INCIDENCIAS" in str(getattr(shape, "text", "") or "")
        and "ABIERTAS" in str(getattr(shape, "text", "") or "")
    )
    dashboard_blob_text = str(getattr(dashboard_blob_shape, "text", "") or "")
    assert "|" not in dashboard_blob_text
    assert "INCIDENCIAS ABIERTAS" in dashboard_blob_text.replace("\n", " ")
    dashboard_run = dashboard_blob_shape.text_frame.paragraphs[0].runs[0]
    assert dashboard_run.font.color.rgb == RGBColor(255, 255, 255)

    dashboard_tables = _native_tables(prs.slides[dashboard_idx])
    assert len(dashboard_tables) == 1
    dashboard_table = dashboard_tables[0]
    assert not _table_intersects_picture(prs.slides[dashboard_idx], dashboard_table)
    _assert_native_table_font_floor(dashboard_table)
    assert int(dashboard_table.top) > int(dashboard_blob_shape.top + dashboard_blob_shape.height)
    mitigation_panel = next(
        (
            shape
            for shape in prs.slides[dashboard_idx].shapes
            if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.AUTO_SHAPE
            and int(getattr(shape, "left", 0)) > 5_400_000
            and int(getattr(shape, "width", 0)) >= 3_000_000
            and int(getattr(shape, "height", 0)) >= 2_000_000
        ),
        None,
    )
    assert mitigation_panel is not None
    dashboard_text = _slide_all_text(prs.slides[dashboard_idx])
    assert "Estado Ready to Verify" in dashboard_text
    assert "Estado New" in dashboard_text
    assert "Estado bloqueadas" in dashboard_text
    assert "Resto:" in dashboard_text
    assert "d. prom." not in dashboard_text
    assert "Incidencias en New:" not in dashboard_text
    assert "Resto de incidencias:" not in dashboard_text
    assert int(dashboard_table.left + dashboard_table.width) < int(mitigation_panel.left)
    assert int(dashboard_table.top + dashboard_table.height) <= int(
        mitigation_panel.top + mitigation_panel.height
    )

    first_zoom_idx = _find_slide_index(prs, "Incidencias, en Pagos, abiertas")
    root_cause_shape = next(
        shape
        for shape in prs.slides[first_zoom_idx].shapes
        if getattr(shape, "has_text_frame", False)
        and any(
            token in str(getattr(shape, "text", "") or "").lower()
            for token in ("causa", "sin incidencias")
        )
    )
    root_run = root_cause_shape.text_frame.paragraphs[0].runs[0]
    assert root_run.font.color.rgb == RGBColor(*period_ppt_mod._TABLE_BODY_FG_RGB)


def test_generate_country_period_followup_ppt_zoom_paginates_when_overflow() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    rows: list[dict[str, object]] = []
    for idx in range(7):
        rows.append(
            {
                "key": f"P-{idx + 1}",
                "summary": (
                    f"INC0001 - PAGOS / SENDA BNC / TRANSFERENCIAS EN TIEMPO REAL / CASO {idx + 1}"
                ),
                "status": "New",
                "priority": "Medium",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            }
        )
    rows.extend(
        [
            {
                "key": "M-1",
                "summary": "Saldo monetarias no actualizado",
                "status": "Analysing",
                "priority": "Medium",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "T-1",
                "summary": "Transferencias con timeout intermitente",
                "status": "Blocked",
                "priority": "Medium",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    dff = pd.DataFrame(rows)
    settings = Settings(
        PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()),
        PERIOD_REPORT_FUNCTIONALITY_DETAIL_ENABLED="true",
    )
    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))
    assert len(prs.slides) == 19
    first_zoom_idx = _find_slide_index(prs, "Incidencias, en Pagos, abiertas en la quincena (I)")
    zoom_titles = [
        str(getattr(shape, "text", "") or "").strip()
        for slide_idx in (first_zoom_idx, first_zoom_idx + 1)
        for shape in prs.slides[slide_idx].shapes
        if getattr(shape, "has_text_frame", False)
    ]
    joined_titles = " | ".join(zoom_titles)
    deck_text = " ".join(_slide_text(slide) for slide in prs.slides)
    assert "Incidencias abiertas por criticidad alta" in deck_text
    assert "Incidencias abiertas con más de 30 días" in deck_text
    assert "Incidencias, en Pagos, abiertas en la quincena (I)" in joined_titles
    assert "Incidencias, en Pagos, abiertas en la quincena (II)" in joined_titles


def test_period_followup_risk_sections_use_native_tables_after_functionality() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "MEXBMI1-101",
                "summary": "Alta criticidad con bloqueo de operativa",
                "status": "New",
                "priority": "High",
                "created": "2026-02-20T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
                "url": "https://jira.example/browse/MEXBMI1-101",
            },
            {
                "key": "EAM-77",
                "summary": "Impedimento en autenticación para clientes",
                "status": "Ready To Verify",
                "priority": "Supone un impedimento",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "SKSEMEX-9",
                "summary": "Incidencia abierta antigua de prioridad media",
                "status": "Analysing",
                "priority": "Medium",
                "created": "2026-02-01T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "MEXBMI1-102",
                "summary": "Alta criticidad adicional 1",
                "status": "New",
                "priority": "High",
                "created": "2026-02-21T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "MEXBMI1-103",
                "summary": "Alta criticidad adicional 2",
                "status": "New",
                "priority": "High",
                "created": "2026-02-22T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "MEXBMI1-104",
                "summary": "Alta criticidad adicional 3",
                "status": "New",
                "priority": "High",
                "created": "2026-02-23T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "MEXBMI1-105",
                "summary": "Alta criticidad adicional 4",
                "status": "New",
                "priority": "High",
                "created": "2026-02-24T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
        ]
    )
    settings = Settings(
        PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()),
        JIRA_BASE_URL="https://jira.example",
    )

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))

    trend_title = "Tendencia por funcionalidad : vista agregada ultimo semestre"
    trend_idx = _find_slide_index(prs, trend_title)
    dashboard_idx = _find_slide_index(
        prs,
        "Seguimiento de KPIs - Incidencias abiertas por funcionalidad",
    )
    high_cover_idx = _find_slide_index(prs, "Incidencias abiertas por criticidad alta")
    high_detail_idx = _find_slide_index(prs, "Incidencias abiertas por criticidad alta (I)")
    aged_cover_idx = _find_slide_index(prs, "Incidencias abiertas con más de 30 días")
    aged_detail_idx = _find_slide_index(prs, "Incidencias abiertas con más de 30 días (I)")
    high_detail_slides = [
        idx
        for idx, slide in enumerate(prs.slides)
        if "Incidencias abiertas por criticidad alta (" in _slide_text(slide)
    ]
    aged_detail_slides = [
        idx
        for idx, slide in enumerate(prs.slides)
        if "Incidencias abiertas con más de 30 días (" in _slide_text(slide)
    ]

    assert trend_idx < dashboard_idx < high_cover_idx < high_detail_idx < aged_cover_idx
    assert aged_cover_idx < aged_detail_idx
    assert len(high_detail_slides) >= 2
    assert len(aged_detail_slides) >= 2
    trend_title_shapes = [
        shape
        for shape in prs.slides[trend_idx].shapes
        if getattr(shape, "has_text_frame", False) and trend_title in str(shape.text or "")
    ]
    assert trend_title_shapes
    assert all("\n" not in str(shape.text or "") for shape in trend_title_shapes)
    assert not _native_tables(prs.slides[high_cover_idx])
    assert not _native_tables(prs.slides[aged_cover_idx])

    template_prs = Presentation(str(bundled_period_ppt_template_path()))
    section_cover_template = template_prs.slides[1]
    section_cover_title = section_cover_template.shapes[1]
    for cover_idx, expected_title in (
        (high_cover_idx, "Incidencias abiertas por criticidad alta"),
        (aged_cover_idx, "Incidencias abiertas con más de 30 días"),
    ):
        cover = prs.slides[cover_idx]
        cover_text = _slide_text(cover)
        assert "Haga clic para agregar" not in cover_text
        assert (
            cover.shapes[0].fill.fore_color.rgb
            == section_cover_template.shapes[0].fill.fore_color.rgb
        )
        assert cover.shapes[1].left == section_cover_title.left
        assert cover.shapes[1].top == section_cover_title.top
        assert cover.shapes[1].width == section_cover_title.width
        assert cover.shapes[1].height == section_cover_title.height
        assert cover.shapes[1].text == expected_title
        assert cover.shapes[1].text_frame.paragraphs[0].runs[0].font.name == (
            section_cover_title.text_frame.paragraphs[0].runs[0].font.name
        )

    expected_headers = {
        "ID",
        "Descripción",
        "Funcionalidad/\nCausa raíz",
        "Estado",
        "Criticidad",
        "Días abierta",
    }
    old_high_note = "Detalle ordenado por 1º : Criticidad, 2º: Días abierta y 3º: Estado"
    old_aged_note = "Detalle ordenado por 1º : Días abierta, 2º: Criticidad y 3º: Estado"
    for slide_idx in high_detail_slides:
        slide_text = _slide_all_text(prs.slides[slide_idx])
        assert period_ppt_mod._RISK_HIGH_PRIORITY_ORDER_NOTE in slide_text
        assert old_high_note not in slide_text
    for slide_idx in aged_detail_slides:
        slide_text = _slide_all_text(prs.slides[slide_idx])
        assert period_ppt_mod._RISK_AGED_ORDER_NOTE in slide_text
        assert old_aged_note not in slide_text
        assert "2ºCrriticidad" not in slide_text
    for slide_idx, expected_ids, order_note, forbidden in (
        (
            high_detail_idx,
            ["EAM-77", "MEXBMI1-101"],
            period_ppt_mod._RISK_HIGH_PRIORITY_ORDER_NOTE,
            "SKSEMEX-9",
        ),
        (
            aged_detail_idx,
            ["SKSEMEX-9", "MEXBMI1-101"],
            period_ppt_mod._RISK_AGED_ORDER_NOTE,
            "",
        ),
    ):
        slide = prs.slides[slide_idx]
        slide_text = _slide_all_text(slide)
        assert "Detalle de incidencias abiertas:" not in slide_text
        assert order_note in slide_text
        tables = _native_tables(slide)
        assert len(tables) == 1
        table_shape = tables[0]
        assert not _table_intersects_picture(slide, table_shape)
        _assert_native_table_font_floor(table_shape)
        headers = {table_shape.table.cell(0, cidx).text for cidx in range(6)}
        assert headers == expected_headers
        table_text = _slide_table_text(slide)
        row_ids = [
            table_shape.table.cell(row_idx, 0).text for row_idx in range(1, len(expected_ids) + 1)
        ]
        assert row_ids == expected_ids
        if forbidden:
            assert forbidden not in table_text
        assert "Descripción" in table_text
        assert "Criticidad" in table_text
        assert "días" in table_text


def test_period_followup_functionality_detail_toggle_off_omits_zoom_slides() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Pagos no refleja saldo",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "B-1",
                "summary": "Login falla en acceso",
                "status": "Analysing",
                "priority": "Medium",
                "created": "2026-03-01T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()))

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))
    deck_text = " ".join(_slide_text(slide) for slide in prs.slides)

    assert len(prs.slides) == 15
    assert "Incidencias abiertas por criticidad alta" in deck_text
    assert "Incidencias abiertas con más de 30 días" in deck_text
    assert "Seguimiento de KPIs - Incidencias abiertas por funcionalidad" in deck_text
    assert "Incidencias, en Pagos, abiertas en la quincena" not in deck_text


def test_functionality_dashboard_table_headers_include_business_wording() -> None:
    assert period_ppt_mod._FUNCTIONALITY_DASHBOARD_TABLE_HEADERS == (
        "#",
        "Resto incidencias abiertas",
        "Nuevas",
        "Agregadas",
        "Días promedio abiertas",
    )
    weights = period_ppt_mod._FUNCTIONALITY_DASHBOARD_TABLE_COLUMN_WEIGHTS
    assert weights[1] < 3.05
    assert weights[3] > 1.12


def test_generate_country_period_followup_ppt_functionality_wording_depends_on_priority_filter() -> (
    None
):
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Pagos no refleja saldo",
                "status": "New",
                "priority": "High",
                "created": "2026-04-05T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-2",
                "summary": "Transferencias con timeout",
                "status": "Blocked",
                "priority": "Medium",
                "created": "2026-04-06T09:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()))

    out_default = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs_default = Presentation(BytesIO(out_default.content))
    default_dashboard_idx = _find_slide_index(
        prs_default,
        "Seguimiento de KPIs - Incidencias abiertas por funcionalidad",
    )
    default_risk_idx = _find_slide_index(prs_default, "Incidencias abiertas por criticidad alta")
    blob_default = " ".join(
        str(getattr(shape, "text", "") or "")
        for idx in range(default_dashboard_idx, default_risk_idx)
        for shape in prs_default.slides[idx].shapes
        if getattr(shape, "has_text_frame", False)
    ).lower()
    assert "seguimiento de kpis - incidencias abiertas por funcionalidad" in blob_default
    assert "incidencias críticas" not in blob_default

    out_critical = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
        functionality_priority_filters=["High", "Highest", "Supone un impedimento"],
    )
    prs_critical = Presentation(BytesIO(out_critical.content))
    critical_dashboard_idx = _find_slide_index(
        prs_critical,
        "Seguimiento de KPIs - Incidencias críticas abiertas por funcionalidad",
    )
    critical_risk_idx = _find_slide_index(prs_critical, "Incidencias abiertas por criticidad alta")
    blob_critical = " ".join(
        str(getattr(shape, "text", "") or "")
        for idx in range(critical_dashboard_idx, critical_risk_idx)
        for shape in prs_critical.slides[idx].shapes
        if getattr(shape, "has_text_frame", False)
    ).lower()
    assert "seguimiento de kpis - incidencias críticas abiertas por funcionalidad" in blob_critical
    assert "incidencias críticas" in blob_critical


def test_period_followup_ppt_resolution_min_max_matches_closed_in_selected_fortnight() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "S-1",
                "summary": "Senda cerrada rápida",
                "status": "Resolved",
                "priority": "High",
                "created": "2026-04-07T08:00:00+00:00",  # 1 día
                "updated": now.isoformat(),
                "resolved": "2026-04-08T08:00:00+00:00",
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "S-2",
                "summary": "Senda cerrada lenta",
                "status": "Resolved",
                "priority": "Medium",
                "created": "2026-03-20T08:00:00+00:00",  # 21 días
                "updated": now.isoformat(),
                "resolved": "2026-04-10T08:00:00+00:00",
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "G-1",
                "summary": "Gema cerrada media",
                "status": "Resolved",
                "priority": "Low",
                "created": "2026-03-31T08:00:00+00:00",  # 10 días
                "updated": now.isoformat(),
                "resolved": "2026-04-10T08:00:00+00:00",
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "S-OUT",
                "summary": "Senda cerrada fuera de quincena",
                "status": "Resolved",
                "priority": "High",
                "created": "2026-03-01T08:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": "2026-03-05T08:00:00+00:00",  # fuera de quincena actual
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "OPEN-1",
                "summary": "Incidencia abierta no debe contar",
                "status": "New",
                "priority": "High",
                "created": "2026-04-09T08:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()))

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))

    quincenal = period_ppt_mod.build_country_quincenal_result(
        df=dff,
        settings=settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        source_label_by_id=period_ppt_mod.source_label_map(
            settings,
            country="México",
            source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        ),
    )
    expected_by_slide = {
        2: quincenal.aggregate.summary,
        3: quincenal.by_source["jira:mexico:senda"].summary,
        4: quincenal.by_source["jira:mexico:gema"].summary,
    }

    for slide_idx, summary in expected_by_slide.items():
        slide_blob = " ".join(
            str(getattr(shape, "text", "") or "")
            for shape in prs.slides[slide_idx].shapes
            if getattr(shape, "has_text_frame", False)
        )
        max_match = re.search(r"MAX:\s*(\d+)\s*d[ií]as", slide_blob, flags=re.IGNORECASE)
        min_match = re.search(r"MIN:\s*(\d+)\s*d[ií]as", slide_blob, flags=re.IGNORECASE)
        assert max_match is not None
        assert min_match is not None
        assert int(max_match.group(1)) == int(round(float(summary.resolution_days_max_now or 0.0)))
        assert int(min_match.group(1)) == int(round(float(summary.resolution_days_min_now or 0.0)))


def test_period_followup_summary_metric_cards_keep_template_blue_text_color() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Issue A",
                "status": "New",
                "priority": "High",
                "created": "2026-04-08T10:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-2",
                "summary": "Issue A2",
                "status": "Resolved",
                "priority": "Medium",
                "created": "2026-04-01T10:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": "2026-04-08T10:00:00+00:00",
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "B-1",
                "summary": "Issue B",
                "status": "Resolved",
                "priority": "High",
                "created": "2026-04-02T10:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": "2026-04-10T10:00:00+00:00",
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()))
    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))

    def _first_run_color(shape: Any) -> RGBColor | None:
        if shape is None or not getattr(shape, "has_text_frame", False):
            return None
        for paragraph in list(shape.text_frame.paragraphs):
            for run in list(paragraph.runs):
                if not str(getattr(run, "text", "") or "").strip():
                    continue
                color = getattr(getattr(run, "font", None), "color", None)
                rgb = getattr(color, "rgb", None)
                if rgb is not None:
                    return rgb
        return None

    for slide_idx in (2, 3, 4):
        slide = prs.slides[slide_idx]
        detail_shape = next(
            shape
            for shape in slide.shapes
            if getattr(shape, "has_text_frame", False) and "TOTAL:" in str(shape.text or "")
        )
        closed_shape = next(
            shape
            for shape in slide.shapes
            if getattr(shape, "has_text_frame", False) and "CERRADA" in str(shape.text or "")
        )
        resolution_shape = next(
            shape
            for shape in slide.shapes
            if getattr(shape, "has_text_frame", False)
            and "DÍAS DE RESOLUCIÓN" in str(shape.text or "")
        )
        created_shape = next(
            shape
            for shape in slide.shapes
            if getattr(shape, "has_text_frame", False) and "CREADA" in str(shape.text or "")
        )
        reference_color = _first_run_color(detail_shape)
        assert reference_color == RGBColor(4, 19, 139)
        assert _first_run_color(closed_shape) == reference_color
        assert _first_run_color(resolution_shape) == reference_color
        assert _first_run_color(created_shape) == reference_color


def test_period_followup_summary_uses_quincenal_flow_wording_and_removes_artifacts(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(period_ppt_mod, "_chart_png", lambda *args, **kwargs: b"")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Actual abierta",
                "status": "New",
                "priority": "High",
                "created": "2026-03-10T10:00:00+00:00",
                "updated": "2026-03-12T10:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "A-2",
                "summary": "Previa cerrada",
                "status": "Resolved",
                "priority": "Medium",
                "created": "2026-02-20T10:00:00+00:00",
                "updated": "2026-03-11T10:00:00+00:00",
                "resolved": "2026-03-11T10:00:00+00:00",
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "B-1",
                "summary": "Previa abierta",
                "status": "New",
                "priority": "High",
                "created": "2026-02-15T10:00:00+00:00",
                "updated": "2026-03-12T10:00:00+00:00",
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
            {
                "key": "B-2",
                "summary": "Actual cerrada",
                "status": "Resolved",
                "priority": "Highest",
                "created": "2026-03-01T10:00:00+00:00",
                "updated": "2026-03-12T10:00:00+00:00",
                "resolved": "2026-03-12T10:00:00+00:00",
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()))

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )

    prs = Presentation(BytesIO(out.content))
    deck_text = " ".join(_slide_all_text(slide) for slide in prs.slides)
    assert "CREADAS DEL 01 AL 15 MAR" in deck_text
    assert "15 FEB - 28 FEB" in deck_text
    assert "TOTAL: 4" in deck_text
    assert "CERRADAS DEL 01 AL 15 MAR" in deck_text
    assert "AHORA" not in deck_text
    assert "ACUMULADO" not in deck_text
    assert "NUEVAS INCIDENCIAS" not in deck_text
    assert "Ver detalle" not in deck_text

    for slide in prs.slides:
        for shape in slide.shapes:
            left = int(getattr(shape, "left", 0) or 0)
            top = int(getattr(shape, "top", 0) or 0)
            right = left + int(getattr(shape, "width", 0) or 0)
            bottom = top + int(getattr(shape, "height", 0) or 0)
            assert left >= 0
            assert top >= 0
            assert right <= int(prs.slide_width)
            assert bottom <= int(prs.slide_height)

    with ZipFile(BytesIO(out.content)) as pptx:
        xml_payload = "\n".join(
            pptx.read(name).decode("utf-8", errors="ignore")
            for name in pptx.namelist()
            if name.endswith(".xml")
        )
    assert 'type="slidenum"' not in xml_payload
    assert "p. </a:t>" not in xml_payload


def test_period_followup_metric_typography_handles_one_to_four_digit_values() -> None:
    values = ["9", "69", "107", "138", "1024"]
    sizes = [
        metric_card_typography(value, "CREADAS DEL 01 AL 15 MAR").value_size_pt for value in values
    ]

    assert min(sizes) >= 17.0
    assert sizes[0] >= sizes[-1]
    for value in values:
        typography = metric_card_typography(value, "CERRADAS DEL 01 AL 15 MAR")
        assert typography.label_size_pt >= 8.6
        assert typography.detail_size_pt >= 8.8


def test_period_followup_functionality_trend_title_matches_template_style() -> None:
    now = pd.Timestamp("2026-04-10T00:00:00+00:00")
    dff = pd.DataFrame(
        [
            {
                "key": "A-1",
                "summary": "Login falla en alta de usuario",
                "status": "New",
                "priority": "High",
                "created": "2026-04-08T10:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:senda",
            },
            {
                "key": "B-1",
                "summary": "Transferencias con timeout",
                "status": "Blocked",
                "priority": "Medium",
                "created": "2026-04-02T10:00:00+00:00",
                "updated": now.isoformat(),
                "resolved": None,
                "country": "México",
                "source_id": "jira:mexico:gema",
            },
        ]
    )
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()))
    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))
    trend_slide = prs.slides[_find_slide_index(prs, "Tendencia por funcionalidad")]

    title_shape = next(
        (
            shape
            for shape in trend_slide.shapes
            if getattr(shape, "has_text_frame", False)
            and "Tendencia por funcionalidad" in str(getattr(shape, "text", "") or "")
        ),
        None,
    )
    assert title_shape is not None

    first_run = None
    for paragraph in title_shape.text_frame.paragraphs:
        for run in paragraph.runs:
            if str(getattr(run, "text", "") or "").strip():
                first_run = run
                break
        if first_run is not None:
            break
    assert first_run is not None
    assert first_run.font.name == "Source Serif 4"
    assert first_run.font.color.rgb == RGBColor(4, 19, 139)
