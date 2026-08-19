#!/usr/bin/env node

import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const APPS_SCRIPT = resolve(ROOT, "apps-script");

function source(name) {
  return readFileSync(resolve(APPS_SCRIPT, name), "utf8");
}

function designTokenMarkup() {
  const web = JSON.parse(
    new vm.Script(`${source("00_Config.gs")}\nJSON.stringify(DESIGN_TOKENS.web)`)
      .runInNewContext({})
  );
  const declarations = (tokens) =>
    Object.entries(tokens).map(([name, value]) => `${name}:${value}`).join(";");
  return `<script>window.__RADAR_SHARE_TOKEN__="";window.__RADAR_LOCAL__=true;</script>` +
    `<style id="radar-design-tokens">:root{${declarations(web.light)}}` +
    `:root[data-theme="dark"]{${declarations(web.dark)}}</style>`;
}

function localRuntimeMarkup() {
  const scope = {
    scopeKey: "espana::*",
    scopeLabel: "España · Agregado",
    country: "España",
    sourceIds: ["jira:espana:core"],
    dataVersion: "local-contract-v3",
    snapshotId: "local-snapshot",
    activatedAt: "2026-07-28T10:00:00Z"
  };
  const chartCatalog = [
    ["timeseries", "Evolución (últimos 90 días)"],
    ["age_buckets", "Distribución antigüedad"],
    ["open_status_bar", "Issues por Estado"],
    ["open_priority_pie", "Issues abiertos por prioridad"],
    ["resolution_hist", "Días abiertas por prioridad"]
  ].map(([id, title]) => ({ id, title, subtitle: "Snapshot local v3", group: "Local" }));
  const figure = {
    data: [{ type: "bar", x: ["Open", "In progress"], y: [8, 5], name: "Issues" }],
    layout: { showlegend: false }
  };
  const issue = {
    issue_uid: "jira:espana:core::RADAR-101",
    key: "RADAR-101",
    summary: "Incidencia de ejemplo para validar la WebApp",
    description: "Dato contractual simulado; GPC no recalcula reglas de negocio.",
    status: "Open",
    priority: "High",
    assignee: "Equipo Radar",
    country: "España",
    source_alias: "Core",
    url: "https://jira.example.com/browse/RADAR-101"
  };
  const overview = {
    stats: { issues_total: 13, issues_open: 8, issues_closed: 5, mean_resolution_days: "3.2d" },
    overviewKpis: [
      { label: "Issues totales", value: "13", detail: "Snapshot local" },
      { label: "Abiertas", value: "8", detail: "Estados no finalistas" },
      { label: "Cerradas", value: "5", detail: "Acumulado" }
    ],
    focusCards: [],
    statusPriorityMatrix: {
      title: "Matriz Estado x Priority",
      total: 8,
      priorities: [{ priority: "High", count: 5 }, { priority: "Medium", count: 3 }],
      rows: [
        {
          status: "Open",
          count: 8,
          cells: [{ priority: "High", count: 5 }, { priority: "Medium", count: 3 }]
        }
      ]
    },
    charts: [
      { id: "timeseries", title: chartCatalog[0].title, subtitle: "Snapshot local", figure },
      { id: "open_priority_pie", title: chartCatalog[3].title, subtitle: "Snapshot local", figure },
      { id: "resolution_hist", title: chartCatalog[4].title, subtitle: "Snapshot local", figure }
    ],
    row_count: 13,
    open_row_count: 8
  };
  const common = {
    materialized: true,
    immutable: true,
    dataVersion: scope.dataVersion,
    scopeVersion: scope.dataVersion,
    scopeKey: scope.scopeKey,
    page: 1,
    pageSize: 50
  };
  const dashboard = (request = {}) => {
    if (request.view === "insights") {
      const activeTab = request.insightsId || "summary";
      const insights = {
        tabs: [
          { id: "summary", label: "Resumen" },
          { id: "functionality", label: "Funcionalidad" },
          { id: "duplicates", label: "Duplicados" },
          { id: "rootCauseEvolutives", label: "Evolutivos causas raíces" },
          { id: "finalistDiscrepancies", label: "Discrepancias finalistas" },
          { id: "people", label: "Personas" }
        ],
        activeTab
      };
      if (activeTab === "summary") insights.periodSummary = {
        caption: "España · Periodo 15/07 - 28/07/2026",
        cards: [
          {
            cardId: "new_now", kicker: "Insights · Creadas", metric: "64",
            detail: "Δ +6,7% vs quincena previa", label: "Creadas en la quincena actual",
            tone: "flow", delta: { displayKind: "improving" }, issues: [issue]
          },
          {
            cardId: "closed_now", kicker: "Insights · Cerradas", metric: "71",
            detail: "Δ -13,4% vs quincena previa", label: "Cerradas en la quincena",
            tone: "warning", delta: { displayKind: "worsening" }, issues: [issue]
          },
          {
            cardId: "resolution_now", kicker: "Insights · Resolución", metric: "16.1d",
            detail: "Δ -37,1% vs quincena previa", label: "Resolución de cerradas",
            tone: "flow", delta: { displayKind: "improving" }, issues: [issue]
          }
        ],
        groups: [{
          label: "Creadas en la quincena actual", count: 64, helpText: "quincena actual",
          tone: "flow", items: [issue]
        }], showOpenSplit: false, sourceBreakdown: []
      };
      if (activeTab === "functionality") insights.functionality = {
        chart: { title: "Incidencias por funcionalidad", subtitle: "Vista acumulada", figure },
        topics: [{
          topic: "Pagos", color: "#0C6DFF", count: 1, pct: 12.5,
          dominantStatus: "Open", dominantPriority: "High",
          brief: "Concentración operativa localizada.",
          flow: { createdCount: 2, resolvedCount: 1, pctDelta: 0.1, direction: "worsening", windowDays: 30 },
          rootCauses: [{ label: "Integración", count: 1 }], issues: [issue]
        }],
        tip: "Contenido materializado por escritorio."
      };
      if (activeTab === "duplicates") insights.duplicates = {
        brief: "Posibles duplicados del snapshot.",
        titleGroups: [{ summary: "Error al confirmar operación", count: 1, issues: [issue] }],
        heuristicGroups: [{ summary: "Coincidencia semántica", count: 1, dominantStatus: "Open", dominantPriority: "High", issues: [issue] }]
      };
      if (["rootCauseEvolutives", "finalistDiscrepancies"].includes(activeTab)) insights[activeTab] = {
        kpis: [{ label: "JIRA pendientes", value: "1", detail: "Snapshot local" }],
        groups: [{
          helixId: "INC0001", helixUrl: "https://example.com/helix/INC0001", helixStatus: "Closed",
          helixText: "Incidencia Helix de ejemplo", jiraCount: 1,
          issues: [{ ...issue, openDays: 18, matchedLabels: ["causa-raiz"], note: "Seguimiento local" }]
        }], totalRows: 1, truncated: false
      };
      if (activeTab === "people") insights.people = { cards: [{
        assignee: "Equipo Radar", openCount: 1, sharePct: 12.5,
        statusBreakdown: [{ status: "Open", count: 1 }],
        risk: { label: "Alto", flowRiskPct: 75, criticalRiskPct: 50 },
        pushPct: 42, blockedCount: 1, aging: { value: "18d", caption: "Issue más antigua" },
        recommendations: ["Priorizar desbloqueo"], oldestIssues: [issue]
      }] };
      return {
        ...common,
        insights
      };
    }
    if (request.view === "trends") {
      const selected = chartCatalog.find((item) => item.id === request.chartId) || chartCatalog[0];
      return {
        ...common,
        trends: {
          chartCatalog,
          selectedChartId: selected.id,
          chart: { ...selected, figure },
          metrics: [{ label: "Issues", value: "13" }],
          cards: [{ title: "Racional local", body: "Contenido materializado por escritorio.", issues: [issue] }],
          executiveTip: "El simulador valida presentación e interacción, no servicios de Google."
        }
      };
    }
    if (request.view === "issues") {
      return { ...common, totalRows: 1, totalPages: 1, rows: [issue] };
    }
    return { ...common, ...overview };
  };
  const bootstrap = {
    app: {
      name: "Bug Resolution Radar · WebApp local",
      version: "2026.08.19.6",
      contractVersion: "5.1.0",
      semanticContract: "desktop-authoritative-v2",
      dataVersion: scope.dataVersion,
      cacheEpoch: "local-20260819-4",
      maxTransferBytes: 33554432,
      scopeVersions: { [scope.scopeKey]: scope.dataVersion },
      materializedOnly: true,
      issueFiltersEnabled: false
    },
    user: { email: "admin.local@bbva.com", role: "admin", displayName: "Admin local" },
    scopes: [scope],
    countries: ["España"],
    sources: [{ source_id: "jira:espana:core", source_type: "materialized", alias: "Core", country: "España" }],
    administration: {
      reportDriveFolder: { id: "local-folder", name: "Informes locales", url: "https://drive.google.com/" },
      importReady: true
    },
    initialState: {
      panel: "overview",
      scopeKey: scope.scopeKey,
      trendChart: "timeseries",
      insightsId: "summary",
      issuesView: "Cards",
      page: 1,
      pageSize: 50
    },
    dashboard: { ...common, ...overview }
  };
  const mocks = {
    getBootstrap: () => bootstrap,
    queryDashboard: (request) => dashboard(request),
    getDashboardViewBundle: () => [],
    recordAnalyticsEvents: (events) => ({ accepted: Array.isArray(events) ? events.length : 0 }),
    getIssueDetail: () => issue,
    getPeriodReportStatus: () => ({
      scopeKey: scope.scopeKey,
      job: {
        reportId: "local-report",
        fileUrl: "https://docs.google.com/presentation/",
        slideCount: 9,
        rowCount: 13,
        newsletterTested: true,
        newsletterSent: false,
        newsletterSenderReady: true,
        newsletterSender: "bug-resolution-radar.group@bbva.com",
        newsletterSenderMode: "Gmail API · remitente corporativo verificado",
        recipientCount: 2
      },
      folder: bootstrap.administration.reportDriveFolder
    }),
    sendPeriodNewsletter: (_reportId, mode) => ({
      recipientCount: mode === "test" ? 1 : 2,
      testRecipient: "admin.local@bbva.com"
    }),
    listImportRuns: () => [{
      started_at: "2026-07-28T10:00:00Z",
      file_name: "traslado-local.brr",
      status: "completed"
    }],
    getAdminConsole: () => ({
      health: {
        status: "Operativa (simulada)",
        appVersion: "2026.08.19.6",
        contractVersion: "5.1.0",
        accessPolicy: "Dominio @bbva.com",
        lastImportAt: scope.activatedAt,
        importedRecords: 13,
        newsletterRecipientsSent: 2,
        analyticsUsers: 3,
        analyticsEvents: 48,
        projectionBytes: 24576,
        dataVersion: scope.dataVersion,
        reportSlides: 9,
        generatedAt: scope.activatedAt,
        versionUrl: "http://127.0.0.1/",
        slidesUrl: "https://docs.google.com/presentation/"
      },
      reportDriveFolder: bootstrap.administration.reportDriveFolder,
      summaryCharts: {
        selected: ["timeseries", "open_priority_pie", "resolution_hist"],
        defaults: ["timeseries", "open_priority_pie", "resolution_hist"]
      },
      jiraSources: [{
        sourceId: "jira:espana:core",
        alias: "Core",
        poTeamLeader: "Responsable local",
        dashboardUrl: "https://jira.example.com/dashboard/42"
      }]
    }),
    saveReportDriveFolder: () => bootstrap.administration.reportDriveFolder,
    getNewsletterSettings: () => ({
      sender: {
        requested: "bug-resolution-radar.group@bbva.com",
        effective: "bug-resolution-radar.group@bbva.com",
        ready: true,
        verificationStatus: "accepted",
        mode: "Gmail API · remitente corporativo verificado"
      },
      reports: [{
        reportId: "local-report",
        scopeKey: scope.scopeKey,
        label: scope.scopeLabel,
        createdAt: scope.activatedAt
      }],
      recipients: [],
      audit: []
    }),
    saveNewsletterRecipient: () => mocks.getNewsletterSettings(),
    getAnalyticsReport: ({ userEmail = "", days = 30 } = {}) => ({
      filters: { userEmail, days },
      summary: {
        events: 48,
        users: 3,
        sessions: 7,
        errors: 0,
        currentWeekEvents: 28,
        previousWeekEvents: 20,
        weekOverWeekPct: 40,
        averageDurationMs: 112,
        p95DurationMs: 240
      },
      users: ["admin.local@bbva.com"],
      events: [{ label: "navigation", count: 18 }],
      panels: [{ label: "overview", count: 16 }, { label: "insights", count: 12 }],
      timeline: [{ day: "2026-07-28", count: 8 }],
      rows: [{
        eventAt: scope.activatedAt,
        userEmail: "admin.local@bbva.com",
        eventName: "navigation",
        durationMs: 84
      }]
    }),
    saveSummaryChartIds: (chartIds) => ({
      chartIds,
      selected: chartIds,
      defaults: ["timeseries", "open_priority_pie", "resolution_hist"]
    })
  };
  return `<script>
  window.Plotly = {
    react(node) {
      node.innerHTML = '<div style="display:grid;place-items:center;height:100%;color:var(--bbva-text-muted)">Gráfico Plotly simulado localmente</div>';
    },
    purge() {}
  };
  (() => {
    const scope = ${JSON.stringify(scope)};
    const chartCatalog = ${JSON.stringify(chartCatalog)};
    const figure = ${JSON.stringify(figure)};
    const issue = ${JSON.stringify(issue)};
    const overview = ${JSON.stringify(overview)};
    const common = ${JSON.stringify(common)};
    const bootstrap = ${JSON.stringify(bootstrap)};
    const executableMocks = {};
    const mocks = executableMocks;
    const dashboard = ${dashboard.toString()};
    ${Object.entries(mocks).map(([name, handler]) =>
      `executableMocks[${JSON.stringify(name)}] = ${handler.toString()};`
    ).join("\n")}
    const runner = (success, failure) => new Proxy({}, {
      get(_target, property) {
        if (property === 'withSuccessHandler') return handler => runner(handler, failure);
        if (property === 'withFailureHandler') return handler => runner(success, handler);
        return (...args) => window.setTimeout(() => {
          try {
            const handler = executableMocks[property];
            if (!handler) throw new Error('RPC local no implementado: ' + String(property));
            success({ ok: true, data: handler(...args) });
          } catch (error) {
            if (failure) failure(error);
          }
        }, 35);
      }
    });
    window.google = { script: { run: runner(null, null) } };
  })();
  </script>`;
}

