from __future__ import annotations

import json
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


def test_apps_script_design_tokens_are_centralized_and_complete() -> None:
    config = _source("00_Config.gs")
    design = _source("DesignSystem.html")
    index = _source("Index.html")
    web_app = _source("60_WebApp.gs")
    newsletter = _function_body(_source("56_Newsletter.gs"), "_newsletterRender_")

    result = subprocess.run(
        ["node", "-"],
        input=config + "\nconsole.log(JSON.stringify(DESIGN_TOKENS.web));",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    web = json.loads(result.stdout)
    for mode in ("light", "dark"):
        assert web[mode]
        assert all(
            isinstance(name, str) and name.startswith("--") and isinstance(value, str) and value
            for name, value in web[mode].items()
        )
    for required in (
        "--bbva-grey-500",
        "--bbva-surface-2",
        "--bbva-shadow",
        "--bbva-radius-container",
        "--bbva-font-sans",
        "--signal-status-progress",
        "--chart-series-1",
    ):
        assert required in web["light"]

    assert "_clientBootstrapMarkup_(sharedToken || '')" in index
    assert "_include_('DesignSystem')" in index
    bootstrap = _function_body(web_app, "_clientBootstrapMarkup_")
    assert "DESIGN_TOKENS.web.light" in bootstrap
    assert "DESIGN_TOKENS.web.dark" in bootstrap
    assert "window.__RADAR_SHARE_TOKEN__" in bootstrap
    assert "radar-design-tokens" in bootstrap
    assert "window.__RADAR_DESIGN_TOKENS__" not in design
    assert "<script>" not in design
    assert "designColor" not in design
    assert "designDark" not in design
    assert "<?" not in design and "?>" not in design
    assert "bbva-grey-100" not in design
    assert re.search(r"#[0-9A-Fa-f]{3,8}\b|rgba?\(", design) is None
    style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", design, flags=re.DOTALL)
    assert style_blocks
    assert all("<?" not in block and "?>" not in block for block in style_blocks)
    embedded_blocks = re.findall(
        r"<(?:script|style)[^>]*>(.*?)</(?:script|style)>",
        index,
        flags=re.DOTALL,
    )
    assert all("<?" not in block and "?>" not in block for block in embedded_blocks)
    assert "DESIGN_TOKENS.radius" in newsletter
    assert "DESIGN_TOKENS.effect.emailShadow" in newsletter


def test_setup_remaps_compatible_sheet_contract_changes_by_header_name() -> None:
    setup = _source("90_Setup.gs")
    migration = _function_body(setup, "_migrateSheetHeaders_")
    setup_application = _function_body(setup, "setupApplication")

    assert "seen.has(header)" in migration
    assert "expected.indexOf(header) < 0" not in migration
    assert "sourceIndex[header] = index" in migration
    assert "formulas[rowIndex][columnIndex] || row[columnIndex]" in migration
    assert "expected.map(function (header)" in migration
    assert "_migrateSheetHeaders_(name, sheet)" in setup_application
    assert "_validateSheetContract_(name)" in setup_application


def test_setup_removes_only_known_legacy_storage_after_contract_creation() -> None:
    setup = _source("90_Setup.gs")
    reset_collisions = _function_body(setup, "_resetLegacyContractCollisions_")
    remove_obsolete = _function_body(setup, "_removeObsoleteStorage_")
    setup_application = _function_body(setup, "setupApplication")

    for sheet_name in (
        "REPORT_JOBS",
        "_TRANSFER_STAGING",
        "HELIX_ITEMS",
        "INSIGHTS_LEARNING",
        "SOURCES",
        "ISSUES",
        "HELIX_LINKS",
        "NOTES",
        "INGEST_RUNS",
    ):
        assert f"'{sheet_name}'" in setup
    assert "_sameHeaders_(_sheetHeaders_(sheet), LEGACY_CONTRACT_HEADERS[sheetName])" in (
        reset_collisions
    )
    assert "ss.deleteSheet(sheet)" in reset_collisions
    assert "OBSOLETE_CONFIG_KEYS.forEach" in remove_obsolete
    assert setup_application.index("_resetLegacyContractCollisions_(ss)") < (
        setup_application.index("Object.keys(CONTRACTS).forEach")
    )
    assert setup_application.index("_removeObsoleteStorage_(ss)") > (
        setup_application.index("Object.keys(CONTRACTS).forEach")
    )
    assert "_seedDefaultNewsletterRecipients_" not in setup
    assert "report_drive_folder" in remove_obsolete


def test_setup_keeps_the_control_sheet_visible() -> None:
    setup_application = _function_body(_source("90_Setup.gs"), "setupApplication")

    show_control = "if (controlSheet && controlSheet.isSheetHidden()) controlSheet.showSheet()"
    hide_other_contracts = "sheet.getName() !== RADAR.sheets.config"
    assert show_control in setup_application
    assert hide_other_contracts in setup_application
    assert setup_application.index(show_control) < setup_application.index(hide_other_contracts)


def test_cloud_transfer_is_strict_desktop_authoritative_v3() -> None:
    config = _source("00_Config.gs")
    adapters = _source("20_Adapters.gs")

    assert re.search(r"transferVersion:\s*3\b", config)
    assert "desktop-authoritative-v2" in config
    assert "data/projection.json" in adapters
    assert "artifacts/period_followup.pptx" in adapters
    assert "data/issues.json" not in adapters
    assert "data/helix.json" not in adapters
    assert "insights_learning.json" not in adapters
    assert "_validateNoCloudActionsDeep_" in adapters
    assert "issue_uid compuesto y único" in adapters
    snapshots = _source("25_MaterializedSnapshots.gs")
    current_record = _function_body(snapshots, "_isCurrentSnapshotRecord_")
    assert "RADAR.projectionContract" in current_record
    assert "RADAR.projectionVersion" in current_record
    assert "_isCurrentSnapshotRecord_(record)" in _function_body(snapshots, "_snapshotRecordById_")


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
    assert "issueUid" in app
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
        "_newsletterScopeKey_",
        "_rebuildApplicationCaches_",
        "_seedDefaultNewsletterRecipients_",
        "listReportDriveFolders",
        "_reportFolderList_",
    ):
        assert obsolete not in all_code


