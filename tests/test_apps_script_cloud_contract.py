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
    assert "report_drive_folder" not in remove_obsolete


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
    assert "desktop-authoritative-v3" in config
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

    assert "Content-Disposition: attachment" in newsletter
    assert "_newsletterMimeBytes_(attachment.getBytes())" in newsletter
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
    assert "function savePreference" not in main
    assert "USER_PREFS" not in _source("00_Config.gs")
    assert "window.localStorage" in _source("App.html")


def test_every_boot_starts_on_overview_without_persisting_last_panel() -> None:
    app = _source("App.html")
    boot = _function_body(app, "boot")
    preferences = _function_body(app, "schedulePreferenceSave")

    assert "state.panel = 'overview';" in boot
    assert "state.route = 'dashboard';" in boot
    assert "state.page = 1;" in boot
    assert "local.panel" not in boot
    assert "panel: state.panel" not in preferences


def test_newsletter_recipients_persist_by_scope_across_new_reports() -> None:
    config = _source("00_Config.gs")
    newsletter = _source("56_Newsletter.gs")
    setup = _source("90_Setup.gs")
    app = _source("App.html")
    save_recipient = _function_body(newsletter, "saveNewsletterRecipient")
    recipient_contract = config[
        config.index("NEWSLETTER_RECIPIENTS:") : config.index("NEWSLETTER_AUDIT:")
    ]
    active_recipients = _function_body(newsletter, "_newsletterRecipientsForScope_")

    assert "['scope_key', 'string', true]" in recipient_contract
    assert "report_id" not in recipient_contract
    assert "snapshot_id" not in recipient_contract
    assert "reportId" in save_recipient
    assert "report.scopeKey + '::' + email" in save_recipient
    assert "scope_key: report.scopeKey" in save_recipient
    assert "email.endsWith('@' + RADAR.allowedDomain)" in save_recipient
    assert "displayName" not in save_recipient
    assert "_assertExactFields_(input, ['reportId', 'email', 'active']" in save_recipient
    assert "return _newsletterSettingsPayload_()" not in save_recipient
    assert "row.active === true" in active_recipients
    assert "_newsletterRecipientsForScope_(report.scopeKey)" in newsletter
    assert "_normalizeNewsletterRecipientStorage_();" in setup
    assert "actual.length > expected.length" in setup
    assert "clearContent();" in setup
    assert "recipient.scopeKey === (selectedReport && selectedReport.scopeKey)" in app
    assert "persistidos para este ámbito" in app


def test_newsletter_recipient_ui_is_email_only() -> None:
    app = _source("App.html")

    assert "recipientEmail" in app
    assert "recipientDisplayName" not in app
    assert "Nombre visible" not in app
    assert "Nombre y apellidos" not in app
    assert "data-display-name" not in app


def test_final_newsletter_requires_a_successful_test_by_connected_admin() -> None:
    newsletter = _source("56_Newsletter.gs")
    sender = _function_body(newsletter, "sendPeriodNewsletter")
    status = _source("57_ReportAutomation.gs")
    app = _source("App.html")

    assert "_newsletterTestWasSentBy_(reportId, user.email)" in sender
    assert "'NEWSLETTER_TEST_REQUIRED'" in sender
    assert "newsletterTested" in status
    assert "job.newsletterTested && !job.newsletterSent" in app
    assert ": 'Enviar newsletter';" in app
    assert "Envía primero una prueba" not in app
    assert "dataset.sending" in app


