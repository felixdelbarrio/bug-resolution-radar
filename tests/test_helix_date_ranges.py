from datetime import datetime, timezone

from bug_resolution_radar.ingest.helix_ingest import (
    _build_filter_criteria,
    _utc_year_create_date_range_ms,
)


def test_utc_year_create_date_range_ms_uses_full_year_boundaries() -> None:
    start_ms, end_ms, year = _utc_year_create_date_range_ms(2026)

    expected_start = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    expected_end = int(datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp() * 1000) - 1

    assert year == 2026
    assert start_ms == expected_start
    assert end_ms == expected_end


def test_utc_year_create_date_range_ms_falls_back_to_current_year_on_invalid_input() -> None:
    _, _, year = _utc_year_create_date_range_ms("abc")

    assert year == datetime.now(timezone.utc).year


def test_utc_year_create_date_range_ms_defaults_to_current_year() -> None:
    _, _, year = _utc_year_create_date_range_ms()

    assert year == datetime.now(timezone.utc).year


def test_build_filter_criteria_includes_create_date_ranges() -> None:
    criteria = _build_filter_criteria("ENTERPRISE WEB SYSTEMS SERVICE OWNER", 1, 2)

    assert criteria == {
        "organizations": ["ENTERPRISE WEB SYSTEMS SERVICE OWNER"],
        "createDateRanges": [{"start": 1, "end": 2}],
    }


def test_build_filter_criteria_includes_optional_filters() -> None:
    criteria = _build_filter_criteria(
        "ENTERPRISE WEB SYSTEMS SERVICE OWNER",
        1,
        2,
        status_mappings=["open", "close"],
        incident_types=["User Service Restoration", "Security Incident"],
        priorities=["High", "Low"],
        companies=[{"name": "BBVA México"}],
        risk_level=["Risk Level 1", "Risk Level 2"],
    )

    assert criteria == {
        "organizations": ["ENTERPRISE WEB SYSTEMS SERVICE OWNER"],
        "createDateRanges": [{"start": 1, "end": 2}],
        "statusMappings": ["open", "close"],
        "incidentTypes": ["User Service Restoration", "Security Incident"],
        "priorities": ["High", "Low"],
        "companies": [{"name": "BBVA México"}],
        "riskLevel": ["Risk Level 1", "Risk Level 2"],
    }
