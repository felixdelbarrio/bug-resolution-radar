import { useEffect, useMemo, useState } from "react";
import type { NoteListPayload } from "../lib/api";
import { isValidIssueReference } from "../lib/issueLinks";

type NotesEditorProps = {
  issueKeys: string[];
  selectedIssueKey: string;
  note: string;
  notes: NoteListPayload["rows"];
  isLoading: boolean;
  isSaving: boolean;
  isDeleting: boolean;
  saveSucceeded: boolean;
  onIssueChange: (issueKey: string) => void;
  onSave: (issueKey: string, note: string) => void;
  onDelete: (issueKey: string) => void;
};

export function NotesEditor({
  issueKeys,
  selectedIssueKey,
  note,
  notes,
  isLoading,
  isSaving,
  isDeleting,
  saveSucceeded,
  onIssueChange,
  onSave,
  onDelete
}: NotesEditorProps) {
  const [issueDraft, setIssueDraft] = useState(selectedIssueKey);
  const [draft, setDraft] = useState("");
  const [validationMessage, setValidationMessage] = useState("");

  useEffect(() => {
    setIssueDraft(selectedIssueKey);
    setDraft(note);
  }, [note, selectedIssueKey]);

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

  const cleanIssueKey = issueDraft.trim().toUpperCase();
  const cleanNote = draft.trim();
  const issueIsValid = isValidIssueReference(cleanIssueKey);
  const canSave = Boolean(cleanIssueKey) && issueIsValid && Boolean(cleanNote) && !isSaving;

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
    onSave(cleanIssueKey, cleanNote);
  }

  function handleClear() {
    setIssueDraft("");
    setDraft("");
    setValidationMessage("");
    onIssueChange("");
  }

  return (
    <section className="notes-layout">
      <section className="surface-panel page-stack">
        <div className="panel-head">
          <div>
            <p className="section-kicker">Notas</p>
            <h3>Seguimiento local</h3>
          </div>
        </div>
        <label className="field notes-issue-field">
          <span>Issue</span>
          <input
            list="notes-issue-suggestions"
            value={issueDraft}
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
        <label className="field">
          <span>Nota (local)</span>
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
        <div className="notes-actions">
          <button
            type="button"
            className="action-button"
            disabled={!canSave}
            onClick={handleSave}
          >
            Guardar nota
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
            disabled={!cleanIssueKey || !issueIsValid || isDeleting}
            onClick={() => onDelete(cleanIssueKey)}
            aria-label="Eliminar nota"
            title="Eliminar nota"
          >
            ×
          </button>
          {isLoading ? <span className="minor-copy">Cargando nota...</span> : null}
          {!isLoading && saveSucceeded ? (
            <span className="minor-copy">Nota guardada localmente.</span>
          ) : null}
          {validationMessage ? <span className="minor-copy">{validationMessage}</span> : null}
        </div>
      </section>

      <section className="surface-card page-stack">
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
              <article className="notes-list-item" key={row.issueKey}>
                <button
                  type="button"
                  className="issue-inline-link issue-key-anchor-button"
                  onClick={() => {
                    setIssueDraft(row.issueKey);
                    setDraft(row.note);
                    setValidationMessage("");
                    onIssueChange(row.issueKey);
                  }}
                >
                  {row.issueKey}
                </button>
                <p>{row.issue?.summary || row.note}</p>
                <small>
                  {[row.issue?.status, row.issue?.priority, row.issue?.assignee]
                    .filter(Boolean)
                    .join(" · ") || (row.enriched ? "Incidencia enriquecida" : "Sin datos del issue")}
                </small>
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
