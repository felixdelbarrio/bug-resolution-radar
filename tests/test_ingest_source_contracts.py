from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

import bug_resolution_radar.config as config_mod
from bug_resolution_radar.analytics.finalist_discrepancies import (
    POST_JQL_LOOKUP_HELIX_KIND,
    build_finalist_status_discrepancies,
)
from bug_resolution_radar.config import (
    Settings,
    all_configured_sources,
    country_rollup_sources,
    helix_service_origin_buug_for_country,
    jira_sources,
    rollup_source_ids,
    save_settings,
)
from bug_resolution_radar.ingest.helix_ingest import _build_arsql_sql
from bug_resolution_radar.ingest.jira_ingest import _jira_issue_to_normalized
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.models.schema_helix import HelixDocument, HelixWorkItem
from bug_resolution_radar.repositories.helix_repo import HelixRepo
from bug_resolution_radar.repositories.issues_store import load_issues_doc, save_issues_doc
from bug_resolution_radar.services import ingest_runner
from bug_resolution_radar.services.ingest_merge import helix_item_to_issue
from bug_resolution_radar.services.ingest_runner import (
    _chunk_count,
    _chunked,
    _jira_incidents_by_country,
    run_finalist_lookup_ingest,
    run_jira_ingest,
)
from bug_resolution_radar.services.settings_contracts import save_settings_payload
from bug_resolution_radar.services.sources_excel import (
    build_sources_export_dataframe,
    import_sources_from_excel_bytes,
)


def _excel_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_excel(buffer, index=False, sheet_name="Fuentes")
    return buffer.getvalue()


def test_helix_service_origin_buug_mapping_preserves_accents() -> None:
    assert helix_service_origin_buug_for_country("Argentina") == "BBVA Argentina"
    assert helix_service_origin_buug_for_country("Colombia") == "BBVA Colombia"
    assert helix_service_origin_buug_for_country("España") == "BBVA España"
    assert helix_service_origin_buug_for_country("México") == "BBVA México"
    assert helix_service_origin_buug_for_country("Perú") == "BBVA Perú"
    assert helix_service_origin_buug_for_country("Peru") == "BBVA Perú"


def test_helix_service_origin_buug_is_normalized_before_persist(
    monkeypatch: Any, tmp_path: Path
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(config_mod, "ENV_PATH", env_path)
    monkeypatch.setattr(config_mod, "ENV_EXAMPLE_PATH", tmp_path / ".env.example")
    settings = Settings(
        SUPPORTED_COUNTRIES="México,España,Peru,Colombia,Argentina",
        HELIX_SOURCES_JSON=(
            '[{"country":"Peru","alias":"PE SmartIT",'
            '"service_origin_buug":"BBVA Peru","service_origin_n1":"ENTERPRISE WEB"}]'
        ),
    )

    save_settings(settings)

    persisted = env_path.read_text(encoding="utf-8")
    assert "BBVA Perú" in persisted
    assert "BBVA Peru" not in persisted
    assert '"country":"Perú"' in persisted


def test_jira_sources_preserve_optional_po_team_leader() -> None:
    settings = Settings(
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"Core","po_team_leader":"Víctor Expósito",'
            '"jql":"project = CORE"}]'
        )
    )

    assert jira_sources(settings)[0]["po_team_leader"] == "Víctor Expósito"


def test_sources_excel_exports_and_imports_jira_po_team_leader() -> None:
    settings = Settings(
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"Core","po_team_leader":"Víctor Expósito",'
            '"jql":"project = CORE"}]'
        )
    )

    exported = build_sources_export_dataframe(settings, source_type="jira")
    assert list(exported.columns) == [
        "source_id",
        "country",
        "alias",
        "po_team_leader",
        "jql",
    ]
    assert exported.iloc[0]["po_team_leader"] == "Víctor Expósito"

    imported = import_sources_from_excel_bytes(
        _excel_bytes(
            pd.DataFrame(
                [
                    {
                        "País": "México",
                        "Alias": "Core",
                        "PO / Team Leader": "Víctor Expósito",
                        "JQL": "project = CORE",
                    },
                    {"País": "México", "Alias": "Retail", "JQL": "project = RET"},
                ]
            )
        ),
        source_type="jira",
        countries=["México"],
    )

    assert imported.rows[0]["po_team_leader"] == "Víctor Expósito"
    assert imported.rows[1]["po_team_leader"] == ""