def test_newsletter_requires_the_corporate_alias_and_never_falls_back_to_personal_identity() -> (
    None
):
    config = _source("00_Config.gs")
    newsletter = _source("56_Newsletter.gs")
    identity = _function_body(newsletter, "_newsletterSenderIdentity_")
    sender = _function_body(newsletter, "sendPeriodNewsletter")
    app = _source("App.html")

    assert "corporateBrand: 'BBVA Banca de Empresas e Instituciones'" in config
    assert "newsletterFrom: 'bug-resolution-radar.group@bbva.com'" in config
    assert "Gmail.Users.Settings.SendAs.list('me')" in identity
    assert "verificationStatus === 'accepted'" in identity
    assert "'NEWSLETTER_SENDER_UNAVAILABLE'" in sender
    assert sender.index("_newsletterSenderIdentity_(true)") < sender.index("_exactReportBlob_(")
    assert "function revalidateNewsletterSender" in newsletter
    assert "_cachePutJson_" in identity
    assert "@bug-resolution-radar.bbva.com" in newsletter
    assert "_newsletterDeliver_(pendingRecipients, subject, rendered, attachment, sender)" in sender
    assert "_newsletterPreviouslyDeliveredRecipients_" in newsletter
    assert "deliveries.length ? 'partial' : 'failed'" in sender
    assert "newsletterSenderReady" in app
    assert "Revalidar buzón" in app
    assert "NEWSLETTER_SENDER_UNAVAILABLE" in _source("99_Core.gs")
    assert "GmailApp" not in newsletter
    assert "MailApp" not in newsletter
    assert "voc-commercial.group@bbva.com" not in newsletter + config


def test_newsletter_and_webapp_apply_the_corporate_brand_and_bbva_email_hierarchy() -> None:
    newsletter = _function_body(_source("56_Newsletter.gs"), "_newsletterRender_")
    index = _source("Index.html")
    design = _source("DesignSystem.html")

    assert index.count("BBVA Banca de Empresas e Instituciones") >= 2
    assert index.count("corporate-lockup") >= 2
    assert ".corporate-lockup" in design
    for expected in (
        "scopeLabel",
        "Resultado correspondiente al seguimiento de incidencias de la última quincena:",
        "Discrepancias estados finalistas",
        "Información generada a ",
        "Backlog abierto",
        "Creadas",
        "Cerradas",
        "Resolución",
        "Abrir presentación",
        "Abrir Radar",
        "Abrir cuadro JIRA",
        "BBVA Banca de Empresas e Instituciones",
        "@media only screen and (max-width:620px)",
    ):
        assert expected in newsletter
    assert "newsletter.responsibleRollups" in newsletter
    assert "DESIGN_TOKENS.radius.container" in newsletter
    assert "_newsletterEmailFont_(DESIGN_TOKENS.font.webBody)" in newsletter


def test_executive_signal_colors_are_consistent_in_webapp_and_newsletter() -> None:
    design = _source("DesignSystem.html")
    newsletter = _function_body(_source("56_Newsletter.gs"), "_newsletterRender_")

    assert (
        '.evolution-hero[data-tone="positive"] { --evolution-accent:var(--bbva-success); }'
        in design
    )
    assert (
        '.evolution-hero[data-tone="mixed"] { --evolution-accent:var(--bbva-warning); }' in design
    )
    assert (
        '.evolution-hero[data-tone="negative"] { --evolution-accent:var(--bbva-danger); }' in design
    )
    assert "evolution.tone === 'positive'" in newsletter
    assert "evolution.tone === 'negative'" in newsletter
    assert "color.warningStrong" in newsletter


def test_newsletter_uses_the_market_pulse_gmail_api_delivery_contract() -> None:
    manifest = json.loads(_source("appsscript.json"))
    newsletter = _source("56_Newsletter.gs")

    services = manifest["dependencies"]["enabledAdvancedServices"]
    assert {"userSymbol": "Gmail", "version": "v1", "serviceId": "gmail"} in services
    assert "https://www.googleapis.com/auth/gmail.send" in manifest["oauthScopes"]
    assert "https://www.googleapis.com/auth/gmail.settings.basic" in manifest["oauthScopes"]
    assert "https://www.googleapis.com/auth/script.send_mail" not in manifest["oauthScopes"]
    assert "https://mail.google.com/" not in manifest["oauthScopes"]
    assert "Gmail.Users.Messages.send({ raw: message.raw }, 'me')" in newsletter
    assert "multipart/mixed" in newsletter
    assert "Content-Disposition: attachment" in newsletter


