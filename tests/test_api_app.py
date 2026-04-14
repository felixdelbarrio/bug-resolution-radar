from __future__ import annotations

import importlib
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from bug_resolution_radar.config import Settings, build_source_id
from bug_resolution_radar.models.schema import IssuesDocument, NormalizedIssue
from bug_resolution_radar.reports.executive_ppt import ExecutiveReportResult
from bug_resolution_radar.reports.period_followup_ppt import PeriodFollowupReportResult
from bug_resolution_radar.repositories.issues_store import save_issues_doc

api_app = importlib.import_module("bug_resolution_radar.api.app")
dashboard_snapshot = importlib.import_module("bug_resolution_radar.services.dashboard_snapshot")


def _settings(tmp_path: Path) -> Settings:
    source_id = build_source_id("jira", "España", "Core")
    return Settings(
        APP_TITLE="Radar",
        DATA_PATH=str((tmp_path / "issues.json").resolve()),
        NOTES_PATH=str((tmp_path / "notes.json").resolve()),
        INSIGHTS_LEARNING_PATH=str((tmp_path / "learning.json").resolve()),
        HELIX_DATA_PATH=str((tmp_path / "helix.json").resolve()),
        JIRA_SOURCES_JSON='[{"country":"España","alias":"Core","jql":"project = RADAR"}]',
        HELIX_SOURCES_JSON=(
            '[{"country":"España","alias":"Helix Core","service_origin_buug":"Canales",'
            '"service_origin_n1":"Pagos","service_origin_n2":"Transferencias"}]'
        ),
        REPORT_PPT_DOWNLOAD_DIR=str((tmp_path / "exports").resolve()),
        PERIOD_PPT_TEMPLATE_PATH="",
        JIRA_BROWSER="chrome",
        HELIX_BROWSER="chrome",
        COUNTRY_ROLLUP_SOURCES_JSON=f'[{{"country":"España","source_ids":["{source_id}"]}}]',
    )


def _seed_issues(settings: Settings) -> str:
    source_id = build_source_id("jira", "España", "Core")
    now = datetime.now(timezone.utc).isoformat()
    save_issues_doc(
        settings.DATA_PATH,
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="RAD-1",
                    summary="Error en login",
                    status="Open",
                    type="Bug",
                    priority="High",
                    created=now,
                    updated=now,
                    assignee="Alice",
                    country="España",
                    source_alias="Core",
                    source_id=source_id,
                    source_type="jira",
                    url="https://jira.example.com/browse/RAD-1",
                )
            ]
        ),
    )
    return source_id


def _seed_functionality_issues(settings: Settings) -> str:
    source_id = build_source_id("jira", "España", "Core")
    base_dt = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc).isoformat()
    save_issues_doc(
        settings.DATA_PATH,
        IssuesDocument(
            issues=[
                NormalizedIssue(
                    key="RAD-10",
                    summary="Error en pagos SPEI",
                    status="New",
                    type="Bug",
                    priority="High",
                    created=base_dt,
                    updated=base_dt,
                    assignee="Alice",
                    country="España",
                    source_alias="Core",
                    source_id=source_id,
                    source_type="jira",
                    url="https://jira.example.com/browse/RAD-10",
                ),
                NormalizedIssue(
                    key="RAD-11",
                    summary="Fallo de login y acceso en web",
                    status="Analysing",
                    type="Bug",
                    priority="Medium",
                    created=base_dt,
                    updated=base_dt,
                    assignee="Bob",
                    country="España",
                    source_alias="Core",
                    source_id=source_id,
                    source_type="jira",
                    url="https://jira.example.com/browse/RAD-11",
                ),
                NormalizedIssue(
                    key="RAD-12",
                    summary="Transferencia internacional rechazada",
                    status="Blocked",
                    type="Bug",
                    priority="Highest",
                    created=base_dt,
                    updated=base_dt,
                    assignee="Carol",
                    country="España",
                    source_alias="Core",
                    source_id=source_id,
                    source_type="jira",
                    url="https://jira.example.com/browse/RAD-12",
                ),
                NormalizedIssue(
                    key="RAD-13",
                    summary="Pagos duplicados en app móvil",
                    status="Analysing",
                    type="Bug",
                    priority="High",
                    created=base_dt,
                    updated=base_dt,
                    assignee="Dana",
                    country="España",
                    source_alias="Core",
                    source_id=source_id,
                    source_type="jira",
                    url="https://jira.example.com/browse/RAD-13",
                ),
            ]
        ),
    )
    return source_id