def test_sources_excel_corrects_imported_helix_buug_for_peru() -> None:
    imported = import_sources_from_excel_bytes(
        _excel_bytes(
            pd.DataFrame(
                [
                    {
                        "País": "Peru",
                        "Alias": "PE SmartIT",
                        "Servicio origen BU/UG": "BBVA Peru",
                    }
                ]
            )
        ),
        source_type="helix",
        countries=["Perú"],
    )

    assert imported.rows[0]["country"] == "Perú"
    assert imported.rows[0]["service_origin_buug"] == "BBVA Perú"


def test_country_rollups_allow_three_or_more_sources_and_validate_country() -> None:
    settings = Settings(
        JIRA_SOURCES_JSON=(
            '[{"country":"México","alias":"Core","jql":"project = CORE"},'
            '{"country":"México","alias":"Retail","jql":"project = RET"},'
            '{"country":"México","alias":"Mobile","jql":"project = MOB"},'
            '{"country":"Colombia","alias":"Bogota","jql":"project = BOG"}]'
        ),
        COUNTRY_ROLLUP_SOURCES_JSON=(
            '[{"country":"México","source_ids":['
            '"jira:mexico:retail","jira:mexico:core","jira:mexico:mobile",'
            '"jira:mexico:core","jira:colombia:bogota","jira:mexico:missing"]}]'
        ),
    )

    assert country_rollup_sources(settings) == {
        "México": ["jira:mexico:retail", "jira:mexico:core", "jira:mexico:mobile"]
    }
    assert rollup_source_ids(settings, country="México") == [
        "jira:mexico:retail",
        "jira:mexico:core",
        "jira:mexico:mobile",
    ]


def test_rollup_source_id_stays_stable_when_source_alias_changes() -> None:
    settings = Settings(
        JIRA_SOURCES_JSON=(
            '[{"source_id":"jira:mexico:core-stable","country":"México",'
            '"alias":"Core nuevo","jql":"project = CORE"}]'
        ),
        HELIX_SOURCES_JSON=(
            '[{"source_id":"helix:mexico:smartit-stable","country":"México",'
            '"alias":"SmartIT nuevo","service_origin_n1":"ENTERPRISE WEB"}]'
        ),
        COUNTRY_ROLLUP_SOURCES_JSON=(
            '[{"country":"México","source_ids":['
            '"jira:mexico:core-stable","helix:mexico:smartit-stable"]}]'
        ),
    )

    assert country_rollup_sources(settings)["México"] == [
        "jira:mexico:core-stable",
        "helix:mexico:smartit-stable",
    ]
    labels = {source["source_id"]: source["alias"] for source in all_configured_sources(settings)}
    assert labels["jira:mexico:core-stable"] == "Core nuevo"
    assert labels["helix:mexico:smartit-stable"] == "SmartIT nuevo"