export function renderWebapp() {
  let html = source("Index.html");
  html = html.replace(/<\?!=\s*_clientBootstrapMarkup_\([^)]*\)\s*\?>/, designTokenMarkup());
  html = html.replace(/<\?!=\s*_include_\('([^']+)'\);\s*\?>/g, (_match, name) => source(`${name}.html`));
  html = html.replace("</head>", `${localRuntimeMarkup()}</head>`);
  if (/<\?[!=]?/.test(html)) {
    throw new Error("La composición local conserva directivas de plantilla sin resolver.");
  }
  return html;
}

export function validateRenderedWebapp(html = renderWebapp()) {
  if (!html.includes("window.__RADAR_LOCAL__=true")) {
    throw new Error("Falta el bootstrap de WebApp local.");
  }
  if (!html.includes("window.google = { script: { run:")) {
    throw new Error("Falta el mock local de google.script.run.");
  }
  for (const [index, match] of [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].entries()) {
    new vm.Script(match[1], { filename: `webapp-local:inline-${index + 1}` });
  }
  return true;
}

function openBrowser(url) {
  const commands = {
    darwin: ["open", [url]],
    win32: ["cmd", ["/c", "start", "", url]]
  };
  const [command, args] = commands[process.platform] || ["xdg-open", [url]];
  const child = spawn(command, args, { detached: true, stdio: "ignore" });
  child.on("error", () => {});
  child.unref();
}

function argumentValue(name, fallback) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function main() {
  const html = renderWebapp();
  validateRenderedWebapp(html);
  if (process.argv.includes("--check")) {
    console.log("WebApp local compuesta y validada correctamente.");
    return;
  }
  const host = argumentValue("--host", "127.0.0.1");
  const port = Number(argumentValue("--port", "4174"));
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("El puerto local no es válido.");
  }
  const server = createServer((request, response) => {
    response.setHeader("Cache-Control", "no-store");
    response.setHeader("X-Content-Type-Options", "nosniff");
    if (request.url === "/healthz") {
      response.writeHead(200, { "Content-Type": "application/json; charset=utf-8" });
      response.end(JSON.stringify({ ok: true, contract: "v3" }));
      return;
    }
    if (request.url !== "/" && request.url !== "/index.html") {
      response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      response.end("Not found");
      return;
    }
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(html);
  });
  server.listen(port, host, () => {
    const url = `http://${host}:${port}/`;
    console.log(`WebApp GPC local disponible en ${url}`);
    console.log("Los servicios Google están simulados; Ctrl+C detiene el servidor.");
    if (!process.argv.includes("--no-open")) openBrowser(url);
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