def test_health_endpoint_reports_ok() -> None:
    client = TestClient(api_app.create_app())
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_dashboard_endpoint_returns_scoped_metrics(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    response = client.get(
        "/api/dashboard",
        params={"country": "España", "sourceId": source_id, "scopeMode": "source"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stats"]["issues_total"] == 1
    assert payload["stats"]["issues_open"] == 1
    assert len(payload["overviewKpis"]) == 4
    assert payload["focusCards"]
    assert payload["statusPriorityMatrix"]["total"] == 1
    assert payload["workspace"]["selectedCountry"] == "España"
    assert payload["workspace"]["selectedSourceId"] == source_id
    assert payload["workspace"]["hasCountryRollup"] is True
    assert payload["workspace"]["countryRollupSourceIds"] == [source_id]


def test_bootstrap_infers_workspace_sources_from_data_when_settings_are_empty(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = Settings(
        APP_TITLE="Radar",
        DATA_PATH=str((tmp_path / "issues.json").resolve()),
        NOTES_PATH=str((tmp_path / "notes.json").resolve()),
        INSIGHTS_LEARNING_PATH=str((tmp_path / "learning.json").resolve()),
        HELIX_DATA_PATH=str((tmp_path / "helix.json").resolve()),
        JIRA_SOURCES_JSON="[]",
        HELIX_SOURCES_JSON="[]",
        REPORT_PPT_DOWNLOAD_DIR=str((tmp_path / "exports").resolve()),
    )
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    response = client.get("/api/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["defaultFilters"] == {"status": [], "priority": [], "assignee": []}
    assert payload["dashboardDefaults"]["defaultTrendChartId"] == "open_status_bar"
    assert payload["workspace"]["selectedCountry"] == "España"
    assert payload["workspace"]["selectedSourceId"] == source_id
    assert payload["workspace"]["sources"][0]["alias"] == "Core"
    assert payload["workspace"]["sources"][0]["source_type"] == "jira"
    assert payload["workspace"]["hasCountryRollup"] is False
    assert payload["workspace"]["countryRollupSourceIds"] == []
    assert payload["workspace"]["filterOptions"]["quincenal"][0] == "Todas"
    assert "designTokens" in payload
    assert "theme" in payload["designTokens"]
    assert "semantic" in payload["designTokens"]
    assert payload["designTokens"]["semantic"]["statusByKey"]["new"] == "#E85D63"
    assert "--bbva-primary" in payload["designTokens"]["theme"]["light"]


def test_scope_context_cache_reuses_filtered_context_for_same_query(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)
    dashboard_snapshot._scope_context_cache.clear()

    original_apply_filters = dashboard_snapshot.apply_filters
    call_count = {"value": 0}

    def _spy_apply_filters(*args, **kwargs):  # type: ignore[no-untyped-def]
        call_count["value"] += 1
        return original_apply_filters(*args, **kwargs)

    monkeypatch.setattr(dashboard_snapshot, "apply_filters", _spy_apply_filters)

    client = TestClient(api_app.create_app())
    params = {"country": "España", "sourceId": source_id, "scopeMode": "source"}
    dashboard_response = client.get("/api/dashboard", params=params)
    issues_response = client.get("/api/issues", params=params)

    assert dashboard_response.status_code == 200
    assert issues_response.status_code == 200
    assert call_count["value"] == 1


def test_trend_detail_and_issue_keys_endpoints_return_filtered_contracts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    trend_response = client.get(
        "/api/trends/detail",
        params={
            "country": "España",
            "sourceId": source_id,
            "scopeMode": "source",
            "chartId": "open_status_bar",
        },
    )
    keys_response = client.get(
        "/api/issues/keys",
        params={
            "country": "España",
            "sourceId": source_id,
            "scopeMode": "source",
        },
    )

    assert trend_response.status_code == 200
    assert trend_response.json()["chart"]["id"] == "open_status_bar"
    assert isinstance(trend_response.json()["sessionDelta"], list)
    assert keys_response.status_code == 200
    assert keys_response.json() == {"total": 1, "keys": ["RAD-1"]}


def test_intelligence_endpoint_returns_streamlit_aligned_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    response = client.get(
        "/api/intelligence",
        params={
            "country": "España",
            "sourceId": source_id,
            "scopeMode": "source",
            "insightsViewMode": "quincenal",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [tab["id"] for tab in payload["tabs"]] == [
        "summary",
        "functionality",
        "duplicates",
        "people",
        "opsHealth",
    ]
    assert "caption" in payload["periodSummary"]
    assert payload["periodSummary"]["cards"]
    assert payload["functionality"]["combo"]["viewMode"] == "quincenal"
    assert "statusOptions" in payload["functionality"]["combo"]
    assert isinstance(payload["functionality"]["topics"], list)
    assert "followup" in payload["functionality"]
    assert isinstance(payload["functionality"]["followup"]["topThree"], list)
    if payload["functionality"]["followup"]["topThree"]:
        first = payload["functionality"]["followup"]["topThree"][0]
        assert "avgOpenDays" in first
        assert "d. promedio" in str(first.get("label", ""))
    assert "brief" in payload["duplicates"]
    assert "cards" in payload["people"]
    assert "kpis" in payload["opsHealth"]


def test_issues_and_kanban_endpoints_serialize_rows_without_pandas_scalars(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    issues_response = client.get(
        "/api/issues",
        params={
            "country": "España",
            "sourceId": source_id,
            "scopeMode": "source",
        },
    )
    kanban_response = client.get(
        "/api/kanban",
        params={
            "country": "España",
            "sourceId": source_id,
            "scopeMode": "source",
        },
    )

    assert issues_response.status_code == 200
    issue_payload = issues_response.json()
    assert issue_payload["total"] == 1
    assert issue_payload["rows"][0]["key"] == "RAD-1"
    assert isinstance(issue_payload["rows"][0]["updated"], str)

    assert kanban_response.status_code == 200
    kanban_payload = kanban_response.json()
    assert kanban_payload[0]["status"] == "Open"
    assert kanban_payload[0]["items"][0]["key"] == "RAD-1"
    assert isinstance(kanban_payload[0]["items"][0]["ageDays"], float)


def test_browser_open_endpoint_allows_fallback_only_on_explicit_click(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)
    captured: dict[str, object] = {}

    def _fake_open(url: str, browser: str, *, allow_system_default_fallback: bool = True) -> bool:
        captured["url"] = url
        captured["browser"] = browser
        captured["allow_system_default_fallback"] = allow_system_default_fallback
        return False

    monkeypatch.setattr(api_app, "open_url_in_configured_browser", _fake_open)

    client = TestClient(api_app.create_app())
    response = client.post(
        "/api/browser/open",
        json={
            "url": "https://jira.example.com/browse/RAD-1",
            "sourceType": "jira",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "opened": False,
        "browser": "chrome",
        "url": "https://jira.example.com/browse/RAD-1",
    }
    assert captured["browser"] == "chrome"
    assert captured["allow_system_default_fallback"] is True


def test_ingest_overview_endpoint_exposes_streamlit_aligned_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    response = client.get("/api/ingest/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["jira"]["configuredCount"] == 1
    assert payload["jira"]["selectedSourceIds"] == [build_source_id("jira", "España", "Core")]
    assert payload["jira"]["lastIngest"]["issues_count"] == 1
    assert payload["helix"]["configuredCount"] == 1
    assert payload["helix"]["lastIngest"]["data_path"].endswith("helix.json")


def test_ingest_selection_endpoint_persists_source_selection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_id = build_source_id("jira", "España", "Core")
    captured: dict[str, object] = {}

    def _fake_persist(
        current: Settings,
        *,
        connector: str,
        selected_source_ids: list[str],
    ) -> Settings:
        captured["connector"] = connector
        captured["selected_source_ids"] = list(selected_source_ids)
        return current.model_copy(update={"JIRA_INGEST_DISABLED_SOURCES_JSON": "[]"})

    monkeypatch.setattr(api_app, "load_settings", lambda: settings)
    monkeypatch.setattr(api_app, "persist_ingest_selection", _fake_persist)

    client = TestClient(api_app.create_app())
    response = client.put("/api/ingest/jira/selection", json={"sourceIds": [source_id]})

    assert response.status_code == 200
    assert captured == {
        "connector": "jira",
        "selected_source_ids": [source_id],
    }
    assert response.json()["jira"]["selectedSourceIds"] == [source_id]


def test_ingest_test_endpoints_run_only_under_explicit_click(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    jira_source_id = build_source_id("jira", "España", "Core")
    helix_source_id = build_source_id("helix", "España", "Helix Core")
    called: list[tuple[str, dict[str, object]]] = []

    def _fake_jira_ingest(*, settings: Settings, dry_run: bool, source: dict[str, str]):
        called.append(("jira", {"dry_run": dry_run, "source_id": source["source_id"]}))
        return True, "jira ok", None

    def _fake_helix_ingest(**kwargs):
        called.append(
            (
                "helix",
                {
                    "dry_run": kwargs.get("dry_run"),
                    "source_id": kwargs.get("source_id"),
                },
            )
        )
        return True, "helix ok", None

    monkeypatch.setattr(api_app, "load_settings", lambda: settings)
    monkeypatch.setattr(api_app, "execute_jira_ingest", _fake_jira_ingest)
    monkeypatch.setattr(api_app, "execute_helix_ingest", _fake_helix_ingest)

    client = TestClient(api_app.create_app())
    jira_response = client.post("/api/ingest/jira/test", json={"sourceIds": [jira_source_id]})
    helix_response = client.post(
        "/api/ingest/helix/test",
        json={"sourceIds": [helix_source_id]},
    )

    assert jira_response.status_code == 200
    assert helix_response.status_code == 200
    assert jira_response.json()["summary"] == "Test Jira OK."
    assert helix_response.json()["summary"] == "Test Helix OK."
    assert called == [
        ("jira", {"dry_run": True, "source_id": jira_source_id}),
        ("helix", {"dry_run": True, "source_id": helix_source_id}),
    ]


def test_helix_ingest_test_endpoint_syncs_settings_into_process_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path).model_copy(
        update={
            "HELIX_DASHBOARD_URL": "https://itsmhelixbbva-smartit.onbmc.com/smartit/app/#/ticket-console",
            "HELIX_PROXY": "http://127.0.0.1:8999",
            "HELIX_SSL_VERIFY": "false",
            "HELIX_ARSQL_BASE_URL": "https://itsmhelixbbva-ir1.onbmc.com",
        }
    )
    helix_source_id = build_source_id("helix", "España", "Helix Core")
    captured: dict[str, str] = {}

    def _fake_helix_ingest(**kwargs):
        del kwargs
        captured["HELIX_DASHBOARD_URL"] = str(os.getenv("HELIX_DASHBOARD_URL", ""))
        captured["HELIX_PROXY"] = str(os.getenv("HELIX_PROXY", ""))
        captured["HELIX_SSL_VERIFY"] = str(os.getenv("HELIX_SSL_VERIFY", ""))
        captured["HELIX_ARSQL_BASE_URL"] = str(os.getenv("HELIX_ARSQL_BASE_URL", ""))
        return True, "helix ok", None

    monkeypatch.setattr(api_app, "load_settings", lambda: settings)
    monkeypatch.setattr(api_app, "execute_helix_ingest", _fake_helix_ingest)

    client = TestClient(api_app.create_app())
    response = client.post(
        "/api/ingest/helix/test",
        json={"sourceIds": [helix_source_id]},
    )

    assert response.status_code == 200
    assert captured == {
        "HELIX_DASHBOARD_URL": settings.HELIX_DASHBOARD_URL,
        "HELIX_PROXY": settings.HELIX_PROXY,
        "HELIX_SSL_VERIFY": settings.HELIX_SSL_VERIFY,
        "HELIX_ARSQL_BASE_URL": settings.HELIX_ARSQL_BASE_URL,
    }


def test_intelligence_functionality_chart_uses_dark_mode_palette_and_stack_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_functionality_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    response = client.get(
        "/api/intelligence",
        params={
            "country": "España",
            "sourceId": source_id,
            "scopeMode": "source",
            "insightsViewMode": "acumulada",
            "darkMode": "true",
        },
    )

    assert response.status_code == 200
    figure = response.json()["functionality"]["chart"]["figure"]
    bar_traces = [trace for trace in figure["data"] if trace.get("type") == "bar"]
    assert [trace["name"] for trace in bar_traces] == [
        "Transferencias",
        "Login y acceso",
        "Pagos",
    ]
    assert [trace["marker"]["color"] for trace in bar_traces] == [
        "#85C8FF",
        "#0051F1",
        "#D64550",
    ]


def test_notes_endpoint_roundtrip(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    put_response = client.put("/api/notes/RAD-9", json={"note": "Investigar con backend"})
    get_response = client.get("/api/notes/RAD-9")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["note"] == "Investigar con backend"


def test_issues_export_endpoint_streams_file(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    response = client.get(
        "/api/issues/export",
        params={
            "country": "España",
            "sourceId": source_id,
            "scopeMode": "source",
            "format": "csv",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "RAD-1" in response.text


def test_settings_sources_export_endpoint_streams_helix_xlsx(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    response = client.get("/api/settings/sources/export", params={"sourceType": "helix"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    frame = pd.read_excel(BytesIO(response.content), sheet_name=0)
    assert list(frame.columns) == [
        "source_id",
        "country",
        "alias",
        "service_origin_buug",
        "service_origin_n1",
        "service_origin_n2",
    ]
    assert frame.iloc[0]["country"] == "España"
    assert frame.iloc[0]["alias"] == "Helix Core"


def test_settings_sources_import_endpoint_parses_helix_excel_and_preserves_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    import_frame = pd.DataFrame(
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
            },
        ]
    )
    buffer = BytesIO()
    import_frame.to_excel(buffer, index=False, sheet_name="Fuentes Helix")

    client = TestClient(api_app.create_app())
    response = client.post(
        "/api/settings/sources/import?sourceType=helix",
        content=buffer.getvalue(),
        headers={
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sourceType"] == "helix"
    assert payload["importedRows"] == 2
    assert payload["skippedRows"] == 0
    assert payload["rows"][0]["country"] == "México"
    assert payload["rows"][0]["alias"] == "MX SmartIT"
    assert payload["rows"][0]["source_type"] == "helix"


def test_dashboard_charts_use_backend_semantic_tokens(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    client = TestClient(api_app.create_app())
    response = client.get(
        "/api/dashboard",
        params={"country": "España", "sourceId": source_id, "scopeMode": "source"},
    )

    assert response.status_code == 200
    charts = {chart["id"]: chart["figure"] for chart in response.json()["charts"]}
    assert charts["timeseries"]["data"][0]["marker"]["color"] == "#E85D63"
    assert charts["age_buckets"]["data"][0]["marker"]["color"] == "#FBBF24"
    assert charts["resolution_hist"]["data"][0]["marker"]["color"] == "#D64550"


def test_executive_report_save_endpoint_persists_artifact(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    def _fake_generate(*args, **kwargs):
        return ExecutiveReportResult(
            file_name="executive-test.pptx",
            content=b"ppt-data",
            slide_count=7,
            total_issues=11,
            open_issues=4,
            closed_issues=7,
            country="España",
            source_id=source_id,
            source_label="Core · JIRA",
            applied_filter_summary="Estado=Todos",
        )

    monkeypatch.setattr(api_app, "generate_executive_report_artifact", _fake_generate)

    client = TestClient(api_app.create_app())
    response = client.post(
        "/api/reports/executive/save",
        json={"country": "España", "sourceId": source_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fileName"] == "executive-test.pptx"
    assert payload["slideCount"] == 7
    assert payload["totalIssues"] == 11
    assert Path(payload["savedPath"]).read_bytes() == b"ppt-data"


def test_period_report_save_endpoint_persists_artifact(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    source_id = _seed_issues(settings)
    second_source_id = build_source_id("jira", "España", "Core 2")
    monkeypatch.setattr(api_app, "load_settings", lambda: settings)

    def _fake_generate(*args, **kwargs):
        return PeriodFollowupReportResult(
            file_name="period-test.pptx",
            content=b"period-ppt",
            slide_count=8,
            total_issues=15,
            open_issues=5,
            closed_issues=10,
            country="España",
            source_ids=(source_id, second_source_id),
            applied_filter_summary="Estado=Todos",
        )

    monkeypatch.setattr(api_app, "generate_period_followup_report_artifact", _fake_generate)

    client = TestClient(api_app.create_app())
    response = client.post(
        "/api/reports/period/save",
        json={"country": "España", "sourceIds": [source_id, second_source_id]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["fileName"] == "period-test.pptx"
    assert payload["slideCount"] == 8
    assert payload["totalIssues"] == 15
    assert Path(payload["savedPath"]).read_bytes() == b"period-ppt"