def test_save_settings_payload_persists_validated_rollups(monkeypatch: Any, tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(config_mod, "ENV_PATH", env_path)
    monkeypatch.setattr(config_mod, "ENV_EXAMPLE_PATH", tmp_path / ".env.example")
    payload = {
        "values": Settings().model_dump(),
        "supportedCountries": ["México", "Colombia"],
        "jiraSources": [
            {"country": "México", "alias": "Core", "jql": "project = CORE"},
            {"country": "México", "alias": "Retail", "jql": "project = RET"},
            {"country": "México", "alias": "Mobile", "jql": "project = MOB"},
            {"country": "Colombia", "alias": "Bogota", "jql": "project = BOG"},
        ],
        "helixSources": [],
        "countryRollupSources": {
            "México": [
                "jira:mexico:core",
                "jira:mexico:retail",
                "jira:mexico:mobile",
                "jira:colombia:bogota",
            ]
        },
        "jiraDisabledSourceIds": [],
        "helixDisabledSourceIds": [],
    }

    saved = save_settings_payload(payload)

    assert "FINALIST_STATUS_ANALYSIS_MODE" not in saved["values"]
    assert saved["countryRollupSources"]["México"] == [
        "jira:mexico:core",
        "jira:mexico:retail",
        "jira:mexico:mobile",
    ]
    persisted = env_path.read_text(encoding="utf-8")
    assert "FINALIST_STATUS_ANALYSIS_MODE" not in persisted


def test_frontend_does_not_expose_legacy_helix_buug_or_two_limit() -> None:
    root = Path(__file__).resolve().parents[1]
    settings_source = (root / "frontend/src/pages/SettingsPage.tsx").read_text(encoding="utf-8")
    ingest_source = (root / "frontend/src/pages/IngestPage.tsx").read_text(encoding="utf-8")
    reports_source = (root / "frontend/src/pages/ReportsPage.tsx").read_text(encoding="utf-8")

    assert "readOnly" in settings_source
    assert "PO / Team Leader" in settings_source
    assert "Modalidad del análisis" not in settings_source
    assert "Cruzar con estados finalistas ingestados del país" not in settings_source
    assert "Considerar sólo orígenes seleccionados" not in settings_source
    assert (
        "Incluir informe de incidencias con discrepancias en estado finalista"
        not in settings_source
    )
    assert "PERIOD_REPORT_FINALIST_DISCREPANCIES_ENABLED" not in settings_source
    assert "Buscar estados finalistas del país" in ingest_source
    assert "Considerar solo estados finalistas del país" not in settings_source
    assert "periodSourceIds.length < 2" not in reports_source
    assert "sin agregados configurados; se omiten slides agregadas" in reports_source


def test_jira_issue_normalization_sets_po_team_leader() -> None:
    issue = _jira_issue_to_normalized(
        {
            "key": "MEX-1",
            "fields": {
                "summary": "Issue con PO",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "MARCELA FONSECA MONTEALEGRE"},
            },
        },
        base_url="https://jira.example",
        country="México",
        alias="Core",
        source_id="jira:mexico:core",
        po_team_leader="Víctor Expósito",
    )

    assert issue.assignee == "MARCELA FONSECA MONTEALEGRE"
    assert issue.po_team_leader == "Víctor Expósito"


def test_jira_inc_lookup_extracts_only_non_finalist_description_incidents() -> None:
    doc = IssuesDocument(
        issues=[
            NormalizedIssue(
                key="MEX-1",
                summary="[Incidentes] INC000104216018",
                description="También aparece INC000104216018 en descripción",
                status="Open",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            ),
            NormalizedIssue(
                key="MEX-2",
                summary="Sin resumen Helix",
                description="Cruce INC000104216019",
                status="Open",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            ),
            NormalizedIssue(
                key="MEX-3",
                summary="Solo resumen INC000104216020",
                description="Plantilla sin incidente Helix",
                status="Open",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            ),
            NormalizedIssue(
                key="MEX-4",
                summary="Finalista",
                description="Cruce INC000104216021",
                status="Accepted",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            ),
            NormalizedIssue(
                key="MEX-5",
                summary="Finalista",
                description="Cruce INC000104216022",
                status="Ready to deploy",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            ),
            NormalizedIssue(
                key="MEX-6",
                summary="Finalista",
                description="Cruce INC000104216023",
                status="Deployed",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            ),
            NormalizedIssue(
                key="MEX-7",
                summary="Finalista typo legacy",
                description="Cruce INC000104216024",
                status="Acepted",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            ),
        ]
    )

    incs = _jira_incidents_by_country(
        doc,
        selected_sources=[{"source_id": "jira:mexico:core"}],
    )

    assert incs == {
        "México": {
            "INC000104216018": ["MEX-1"],
            "INC000104216019": ["MEX-2"],
        }
    }


