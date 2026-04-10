import type { KanbanPayload } from "../lib/api";
import {
  kanbanHeaderStyle,
  neutralChipStyle,
  semanticChipStyle
} from "../lib/semanticColors";

type KanbanBoardProps = {
  columns: KanbanPayload;
  onOpenIssue: (row: Record<string, string | number | undefined>) => void;
  selectedStatuses: string[];
  onStatusClick: (status: string) => void;
};

function classNames(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(" ");
}

function formatDate(value: string) {
  return value ? value.slice(0, 10) : "";
}

export function KanbanBoard({
  columns,
  onOpenIssue,
  selectedStatuses,
  onStatusClick
}: KanbanBoardProps) {
  if (columns.length === 0) {
    return (
      <section className="surface-panel empty-panel">
        <h3>No hay incidencias abiertas para mostrar</h3>
        <p>La selección actual no deja estados abiertos visibles en Kanban.</p>
      </section>
    );
  }

  return (
    <section className="kanban-grid">
      {columns.map((column) => (
        <article className="kanban-column" key={column.status}>
          <header className="kanban-column-head">
            <button
              type="button"
              className={classNames(
                "kanban-column-button",
                selectedStatuses.includes(column.status) && "kanban-column-button-active"
              )}
              style={kanbanHeaderStyle(column.status, selectedStatuses.includes(column.status))}
              onClick={() => onStatusClick(column.status)}
            >
              {column.status} ({column.count})
            </button>
          </header>
          <div className="kanban-stack">
            {column.items.map((item) => (
              <article className="kanban-card" key={`${item.key}-${item.source_alias}`}>
                <button
                  type="button"
                  className="kanban-card-link issue-key-anchor-button"
                  onClick={() => onOpenIssue(item)}
                >
                  {item.key}
                </button>
                <p className="kanban-card-summary">{item.summary || "Sin resumen"}</p>
                <div className="kanban-card-meta">
                  <span
                    className="issue-chip"
                    style={semanticChipStyle(item.priority || "", "priority")}
                  >
                    {item.priority || "(sin priority)"}
                  </span>
                  {item.assignee ? (
                    <span className="issue-chip issue-chip-neutral" style={neutralChipStyle("0.78rem")}>
                      {item.assignee}
                    </span>
                  ) : null}
                  <span className="issue-chip issue-chip-neutral" style={neutralChipStyle("0.78rem")}>
                    {formatDate(item.updated) || `${Math.round(Number(item.ageDays ?? 0))}d`}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </article>
      ))}
    </section>
  );
}
