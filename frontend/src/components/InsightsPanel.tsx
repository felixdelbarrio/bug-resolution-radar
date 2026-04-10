import { useState } from "react";
import type { IntelligencePayload, IssueRecord } from "../lib/api";
import {
  neutralChipStyle,
  semanticButtonStyle,
  semanticChipStyle
} from "../lib/semanticColors";
import { ChartFigure } from "./ChartFigure";

type InsightsPanelProps = {
  data: IntelligencePayload;
  params: {
    insightsTab: string;
    insightsViewMode: string;
    insightsStatusManual: string;
  };
  onChange: (patch: Record<string, string | string[]>) => void;
  onOpenIssue: (row: IssueRecord) => Promise<void>;
};

type FilterComboProps = {
  label: string;
  options: string[];
  selected: string[];
  kind?: "status" | "priority";
  onChange: (next: string[]) => void;
};

function classNames(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(" ");
}

function FilterCombo({ label, options, selected, kind, onChange }: FilterComboProps) {
  const summary = selected.length > 0 ? selected.join(", ") : "Sin valor";
  return (
    <details className="filter-combo insights-combo">
      <summary className="filter-combo-summary">
        <span>{label}</span>
        <strong>{summary}</strong>
      </summary>
      <div className="filter-combo-menu">
        {options.length === 0 ? <span className="filter-empty">Sin opciones</span> : null}
        {options.map((option) => {
          const checked = selected.includes(option);
          return (
            <label key={option} className="filter-check">
              <input
                type="checkbox"
                checked={checked}
                onChange={() =>
                  onChange(
                    checked
                      ? selected.filter((item) => item !== option)
                      : [...selected, option]
                  )
                }
              />
              <span
                className={kind ? "filter-check-value filter-check-value-semantic" : "filter-check-value"}
                style={kind ? semanticChipStyle(option, kind) : undefined}
              >
                {option}
              </span>
            </label>
          );
        })}
      </div>
    </details>
  );
}

function issueSubtitle(issue: IssueRecord) {
  return [issue.status, issue.priority, issue.assignee].filter(Boolean).join(" · ");
}