def test_admin_controls_are_revealed_only_after_an_admin_bootstrap() -> None:
    app = _source("App.html")
    design = _source("DesignSystem.html")
    main = _source("10_Main.gs")

    assert ".admin-only { display: none !important; }" in design
    assert ".is-admin .admin-only { display: inline-flex !important; }" in design
    assert "isAdmin() && !isShared() ? 'is-admin' : ''" in app
    assert "_requireAdmin_()" in _function_body(main, "validateTransferImport")
    assert "_requireAdmin_()" in _function_body(main, "commitTransferImport")


def test_report_folder_is_global_and_blocks_validation_when_missing() -> None:
    main = _source("10_Main.gs")
    report = _source("55_PeriodReport.gs")

    assert "_configuredReportDriveFolder_();" in _function_body(main, "validateTransferImport")
    assert "_configuredReportDriveFolder_()" in _function_body(main, "_publishDecodedTransfer_")
    assert "_setConfig_(" in _function_body(report, "saveReportDriveFolder")
    assert "'REPORT_DRIVE_FOLDER'" in _function_body(report, "saveReportDriveFolder")
    assert "_preferenceMap_" not in _function_body(main, "_publishDecodedTransfer_")
    assert "report_drive_folder" not in _function_body(main, "savePreference")


def test_newsletter_recipients_are_pinned_to_a_loaded_report() -> None:
    config = _source("00_Config.gs")
    newsletter = _source("56_Newsletter.gs")
    save_recipient = _function_body(newsletter, "saveNewsletterRecipient")

    assert "['report_id', 'string', true]" in config
    assert "['snapshot_id', 'string', true]" in config
    assert "reportId" in save_recipient
    assert "report_id: report.reportId" in save_recipient
    assert "snapshot_id: report.snapshotId" in save_recipient
    assert "_newsletterUsers_().find" in save_recipient
    assert "usuario activo y autorizado" in save_recipient
    assert "_newsletterRecipientsForReport_" in newsletter


