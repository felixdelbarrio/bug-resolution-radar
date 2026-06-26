import { useEffect, useMemo, useState } from "react";
import type { NoteEntryPayload, NoteListPayload } from "../lib/api";
import { cn } from "../lib/cn";
import { isValidIssueReference } from "../lib/issueLinks";

type NotesEditorProps = {
  issueKeys: string[];
  selectedIssueKey: string;
  entries: NoteEntryPayload[];
  notes: NoteListPayload["rows"];
  isLoading: boolean;
  isSaving: boolean;
  isDeleting: boolean;
  saveSucceeded: boolean;
  onIssueChange: (issueKey: string) => void;
  onSave: (issueKey: string, note: string) => void;
  onDelete: (issueKey: string) => void;
  onDeleteEntry: (issueKey: string, entryId: string) => void;
};

export function NotesEditor({
  issueKeys,
  selectedIssueKey,
  entries,
  notes,
  isLoading,
  isSaving,
  isDeleting,
  saveSucceeded,
  onIssueChange,
  onSave,
  onDelete,
  onDeleteEntry
}: NotesEditorProps) {
  const [issueDraft, setIssueDraft] = useState(selectedIssueKey);
  const [draft, setDraft] = useState("");
  const [validationMessage, setValidationMessage] = useState("");

  useEffect(() => {
    setIssueDraft(selectedIssueKey);
    setValidationMessage("");
  }, [selectedIssueKey]);

  useEffect(() => {
    if (saveSucceeded) {
      setDraft("");
    }
  }, [saveSucceeded]);

  const suggestions = useMemo(() => {
    const seen = new Set<string>();
    return issueKeys
      .map((key) => key.trim().toUpperCase())
      .filter((key) => {
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 500);
  }, [issueKeys]);

  const knownIssueReferences = useMemo(() => {
    const seen = new Set<string>();
    for (const key of [...issueKeys, ...notes.map((row) => row.issueKey)]) {
      const cleanKey = key.trim().toUpperCase();
      if (cleanKey) {
        seen.add(cleanKey);
      }
    }
    return [...seen];
  }, [issueKeys, notes]);

  const knownIssueSet = useMemo(() => new Set(knownIssueReferences), [knownIssueReferences]);

  const cleanIssueKey = issueDraft.trim().toUpperCase();
  const cleanNote = draft.trim();
  const issueIsValid = isValidIssueReference(cleanIssueKey);
  const canSave = Boolean(cleanIssueKey) && issueIsValid && Boolean(cleanNote) && !isSaving;
  const selectedListRow = notes.find((row) => row.issueKey === cleanIssueKey);
  const visibleEntries =
    cleanIssueKey === selectedIssueKey ? entries : selectedListRow?.entries ?? [];
  const selectedMeta = selectedListRow?.issue;

  useEffect(() => {
    if (!issueIsValid || !knownIssueSet.has(cleanIssueKey) || cleanIssueKey === selectedIssueKey) {
      return;
    }
    const timer = window.setTimeout(() => {
      onIssueChange(cleanIssueKey);
    }, 260);
    return () => window.clearTimeout(timer);
  }, [cleanIssueKey, issueIsValid, knownIssueSet, onIssueChange, selectedIssueKey]);

  function commitIssueDraft() {
    if (cleanIssueKey && issueIsValid && cleanIssueKey !== selectedIssueKey) {
      onIssueChange(cleanIssueKey);
    }
  }

  function handleSave() {
    if (!cleanIssueKey) {
      setValidationMessage("Introduce un issue JIRA o Helix.");
      return;
    }
    if (!issueIsValid) {
      setValidationMessage("El issue debe tener formato JIRA o Helix válido.");
      return;
    }
    if (!cleanNote) {
      setValidationMessage("La nota no puede estar vacía.");
      return;
    }
    setValidationMessage("");
    commitIssueDraft();
    onSave(cleanIssueKey, cleanNote);
  }

  function handleClear() {
    setIssueDraft("");
    setDraft("");
    setValidationMessage("");
    onIssueChange("");
  }

  function handleSelectIssue(issueKey: string) {
    setIssueDraft(issueKey);
    setDraft("");
    setValidationMessage("");
    onIssueChange(issueKey);
  }

  return (
    <section className="notes-layout">
      <section className="surface-panel notes-composer page-stack">
        <div className="panel-head">
          <div>
            <p className="section-kicker">Notas</p>
            <h3>Seguimiento local</h3>
          </div>
          {visibleEntries.length > 0 ? (
            <span className="notes-count-pill">{visibleEntries.length} entradas</span>
          ) : null}
        </div>
        <div className="notes-compose-grid">
          <label className="field notes-issue-field">
            <span>Issue</span>
            <input
              list="notes-issue-suggestions"
              value={issueDraft}
              onBlur={commitIssueDraft}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  commitIssueDraft();
                }
              }}
              onChange={(event) => {
                setIssueDraft(event.target.value);
                setValidationMessage("");
              }}
              placeholder="MEXBMI1-12345"
            />
            <datalist id="notes-issue-suggestions">
              {suggestions.map((issueKey) => (
                <option key={issueKey} value={issueKey} />
              ))}
            </datalist>
          </label>
          <label className="field notes-draft-field">
            <span>Nuevo comentario</span>
            <textarea
              className="notes-area"
              value={draft}
              onChange={(event) => {
                setDraft(event.target.value);
                setValidationMessage("");
              }}
              placeholder="Anota contexto operativo para esta issue..."
            />
          </label>
        </div>
        <div className="notes-actions">
          <button
            type="button"
            className="action-button"
            disabled={!canSave}
            onClick={handleSave}
          >
            Añadir a bitácora
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={handleClear}
          >
            Limpiar
          </button>
          <button
            type="button"
            className="secondary-button"
            disabled={!cleanIssueKey || !issueIsValid || visibleEntries.length === 0 || isDeleting}
            onClick={() => onDelete(cleanIssueKey)}
            aria-label="Eliminar bitácora completa"
            title="Eliminar bitácora completa"
          >
            ×
          </button>
          {isLoading ? <span className="minor-copy">Cargando nota...</span> : null}
          {!isLoading && saveSucceeded ? (
            <span className="minor-copy">Comentario añadido a la bitácora.</span>
          ) : null}
          {validationMessage ? <span className="minor-copy">{validationMessage}</span> : null}
        </div>

        <div className="notes-history">
          <div className="notes-history-head">
            <div>
              <p className="section-kicker">Bitácora</p>
              <h4>{cleanIssueKey || "Sin issue seleccionado"}</h4>
            </div>
            {selectedMeta?.status || selectedMeta?.priority ? (
              <span className="notes-meta-chip">
                {[selectedMeta?.status, selectedMeta?.priority].filter(Boolean).join(" · ")}
              </span>
            ) : null}
          </div>
          {visibleEntries.length === 0 ? (
            <p className="issue-list-empty">No hay comentarios guardados para esta incidencia.</p>
          ) : (
            <ol className="notes-timeline">
              {visibleEntries.map((entry) => (
                <li className="notes-timeline-item" key={entry.id}>
                  <div className="notes-timeline-date">{entry.dateLabel}</div>
                  <p>{entry.note}</p>
                  <button
                    type="button"
                    className="notes-entry-delete-button"
                    disabled={isDeleting || !cleanIssueKey}
                    onClick={() => onDeleteEntry(cleanIssueKey, entry.id)}
                    aria-label={`Eliminar comentario de ${entry.dateLabel}`}
                    title="Eliminar este comentario"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>

      <section className="surface-card notes-index-panel page-stack">
        <div className="panel-head">
          <div>
            <p className="section-kicker">Incidencias con notas</p>
            <h3>{notes.length} guardadas</h3>
          </div>
        </div>
        {notes.length === 0 ? (
          <p className="issue-list-empty">Todavía no hay notas locales en esta selección.</p>
        ) : (
          <div className="notes-list">
            {notes.map((row) => (
              <article
                className={cn(
                  "notes-list-item",
                  row.issueKey === cleanIssueKey && "notes-list-item-active"
                )}
                key={row.issueKey}
              >
                <button
                  type="button"
                  className="issue-inline-link issue-key-anchor-button"
                  onClick={() => handleSelectIssue(row.issueKey)}
                >
                  {row.issueKey}
                </button>
                <p>{row.issue?.summary || row.entries[0]?.note || row.note}</p>
                <div className="notes-list-note-preview">{row.entries.at(-1)?.note || row.note}</div>
                <small>
                  {[row.issue?.status, row.issue?.priority, row.issue?.assignee]
                    .filter(Boolean)
                    .join(" · ") || (row.enriched ? "Incidencia enriquecida" : "Sin datos del issue")}
                </small>
                <span className="notes-list-date">
                  {row.latestDateLabel || `${row.entryCount} entradas`}
                </span>
                <button
                  type="button"
                  className="notes-delete-button"
                  onClick={() => onDelete(row.issueKey)}
                  disabled={isDeleting}
                  aria-label={`Eliminar nota de ${row.issueKey}`}
                  title="Eliminar nota"
                >
                  ×
                </button>
              </article>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
