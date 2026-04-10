import { useEffect, useMemo } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient
} from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import {
  fetchJson,
  postJson,
  putJson,
  type DashboardPayload,
  type IntelligencePayload,
  type IssueKeysPayload,
  type IssuesPayload,
  type KanbanPayload,
  type TrendDetailPayload
} from "../lib/api";
import type { ShellContextValue } from "../components/AppShell";
import { ChartFigure } from "../components/ChartFigure";
import { DashboardFilters } from "../components/DashboardFilters";
import { InsightsPanel } from "../components/InsightsPanel";
import { IssuesPanel } from "../components/IssuesPanel";
import { KanbanBoard } from "../components/KanbanBoard";
import { NotesEditor } from "../components/NotesEditor";
import { StatusPriorityMatrix } from "../components/StatusPriorityMatrix";

type QueryParams = Record<string, string | number | boolean | string[]>;

function queryParams(
  params: ShellContextValue["dashboardState"]["params"],
  issueLikeQuery: string,
  darkMode: boolean
): QueryParams {
  return {
    country: params.country,
    sourceId: params.sourceId,
    scopeMode: params.scopeMode,
    status: params.status,
    priority: params.priority,
    assignee: params.assignee,
    quincenalScope: params.quincenalScope,
    issueSortCol: params.issueSortCol,
    issueLikeQuery,
    darkMode
  };
}

function issuesQueryParams(
  params: ShellContextValue["dashboardState"]["params"],
  issueLikeQuery: string,
  darkMode: boolean,
  page: number,
  pageSize: number
): QueryParams {
  const tableView = params.issuesView === "Tabla";
  return {
    ...queryParams(params, issueLikeQuery, darkMode),
    offset: tableView ? 0 : Math.max(0, page - 1) * pageSize,
    limit: tableView ? 50000 : pageSize,
    sortBy: params.issueSortCol,
    sortDir: params.issueSortDir
  };
}

function issueExportParams(
  params: ShellContextValue["dashboardState"]["params"],
  darkMode: boolean
): QueryParams {
  return queryParams(params, params.issueLikeQuery, darkMode);
}

function classNames(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(" ");
}

function focusCardActionLabel(
  card: DashboardPayload["focusCards"][number]
) {
  return `${card.title || "Abrir foco"} ↗`;
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <section className="surface-panel empty-panel">
      <h3>{title}</h3>
      <p>{description}</p>
    </section>
  );
}

function QueryErrorState({ title, error }: { title: string; error: unknown }) {
  const description =
    error instanceof Error ? error.message : "La API no ha devuelto un payload válido.";
  return <EmptyState title={title} description={description} />;
}

