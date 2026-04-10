import { semanticButtonStyle } from "../lib/semanticColors";

type MatrixPayload = {
  title: string;
  total: number;
  priorities: Array<{ priority: string; count: number }>;
  rows: Array<{
    status: string;
    count: number;
    cells: Array<{ priority: string; count: number }>;
  }>;
  selected: {
    status: string[];
    priority: string[];
  };
};

type StatusPriorityMatrixProps = {
  matrix: MatrixPayload;
  onChange: (patch: Record<string, string | string[]>) => void;
};

function priorityLabel(priority: string) {
  return priority === "Supone un impedimento" ? "Impedimento" : priority;
}

function classNames(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(" ");
}

export function StatusPriorityMatrix({ matrix, onChange }: StatusPriorityMatrixProps) {
  if (!matrix.rows.length || !matrix.priorities.length) {
    return null;
  }

  const selectedStatuses = matrix.selected.status;
  const selectedPriorities = matrix.selected.priority;

  function toggleStatus(status: string) {
    const exists = selectedStatuses.includes(status);
    const next = exists
      ? selectedStatuses.filter((value) => value !== status)
      : [...selectedStatuses, status];
    onChange({
      status: next,
      priority: next.length > 0 ? selectedPriorities : [],
      issuePage: "1"
    });
  }

  function togglePriority(priority: string) {
    onChange({
      priority: selectedPriorities.length === 1 && selectedPriorities[0] === priority ? [] : [priority],
      issuePage: "1"
    });
  }

  function toggleCell(status: string, priority: string) {
    const nextStatuses = selectedStatuses.includes(status)
      ? selectedStatuses.filter((value) => value !== status)
      : [...selectedStatuses, status];
    onChange({
      status: nextStatuses,
      priority: nextStatuses.length > 0 ? [priority] : [],
      issuePage: "1"
    });
  }

  return (
    <section className="surface-panel">
      <div className="panel-head">
        <div>
          <p className="section-kicker">Overview</p>
          <h3>{matrix.title}</h3>
        </div>
        <span className="metric-chip">{matrix.total} issues</span>
      </div>
      <p className="minor-copy">
        {selectedStatuses.length || selectedPriorities.length
          ? `Seleccionado: Estado=${selectedStatuses.join(", ") || "(todos)"} · Priority=${selectedPriorities
              .map(priorityLabel)
              .join(", ") || "(todas)"}`
          : "Click en cabeceras o celdas para sincronizar filtros con Issues y Kanban."}
      </p>
      <div className="matrix-shell">
        <table className="matrix-table">
          <thead>
            <tr>
              <th>Estado ({matrix.total})</th>
              {matrix.priorities.map((priority) => (
                <th key={priority.priority}>
                  <button
                    type="button"
                    className={classNames(
                      "matrix-header-button",
                      selectedPriorities.includes(priority.priority) && "matrix-header-button-active"
                    )}
                    style={semanticButtonStyle(
                      priority.priority,
                      "priority",
                      selectedPriorities.includes(priority.priority)
                    )}
                    disabled={priority.count === 0}
                    onClick={() => togglePriority(priority.priority)}
                  >
                    {priorityLabel(priority.priority)} ({priority.count})
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((row) => (
              <tr key={row.status}>
                <th>
                  <button
                    type="button"
                    className={classNames(
                      "matrix-header-button",
                      selectedStatuses.includes(row.status) && "matrix-header-button-active"
                    )}
                    style={semanticButtonStyle(
                      row.status,
                      "status",
                      selectedStatuses.includes(row.status)
                    )}
                    disabled={row.count === 0}
                    onClick={() => toggleStatus(row.status)}
                  >
                    {row.status} ({row.count})
                  </button>
                </th>
                {row.cells.map((cell) => (
                  <td key={`${row.status}-${cell.priority}`}>
                    <button
                      type="button"
                      className={classNames(
                        "matrix-cell-button",
                        selectedStatuses.includes(row.status) &&
                          selectedPriorities.includes(cell.priority) &&
                          "matrix-cell-button-active"
                      )}
                      disabled={cell.count === 0}
                      onClick={() => toggleCell(row.status, cell.priority)}
                    >
                      {cell.count}
                    </button>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
