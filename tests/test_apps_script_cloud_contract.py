from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS_SCRIPT = ROOT / "apps-script"


def _source(name: str) -> str:
    return (APPS_SCRIPT / name).read_text(encoding="utf-8")


def _function_body(source: str, function_name: str) -> str:
    match = re.search(
        rf"\bfunction\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{",
        source,
    )
    assert match is not None, f"No existe la función {function_name}"
    start = match.end()
    depth = 1
    index = start
    quote = ""
    escaped = False
    while index < len(source):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
        index += 1
    raise AssertionError(f"La función {function_name} no cierra correctamente")


def test_apps_script_sources_are_valid_javascript() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(APPS_SCRIPT.glob("*.gs"))
    )
    result = subprocess.run(
        ["node", "--check", "-"],
        input=sources,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_apps_script_has_no_duplicate_global_functions() -> None:
    declarations: dict[str, list[str]] = {}
    for path in sorted(APPS_SCRIPT.glob("*.gs")):
        for function_name in re.findall(
            r"(?m)^function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(",
            path.read_text(encoding="utf-8"),
        ):
            declarations.setdefault(function_name, []).append(path.name)
    duplicates = {
        function_name: files for function_name, files in declarations.items() if len(files) > 1
    }
    assert duplicates == {}


def test_cloud_transfer_is_strict_desktop_authoritative_v2() -> None:
    config = _source("00_Config.gs")
    adapters = _source("20_Adapters.gs")

    assert re.search(r"transferVersion:\s*2\b", config)
    assert "desktop-authoritative-v1" in config
    assert "data/projection.json" in adapters
    assert "artifacts/period_followup.pptx" in adapters
    assert "data/issues.json" not in adapters
    assert "data/helix.json" not in adapters
    assert "insights_learning.json" not in adapters
    assert "_validateNoCloudActionsDeep_" in adapters
    assert "issue_uid compuesto y único" in adapters


def test_dashboard_rpc_cannot_accept_incident_filters_or_recalculate_business_rules() -> None:
    materialized = _source("25_MaterializedSnapshots.gs")
    normalizer = _function_body(materialized, "_normalizeMaterializedRequest_")
    dashboard = _function_body(materialized, "_dashboardPayload_")

    for forbidden in (
        "status",
        "priority",
        "assignee",
        "functionality",
        "quincenalScope",
        "openOnly",
        "search",
        "issueKeys",
    ):
        assert re.search(rf"\b{forbidden}\b", normalizer) is None

    assert re.search(r"materialized|projection|snapshot", dashboard, re.IGNORECASE)
    for forbidden_helper in (
        "_computeMetrics_",
        "_insightsPayload_",
        "_issueRows_",
        "_reportingWindow_",
        "_applyFilters_",
    ):
        assert forbidden_helper not in dashboard

    all_server_code = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(APPS_SCRIPT.glob("*.gs"))
    )
    for obsolete_helper in (
        "_computeMetrics_",
        "_reportingWindow_",
        "_applyIssueFilters_",
    ):
        assert obsolete_helper not in all_server_code


def test_cloud_ui_has_no_incident_filter_controls_or_filter_drilldowns() -> None:
    app = _source("App.html")
    for obsolete_identifier in (
        "dashboardFilters",
        "quincenalScope",
        "issuesSearch",
        "insightsStatus",
        "insightsPriority",
        "insightsFunctionality",
        "insightFilterCombo",
        "applyDashboardFilters",
    ):
        assert obsolete_identifier not in app


def test_newsletter_attaches_the_canonical_pptx() -> None:
    newsletter = _source("56_Newsletter.gs")
    report_storage = _source("55_PeriodReport.gs")

    assert re.search(r"\battachments\s*:", newsletter)
    assert re.search(r"pptx", newsletter, re.IGNORECASE)
    assert "_exactReportBlob_" in newsletter
    assert re.search(r"getBlob\s*\(", report_storage)


def test_snapshot_parts_are_sectional_integrity_checked_and_sheet_safe() -> None:
    materialized = _source("25_MaterializedSnapshots.gs")
    writer = _function_body(materialized, "_appendSnapshotParts_")
    reader = _function_body(materialized, "_loadSnapshotPart_")

    assert "base64Encode" in writer
    assert "'b64:'" in writer
    assert "base64Decode" in reader
    assert "chunk_sha256" in reader
    assert "descriptor.sha256" in reader
    assert "MATERIALIZED_PARTS" in _source("00_Config.gs")


def test_issue_detail_uses_scope_and_composite_identity() -> None:
    main = _function_body(_source("10_Main.gs"), "getIssueDetail")
    app = _source("App.html")

    assert "scopeKey" in main
    assert "issueUid" in main
    assert "issueKey" not in main
    assert "issue_uid" in app
    assert re.search(
        r"getIssueDetail'\s*,\s*\{\s*scopeKey:\s*state\.scopeKey,\s*issueUid",
        app,
    )


def test_legacy_cloud_calculators_admin_and_report_queues_are_removed() -> None:
    all_code = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(APPS_SCRIPT.glob("*"))
        if path.is_file() and path.name != "BrandAssets.html"
    )
    for obsolete in (
        "_computeMetrics_",
        "_reportingWindow_",
        "_applyIssueFilters_",
        "processReportGenerationQueue",
        "runReportGenerationWatchdog",
        "_getHealthStatus_",
        "adminClearCaches",
        "_ensureContractSheet_",
        "_replaceRecords_",
    ):
        assert obsolete not in all_code