def test_helix_lookup_batches_are_configurable_and_arsql_filters_buug() -> None:
    inc_ids = [f"INC{idx:012d}" for idx in range(100)]
    assert [len(batch) for batch in _chunked(inc_ids, size=25)] == [25, 25, 25, 25]
    assert _chunk_count(len(inc_ids), size=25) == 4

    sql = _build_arsql_sql(
        create_start_ms=0,
        create_end_ms=1000,
        limit=25,
        offset=0,
        source_service_n1=["ENTERPRISE WEB"],
        incident_types=["Incidencia"],
        incident_ids=["INC000104216018", "INC000104216019"],
        companies=["BBVA Perú"],
        environments=["Production"],
        time_fields=["Submit Date"],
        incident_ids_only=True,
    )

    assert "INC000104216018" in sql
    assert "INC000104216019" in sql
    assert "BBVA Perú" in sql
    assert "`HPD:Help Desk`.`BBVA_SourceServiceBUUG` IN ('BBVA Perú')" in sql


def test_shared_helix_item_mapping_preserves_lookup_metadata() -> None:
    item = HelixWorkItem(
        id="INC000104216018",
        summary="Cerrado",
        description="Detalle recuperado",
        executive_description="Impacto ejecutivo recuperado",
        status="Closed",
        closed_date="2026-05-21T00:00:00+00:00",
        last_modified="2026-05-22T00:00:00+00:00",
        country="México",
        source_id="helix:mexico:lookup-estados-finalistas-jira",
        source_alias="Lookup estados finalistas Jira",
        helix_lookup_kind=POST_JQL_LOOKUP_HELIX_KIND,
    )

    issue = helix_item_to_issue(item)

    assert issue.description == "Detalle recuperado"
    assert issue.helix_executive_description == "Impacto ejecutivo recuperado"
    assert issue.resolved == "2026-05-21T00:00:00+00:00"
    assert issue.helix_lookup_kind == POST_JQL_LOOKUP_HELIX_KIND


def test_finalist_lookup_ingest_persists_helix_internal_id_and_partial_progress(
    monkeypatch: Any, tmp_path: Path, caplog: Any
) -> None:
    data_path = tmp_path / "issues.json"
    helix_path = tmp_path / "helix.json"
    settings = Settings(
        DATA_PATH=str(data_path),
        HELIX_DATA_PATH=str(helix_path),
        HELIX_INC_LOOKUP_BATCH_SIZE=1,
    )
    selected_source = {
        "source_id": "jira:mexico:core",
        "source_type": "jira",
        "country": "México",
        "alias": "Core",
        "jql": "project = CORE",
    }
    jira_doc = IssuesDocument(
        issues=[
            NormalizedIssue(
                key="MEX-1",
                summary="[Incidentes] INC000104216018",
                description="Cruce operativo INC000104216018",
                status="To Rework",
                type="Bug",
                priority="High",
                assignee="Ana",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
                created="2026-05-01T00:00:00Z",
                updated="2026-05-20T00:00:00Z",
            ),
            NormalizedIssue(
                key="MEX-2",
                summary="Cruce INC000104216019",
                description="Cruce operativo INC000104216019",
                status="To Rework",
                type="Bug",
                priority="High",
                assignee="Luis",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
                created="2026-05-01T00:00:00Z",
                updated="2026-05-20T00:00:00Z",
            ),
        ]
    )

    def _fake_helix(*_: Any, **kwargs: Any) -> tuple[bool, str, HelixDocument]:
        batch = list(kwargs.get("incident_ids") or [])
        assert kwargs["service_origin_buug"] == "BBVA México"
        assert kwargs["allow_interactive_bootstrap"] is False
        assert kwargs["helix_lookup_kind"] == POST_JQL_LOOKUP_HELIX_KIND
        if batch == ["INC000104216019"]:
            raise RuntimeError("fallo controlado")
        item = HelixWorkItem(
            id="INC000104216018",
            internal_id="IDGAA5V0HK7ZIAQ0ABCDEF12345678",
            summary="Cerrado en Helix",
            description="Detalle recuperado",
            status="Closed",
            closed_date="2026-05-21T00:00:00+00:00",
            last_modified="2026-05-21T00:00:00+00:00",
            url="https://helix.example/smartit/app/#/incident/IDGAA5V0HK7ZIAQ0ABCDEF12345678",
            country="México",
            service_origin_buug="BBVA México",
            source_id=kwargs["source_id"],
            source_alias=kwargs["source_alias"],
            matched_jira_keys=["MEX-1"],
        )
        return True, "Helix OK", HelixDocument(items=[item])

    save_issues_doc(str(data_path), jira_doc)
    monkeypatch.setattr(ingest_runner, "lookup_helix_incidents_by_arsql", _fake_helix)
    events: list[tuple[str, str]] = []
    caplog.set_level(logging.INFO, logger="bug_resolution_radar.services.ingest_runner")

    result = run_finalist_lookup_ingest(
        settings,
        selected_sources=[selected_source],
        on_source_result=lambda ok, msg, _completed, _total: events.append(
            ("result", f"{ok}:{msg}")
        ),
        on_message=lambda _ok, msg: events.append(("message", msg)),
    )

    assert result["state"] == "partial"
    assert any("Iniciando ingesta" in event[1] for event in events)
    assert any(event[0] == "result" for event in events)
    stored = HelixRepo(helix_path).load()
    assert stored is not None
    assert stored.items[0].internal_id == "IDGAA5V0HK7ZIAQ0ABCDEF12345678"
    assert stored.items[0].matched_jira_keys == ["MEX-1"]
    saved_issue_keys = {issue.key for issue in load_issues_doc(str(data_path)).issues}
    assert "INC000104216018" in saved_issue_keys
    log_rows = [record for record in caplog.records if record.message == "helix_inc_lookup_batch"]
    assert len(log_rows) == 2
    assert any(getattr(record, "error", "") for record in log_rows)

    discrepancies = build_finalist_status_discrepancies(
        pd.DataFrame([issue.model_dump() for issue in load_issues_doc(str(data_path)).issues]),
        settings=Settings(),
        country="México",
        source_ids=["jira:mexico:core"],
        reference_day=pd.Timestamp("2026-05-22"),
    )
    assert discrepancies["helix_id"].tolist() == ["INC000104216018"]


