from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from bug_resolution_radar.config import Settings, build_source_id
from bug_resolution_radar.services.sources_excel import (
    build_sources_export_dataframe,
    import_sources_from_excel_bytes,
)


def _build_excel_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_excel(buffer, index=False, sheet_name="Fuentes")
    return buffer.getvalue()


def test_build_sources_export_dataframe_for_helix_keeps_expected_columns_and_order() -> None:
    settings = Settings(
        HELIX_SOURCES_JSON=(
            '[{"country":"México","alias":"MX SmartIT","service_origin_buug":"BBVA México",'
            '"service_origin_n1":"ENTERPRISE WEB"}]'
        )
    )

    frame = build_sources_export_dataframe(settings, source_type="helix")

    assert list(frame.columns) == [
        "source_id",
        "country",
        "alias",
        "service_origin_buug",
        "service_origin_n1",
        "service_origin_n2",
    ]
    assert frame.iloc[0]["source_id"] == build_source_id("helix", "México", "MX SmartIT")
    assert frame.iloc[0]["service_origin_n2"] == ""


def test_import_sources_from_excel_bytes_helix_normalizes_headers_and_preserves_first_row() -> None:
    frame = pd.DataFrame(
        [
            {
                "País": "México",
                "Alias": "MX SmartIT",
                "Servicio origen BU/UG": "BBVA México",
                "Servicio origen N1": "ENTERPRISE WEB",
            },
            {
                "País": "España",
                "Alias": "Incident Report",
                "Servicio origen BU/UG": "BBVA España",
                "Servicio origen N1": "ENTERPRISES CHANNEL",
                "Servicio origen N2": "WEB BBVA EMPRESAS",
            },
        ]
    )

    imported = import_sources_from_excel_bytes(
        _build_excel_bytes(frame),
        source_type="helix",
        countries=["México", "España"],
    )

    assert imported.imported_rows == 2
    assert imported.skipped_rows == 0
    assert imported.warnings == []
    assert imported.rows[0]["country"] == "México"
    assert imported.rows[0]["alias"] == "MX SmartIT"
    assert imported.rows[0]["source_id"] == build_source_id("helix", "México", "MX SmartIT")
    assert imported.rows[1]["country"] == "España"


def test_import_sources_from_excel_bytes_skips_invalid_country_with_warning() -> None:
    frame = pd.DataFrame(
        [
            {"country": "México", "alias": "MX SmartIT", "service_origin_n1": "ENTERPRISE WEB"},
            {"country": "Chile", "alias": "Chile SmartIT", "service_origin_n1": "ENTERPRISE WEB"},
        ]
    )

    imported = import_sources_from_excel_bytes(
        _build_excel_bytes(frame),
        source_type="helix",
        countries=["México", "España"],
    )

    assert imported.imported_rows == 1
    assert imported.skipped_rows == 1
    assert imported.rows[0]["country"] == "México"
    assert any("país no soportado" in warning for warning in imported.warnings)


def test_import_sources_from_excel_bytes_fails_when_required_columns_missing() -> None:
    frame = pd.DataFrame([{"country": "México", "service_origin_n1": "ENTERPRISE WEB"}])

    with pytest.raises(ValueError, match="columnas obligatorias"):
        import_sources_from_excel_bytes(
            _build_excel_bytes(frame),
            source_type="helix",
            countries=["México"],
        )

