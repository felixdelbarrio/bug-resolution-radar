from __future__ import annotations

from pathlib import Path

import pandas as pd
from pptx import Presentation

from bug_resolution_radar.config import Settings
from bug_resolution_radar.reports import generate_country_period_followup_ppt


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

    assert out.slide_count == 8
    assert out.total_issues == 2
    assert out.open_issues == 1
    assert out.closed_issues == 1
    assert out.content


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

    assert out.slide_count == 8
    assert out.total_issues == 2
    assert out.open_issues == 1
    assert out.closed_issues == 1
    assert out.content
