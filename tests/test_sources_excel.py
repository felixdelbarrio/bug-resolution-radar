from __future__ import annotations

from io import BytesIO

import pandas as pd
import pytest

from bug_resolution_radar.config import Settings, build_source_id
from bug_resolution_radar.services.sources_excel import (
    _TRANSVERSAL_SHEET_NAME,
    build_sources_export_dataframe,
    build_sources_export_excel_bytes,
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


def test_import_sources_from_excel_bytes_helix_normalizes_headers_and_sorts_by_country_alias() -> (
    None
):
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
    assert imported.settings_values == {}
    assert imported.rows[0]["country"] == "España"
    assert imported.rows[0]["alias"] == "Incident Report"
    assert imported.rows[1]["country"] == "México"
    assert imported.rows[1]["alias"] == "MX SmartIT"
    assert imported.rows[1]["source_id"] == build_source_id("helix", "México", "MX SmartIT")
    assert imported.rows[0]["source_id"] == build_source_id("helix", "España", "Incident Report")


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
    assert imported.settings_values == {}
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


def test_build_sources_export_excel_bytes_includes_transversal_sheet() -> None:
    settings = Settings(
        HELIX_PROXY="http://127.0.0.1:8999",
        HELIX_BROWSER="chrome",
        HELIX_SSL_VERIFY="false",
        HELIX_DASHBOARD_URL="https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console",
        HELIX_SOURCES_JSON=(
            '[{"country":"México","alias":"MX SmartIT","service_origin_buug":"BBVA México",'
            '"service_origin_n1":"ENTERPRISE WEB"}]'
        ),
    )

    payload = build_sources_export_excel_bytes(settings, source_type="helix")
    xl = pd.ExcelFile(BytesIO(payload))

    assert "Fuentes Helix" in xl.sheet_names
    assert _TRANSVERSAL_SHEET_NAME in xl.sheet_names
    trans = xl.parse(_TRANSVERSAL_SHEET_NAME)
    assert set(trans.columns) == {"key", "value"}
    values = {str(row["key"]): str(row["value"]) for row in trans.to_dict(orient="records")}
    assert values["HELIX_PROXY"] == "http://127.0.0.1:8999"
    assert values["HELIX_BROWSER"] == "chrome"
    assert values["HELIX_SSL_VERIFY"] == "false"
    assert values["HELIX_COOKIE_SOURCE"] == "browser"


def test_import_sources_from_excel_bytes_reads_transversal_values_sheet() -> None:
    source = pd.DataFrame(
        [
            {
                "country": "México",
                "alias": "MX SmartIT",
                "service_origin_buug": "BBVA México",
                "service_origin_n1": "ENTERPRISE WEB",
            }
        ]
    )
    trans = pd.DataFrame(
        [
            {"key": "HELIX_PROXY", "value": "http://127.0.0.1:8999"},
            {"key": "HELIX_BROWSER", "value": "chrome"},
            {"key": "HELIX_SSL_VERIFY", "value": "false"},
            {
                "key": "HELIX_DASHBOARD_URL",
                "value": "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console",
            },
            {"key": "HELIX_COOKIE_SOURCE", "value": "manual"},
        ]
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        source.to_excel(writer, index=False, sheet_name="Fuentes Helix")
        trans.to_excel(writer, index=False, sheet_name=_TRANSVERSAL_SHEET_NAME)

    imported = import_sources_from_excel_bytes(
        buffer.getvalue(),
        source_type="helix",
        countries=["México"],
    )

    assert imported.imported_rows == 1
    assert imported.skipped_rows == 0
    assert imported.settings_values == {
        "HELIX_PROXY": "http://127.0.0.1:8999",
        "HELIX_BROWSER": "chrome",
        "HELIX_SSL_VERIFY": "false",
        "HELIX_DASHBOARD_URL": "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console",
        "HELIX_COOKIE_SOURCE": "manual",
    }


def test_import_sources_from_excel_bytes_jira_sorts_by_country_alias() -> None:
    frame = pd.DataFrame(
        [
            {"country": "México", "alias": "Zeta", "jql": "project = MX"},
            {"country": "España", "alias": "Alpha", "jql": "project = ES"},
            {"country": "España", "alias": "Zeta", "jql": "project = ES"},
        ]
    )

    imported = import_sources_from_excel_bytes(
        _build_excel_bytes(frame),
        source_type="jira",
        countries=["México", "España"],
    )

    assert imported.imported_rows == 3
    assert imported.rows[0]["country"] == "España"
    assert imported.rows[0]["alias"] == "Alpha"
    assert imported.rows[1]["country"] == "España"
    assert imported.rows[1]["alias"] == "Zeta"
    assert imported.rows[2]["country"] == "México"
