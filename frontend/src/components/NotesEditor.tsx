import { useEffect, useMemo, useState } from "react";
import type { NoteEntryPayload, NoteListPayload } from "../lib/api";
import { cn } from "../lib/cn";
import { isValidIssueReference } from "../lib/issueLinks";
import {
  issueStateBucket,
  issueStateLabel,
  type IssueStateBucket
} from "../lib/statusSemantics";

type NotesRow = NoteListPayload["rows"][number];

const NOTE_BUCKETS: Array<{ id: IssueStateBucket; label: string }> = [
  { id: "open", label: "Abiertas" },
  { id: "closed", label: "Cerradas" }
];

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
  onUpdateEntry: (issueKey: string, entryId: string, note: string) => void;
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
  onUpdateEntry,
  onDelete,
  onDeleteEntry
}: NotesEditorProps) {
  const [issueDraft, setIssueDraft] = useState(selectedIssueKey);
  const [draft, setDraft] = useState("");
  const [editingEntryId, setEditingEntryId] = useState("");
  const [validationMessage, setValidationMessage] = useState("");
  const [selectedBucket, setSelectedBucket] = useState<IssueStateBucket>("open");

  useEffect(() => {
    setIssueDraft(selectedIssueKey);
    setEditingEntryId("");
    setValidationMessage("");
  }, [selectedIssueKey]);

  useEffect(() => {
    if (saveSucceeded) {
      setDraft("");
      setEditingEntryId("");
    }
  }, [saveSucceeded]);

  const knownIssueReferences = useMemo(() => {
    const seen = new Set<string>();
    for (const key of issueKeys) {
      const cleanKey = key.trim().toUpperCase();
      if (cleanKey) {
        seen.add(cleanKey);
      }
    }
    return seen;
  }, [issueKeys]);

  const cleanIssueKey = issueDraft.trim().toUpperCase();
  const cleanNote = draft.trim();
  const issueIsValid = isValidIssueReference(cleanIssueKey);
  const issueExists = knownIssueReferences.has(cleanIssueKey);
  const canSave =
    Boolean(cleanIssueKey) && issueIsValid && issueExists && Boolean(cleanNote) && !isSaving;
  const selectedListRow = notes.find((row) => row.issueKey === cleanIssueKey);
  const visibleEntries =
    cleanIssueKey === selectedIssueKey ? entries : selectedListRow?.entries ?? [];
  const selectedMeta = selectedListRow?.issue;
  const selectedState = issueStateBucket(selectedMeta);
  const selectedStateLabel = issueStateLabel(selectedState);
  const groupedNotes = useMemo(() => {
    const groups: Record<IssueStateBucket, NotesRow[]> = {
      open: [],
      closed: []
    };
    for (const row of notes) {
      groups[issueStateBucket(row.issue)].push(row);
    }
    return groups;
  }, [notes]);
  const openRows = groupedNotes.open;
  const closedRows = groupedNotes.closed;
  const selectedNotesRows = groupedNotes[selectedBucket];

  useEffect(() => {
    if (selectedListRow) {
      setSelectedBucket(issueStateBucket(selectedListRow.issue));
    }
  }, [selectedListRow]);

  useEffect(() => {
    if (selectedBucket === "open" && openRows.length === 0 && closedRows.length > 0) {
      setSelectedBucket("closed");
    }
    if (selectedBucket === "closed" && closedRows.length === 0 && openRows.length > 0) {
      setSelectedBucket("open");
    }
  }, [closedRows.length, openRows.length, selectedBucket]);

  function commitIssueDraft(): boolean {
    if (!cleanIssueKey) {
      setValidationMessage("Introduce un issue JIRA o Helix.");
      return false;
    }
    if (!issueIsValid) {
      setValidationMessage("El issue debe tener formato JIRA o Helix válido.");
      return false;
    }
    if (!issueExists) {
      setValidationMessage("La incidencia no está ingestada.");
      return false;
    }
    setValidationMessage("");
    if (cleanIssueKey !== selectedIssueKey) {
      onIssueChange(cleanIssueKey);
    }
    return true;
  }

  function handleBucketChange(bucket: IssueStateBucket) {
    setSelectedBucket(bucket);
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
    if (!issueExists) {
      setValidationMessage("La incidencia no está ingestada.");
      return;
    }
    if (!cleanNote) {
      setValidationMessage("La nota no puede estar vacía.");
      return;
    }
    setValidationMessage("");
    if (editingEntryId) {
      onUpdateEntry(cleanIssueKey, editingEntryId, cleanNote);
    } else {
      if (!commitIssueDraft()) {
        return;
      }
      onSave(cleanIssueKey, cleanNote);
    }
  }

  function handleClear() {
    if (editingEntryId) {
      setDraft("");
      setEditingEntryId("");
      setValidationMessage("");
      return;
    }
    setIssueDraft("");
    setDraft("");
    setEditingEntryId("");
    setValidationMessage("");
    onIssueChange("");
  }

  function handleSelectIssue(issueKey: string) {
    setIssueDraft(issueKey);
    setDraft("");
    setEditingEntryId("");
    setValidationMessage("");
    onIssueChange(issueKey);
  }

  function handleEditEntry(entry: NoteEntryPayload) {
    setEditingEntryId(entry.id);
    setDraft(entry.note);
    setValidationMessage("");
  }

  return (
    <section className="notes-layout">
      <section className="surface-panel notes-composer page-stack">
        <div className="panel-head">
          <div>
            <p className="section-kicker">Notas</p>
            <h3>Seguimiento local</h3>
          </div>
          <div className="notes-panel-badges">
            {cleanIssueKey && selectedListRow ? (
              <span className={cn("notes-state-chip", `notes-state-chip-${selectedState}`)}>
                {selectedStateLabel}
              </span>
            ) : null}
            {visibleEntries.length > 0 ? (
              <span className="notes-count-pill">{visibleEntries.length} entradas</span>
            ) : null}
          </div>
        </div>
        <div className="notes-compose-grid">
          <label className="field notes-issue-field">
            <span>Issue</span>
            <input
              value={issueDraft}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  commitIssueDraft();
                }
              }}
              onChange={(event) => {
                setIssueDraft(event.target.value);
                setEditingEntryId("");
                setValidationMessage("");
              }}
              placeholder="MEXBMI1-12345"
            />
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
            {editingEntryId ? "Actualizar entrada" : "Añadir a bitácora"}
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={handleClear}
          >
            {editingEntryId ? "Cancelar edición" : "Limpiar"}
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
                  <div className="notes-entry-actions">
                    <button
                      type="button"
                      className="notes-entry-action-button notes-entry-edit-button"
                      disabled={isSaving || !cleanIssueKey}
                      onClick={() => handleEditEntry(entry)}
                      aria-label={`Editar comentario de ${entry.dateLabel}`}
                      title="Editar este comentario"
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="notes-entry-action-button notes-entry-delete-button"
                      disabled={isDeleting || !cleanIssueKey}
                      onClick={() => onDeleteEntry(cleanIssueKey, entry.id)}
                      aria-label={`Eliminar comentario de ${entry.dateLabel}`}
                      title="Eliminar este comentario"
                    >
                      ×
                    </button>
                  </div>
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
            <h3>{selectedNotesRows.length} visibles</h3>
          </div>
          <span className="notes-count-pill">{notes.length} total</span>
        </div>
        {notes.length === 0 ? (
          <p className="issue-list-empty">Todavía no hay notas locales en esta selección.</p>
        ) : (
          <>
            <div className="notes-index-summary" aria-label="Resumen de bitácoras">
              <div className="notes-index-stat notes-index-stat-open">
                <span>Abiertas</span>
                <strong>{openRows.length}</strong>
              </div>
              <div className="notes-index-stat notes-index-stat-closed">
                <span>Cerradas</span>
                <strong>{closedRows.length}</strong>
              </div>
            </div>
            <div className="notes-bucket-tabs" role="tablist" aria-label="Tipo de bitácora">
              {NOTE_BUCKETS.map((bucket) => {
                const count = groupedNotes[bucket.id].length;
                const isActiveBucket = selectedBucket === bucket.id;
                return (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={isActiveBucket}
                    className={cn(
                      "notes-bucket-tab",
                      `notes-bucket-tab-${bucket.id}`,
                      isActiveBucket && "notes-bucket-tab-active"
                    )}
                    key={bucket.id}
                    onClick={() => handleBucketChange(bucket.id)}
                  >
                    <span>{bucket.label}</span>
                    <strong>{count}</strong>
                  </button>
                );
              })}
            </div>
            {selectedNotesRows.length === 0 ? (
              <p className="issue-list-empty">No hay bitácoras en esta categoría.</p>
            ) : (
              <div className="notes-list">
                {selectedNotesRows.map((row) => {
                  const state = issueStateBucket(row.issue);
                  const metaParts = [
                    row.issue?.status,
                    row.issue?.priority,
                    row.issue?.assignee
                  ].filter(Boolean);
                  return (
                    <article
                      className={cn(
                        "notes-list-item",
                        `notes-list-item-${state}`,
                        row.issueKey === cleanIssueKey && "notes-list-item-active"
                      )}
                      key={row.issueKey}
                    >
                      <div className="notes-list-item-head">
                        <button
                          type="button"
                          className="issue-inline-link issue-key-anchor-button"
                          onClick={() => handleSelectIssue(row.issueKey)}
                        >
                          {row.issueKey}
                        </button>
                        <span className="notes-list-entry-count">
                          {row.entryCount} {row.entryCount === 1 ? "entrada" : "entradas"}
                        </span>
                      </div>
                      <p>{row.issue?.summary || row.entries[0]?.note || row.note}</p>
                      <div className="notes-list-note-preview">
                        {row.entries.at(-1)?.note || row.note}
                      </div>
                      <div className="notes-list-meta-row">
                        <span
                          className={cn(
                            "notes-state-chip",
                            `notes-state-chip-${state}`
                          )}
                        >
                          {issueStateLabel(state)}
                        </span>
                        {metaParts.length > 0 ? <small>{metaParts.join(" · ")}</small> : null}
                        {metaParts.length === 0 ? (
                          <small>{row.enriched ? "Incidencia enriquecida" : "Sin datos del issue"}</small>
                        ) : null}
                      </div>
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
                  );
                })}
              </div>
            )}
          </>
        )}
      </section>
    </section>
  );
}