def test_finalist_lookup_ingest_skips_without_inc_references(
    monkeypatch: Any, tmp_path: Path
) -> None:
    data_path = tmp_path / "issues.json"
    settings = Settings(
        DATA_PATH=str(data_path),
        HELIX_DATA_PATH=str(tmp_path / "helix.json"),
    )
    jira_doc = IssuesDocument(
        issues=[
            NormalizedIssue(
                key="MEX-1",
                summary="Sin incidente Helix",
                status="Open",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            )
        ]
    )

    save_issues_doc(str(data_path), jira_doc)

    result = run_finalist_lookup_ingest(
        settings,
        selected_sources=[
            {
                "source_id": "jira:mexico:core",
                "country": "México",
                "alias": "Core",
                "jql": "project = CORE",
            }
        ],
    )

    assert result["state"] == "skipped_no_inc"
    assert "no se encontraron referencias INC" in result["summary"]


def test_lookup_does_not_query_ad_hoc_incidents_already_closed_or_resolved(
    monkeypatch: Any, tmp_path: Path
) -> None:
    data_path = tmp_path / "issues.json"
    helix_path = tmp_path / "helix.json"
    HelixRepo(helix_path).save(
        HelixDocument(
            items=[
                HelixWorkItem(
                    id="INC000104216018",
                    status="Closed",
                    country="México",
                    source_id="helix:mexico:lookup-estados-finalistas-jira",
                    source_alias="Lookup estados finalistas Jira",
                    helix_lookup_kind=POST_JQL_LOOKUP_HELIX_KIND,
                    lookup_at="2026-05-22T00:00:00+00:00",
                )
            ]
        )
    )
    settings = Settings(
        DATA_PATH=str(data_path),
        HELIX_DATA_PATH=str(helix_path),
    )
    jira_doc = IssuesDocument(
        issues=[
            NormalizedIssue(
                key="MEX-1",
                summary="Cruce INC000104216018",
                description="Cruce operativo INC000104216018",
                status="Open",
                type="Bug",
                priority="High",
                country="México",
                source_type="jira",
                source_id="jira:mexico:core",
                source_alias="Core",
            )
        ]
    )
    called = False

    def _fail_if_called(**_: Any) -> tuple[bool, str, HelixDocument]:
        nonlocal called
        called = True
        return True, "unexpected", HelixDocument.empty()

    save_issues_doc(str(data_path), jira_doc)
    monkeypatch.setattr(ingest_runner, "lookup_helix_incidents_by_arsql", _fail_if_called)

    result = run_finalist_lookup_ingest(
        settings,
        selected_sources=[
            {
                "source_id": "jira:mexico:core",
                "country": "México",
                "alias": "Core",
                "jql": "project = CORE",
            }
        ],
    )

    assert result["state"] == "skipped_cached"
    assert called is False


