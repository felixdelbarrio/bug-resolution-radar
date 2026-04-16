import { useState } from "react";
import { downloadGet } from "../lib/api";
import { cn } from "../lib/cn";
import { neutralChipStyle, semanticChipStyle } from "../lib/semanticColors";

type IssuesPanelProps = {
  rows: Array<Record<string, string>>;
  total: number;
  page: number;
  pageSize: number;
  view: string;
  sortCol: string;
  sortDir: string;
  issueLikeQuery: string;
  queryParams: Record<string, string | string[] | boolean>;
  sourceType: string;
  isRefreshing: boolean;
  onOpenIssue: (row: Record<string, string | number | undefined>) => void;
  onChange: (patch: Record<string, string | string[]>) => void;
};

const sortOptions = [
  ["updated", "Updated"],
  ["created", "Created"],
  ["resolved", "Resolved"],
  ["status", "Status"],
  ["priority", "Priority"],
  ["assignee", "Assignee"],
  ["type", "Type"],
  ["summary", "Summary"],
  ["description", "Description"],
  ["key", "ID"],
  ["country", "Country"],
  ["source_type", "Origen"]
] as const;

function formatDate(value: string) {
  return value ? value.slice(0, 10) : "";
}

function dayDiff(from: string, to?: string) {
  if (!from) {
    return 0;
  }
  const start = new Date(from).getTime();
  const end = to ? new Date(to).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) {
    return 0;
  }
  return Math.max(0, Math.round((end - start) / 86_400_000));
}

function isClosed(row: Record<string, string>) {
  const status = String(row.status ?? "").trim().toLowerCase();
  if (row.resolved) {
    return true;
  }
  return ["closed", "resolved", "done", "deployed", "accepted"].some((token) =>
    status.includes(token)
  );
}

function Pager({
  page,
  totalPages,
  total,
  pageSize,
  onChange
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onChange: (next: string) => void;
}) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);
  return (
    <div className="issues-pager surface-panel">
      <button
        type="button"
        className="secondary-button"
        disabled={page <= 1}
        onClick={() => onChange(String(page - 1))}
      >
        ◀ Anterior
      </button>
      <div className="issues-pager-info">
        <strong>
          Página {page} de {totalPages}
        </strong>
        <span>
          Mostrando {start}-{end} de {total}
        </span>
      </div>
      <button
        type="button"
        className="secondary-button"
        disabled={page >= totalPages}
        onClick={() => onChange(String(page + 1))}
      >
        Siguiente ▶
      </button>
    </div>
  );
}