def test_final_newsletter_requires_a_successful_test_by_connected_admin() -> None:
    newsletter = _source("56_Newsletter.gs")
    sender = _function_body(newsletter, "sendPeriodNewsletter")
    status = _source("57_ReportAutomation.gs")
    app = _source("App.html")

    assert "_newsletterTestWasSentBy_(reportId, user.email)" in sender
    assert "'NEWSLETTER_TEST_REQUIRED'" in sender
    assert "newsletterTested" in status
    assert "job.newsletterTested && !job.newsletterSent" in app


def test_ingestion_regenerates_stable_versioned_caches_for_all_main_views() -> None:
    main = _function_body(_source("10_Main.gs"), "commitTransferImport")
    materialized = _function_body(_source("25_MaterializedSnapshots.gs"), "_warmSnapshotViews_")
    app = _source("App.html")
    cache = _source("Cache.html")

    assert main.index("_invalidateCaches_()") < main.index("_warmSnapshotViews_")
    for view_name in ("overview", "insights", "trends", "issues"):
        assert f"view: '{view_name}'" in materialized
    assert "kanban" not in materialized.casefold()
    assert "cacheGeneration: state.bootstrap.app.cacheEpoch" in app
    assert "scopeVersion: scope.dataVersion" in app
    assert "key.cacheGeneration !== current.cacheGeneration" in cache
    assert "key.scopeVersion" in cache


def test_cloud_removes_retired_views_and_generative_newsletter_code() -> None:
    cloud_code = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(APPS_SCRIPT.glob("*"))
        if path.is_file() and path.name != "BrandAssets.html"
    )
    folded = cloud_code.casefold()
    assert "kanban" not in folded
    assert "opshealth" not in folded
    assert "salud operativa" not in folded
    runtime_newsletter = _source("56_Newsletter.gs").casefold()
    assert "gemini" not in runtime_newsletter
    assert "urlfetchapp" not in _source("56_Newsletter.gs").casefold()
    assert "properties.deleteproperty(key)" in _source("90_Setup.gs").casefold()


def test_domain_access_and_configuration_are_separated_by_role() -> None:
    manifest = json.loads(_source("appsscript.json"))
    main = _source("10_Main.gs")
    index = _source("Index.html")
    design = _source("DesignSystem.html")

    assert manifest["webapp"] == {"access": "DOMAIN", "executeAs": "USER_ACCESSING"}
    assert "email.endsWith('@' + RADAR.allowedDomain)" in _function_body(main, "_requireUser_")
    assert "role: 'viewer'" in _function_body(main, "_requireUser_")
    assert "user.role === 'admin'" in _function_body(main, "_requireAdmin_")
    assert index.count("scope-admin-control") >= 3
    assert ".scope-admin-control { display: none !important; }" in design
    assert ".is-admin .scope-admin-control" in design


def test_admin_console_covers_health_drive_newsletter_analytics_and_summary_charts() -> None:
    administration = _source("58_Administration.gs")
    newsletter = _source("56_Newsletter.gs")
    app = _source("App.html")

    for rpc in (
        "getAdminConsole",
        "browseReportDriveFolders",
        "recordAnalyticsEvents",
        "getAnalyticsReport",
        "saveSummaryChartIds",
    ):
        assert f"function {rpc}" in administration
    assert "weekOverWeekPct" in administration
    assert "body_text" in _source("00_Config.gs")
    assert "slides_url" in _source("00_Config.gs")
    assert "_newsletterSenderIdentity_" in newsletter
    assert "sender.usesAlias" in newsletter
    assert "context.newsletter.draft.subject" in newsletter
    for label in (
        "Estado de la WebApp",
        "Carpeta de Drive",
        "Fuentes JIRA",
        "Newsletter",
        "Adopción y analítica",
        "Gráficos de Resumen",
        "Descargar JSON para Codex",
    ):
        assert label in app


def test_plotly_is_loaded_on_demand_and_navigation_discards_stale_responses() -> None:
    index = _source("Index.html")
    charts = _source("Charts.html")
    app = _source("App.html")

    assert "cdn.plot.ly" not in index
    assert "function loadPlotly()" in charts
    assert "document.head.appendChild(script)" in charts
    assert "navigationEpoch" in app
    assert "expectedEpoch !== state.navigationEpoch" in app
    assert "showRouteLoading" in _function_body(app, "openPanel")