def test_lookup_reuses_historical_finalist_helix_items_without_arsql(
    monkeypatch: Any, tmp_path: Path
) -> None:
    data_path = tmp_path / "issues.json"
    helix_path = tmp_path / "helix.json"
    HelixRepo(helix_path).save(
        HelixDocument(
            items=[
                HelixWorkItem(
                    id="INC000102885426",
                    status="Closed",
                    country="México",
                    service_origin_buug="BBVA México",
                    source_id="helix:mexico:mx-smartit",
                    source_alias="MX SmartIT",
                    lookup_at="2026-05-20T00:00:00+00:00",
                    url="https://helix.example/smartit/app/#/incidentPV/IDG102885426",
                )
            ]
        )
    )
    save_issues_doc(
        str(data_path),
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="SKSEMEX-84900",
                    summary="INC000102885426 - liquidez",
                    description="Cruce operativo INC000102885426",
                    status="En progreso",
                    type="Historia",
                    priority="Medium",
                    country="México",
                    source_type="jira",
                    source_id="jira:mexico:core",
                    source_alias="Core",
                )
            ]
        ),
    )
    called = False

    def _fail_if_called(**_: Any) -> tuple[bool, str, HelixDocument]:
        nonlocal called
        called = True
        return True, "unexpected", HelixDocument.empty()

    monkeypatch.setattr(ingest_runner, "lookup_helix_incidents_by_arsql", _fail_if_called)

    result = run_finalist_lookup_ingest(
        Settings(DATA_PATH=str(data_path), HELIX_DATA_PATH=str(helix_path)),
        selected_sources=[
            {
                "source_id": "jira:mexico:core",
                "country": "México",
                "alias": "Core",
                "jql": "project = CORE",
            }
        ],
    )

    assert result["state"] == "skipped_cached"
    assert result["cached_final_count"] == 1
    assert called is False
    stored_issues = load_issues_doc(str(data_path)).issues
    cached = next(issue for issue in stored_issues if issue.key == "INC000102885426")
    assert cached.source_id == "helix:mexico:lookup-estados-finalistas-jira"
    assert cached.helix_lookup_kind == POST_JQL_LOOKUP_HELIX_KIND
    assert cached.url == "https://helix.example/smartit/app/#/incidentPV/IDG102885426"