export function IssuesPanel({
  rows,
  total,
  page,
  pageSize,
  view,
  sortCol,
  sortDir,
  issueLikeQuery,
  queryParams,
  sourceType,
  isRefreshing,
  onOpenIssue,
  onChange
}: IssuesPanelProps) {
  const [downloadState, setDownloadState] = useState<"standard" | "helix-raw" | null>(null);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);
  const tableView = view === "Tabla";
  const helixExportAvailable = String(sourceType || "").trim().toLowerCase() === "helix";
  const summaryLabel =
    total === 0
      ? "0 issues filtradas"
      : tableView
        ? `${total} issues filtradas`
        : `Mostrando ${start}-${end} de ${total} issues filtradas`;

  async function handleDownload(path: string, kind: "standard" | "helix-raw", suggestedName: string) {
    try {
      setDownloadState(kind);
      await downloadGet(path, queryParams, suggestedName);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "No se pudo completar la descarga.";
      window.alert(message);
    } finally {
      setDownloadState(null);
    }
  }

  return (
    <section className="page-stack">
      <section className="surface-panel issues-topbar">
        <p className="minor-copy issues-count-caption">{summaryLabel}</p>
        {isRefreshing ? <span className="issues-refresh-pill">Actualizando backlog…</span> : null}
        <div className="issues-view-toggle">
          <button
            type="button"
            className={cn(
              "secondary-button",
              view === "Cards" && "issues-toggle-active"
            )}
            onClick={() => onChange({ issuesView: "Cards", issuePage: "1" })}
          >
            Cards
          </button>
          <button
            type="button"
            className={cn(
              "secondary-button",
              view === "Tabla" && "issues-toggle-active"
            )}
            onClick={() => onChange({ issuesView: "Tabla", issuePage: "1" })}
          >
            Tabla
          </button>
        </div>
      </section>

      <section className="surface-panel issues-sortbar">
        <div className="issues-sort-controls">
          <label className="field">
            <span>Ordenar por</span>
            <select
              value={sortCol}
              onChange={(event) =>
                onChange({ issueSortCol: event.target.value, issuePage: "1" })
              }
            >
              {sortOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Buscar similares por {sortCol}</span>
            <input
              value={issueLikeQuery}
              placeholder={`Like sobre ${sortCol}`}
              onChange={(event) =>
                onChange({ issueLikeQuery: event.target.value, issuePage: "1" })
              }
            />
          </label>
        </div>
        <div className="issues-sort-actions">
          <label className="checkbox-field checkbox-field-inline">
            <input
              type="checkbox"
              checked={sortDir === "asc"}
              onChange={(event) =>
                onChange({ issueSortDir: event.target.checked ? "asc" : "desc", issuePage: "1" })
              }
            />
            <span>Ascendente</span>
          </label>
          <button
            type="button"
            className="action-button"
            disabled={Boolean(downloadState) || isRefreshing}
            onClick={() => void handleDownload("/api/issues/export", "standard", "issues.xlsx")}
          >
            {downloadState === "standard" ? "Descargando..." : "Excel"}
          </button>
          {helixExportAvailable ? (
            <button
              type="button"
              className="secondary-button"
              disabled={Boolean(downloadState) || isRefreshing}
              onClick={() =>
                void handleDownload(
                  "/api/issues/export/helix-raw",
                  "helix-raw",
                  "helix_raw_issues.xlsx"
                )
              }
            >
              {downloadState === "helix-raw" ? "Preparando Helix Raw..." : "Helix Raw"}
            </button>
          ) : null}
        </div>
      </section>

      {total === 0 ? (
        <section className="surface-panel empty-panel">
          <h3>No hay issues para mostrar</h3>
          <p>La combinación actual de filtros no devuelve incidencias.</p>
        </section>
      ) : view === "Cards" ? (
        <section className="issues-card-stack">
          {rows.map((row) => {
            const closed = isClosed(row);
            const ageDays = closed ? dayDiff(row.created, row.resolved) : dayDiff(row.created);
            return (
              <article className="issue-card" key={`${row.key}-${row.source_id}`}>
                <button
                  type="button"
                  className="issue-primary-link"
                  onClick={() => onOpenIssue(row)}
                >
                  <span className="issue-key-anchor-button">{row.key}</span>
                  <strong className="issue-card-title">{row.summary || "Sin título"}</strong>
                </button>
                {row.description ? <p className="issue-card-description">{row.description}</p> : null}
                <div className="issue-card-badges">
                  <span
                    className="issue-chip"
                    style={semanticChipStyle(row.priority || "", "priority")}
                  >
                    Priority: {row.priority || "—"}
                  </span>
                  <span
                    className="issue-chip"
                    style={semanticChipStyle(row.status || "", "status")}
                  >
                    Status: {row.status || "—"}
                  </span>
                  <span className="issue-chip issue-chip-neutral" style={neutralChipStyle()}>
                    Assignee: {row.assignee || "—"}
                  </span>
                  <span className="issue-chip issue-chip-neutral" style={neutralChipStyle()}>
                    {closed ? "Resolved in" : "Open age"}: {ageDays}d
                  </span>
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <section className="surface-card issues-table-shell">
          <div className="table-wrap">
            <table className="issues-table">
              <colgroup>
                <col className="issues-col-id" />
                <col className="issues-col-summary" />
                <col className="issues-col-description" />
                <col className="issues-col-status" />
                <col className="issues-col-type" />
                <col className="issues-col-priority" />
                <col className="issues-col-date" />
                <col className="issues-col-date" />
                <col className="issues-col-date" />
                <col className="issues-col-assignee" />
              </colgroup>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Summary</th>
                  <th>Description</th>
                  <th>Status</th>
                  <th>Type</th>
                  <th>Priority</th>
                  <th>Created</th>
                  <th>Updated</th>
                  <th>Resolved</th>
                  <th>Assignee</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.key}-${row.source_id}`}>
                    <td className="issues-id-cell">
                      <button
                        type="button"
                        className="issue-inline-link issue-key-anchor-button"
                        onClick={() => onOpenIssue(row)}
                      >
                        {row.key}
                      </button>
                    </td>
                    <td className="issues-summary-cell">
                      <button
                        type="button"
                        className="issue-inline-link issue-primary-link issue-primary-link-inline"
                        onClick={() => onOpenIssue(row)}
                        title={row.summary || ""}
                      >
                        <strong className="issue-primary-link-title">{row.summary || "—"}</strong>
                      </button>
                    </td>
                    <td className="issues-description-cell" title={row.description || ""}>
                      {row.description || "—"}
                    </td>
                    <td>
                      <span
                        className="issue-chip issue-chip-table"
                        style={semanticChipStyle(row.status || "", "status")}
                      >
                        {row.status || "—"}
                      </span>
                    </td>
                    <td>
                      <span className="issue-table-token">{row.type || "—"}</span>
                    </td>
                    <td>
                      <span
                        className="issue-chip issue-chip-table"
                        style={semanticChipStyle(row.priority || "", "priority")}
                      >
                        {row.priority || "—"}
                      </span>
                    </td>
                    <td className="issue-table-date">{formatDate(row.created) || "—"}</td>
                    <td className="issue-table-date">{formatDate(row.updated) || "—"}</td>
                    <td className="issue-table-date">{formatDate(row.resolved) || "—"}</td>
                    <td className="issue-table-assignee">{row.assignee || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {!tableView ? (
        <Pager
          page={page}
          totalPages={totalPages}
          total={total}
          pageSize={pageSize}
          onChange={(next) => onChange({ issuePage: next })}
        />
      ) : null}
    </section>
  );
}
