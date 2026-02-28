from datetime import datetime, timedelta, timezone

from bug_resolution_radar.ingest.helix_ingest import (
    _arsql_missing_field_name_from_payload,
    _build_arsql_sql,
    _cache_pending_refresh_ids,
    _optimize_create_start_from_cache,
    _resolve_create_date_range_ms,
    _utc_year_create_date_range_ms,
)
from bug_resolution_radar.models.schema_helix import HelixWorkItem


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


def test_resolve_create_date_range_ms_defaults_to_natural_year_plus_7_days() -> None:
    now = datetime(2026, 2, 27, 10, 30, 0, tzinfo=timezone.utc)

    start_ms, end_ms, rule = _resolve_create_date_range_ms(now=now)

    expected_start = int(datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    expected_end = int((now + timedelta(days=7)).timestamp() * 1000)

    assert start_ms == expected_start
    assert end_ms == expected_end
    assert "natural_year=2026" in rule


def test_resolve_create_date_range_ms_uses_analysis_lookback_plus_one_month() -> None:
    now = datetime(2026, 2, 27, 10, 30, 0, tzinfo=timezone.utc)

    start_ms, end_ms, rule = _resolve_create_date_range_ms(
        analysis_lookback_months=12,
        now=now,
    )

    expected_start = int(datetime(2025, 1, 27, 10, 30, 0, tzinfo=timezone.utc).timestamp() * 1000)
    expected_end = int((now + timedelta(days=7)).timestamp() * 1000)

    assert start_ms == expected_start
    assert end_ms == expected_end
    assert "analysis_lookback_months=12" in rule
    assert "effective=13m" in rule


def test_optimize_create_start_from_cache_uses_recent_tail_even_with_non_final_items() -> None:
    base_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    base_end = int(datetime(2026, 2, 28, tzinfo=timezone.utc).timestamp() * 1000)
    cached_items = [
        HelixWorkItem(
            id="INC-1",
            status="Closed",
            source_id="helix:mexico:web",
            target_date="2025-02-01T00:00:00+00:00",
        ),
        HelixWorkItem(
            id="INC-2",
            status="Open",
            source_id="helix:mexico:web",
            target_date="2025-10-15T08:00:00+00:00",
        ),
        HelixWorkItem(
            id="INC-3",
            status="Resolved",
            source_id="helix:mexico:web",
            target_date="2026-01-20T00:00:00+00:00",
        ),
    ]

    optimized_start, rule = _optimize_create_start_from_cache(
        cached_items,
        base_start_ms=base_start,
        base_end_ms=base_end,
    )

    expected_start = int(
        (datetime(2026, 1, 20, 0, 0, 0, tzinfo=timezone.utc) - timedelta(days=7)).timestamp() * 1000
    )
    assert optimized_start == expected_start
    assert "cache_non_final=1/3" in rule


def test_cache_pending_refresh_ids_returns_only_non_final_ids_within_window() -> None:
    base_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    base_end = int(datetime(2026, 2, 28, tzinfo=timezone.utc).timestamp() * 1000)
    cached_items = [
        HelixWorkItem(
            id="INC-1",
            status="Closed",
            source_id="helix:mexico:web",
            target_date="2025-02-01T00:00:00+00:00",
        ),
        HelixWorkItem(
            id="INC-2",
            status="Open",
            source_id="helix:mexico:web",
            target_date="2025-10-15T08:00:00+00:00",
        ),
        HelixWorkItem(
            id="INC-3",
            status="Accepted",
            source_id="helix:mexico:web",
            target_date="2026-01-20T00:00:00+00:00",
        ),
    ]

    pending_ids = _cache_pending_refresh_ids(
        cached_items,
        base_start_ms=base_start,
        base_end_ms=base_end,
    )
    assert pending_ids == ["INC-2"]


def test_optimize_create_start_from_cache_all_final_uses_recent_tail_from_last_item() -> None:
    base_start = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    base_end = int(datetime(2026, 2, 28, tzinfo=timezone.utc).timestamp() * 1000)
    cached_items = [
        HelixWorkItem(
            id="INC-10",
            status="Closed",
            source_id="helix:mexico:web",
            target_date="2025-06-01T00:00:00+00:00",
        ),
        HelixWorkItem(
            id="INC-11",
            status="Resolved",
            source_id="helix:mexico:web",
            target_date="2025-12-10T12:00:00+00:00",
        ),
    ]

    optimized_start, rule = _optimize_create_start_from_cache(
        cached_items,
        base_start_ms=base_start,
        base_end_ms=base_end,
        all_final_tail_days=7,
    )

    expected_start = int(
        (datetime(2025, 12, 10, 12, 0, 0, tzinfo=timezone.utc) - timedelta(days=7)).timestamp()
        * 1000
    )
    assert optimized_start == expected_start
    assert "cache_all_final=2" in rule


def test_build_arsql_sql_includes_incident_ids_filter_when_provided() -> None:
    sql = _build_arsql_sql(
        create_start_ms=1000,
        create_end_ms=2000,
        limit=10,
        offset=0,
        incident_ids=["INC-1", "INC-2"],
        time_fields=["Submit Date"],
    )

    assert "`HPD:Help Desk`.`Incident Number` IN ('INC-1', 'INC-2')" in sql


def test_build_arsql_sql_contains_core_filters_and_pagination() -> None:
    sql = _build_arsql_sql(
        create_start_ms=1000,
        create_end_ms=2000,
        limit=75,
        offset=150,
        source_service_n1=["ENTERPRISE WEB"],
        source_service_n2=["WEB BBVA EMPRESAS", "APP - BBVA EMPRESAS"],
        incident_types=["User Service Restoration", "Security Incident"],
        companies=["BBVA México"],
    )

    assert "`HPD:Help Desk`.`Incident Number` AS `id`" in sql
    assert "`HPD:Help Desk`.`Incident Number` IS NOT NULL" in sql
    assert "`HPD:Help Desk`.`BBVA_SourceServiceN1` IN ('ENTERPRISE WEB')" in sql
    assert (
        "`HPD:Help Desk`.`BBVA_SourceServiceN2` IN ('WEB BBVA EMPRESAS', "
        "'APP - BBVA EMPRESAS')" in sql
    )
    assert (
        "`HPD:Help Desk`.`BBVA_Tipo_de_Incidencia` IN ('User Service Restoration', "
        "'Security Incident')" in sql
    )
    assert "`HPD:Help Desk`.`BBVA_SourceServiceBUUG` IN ('BBVA México')" in sql
    assert ", * FROM `HPD:Help Desk`" in sql
    assert "LIMIT 75 OFFSET 150" in sql


def test_build_arsql_sql_falls_back_incident_type_filter_to_service_type_with_mapped_values() -> (
    None
):
    sql = _build_arsql_sql(
        create_start_ms=1000,
        create_end_ms=2000,
        limit=25,
        offset=0,
        incident_types=["Incidencia", "Consulta", "Evento Monitorización"],
        disabled_fields={
            "BBVA_Tipo_de_Incidencia",
            "BBVA_TipoDeIncidencia",
            "BBVA_TipoIncidencia",
            "BBVA_TypeOfIncident",
            "BBVA_IncidentType",
            "Tipo_de_Incidencia",
        },
    )

    assert "`HPD:Help Desk`.`Service Type` IN (" in sql
    for token in (
        "'Incident'",
        "'Monitoring Event'",
        "'Event'",
        "'Evento Monitorización'",
        "'Question'",
        "'Consultation'",
        "'Request'",
        "'Service Request'",
    ):
        assert token in sql


def test_build_arsql_sql_can_filter_submit_date_only_and_environment() -> None:
    sql = _build_arsql_sql(
        create_start_ms=1000,
        create_end_ms=2000,
        limit=25,
        offset=0,
        environments=["Production"],
        time_fields=["Submit Date"],
    )

    assert "`HPD:Help Desk`.`Submit Date` BETWEEN" in sql
    assert "`HPD:Help Desk`.`Last Modified Date` BETWEEN" not in sql
    assert "`HPD:Help Desk`.`BBVA_Environment` IN ('Production', 'Producción')" in sql


def test_build_arsql_sql_can_disable_wide_select() -> None:
    sql = _build_arsql_sql(
        create_start_ms=1000,
        create_end_ms=2000,
        limit=10,
        offset=0,
        include_all_fields=False,
    )

    assert ", * FROM `HPD:Help Desk`" not in sql


def test_build_arsql_sql_falls_back_company_filter_when_source_buug_field_missing() -> None:
    sql = _build_arsql_sql(
        create_start_ms=1000,
        create_end_ms=2000,
        limit=10,
        offset=0,
        companies=["BBVA México"],
        disabled_fields={"BBVA_SourceServiceBUUG"},
    )

    assert "`HPD:Help Desk`.`BBVA_SourceServiceBUUG` IN ('BBVA México')" not in sql
    assert "`HPD:Help Desk`.`BBVA_SourceServiceCompany` IN ('BBVA México')" in sql


def test_build_arsql_sql_falls_back_company_filter_to_contact_company_as_last_resort() -> None:
    sql = _build_arsql_sql(
        create_start_ms=1000,
        create_end_ms=2000,
        limit=10,
        offset=0,
        companies=["BBVA México"],
        disabled_fields={"BBVA_SourceServiceBUUG", "BBVA_SourceServiceCompany"},
    )

    assert "`HPD:Help Desk`.`Contact Company` IN ('BBVA México')" in sql


def test_arsql_missing_field_name_from_payload_extracts_field_name() -> None:
    payload = [
        {
            "messageType": "ERROR",
            "messageText": "Field does not exist on current form",
            "messageAppendedText": "HPD:Help Desk : <BBVA_SourceServiceBUUG>",
            "messageNumber": 314,
        }
    ]
    assert _arsql_missing_field_name_from_payload(payload) == "BBVA_SourceServiceBUUG"