function IssueList({
  issues,
  onOpenIssue,
  emptyMessage = "No hay incidencias en este bloque."
}: {
  issues: IssueRecord[];
  onOpenIssue: (row: IssueRecord) => Promise<void>;
  emptyMessage?: string;
}) {
  if (issues.length === 0) {
    return <p className="issue-list-empty">{emptyMessage}</p>;
  }
  return (
    <div className="issue-stack">
      {issues.map((issue) => (
        <article key={issue.key} className="insight-issue-card">
          <div className="insight-issue-copy">
            <button
              type="button"
              className="issue-key-button insight-issue-key"
              onClick={() => void onOpenIssue(issue)}
            >
              {issue.key}
            </button>
            <div className="issue-card-badges insight-issue-chip-row">
              <span className="issue-chip" style={semanticChipStyle(issue.status || "", "status")}>
                {issue.status || "(sin estado)"}
              </span>
              <span
                className="issue-chip"
                style={semanticChipStyle(issue.priority || "", "priority")}
              >
                {issue.priority || "(sin priority)"}
              </span>
              {issue.assignee ? (
                <span className="issue-chip issue-chip-neutral" style={neutralChipStyle("0.78rem")}>
                  {issue.assignee}
                </span>
              ) : null}
              <span className="issue-chip issue-chip-neutral" style={neutralChipStyle("0.78rem")}>
                {issue.ageDays > 0 ? `${Math.round(issue.ageDays)}d` : "0d"}
              </span>
            </div>
            <p>{issue.summary || "(sin summary)"}</p>
            <small>{issueSubtitle(issue)}</small>
          </div>
          <div className="insight-issue-meta">
            <button
              type="button"
              className="ghost-button"
              onClick={() => void onOpenIssue(issue)}
            >
              Abrir
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function flowLabel(direction: string) {
  if (direction === "improving") {
    return "Mejorando";
  }
  if (direction === "worsening") {
    return "Empeorando";
  }
  return "Estable";
}

export function InsightsPanel({
  data,
  params,
  onChange,
  onOpenIssue
}: InsightsPanelProps) {
  const [duplicatesView, setDuplicatesView] = useState<"title" | "heuristic">("title");
  const activeTab =
    data.tabs.find((tab) => tab.id === params.insightsTab)?.id ?? data.tabs[0]?.id ?? "summary";
  const combo = data.functionality.combo;

  function jumpToIssues(quincenalScopeLabel: string) {
    onChange({
      panel: "issues",
      quincenalScope: quincenalScopeLabel,
      issuePage: "1"
    });
  }

  function handleViewModeChange(nextViewMode: string) {
    const patch: Record<string, string | string[]> = {
      insightsViewMode: nextViewMode
    };
    if (!params.insightsStatusManual) {
      patch.insightsStatus = [];
    }
    onChange(patch);
  }

  return (
    <section className="page-stack">
      <section className="surface-panel insights-tabs-shell">
        <nav className="subtab-strip" aria-label="Navegación de insights">
          {data.tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={classNames("subtab-button", activeTab === tab.id && "subtab-button-active")}
              onClick={() => onChange({ insightsTab: tab.id })}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </section>

      {activeTab === "summary" ? (
        <section className="page-stack">
          <section className="surface-panel page-stack">
            <p className="inline-caption">{data.periodSummary.caption}</p>
            <div className="period-card-grid">
              {data.periodSummary.cards.map((card) => (
                <button
                  type="button"
                  key={card.cardId}
                  className="period-action-card"
                  onClick={() => jumpToIssues(card.quincenalScopeLabel)}
                >
                  <span>{card.kicker}</span>
                  <strong>{card.metric}</strong>
                  <p>{card.detail}</p>
                  <small>{card.label}</small>
                </button>
              ))}
            </div>
          </section>

          <section className="surface-panel page-stack">
            {data.periodSummary.groups.map((group) => (
              <details className="insight-detail-block" key={group.label}>
                <summary>
                  <span>{group.label}</span>
                  <strong>{group.count}</strong>
                </summary>
                {group.helpText ? <p className="inline-caption">{group.helpText}</p> : null}
                <div className="detail-actions-row">
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={() => jumpToIssues(group.quincenalScopeLabel)}
                  >
                    Abrir en Issues
                  </button>
                </div>
                <IssueList issues={group.items} onOpenIssue={onOpenIssue} />
              </details>
            ))}
          </section>

          {data.periodSummary.sourceBreakdown.length > 0 ? (
            <section className="surface-panel page-stack">
              <div className="panel-head">
                <div>
                  <p className="section-kicker">Resumen</p>
                  <h3>Corte por origen seleccionado</h3>
                </div>
              </div>
              <div className="simple-table">
                <div className="simple-table-head">
                  <span>Origen</span>
                  <span>Abiertas</span>
                  <span>{data.periodSummary.sourceBreakdown[0]?.focus.label}</span>
                  <span>{data.periodSummary.sourceBreakdown[0]?.other.label}</span>
                  <span>Nuevas ahora</span>
                  <span>Cerradas ahora</span>
                  <span>Resolución</span>
                </div>
                {data.periodSummary.sourceBreakdown.map((row) => (
                  <div className="simple-table-row" key={row.source}>
                    <span>{row.source}</span>
                    <span>{row.abiertas}</span>
                    <span>{row.focus.value}</span>
                    <span>{row.other.value}</span>
                    <span>{row.nuevasAhora}</span>
                    <span>{row.cerradasAhora}</span>
                    <span>{row.resolucionAhora}</span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </section>
      ) : null}

      {activeTab === "functionality" ? (
        <section className="page-stack">
          <section className="surface-panel page-stack">
            <div className="insights-filter-shell">
              <div className="insights-filter-kicker">Filtros</div>
              <div className="insights-filter-grid">
                <label className="field">
                  <span>Vista</span>
                  <select
                    value={combo.viewMode}
                    onChange={(event) => handleViewModeChange(event.target.value)}
                  >
                    {combo.viewModeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
                <FilterCombo
                  label="Estado"
                  options={combo.statusOptions}
                  selected={combo.selectedStatuses}
                  kind="status"
                  onChange={(next) =>
                    onChange({
                      insightsStatus: next,
                      insightsStatusManual: "1"
                    })
                  }
                />
                <FilterCombo
                  label="Prioridad"
                  options={combo.priorityOptions}
                  selected={combo.selectedPriorities}
                  kind="priority"
                  onChange={(next) => onChange({ insightsPriority: next })}
                />
                <FilterCombo
                  label="Funcionalidades"
                  options={combo.functionalityOptions}
                  selected={combo.selectedFunctionalities}
                  onChange={(next) => onChange({ insightsFunctionality: next })}
                />
              </div>
            </div>

            {data.functionality.chart ? (
              <article className="chart-card trend-chart-card">
                <div className="chart-copy">
                  <div>
                    <p className="eyebrow">Insights</p>
                    <h4>{data.functionality.chart.title}</h4>
                    <p>{data.functionality.chart.subtitle}</p>
                  </div>
                </div>
                {data.functionality.chart.figure ? (
                  <ChartFigure figure={data.functionality.chart.figure} height={380} />
                ) : (
                  <p className="issue-list-empty">
                    No hay histórico suficiente para construir la tendencia seleccionada.
                  </p>
                )}
              </article>
            ) : (
              <section className="surface-panel empty-panel">
                <h3>Sin tendencia disponible</h3>
                <p>No hay histórico suficiente para construir la tendencia seleccionada.</p>
              </section>
            )}
          </section>

          {data.functionality.topics.map((topic) => (
            <details className="insight-detail-block" key={topic.topic}>
              <summary>
                <span>
                  {topic.count} issues · {topic.pct.toFixed(1)}% · {topic.topic}
                </span>
                <strong>{topic.dominantPriority}</strong>
              </summary>
              <div className="topic-meta-row">
                <span className="issue-chip" style={semanticChipStyle(topic.dominantStatus || "", "status")}>
                  {topic.dominantStatus}
                </span>
                <span
                  className="issue-chip"
                  style={semanticChipStyle(topic.dominantPriority || "", "priority")}
                >
                  {topic.dominantPriority}
                </span>
              </div>
              <p className="topic-brief">{topic.brief}</p>
              {topic.flow ? (
                <div className="flow-summary-card">
                  <strong>{flowLabel(topic.flow.direction)}</strong>
                  <span>
                    {topic.flow.createdCount} creadas · {topic.flow.resolvedCount} resueltas ·{" "}
                    {(topic.flow.pctDelta * 100).toFixed(1)}% en {topic.flow.windowDays} días
                  </span>
                </div>
              ) : null}
              {topic.rootCauses.length > 0 ? (
                <ul className="signal-list">
                  {topic.rootCauses.map((cause) => (
                    <li key={`${topic.topic}-${cause.label}`}>
                      {cause.label} · {cause.count}
                    </li>
                  ))}
                </ul>
              ) : null}
              <IssueList issues={topic.issues} onOpenIssue={onOpenIssue} />
            </details>
          ))}
          <p className="inline-caption">{data.functionality.tip}</p>
        </section>
      ) : null}

      {activeTab === "duplicates" ? (
        <section className="page-stack">
          <section className="surface-panel page-stack">
            <p className="inline-caption">{data.duplicates.brief}</p>
            <div className="soft-toggle-row">
              <button
                type="button"
                className={classNames(
                  "soft-toggle-button",
                  duplicatesView === "title" && "soft-toggle-button-active"
                )}
                onClick={() => setDuplicatesView("title")}
              >
                Por título
              </button>
              <button
                type="button"
                className={classNames(
                  "soft-toggle-button",
                  duplicatesView === "heuristic" && "soft-toggle-button-active"
                )}
                onClick={() => setDuplicatesView("heuristic")}
              >
                Por heurística
              </button>
            </div>
          </section>

          {(duplicatesView === "title"
            ? data.duplicates.titleGroups.map((group) => (
                <details className="insight-detail-block" key={`title-${group.summary}`}>
                  <summary>
                    <span>{group.summary}</span>
                    <strong>{group.count}</strong>
                  </summary>
                  <IssueList issues={group.issues} onOpenIssue={onOpenIssue} />
                </details>
              ))
            : data.duplicates.heuristicGroups.map((group) => (
                <details className="insight-detail-block" key={`heur-${group.summary}`}>
                  <summary>
                    <span>{group.summary}</span>
                    <strong>{group.count}</strong>
                  </summary>
                  <div className="topic-meta-row">
                    <span className="issue-chip" style={semanticChipStyle(group.dominantStatus || "", "status")}>
                      {group.dominantStatus}
                    </span>
                    <span
                      className="issue-chip"
                      style={semanticChipStyle(group.dominantPriority || "", "priority")}
                    >
                      {group.dominantPriority}
                    </span>
                  </div>
                  <IssueList issues={group.issues} onOpenIssue={onOpenIssue} />
                </details>
              )))}
        </section>
      ) : null}

      {activeTab === "people" ? (
        <section className="page-stack">
          {data.people.cards.map((card) => (
            <details className="insight-detail-block" key={card.assignee}>
              <summary>
                <span>
                  {card.assignee} · {card.openCount} abiertas · {card.sharePct.toFixed(1)}%
                </span>
                <strong>{card.risk.label}</strong>
              </summary>
              <div className="people-state-grid-react">
                {card.statusBreakdown.map((bucket) => (
                  <article
                    className="people-state-tile"
                    key={`${card.assignee}-${bucket.status}`}
                    style={semanticButtonStyle(bucket.status, "status", false)}
                  >
                    <strong>{bucket.count}</strong>
                    <span>{bucket.status}</span>
                  </article>
                ))}
              </div>
              <div className="people-kpi-grid-react">
                <article className="mini-kpi-card">
                  <span>Riesgo operativo</span>
                  <strong>{card.risk.label}</strong>
                  <small>
                    Flujo {card.risk.flowRiskPct.toFixed(0)}% · Criticidad{" "}
                    {card.risk.criticalRiskPct.toFixed(0)}%
                  </small>
                </article>
                <article className="mini-kpi-card">
                  <span>Empuje a salida</span>
                  <strong>{card.pushPct.toFixed(0)}%</strong>
                  <small>Cuanto más alto, mejor ritmo</small>
                </article>
                <article className="mini-kpi-card">
                  <span>Bloqueadas</span>
                  <strong>{card.blockedCount}</strong>
                  <small>Prioridad alta para desbloqueo</small>
                </article>
                <article className="mini-kpi-card">
                  <span>Antigüedad crítica</span>
                  <strong>{card.aging.value}</strong>
                  <small>{card.aging.caption}</small>
                </article>
              </div>
              <div className="recommendation-card">
                <strong>Plan recomendado</strong>
                <ul className="signal-list">
                  {card.recommendations.map((recommendation) => (
                    <li key={`${card.assignee}-${recommendation}`}>{recommendation}</li>
                  ))}
                </ul>
              </div>
              <div className="page-stack">
                <p className="inline-caption">Top 3 más antiguas</p>
                <IssueList
                  issues={card.oldestIssues}
                  onOpenIssue={onOpenIssue}
                  emptyMessage="No hay incidencias con antigüedad suficiente para mostrar."
                />
              </div>
            </details>
          ))}
        </section>
      ) : null}

      {activeTab === "opsHealth" ? (
        <section className="page-stack">
          <section className="surface-panel page-stack">
            <div className="ops-kpi-grid-react">
              {data.opsHealth.kpis.map((kpi) => (
                <article className="mini-kpi-card" key={kpi.label}>
                  <span>{kpi.label}</span>
                  <strong>{kpi.value}</strong>
                  <small>{kpi.detail}</small>
                </article>
              ))}
            </div>
            {data.opsHealth.brief.length > 0 ? (
              <div className="recommendation-card">
                <strong>Lectura rápida</strong>
                <ul className="signal-list">
                  {data.opsHealth.brief.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          <section className="surface-panel page-stack">
            <div className="panel-head">
              <div>
                <p className="section-kicker">Operativa</p>
                <h3>Top 10 abiertas más antiguas</h3>
              </div>
            </div>
            <IssueList
              issues={data.opsHealth.oldestIssues}
              onOpenIssue={onOpenIssue}
              emptyMessage="No hay antigüedad suficiente para construir el ranking."
            />
          </section>
        </section>
      ) : null}
    </section>
  );
}
