from __future__ import annotations

from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE

from bug_resolution_radar.config import Settings
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.reports.branding import add_corporate_lockup_to_all_slides
from bug_resolution_radar.repositories.issues_store import load_issues_meta, save_issues_doc
from bug_resolution_radar.services.issue_enrichment import enrich_issue_dataframe_with_helix
from bug_resolution_radar.theme.brand_identity import frontend_brand_contract


def test_brand_contract_and_presentation_lockup_are_canonical() -> None:
    contract = frontend_brand_contract()
    assert contract == {
        "name": "BBVA Banca de Empresas e Instituciones",
        "wordmark": "BBVA",
        "descriptorLines": ["Banca de Empresas", "e Instituciones"],
    }

    presentation = Presentation()
    light_slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    dark_slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    background = dark_slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RECTANGLE,
        0,
        0,
        presentation.slide_width,
        presentation.slide_height,
    )
    background.fill.solid()
    background.fill.fore_color.rgb = RGBColor(7, 14, 70)

    add_corporate_lockup_to_all_slides(presentation)
    add_corporate_lockup_to_all_slides(presentation)

    for slide in (light_slide, dark_slide):
        brand_shapes = [shape for shape in slide.shapes if shape.name.startswith("BBVA Corporate")]
        assert len(brand_shapes) == 3
        assert any(getattr(shape, "text", "") == "BBVA" for shape in brand_shapes)
        assert any("Banca de Empresas" in getattr(shape, "text", "") for shape in brand_shapes)


def test_issue_metadata_sidecar_avoids_loading_full_document(tmp_path: Path) -> None:
    path = tmp_path / "issues.json"
    save_issues_doc(
        str(path),
        IssuesDocument(
            schema_version="1.0",
            ingested_at="2026-08-20T09:00:00+00:00",
            jira_base_url="https://jira.example.com",
            query="project = RADAR",
            issues=[
                NormalizedIssue(
                    key="RAD-1",
                    summary="Incidencia",
                    status="Open",
                    type="Bug",
                    priority="Medium",
                    source_id="jira:espana:core",
                    source_type="jira",
                )
            ],
        ),
    )

    metadata = load_issues_meta(str(path))
    assert metadata["issues_count"] == 1
    assert metadata["jira_source_count"] == 1
    assert metadata["query"] == "project = RADAR"


def test_helix_enrichment_prefers_columnar_sidecar(tmp_path: Path) -> None:
    helix_path = tmp_path / "helix.json"
    helix_path.write_text("not-json", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "id": "INC001",
                "source_id": "helix:mexico:gema",
                "BBVA_ExecutiveDescription": "Servicio recuperado",
            }
        ]
    ).to_parquet(helix_path.with_suffix(".raw.parquet"), index=False)
    settings = Settings(HELIX_DATA_PATH=str(helix_path))
    source = pd.DataFrame(
        [
            {
                "key": "INC001",
                "source_id": "helix:mexico:gema",
                "helix_executive_description": "",
            }
        ]
    )

    enriched = enrich_issue_dataframe_with_helix(source, settings=settings)
    assert enriched.loc[0, "helix_executive_description"] == "Servicio recuperado"