def test_materialized_insight_variants_keep_the_desktop_payload_shape() -> None:
    materialized = _function_body(
        _source("25_MaterializedSnapshots.gs"), "_materializedViewPayload_"
    )
    app = _source("App.html")

    assert "insights[activeId] = selected" in materialized
    assert "else insights[activeId]" in materialized
    for expected in (
        "renderFunctionalityInsight",
        "renderDuplicatesInsight",
        "renderFinalistInsight",
        "renderPeopleInsight",
        "Corte por origen seleccionado",
    ):
        assert expected in app
    for forbidden in (
        "insightsStatus",
        "insightsPriority",
        "insightsFunctionality",
    ):
        assert forbidden not in app


def test_period_summary_keeps_kpis_separate_from_issue_lists_and_insight_click_is_atomic() -> None:
    app = _source("App.html")
    summary = app[
        app.index("data.periodSummary.cards.map") : app.index("data.periodSummary.groups || []")
    ]
    open_insight = _function_body(app, "openInsight")

    assert "issueList(" not in summary
    assert "data-delta-kind" in summary
    assert "const epoch = ++state.navigationEpoch" in open_insight
    assert "await refreshDashboard(epoch)" in open_insight
    assert "button.disabled = true" in open_insight


def test_webapp_version_is_explicit_and_registered_automatically() -> None:
    config = _source("00_Config.gs")
    administration = _source("58_Administration.gs")
    main = _source("10_Main.gs")
    setup = _source("90_Setup.gs")

    assert re.search(r"appVersion:\s*'\d{4}\.\d{2}\.\d{2}\.\d+'", config)
    register = _function_body(administration, "registerAppVersion")
    assert "_registerAppVersion_(user.email)" in register
    assert "RPC.call('registerAppVersion')" in _source("App.html")
    assert "_registerAppVersion_" not in _function_body(main, "getBootstrap")
    assert "'APP_VERSION'" in _function_body(administration, "_registerAppVersion_")
    assert "RADAR.appVersion" in _function_body(setup, "setupApplication")
    assert "version: RADAR.appVersion" in _function_body(main, "getBootstrap")


def test_aggregate_scope_really_hides_origin_for_admins() -> None:
    app = _source("App.html")
    design = _source("DesignSystem.html")

    assert "sourceSlot.classList.toggle('hidden', rollup)" in app
    assert "sourceSlot.setAttribute('aria-hidden', String(rollup))" in app
    assert ".is-admin .scope-admin-control.hidden { display: none !important; }" in design


def test_dashboard_cache_loads_variants_on_demand_without_eager_bundle_rpc() -> None:
    main = _source("10_Main.gs")
    app = _source("App.html")
    sheets = _source("40_Sheets.gs")
    cache = _source("Cache.html")

    assert "function getDashboardViewBundle" not in main
    assert "RPC.call('getDashboardViewBundle'" not in app
    assert "state.memory.set(key, payload)" in app
    assert "const operationBudgetMs = 500" in cache
    assert "_recordsCacheEnabled_" in sheets
    assert "RADAR.sheets.snapshotParts" in _function_body(sheets, "_recordsCacheEnabled_")


def test_webapp_dark_mode_uses_bbva_dark_surfaces_and_preserves_brand_hero() -> None:
    config = _source("00_Config.gs")
    design = _source("DesignSystem.html")

    for expected in (
        "grey200: '#11192D'",
        "grey300: '#222C42'",
        "grey400: '#334056'",
        "grey500: '#46536D'",
        "electric: '#85C8FF'",
        "success: '#9CE67E'",
        "warning: '#FFC553'",
        "danger: '#FF5252'",
    ):
        assert expected in config
    assert "'--bbva-brand-midnight': color.midnight" in config
    assert "'--bbva-inverse-surface': 'var(--bbva-grey-400)'" in config
    assert "var(--bbva-brand-midnight)" in design
    assert "background: var(--bbva-inverse-surface)" in design


