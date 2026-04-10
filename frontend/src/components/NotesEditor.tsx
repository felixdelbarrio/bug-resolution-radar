import { useEffect, useState } from "react";

type NotesEditorProps = {
  issueKeys: string[];
  selectedIssueKey: string;
  note: string;
  isLoading: boolean;
  isSaving: boolean;
  saveSucceeded: boolean;
  onIssueChange: (issueKey: string) => void;
  onSave: (issueKey: string, note: string) => void;
};

export function NotesEditor({
  issueKeys,
  selectedIssueKey,
  note,
  isLoading,
  isSaving,
  saveSucceeded,
  onIssueChange,
  onSave
}: NotesEditorProps) {
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setDraft(note);
  }, [note, selectedIssueKey]);

  if (issueKeys.length === 0) {
    return (
      <section className="surface-panel empty-panel">
        <h3>No hay issues disponibles para notas</h3>
        <p>La selección actual no devuelve incidencias sobre las que guardar contexto local.</p>
      </section>
    );
  }

  return (
    <section className="surface-panel page-stack">
      <div className="panel-head">
        <div>
          <p className="section-kicker">Notas</p>
          <h3>Seguimiento local</h3>
        </div>
      </div>
      <label className="field notes-issue-field">
        <span>Issue</span>
        <select value={selectedIssueKey} onChange={(event) => onIssueChange(event.target.value)}>
          {issueKeys.map((issueKey) => (
            <option key={issueKey} value={issueKey}>
              {issueKey}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Nota (local)</span>
        <textarea
          className="notes-area"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Anota contexto operativo para esta issue..."
        />
      </label>
      <div className="notes-actions">
        <button
          type="button"
          className="action-button"
          disabled={!selectedIssueKey || isSaving}
          onClick={() => onSave(selectedIssueKey, draft)}
        >
          Guardar nota
        </button>
        {isLoading ? <span className="minor-copy">Cargando nota…</span> : null}
        {!isLoading && saveSucceeded ? <span className="minor-copy">Nota guardada localmente.</span> : null}
      </div>
    </section>
  );
}
