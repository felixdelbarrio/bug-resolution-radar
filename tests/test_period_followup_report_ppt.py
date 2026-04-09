from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE, MSO_VERTICAL_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn

from bug_resolution_radar.config import Settings, bundled_period_ppt_template_path
from bug_resolution_radar.reports import generate_country_period_followup_ppt
from bug_resolution_radar.reports import period_followup_ppt as period_ppt_mod


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

    assert out.slide_count == 13
    assert out.total_issues == 2
    assert out.open_issues == 1
    assert out.closed_issues == 1
    assert out.content
    prs = Presentation(BytesIO(out.content))
    assert len(prs.slides) == 13
    s9_text = " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in prs.slides[8].shapes
        if getattr(shape, "has_text_frame", False)
    )
    s10_text = " ".join(
        str(getattr(shape, "text", "") or "")
        for shape in prs.slides[9].shapes
        if getattr(shape, "has_text_frame", False)
    )
    assert "quincena" in s9_text.lower()
    assert "funcionalidad" in s10_text.lower()
    # Functional follow-up slides must preserve light background from source template.
    bg_fill = prs.slides[9].background.fill
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

    assert out.slide_count == 13
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

    # Regression guard: evolution slides must keep exactly 3 rendered chart panels.
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
        assert len(pic_shapes) == 3

    # Regression guard: summary metrics should not concatenate duplicated labels.
    s4 = prs.slides[3]
    s4_closed = str(s4.shapes[8].text or "").upper().replace(" ", "")
    s4_days = str(s4.shapes[11].text or "").upper().replace(" ", "")
    assert "CERRADASINCIDENCIA" not in s4_closed
    assert "RESOLUCIÓNDÍASDERESOLUCIÓN" not in s4_days

    # Long titles should be marked for in-shape fit in PowerPoint.
    s5_title = prs.slides[4].shapes[2]
    assert s5_title.text_frame.auto_size == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE


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
    assert called_chart_ids.count("age_buckets") == 2
    assert called_chart_ids.count("resolution_hist") == 2
    assert called_chart_ids.count("open_priority_pie") == 2


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
    )
    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))
    dashboard_slide = prs.slides[9]
    assert not any(getattr(shape, "has_table", False) for shape in dashboard_slide.shapes)
    dashboard_table_picture = [
        shape
        for shape in dashboard_slide.shapes
        if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.PICTURE
        and int(getattr(shape, "width", 0)) >= 2_900_000
        and int(getattr(shape, "height", 0)) >= 2_900_000
    ]
    assert dashboard_table_picture

    # Slides 11-13 (0-based 10-12): zooms de funcionalidad.
    for slide_idx in (10, 11, 12):
        slide = prs.slides[slide_idx]
        zoom_tables = [shape for shape in slide.shapes if getattr(shape, "has_table", False)]
        assert len(zoom_tables) == 1

    zoom_table = [shape for shape in prs.slides[10].shapes if getattr(shape, "has_table", False)][
        0
    ].table
    first_data_key_cell = zoom_table.cell(1, 0)
    runs = list(first_data_key_cell.text_frame.paragraphs[0].runs)
    assert runs
    assert str(runs[0].hyperlink.address or "").startswith("https://")
    assert first_data_key_cell.text_frame.paragraphs[0].alignment == PP_ALIGN.LEFT
    assert first_data_key_cell.vertical_anchor == MSO_VERTICAL_ANCHOR.MIDDLE
    header_criticity_cell = zoom_table.cell(0, 4)
    header_runs = list(header_criticity_cell.text_frame.paragraphs[0].runs)
    assert header_runs
    assert float(header_runs[0].font.size.pt) <= 9.0
    tc_pr = first_data_key_cell._tc.tcPr
    assert tc_pr.find(qn("a:lnL")) is not None
    assert tc_pr.find(qn("a:lnR")) is not None
    assert tc_pr.find(qn("a:lnT")) is not None
    assert tc_pr.find(qn("a:lnB")) is not None


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
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()))

    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))

    dashboard_blob_shape = next(
        shape
        for shape in prs.slides[9].shapes
        if getattr(shape, "has_text_frame", False)
        and "INCIDENCIAS" in str(getattr(shape, "text", "") or "")
        and "ABIERTAS" in str(getattr(shape, "text", "") or "")
    )
    dashboard_run = dashboard_blob_shape.text_frame.paragraphs[0].runs[0]
    assert dashboard_run.font.color.rgb == RGBColor(255, 255, 255)

    root_cause_shape = next(
        shape
        for shape in prs.slides[10].shapes
        if getattr(shape, "has_text_frame", False)
        and any(
            token in str(getattr(shape, "text", "") or "").lower()
            for token in ("causa", "sin incidencias")
        )
    )
    root_run = root_cause_shape.text_frame.paragraphs[0].runs[0]
    assert root_run.font.color.rgb == RGBColor(0, 19, 145)


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
    settings = Settings(PERIOD_PPT_TEMPLATE_PATH=str(bundled_period_ppt_template_path()))
    out = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
    )
    prs = Presentation(BytesIO(out.content))
    assert len(prs.slides) == 14
    zoom_titles = [
        str(getattr(shape, "text", "") or "").strip()
        for slide_idx in (10, 11)
        for shape in prs.slides[slide_idx].shapes
        if getattr(shape, "has_text_frame", False)
    ]
    joined_titles = " | ".join(zoom_titles)
    assert "Incidencias, en Pagos, abiertas en la quincena (I)" in joined_titles
    assert "Incidencias, en Pagos, abiertas en la quincena (II)" in joined_titles


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
    blob_default = " ".join(
        str(getattr(shape, "text", "") or "")
        for idx in (8, 9, 10, 11, 12)
        for shape in prs_default.slides[idx].shapes
        if getattr(shape, "has_text_frame", False)
    ).lower()
    assert "incidencias críticas" not in blob_default

    out_critical = generate_country_period_followup_ppt(
        settings,
        country="México",
        source_ids=["jira:mexico:senda", "jira:mexico:gema"],
        dff_override=dff,
        functionality_priority_filters=["High", "Highest", "Supone un impedimento"],
    )
    prs_critical = Presentation(BytesIO(out_critical.content))
    blob_critical = " ".join(
        str(getattr(shape, "text", "") or "")
        for idx in (8, 9, 10, 11, 12)
        for shape in prs_critical.slides[idx].shapes
        if getattr(shape, "has_text_frame", False)
    ).lower()
    assert "incidencias críticas" in blob_critical