def test_ingestion_invalidates_versioned_caches_without_eager_view_warming() -> None:
    main = _function_body(_source("10_Main.gs"), "commitTransferImport")
    app = _source("App.html")
    cache = _source("Cache.html")

    assert "_invalidateCaches_()" in main
    assert "_warmSnapshotViews_" not in main
    assert "function _warmSnapshotViews_" not in _source("25_MaterializedSnapshots.gs")
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

    assert manifest["webapp"] == {"access": "DOMAIN", "executeAs": "USER_DEPLOYING"}
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
        "recordAnalyticsEvents",
        "getAnalyticsReport",
        "saveSummaryChartIds",
    ):
        assert f"function {rpc}" in administration
    assert "Picker" not in administration + app
    assert "folderReference" in app
    assert "recipientForm" in app
    assert "Añadir destinatario" in app
    assert "weekOverWeekPct" in administration
    assert "body_text" in _source("00_Config.gs")
    assert "slides_url" in _source("00_Config.gs")
    assert "_newsletterSenderIdentity_" in newsletter
    assert "sender.ready" in newsletter
    assert "context.newsletter.draft.subject" in newsletter
    for label in (
        "Estado de la WebApp",
        "Carpeta de Drive",
        "Fuentes JIRA",
        "Newsletter",
        "Adopción y analítica",
        "Gráficos de Resumen",
        "Actualizar y descargar JSON para Codex",
    ):
        assert label in app


def test_analytics_export_flushes_pending_events_and_is_self_describing() -> None:
    administration = _function_body(_source("58_Administration.gs"), "getAnalyticsReport")
    app = _source("App.html")

    assert "await deadline(flushAnalytics()" in app
    assert "captureMode: 'export'" in app
    assert app.index("await deadline(flushAnalytics()") < app.index("captureMode: 'export'")
    for field in (
        "schemaVersion: '2.2'",
        "generatedAt: generatedAt",
        "queryStartAt:",
        "queryEndAt:",
        "dataAsOf:",
        "matchingRows: rows.length",
        "includedRows: detailRows.length",
        "rowsTruncated: rows.length > detailLimit",
        "invalidTimestampRows:",
        "futureTimestampRowsExcluded:",
        "summaryCompleteForWindow: allRows.length < 50000",
        "canonicalization: 'JSON con claves de objeto ordenadas alfabéticamente, sin integrity'",
    ):
        assert field in administration
    assert "summary: 'Calculado con todos los eventos conservados" in administration
    assert "duration: 'averageDurationMs y p95DurationMs excluyen" in administration
    assert "_analyticsCanonicalJson_(report)" in administration
    assert "item instanceof Date" in _source("58_Administration.gs")
    assert "captureMode === 'export' ? 2000 : 100" in administration
    assert "unversionedEvents" in administration
    assert "versionAttribution" in administration
    assert "legacy-unknown" in administration
    assert "_telemetry" in app


def test_telemetry_warning_and_report_are_admin_only() -> None:
    administration = _function_body(_source("58_Administration.gs"), "getAnalyticsReport")
    render_settings = _function_body(_source("App.html"), "renderSettings")
    design = _source("DesignSystem.html")

    assert "_requireAdmin_();" in administration
    assert "if (!isAdmin() || isShared())" in render_settings
    assert render_settings.index("if (!isAdmin() || isShared())") < render_settings.index(
        "analyticsWarning"
    )
    assert "admin-telemetry-only" in render_settings
    assert ".admin-telemetry-only { display: none !important; }" in design
    assert ".is-admin .admin-telemetry-only { display: grid !important; }" in design


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
