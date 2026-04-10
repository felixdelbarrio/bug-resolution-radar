import { semanticChipStyle } from "../lib/semanticColors";

type DashboardFiltersProps = {
  filterOptions?: {
    status: string[];
    priority: string[];
    assignee: string[];
    quincenal: string[];
  };
  status: string[];
  priority: string[];
  assignee: string[];
  quincenalScope: string;
  onChange: (patch: Record<string, string | string[]>) => void;
};

type MultiFilterProps = {
  label: string;
  options: string[];
  selected: string[];
  kind?: "status" | "priority";
  emptyLabel?: string;
  onChange: (next: string[]) => void;
};

function FilterCombo({
  label,
  options,
  selected,
  kind,
  emptyLabel = "Todas",
  onChange
}: MultiFilterProps) {
  const compactSummary =
    selected.length === 0
      ? emptyLabel
      : selected.length <= 2
        ? selected.join(" · ")
        : `${selected.length} seleccionados`;

  return (
    <details className="filter-combo">
      <summary className="filter-combo-summary">
        <span>{label}</span>
        {kind && selected.length > 0 ? (
          <div className="filter-summary-pill-row">
            {selected.slice(0, 2).map((item) => (
              <span
                key={item}
                className="filter-summary-pill"
                style={semanticChipStyle(item, kind)}
              >
                {item}
              </span>
            ))}
            {selected.length > 2 ? (
              <span className="filter-summary-more">+{selected.length - 2}</span>
            ) : null}
          </div>
        ) : (
          <strong
            className={
              selected.length === 0 ? "filter-combo-summary-placeholder" : undefined
            }
          >
            {compactSummary}
          </strong>
        )}
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

export function DashboardFilters({
  filterOptions,
  status,
  priority,
  assignee,
  quincenalScope,
  onChange
}: DashboardFiltersProps) {
  return (
    <section className="surface-panel dashboard-filters">
      <FilterCombo
        label="Estado"
        options={filterOptions?.status ?? []}
        selected={status}
        kind="status"
        emptyLabel="Todos"
        onChange={(next) => onChange({ status: next, issuePage: "1" })}
      />
      <FilterCombo
        label="Priority"
        options={filterOptions?.priority ?? []}
        selected={priority}
        kind="priority"
        emptyLabel="Todas"
        onChange={(next) => onChange({ priority: next, issuePage: "1" })}
      />
      <FilterCombo
        label="Asignado"
        options={filterOptions?.assignee ?? []}
        selected={assignee}
        emptyLabel="Todos"
        onChange={(next) => onChange({ assignee: next, issuePage: "1" })}
      />
      <label className="filter-select">
        <span>Quincenal</span>
        <select
          value={quincenalScope}
          onChange={(event) =>
            onChange({ quincenalScope: event.target.value, issuePage: "1" })
          }
        >
          {(filterOptions?.quincenal ?? ["Todas"]).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