def test_run_jira_ingest_does_not_trigger_finalist_lookup(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[str] = []

    def _fake_jira(**_: Any) -> tuple[bool, str, IssuesDocument]:
        return (
            True,
            "Jira OK",
            IssuesDocument(
                issues=[
                    NormalizedIssue(
                        key="MEX-1",
                        summary="Cruce INC000104216018",
                        description="Cruce operativo INC000104216018",
                        status="Open",
                        type="Bug",
                        priority="High",
                        country="México",
                        source_type="jira",
                        source_id="jira:mexico:core",
                        source_alias="Core",
                    )
                ]
            ),
        )

    def _fake_lookup(*_: Any, **kwargs: Any) -> tuple[bool, str, HelixDocument]:
        calls.append(str(kwargs.get("source_id") or ""))
        return True, "Helix OK", HelixDocument.empty()

    monkeypatch.setattr(ingest_runner, "ingest_jira", _fake_jira)
    monkeypatch.setattr(ingest_runner, "lookup_helix_incidents_by_arsql", _fake_lookup)

    result = run_jira_ingest(
        Settings(
            DATA_PATH=str(tmp_path / "jira.json"),
            HELIX_DATA_PATH=str(tmp_path / "helix.json"),
        ),
        selected_sources=[
            {
                "source_id": "jira:mexico:core",
                "country": "México",
                "alias": "Core",
                "jql": "project = CORE",
            }
        ],
    )

    assert result["state"] == "success"
    assert "post_jql_lookup" not in result
    assert calls == []


def test_finalist_lookup_ingest_runs_independently_from_saved_jira_data(
    monkeypatch: Any, tmp_path: Path
) -> None:
    data_path = tmp_path / "issues.json"
    save_issues_doc(
        str(data_path),
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="MEX-1",
                    summary="Cruce INC000104216018",
                    description="Cruce operativo INC000104216018",
                    status="Open",
                    type="Bug",
                    priority="High",
                    country="México",
                    source_type="jira",
                    source_id="jira:mexico:core",
                    source_alias="Core",
                )
            ]
        ),
    )
    calls: list[str] = []

    def _fake_lookup(*_: Any, **kwargs: Any) -> tuple[bool, str, HelixDocument]:
        calls.extend(list(kwargs.get("incident_ids") or []))
        return True, "Helix OK", HelixDocument.empty()

    monkeypatch.setattr(ingest_runner, "lookup_helix_incidents_by_arsql", _fake_lookup)

    result = run_finalist_lookup_ingest(
        Settings(
            DATA_PATH=str(data_path),
            HELIX_DATA_PATH=str(tmp_path / "helix.json"),
        ),
        selected_sources=[
            {
                "source_id": "jira:mexico:core",
                "country": "México",
                "alias": "Core",
                "jql": "project = CORE",
            }
        ],
    )

    assert result["state"] == "success"
    assert calls == ["INC000104216018"]


def test_finalist_lookup_stops_batches_when_session_unavailable(
    monkeypatch: Any, tmp_path: Path
) -> None:
    data_path = tmp_path / "issues.json"
    helix_path = tmp_path / "helix.json"
    settings = Settings(
        DATA_PATH=str(data_path),
        HELIX_DATA_PATH=str(helix_path),
        HELIX_INC_LOOKUP_BATCH_SIZE=1,
    )
    calls = 0

    save_issues_doc(
        str(data_path),
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="MEX-1",
                    summary="Cruce INC000104216018 INC000104216019 INC000104216020",
                    description="Cruce operativo INC000104216018 INC000104216019 INC000104216020",
                    status="Open",
                    type="Bug",
                    priority="High",
                    country="México",
                    source_type="jira",
                    source_id="jira:mexico:core",
                    source_alias="Core",
                )
            ]
        ),
    )

    def _fake_lookup(*_: Any, **__: Any) -> tuple[bool, str, None]:
        nonlocal calls
        calls += 1
        return (
            False,
            "México · Lookup estados finalistas Jira: "
            "Helix session unavailable for non-interactive ARSQL lookup.",
            None,
        )

    monkeypatch.setattr(ingest_runner, "lookup_helix_incidents_by_arsql", _fake_lookup)

    result = run_finalist_lookup_ingest(
        settings,
        selected_sources=[
            {
                "source_id": "jira:mexico:core",
                "country": "México",
                "alias": "Core",
                "jql": "project = CORE",
            }
        ],
    )

    assert calls == 1
    assert result["state"] == "error"
    assert result["missing_count"] == 3
    assert result["error_count"] == 1
    assert any(
        "detenido tras error de sesión" in str(message.get("message") or "")
        for message in result["messages"]
    )
    persisted = HelixRepo(helix_path).load()
    assert persisted is not None
    assert {item.id for item in persisted.items if item.lookup_status == "error"} == {
        "INC000104216018",
        "INC000104216019",
        "INC000104216020",
    }