export function DashboardPage() {
  const { bootstrap, workspace, dashboardState, themeMode } =
    useOutletContext<ShellContextValue>();
  const queryClient = useQueryClient();
  const darkMode = themeMode === "dark";
  const activePanel = dashboardState.params.panel;
  const pageSize = 30;
  const currentPage = Math.max(1, Number.parseInt(dashboardState.params.issuePage, 10) || 1);
  const trendChartId =
    dashboardState.params.trendChart || bootstrap?.dashboardDefaults.defaultTrendChartId || "";
  const paramsSignature = JSON.stringify(dashboardState.params);
  const commonQueryOptions = {
    staleTime: 45_000,
    gcTime: 300_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    placeholderData: keepPreviousData
  } as const;
  const sharedScopeParams = useMemo(
    () =>
      queryParams(
        dashboardState.params,
        dashboardState.deferredIssueLikeQuery,
        darkMode
      ),
    [paramsSignature, dashboardState.deferredIssueLikeQuery, darkMode]
  );
  const overviewQueryParams = useMemo(
    () => ({
      ...sharedScopeParams,
      chartIds: bootstrap?.dashboardDefaults.summaryChartIds ?? []
    }),
    [sharedScopeParams, bootstrap?.dashboardDefaults.summaryChartIds]
  );
  const trendDetailQueryParams = useMemo(
    () => ({
      ...sharedScopeParams,
      chartId: trendChartId
    }),
    [sharedScopeParams, trendChartId]
  );
  const intelligenceQueryParams = useMemo(
    () => ({
      ...sharedScopeParams,
      insightsViewMode: dashboardState.params.insightsViewMode,
      insightsStatus: dashboardState.params.insightsStatus,
      insightsPriority: dashboardState.params.insightsPriority,
      insightsFunctionality: dashboardState.params.insightsFunctionality,
      insightsStatusManual: dashboardState.params.insightsStatusManual === "1"
    }),
    [sharedScopeParams, paramsSignature]
  );
  const issuesPanelQueryParams = useMemo(
    () =>
      issuesQueryParams(
        dashboardState.params,
        dashboardState.deferredIssueLikeQuery,
        darkMode,
        currentPage,
        pageSize
      ),
    [
      paramsSignature,
      dashboardState.deferredIssueLikeQuery,
      darkMode,
      currentPage,
      pageSize
    ]
  );

  useEffect(() => {
    if (!bootstrap?.dashboardDefaults.defaultTrendChartId) {
      return;
    }
    if (dashboardState.params.trendChart) {
      return;
    }
    dashboardState.update({
      trendChart: bootstrap.dashboardDefaults.defaultTrendChartId
    });
  }, [
    bootstrap?.dashboardDefaults.defaultTrendChartId,
    dashboardState,
    dashboardState.params.trendChart
  ]);

  const overview = useQuery({
    queryKey: ["dashboard-overview", overviewQueryParams],
    queryFn: () => fetchJson<DashboardPayload>("/api/dashboard", overviewQueryParams),
    enabled: Boolean(workspace?.selectedCountry) && activePanel === "overview",
    ...commonQueryOptions
  });

  const trendDetail = useQuery({
    queryKey: ["dashboard-trend-detail", trendDetailQueryParams],
    queryFn: () =>
      fetchJson<TrendDetailPayload>("/api/trends/detail", trendDetailQueryParams),
    enabled:
      Boolean(workspace?.selectedCountry) &&
      activePanel === "trends" &&
      Boolean(trendChartId),
    ...commonQueryOptions
  });

  const intelligence = useQuery({
    queryKey: ["dashboard-intelligence", intelligenceQueryParams],
    queryFn: () =>
      fetchJson<IntelligencePayload>("/api/intelligence", intelligenceQueryParams),
    enabled: Boolean(workspace?.selectedCountry) && activePanel === "insights",
    ...commonQueryOptions
  });

  const issues = useQuery({
    queryKey: ["dashboard-issues", issuesPanelQueryParams],
    queryFn: () =>
      fetchJson<IssuesPayload>("/api/issues", issuesPanelQueryParams),
    enabled: Boolean(workspace?.selectedCountry) && activePanel === "issues",
    ...commonQueryOptions
  });

  const kanban = useQuery({
    queryKey: ["dashboard-kanban", sharedScopeParams],
    queryFn: () =>
      fetchJson<KanbanPayload>("/api/kanban", sharedScopeParams),
    enabled: Boolean(workspace?.selectedCountry) && activePanel === "kanban",
    ...commonQueryOptions
  });

  const issueKeys = useQuery({
    queryKey: ["dashboard-note-keys", sharedScopeParams],
    queryFn: () =>
      fetchJson<IssueKeysPayload>("/api/issues/keys", sharedScopeParams),
    enabled: Boolean(workspace?.selectedCountry) && activePanel === "notes"
  });

  useEffect(() => {
    if (activePanel !== "notes") {
      return;
    }
    const keys = issueKeys.data?.keys ?? [];
    if (keys.length === 0) {
      return;
    }
    if (keys.includes(dashboardState.params.notesIssueKey)) {
      return;
    }
    dashboardState.update({
      notesIssueKey: keys[0]
    });
  }, [activePanel, dashboardState, dashboardState.params.notesIssueKey, issueKeys.data?.keys]);

  useEffect(() => {
    if (!workspace?.selectedCountry) {
      return;
    }
    const timer = window.setTimeout(() => {
      void import("../components/ChartFigurePlot");
      void queryClient.prefetchQuery({
        queryKey: ["dashboard-overview", overviewQueryParams],
        queryFn: () => fetchJson<DashboardPayload>("/api/dashboard", overviewQueryParams),
        staleTime: commonQueryOptions.staleTime,
      });
      if (trendChartId) {
        void queryClient.prefetchQuery({
          queryKey: ["dashboard-trend-detail", trendDetailQueryParams],
          queryFn: () =>
            fetchJson<TrendDetailPayload>("/api/trends/detail", trendDetailQueryParams),
          staleTime: commonQueryOptions.staleTime,
        });
      }
      void queryClient.prefetchQuery({
        queryKey: ["dashboard-intelligence", intelligenceQueryParams],
        queryFn: () =>
          fetchJson<IntelligencePayload>("/api/intelligence", intelligenceQueryParams),
        staleTime: commonQueryOptions.staleTime,
      });
      void queryClient.prefetchQuery({
        queryKey: ["dashboard-issues", issuesPanelQueryParams],
        queryFn: () =>
          fetchJson<IssuesPayload>("/api/issues", issuesPanelQueryParams),
        staleTime: commonQueryOptions.staleTime,
      });
      void queryClient.prefetchQuery({
        queryKey: ["dashboard-kanban", sharedScopeParams],
        queryFn: () =>
          fetchJson<KanbanPayload>("/api/kanban", sharedScopeParams),
        staleTime: commonQueryOptions.staleTime,
      });
    }, 90);

    return () => window.clearTimeout(timer);
  }, [
    workspace?.selectedCountry,
    queryClient,
    overviewQueryParams,
    trendDetailQueryParams,
    intelligenceQueryParams,
    issuesPanelQueryParams,
    sharedScopeParams,
    trendChartId,
    commonQueryOptions.staleTime
  ]);

  const note = useQuery({
    queryKey: ["dashboard-note", dashboardState.params.notesIssueKey],
    queryFn: () =>
      fetchJson<{ note: string }>(
        `/api/notes/${encodeURIComponent(dashboardState.params.notesIssueKey)}`
      ),
    enabled:
      Boolean(workspace?.selectedCountry) &&
      activePanel === "notes" &&
      Boolean(dashboardState.params.notesIssueKey)
  });

  const saveNote = useMutation({
    mutationFn: ({ issueKey, noteText }: { issueKey: string; noteText: string }) =>
      putJson(`/api/notes/${encodeURIComponent(issueKey)}`, { note: noteText }),
    onSuccess: async (_payload, variables) => {
      await queryClient.invalidateQueries({
        queryKey: ["dashboard-note", variables.issueKey]
      });
    }
  });

  async function openIssue(row: Record<string, string | number | undefined>) {
    const url = String(row.url ?? "").trim();
    try {
      const result = await postJson<{ opened: boolean; browser: string; url: string }>(
        "/api/browser/open",
        {
          url,
          sourceType: String(row.source_type ?? "")
        }
      );
      if (result.opened) {
        return;
      }
      if (url) {
        const popup = window.open(url, "_blank", "noopener,noreferrer");
        if (popup) {
          return;
        }
      }
      window.alert(`No se pudo abrir la incidencia en ${result.browser}.`);
    } catch (error) {
      if (url) {
        const popup = window.open(url, "_blank", "noopener,noreferrer");
        if (popup) {
          return;
        }
      }
      const message =
        error instanceof Error ? error.message : "No se pudo abrir la incidencia.";
      window.alert(message);
    }
  }

  function handleFocusCard(card: DashboardPayload["focusCards"][number]) {
    const targetInsightsTab =
      card.target === "people"
        ? "people"
        : card.target === "top_topics"
          ? "functionality"
          : dashboardState.params.insightsTab;
    dashboardState.update({
      panel: card.panel,
      trendChart: card.panel === "trends" ? card.target : dashboardState.params.trendChart,
      insightsTab: card.panel === "insights" ? targetInsightsTab : dashboardState.params.insightsTab
    });
  }

  function handleTrendInsightFilters(
    insight: TrendDetailPayload["cards"][number]
  ) {
    dashboardState.update({
      panel: "issues",
      status: insight.statusFilters,
      priority: insight.priorityFilters,
      assignee: insight.assigneeFilters,
      issuePage: "1"
    });
  }

  if (!workspace?.hasData) {
    return (
      <EmptyState
        title="No hay datos todavía"
        description="Ejecuta una ingesta para poblar el radar y activar las vistas del dashboard."
      />
    );
  }

  if (!workspace.selectedCountry) {
    return (
      <EmptyState
        title="No hay alcance operativo"
        description="El workspace no ha podido resolver país y origen con la configuración actual."
      />
    );
  }

  if (activePanel === "overview") {
    if (!overview.data && overview.isLoading) {
      return (
        <EmptyState
          title="Cargando resumen operativo"
          description="Preparando KPIs, focos accionables y gráficos resumen."
        />
      );
    }
    if (overview.error) {
      return <QueryErrorState title="No se ha podido construir el overview" error={overview.error} />;
    }
    if (!overview.data) {
      return (
        <EmptyState
          title="No se ha podido construir el overview"
          description="La API no ha devuelto datos para la vista Resumen."
        />
      );
    }

    return (
      <section className="page-stack">
        <section className="overview-kpi-grid">
          {overview.data.overviewKpis.map((kpi) => (
            <article className="kpi-card" key={kpi.label}>
              <span>{kpi.label}</span>
              <strong>{kpi.value}</strong>
              <small>{kpi.hint}</small>
            </article>
          ))}
        </section>

        <section className="page-stack">
          <div className="panel-head">
            <div>
              <h3>Focos accionables</h3>
            </div>
          </div>
          <div className="focus-card-grid">
            {overview.data.focusCards.map((card) => (
              <button
                type="button"
                className={classNames("focus-card", `focus-card-${card.tone}`)}
                key={card.cardId}
                onClick={() => handleFocusCard(card)}
              >
                <span className="focus-card-kicker">{card.kicker}</span>
                <strong className="focus-card-metric">{card.metric}</strong>
                <span className="focus-card-title">{card.title}</span>
                <span className="focus-card-detail">{card.detail}</span>
                <span className="focus-card-footer">
                  <span className="focus-card-action">{focusCardActionLabel(card)}</span>
                  <span className="focus-card-arrow" aria-hidden="true">
                    →
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="chart-grid overview-summary-grid">
          {overview.data.charts.map((chart) => (
            <article className="chart-card" key={chart.id}>
              <div className="chart-copy">
                <div>
                  <p className="eyebrow">{chart.group}</p>
                  <h4>{chart.title}</h4>
                  <p>{chart.subtitle}</p>
                </div>
              </div>
              <ChartFigure figure={chart.figure} />
            </article>
          ))}
        </section>

        <StatusPriorityMatrix
          matrix={overview.data.statusPriorityMatrix}
          onChange={dashboardState.update}
        />
      </section>
    );
  }

  if (activePanel === "trends") {
    if (!trendDetail.data?.chart && trendDetail.isLoading) {
      return (
        <EmptyState
          title="Cargando tendencias"
          description="Preparando gráfico seleccionado y señales contextuales."
        />
      );
    }
    if (trendDetail.error) {
      return <QueryErrorState title="No se han podido cargar las tendencias" error={trendDetail.error} />;
    }
    if (!trendDetail.data?.chart) {
      return (
        <EmptyState
          title="No hay gráfico disponible"
          description="La combinación actual de filtros no devuelve datos para la tendencia seleccionada."
        />
      );
    }

    return (
      <section className="page-stack">
        <section className="surface-panel page-stack">
          <label className="field trend-selector-field">
            <span>Gráfico</span>
            <select
              value={trendChartId}
              onChange={(event) => dashboardState.update({ trendChart: event.target.value })}
            >
              {(bootstrap?.chartsCatalog ?? []).map((chart) => (
                <option key={chart.id} value={chart.id}>
                  {chart.label}
                </option>
              ))}
            </select>
          </label>

          {trendDetail.data.adaptedForTerminal ? (
            <div className="inline-notice">
              Vista adaptada al estado finalista seleccionado: el gráfico conserva incidencias finalizadas para no perder señal.
            </div>
          ) : null}

          <article className="chart-card trend-chart-card">
            <div className="chart-copy">
              <div>
                <p className="eyebrow">{trendDetail.data.chart.id}</p>
                <h4>{trendDetail.data.chart.title}</h4>
                <p>{trendDetail.data.chart.subtitle}</p>
              </div>
              {trendDetail.data.executiveTip ? (
                <p className="trend-executive-tip">{trendDetail.data.executiveTip}</p>
              ) : null}
            </div>

            {trendDetail.data.metrics.length > 0 ? (
              <div className="trend-metrics-grid">
                {trendDetail.data.metrics.map((metric) => (
                  <article className="trend-metric-card" key={metric.label}>
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </article>
                ))}
              </div>
            ) : null}

            <ChartFigure figure={trendDetail.data.chart.figure} height={380} />
          </article>

          {trendDetail.data.cards.length > 0 ? (
            <div className="trend-insight-grid">
              {trendDetail.data.cards.map((card, index) => (
                <button
                  type="button"
                  className="trend-insight-card"
                  key={`${card.title}-${index}`}
                  onClick={() => handleTrendInsightFilters(card)}
                >
                  <strong>{card.title}</strong>
                  <span>{card.body}</span>
                </button>
              ))}
            </div>
          ) : null}
        </section>
      </section>
    );
  }

  if (activePanel === "insights") {
    if (!intelligence.data && intelligence.isLoading) {
      return (
        <EmptyState
          title="Cargando insights"
          description="Preparando temáticas, duplicidades y recomendaciones."
        />
      );
    }
    if (intelligence.error) {
      return <QueryErrorState title="No se han podido cargar los insights" error={intelligence.error} />;
    }

    return (
      <InsightsPanel
        data={intelligence.data}
        params={{
          insightsTab: dashboardState.params.insightsTab,
          insightsViewMode: dashboardState.params.insightsViewMode,
          insightsStatusManual: dashboardState.params.insightsStatusManual
        }}
        onChange={dashboardState.update}
        onOpenIssue={openIssue}
      />
    );
  }

  if (activePanel === "issues") {
    if (!issues.data && issues.isLoading) {
      return (
        <EmptyState
          title="Cargando issues"
          description="Aplicando filtros, búsqueda y ordenación sobre el backlog."
        />
      );
    }
    if (issues.error) {
      return <QueryErrorState title="No se han podido cargar las issues" error={issues.error} />;
    }

    return (
      <section className="page-stack">
        <DashboardFilters
          filterOptions={workspace.filterOptions}
          status={dashboardState.params.status}
          priority={dashboardState.params.priority}
          assignee={dashboardState.params.assignee}
          quincenalScope={dashboardState.params.quincenalScope}
          onChange={dashboardState.update}
        />
        <IssuesPanel
          rows={issues.data?.rows ?? []}
          total={issues.data?.total ?? 0}
          page={currentPage}
          pageSize={pageSize}
          view={dashboardState.params.issuesView}
          sortCol={dashboardState.params.issueSortCol}
          sortDir={dashboardState.params.issueSortDir}
          issueLikeQuery={dashboardState.params.issueLikeQuery}
          queryParams={issueExportParams(dashboardState.params, darkMode)}
          onOpenIssue={openIssue}
          onChange={dashboardState.update}
        />
      </section>
    );
  }

  if (activePanel === "kanban") {
    if (!kanban.data && kanban.isLoading) {
      return (
        <EmptyState
          title="Cargando tablero"
          description="Preparando las columnas Kanban con la selección actual."
        />
      );
    }
    if (kanban.error) {
      return <QueryErrorState title="No se ha podido construir el Kanban" error={kanban.error} />;
    }

    return (
      <section className="page-stack">
        <DashboardFilters
          filterOptions={workspace.filterOptions}
          status={dashboardState.params.status}
          priority={dashboardState.params.priority}
          assignee={dashboardState.params.assignee}
          quincenalScope={dashboardState.params.quincenalScope}
          onChange={dashboardState.update}
        />
        <KanbanBoard
          columns={kanban.data ?? []}
          onOpenIssue={openIssue}
          selectedStatuses={dashboardState.params.status}
          onStatusClick={(status) =>
            dashboardState.update({
              status: [status],
              issuePage: "1"
            })
          }
        />
      </section>
    );
  }

  if (activePanel === "notes") {
    if (issueKeys.error) {
      return <QueryErrorState title="No se han podido cargar las notas" error={issueKeys.error} />;
    }
    if (note.error) {
      return <QueryErrorState title="No se ha podido cargar la nota" error={note.error} />;
    }

    return (
      <NotesEditor
        issueKeys={issueKeys.data?.keys ?? []}
        selectedIssueKey={dashboardState.params.notesIssueKey}
        note={note.data?.note ?? ""}
        isLoading={issueKeys.isLoading || note.isLoading}
        isSaving={saveNote.isPending}
        saveSucceeded={saveNote.isSuccess}
        onIssueChange={(issueKey) => {
          saveNote.reset();
          dashboardState.update({ notesIssueKey: issueKey });
        }}
        onSave={(issueKey, noteText) => saveNote.mutate({ issueKey, noteText })}
      />
    );
  }

  return (
    <EmptyState
      title="Vista no disponible"
      description="La sección solicitada no forma parte del dashboard operativo."
    />
  );
}
