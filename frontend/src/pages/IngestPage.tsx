import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchJson,
  normalizeSettingsPayload,
  postJson,
  putJson,
  type IngestLastRunPayload,
  type IngestOverviewPayload,
  type IngestResult,
  type SettingsPayload,
  type WorkspaceSource
} from "../lib/api";

type Connector = "jira" | "helix";

type ConnectorFeedback = {
  title: string;
  result?: IngestResult;
  error?: string;
};

const CONNECTOR_COPY: Record<
  Connector,
  {
    title: string;
    selectionLabel: string;
    configuredLabel: string;
    testLabel: string;
    runLabel: string;
    lastRunTitle: string;
    helpText: string;
    columns: Array<{ key: keyof WorkspaceSource; label: string }>;
  }
> = {
  jira: {
    title: "Fuentes Jira a ingestar",
    selectionLabel: "Seleccionadas para ingesta Jira",
    configuredLabel: "Fuentes Jira configuradas",
    testLabel: "Test Jira",
    runLabel: "Reingestar Jira",
    lastRunTitle: "Última ingesta (Jira)",
    helpText:
      "Por defecto todas marcadas. Este selector se guarda automáticamente en la configuración.",
    columns: [
      { key: "country", label: "country" },
      { key: "alias", label: "alias" },
      { key: "jql", label: "jql" }
    ]
  },
  helix: {
    title: "Fuentes Helix a ingestar",
    selectionLabel: "Seleccionadas para ingesta Helix",
    configuredLabel: "Fuentes Helix configuradas",
    testLabel: "Test Helix",
    runLabel: "Reingestar Helix",
    lastRunTitle: "Última ingesta (Helix)",
    helpText:
      "Por defecto todas marcadas. Este selector se guarda automáticamente en la configuración.",
    columns: [
      { key: "country", label: "country" },
      { key: "alias", label: "alias" },
      { key: "service_origin_buug", label: "Servicio Origen BU/UG" },
      { key: "service_origin_n1", label: "Servicio Origen N1" },
      { key: "service_origin_n2", label: "Servicio Origen N2" }
    ]
  }
};

function classNames(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(" ");
}

function resetLastIngest(
  connector: Connector,
  payload: IngestLastRunPayload
): IngestLastRunPayload {
  if (connector === "jira") {
    return {
      ...payload,
      ingested_at: "",
      jira_base_url: "",
      query: "",
      jira_source_count: 0,
      issues_count: 0
    };
  }
  return {
    ...payload,
    ingested_at: "",
    helix_base_url: "",
    query: "",
    helix_source_count: 0,
    items_count: 0
  };
}

function JsonBlock({ payload }: { payload: IngestLastRunPayload }) {
  return (
    <pre className="ingest-json-block">
      <code>{JSON.stringify(payload, null, 2)}</code>
    </pre>
  );
}

function FeedbackPanel({ feedback }: { feedback?: ConnectorFeedback }) {
  if (!feedback) {
    return null;
  }
  if (feedback.error) {
    return (
      <section className="inline-notice page-stack">
        <strong>{feedback.title}</strong>
        <p className="inline-caption">{feedback.error}</p>
      </section>
    );
  }
  if (!feedback.result) {
    return null;
  }
  return (
    <section className="inline-notice page-stack">
      <strong>{feedback.result.summary}</strong>
      <ul className="signal-list">
        {feedback.result.messages.map((item) => (
          <li
            key={`${feedback.title}-${item.message}`}
            className={item.ok ? "ingest-feedback-ok" : "ingest-feedback-error"}
          >
            {item.message}
          </li>
        ))}
      </ul>
    </section>
  );
}

function IngestSourceTable({
  connector,
  sources,
  selectedSourceIds,
  disabled,
  onToggle
}: {
  connector: Connector;
  sources: WorkspaceSource[];
  selectedSourceIds: string[];
  disabled: boolean;
  onToggle: (sourceId: string) => void;
}) {
  const copy = CONNECTOR_COPY[connector];
  const gridTemplateColumns = `96px repeat(${copy.columns.length}, minmax(0, 1fr))`;
  if (sources.length === 0) {
    return <p className="issue-list-empty">Sin orígenes configurados.</p>;
  }

  return (
    <div className="ingest-source-table" role="table" aria-label={copy.title}>
      <div className="ingest-source-head" role="row" style={{ gridTemplateColumns }}>
        <span className="ingest-source-checkbox-head">Ingestar</span>
        {copy.columns.map((column) => (
          <span key={String(column.key)}>{column.label}</span>
        ))}
      </div>
      {sources.map((source) => {
        const checked = selectedSourceIds.includes(source.source_id);
        return (
          <label
            key={source.source_id}
            className={classNames(
              "ingest-source-row",
              checked && "ingest-source-row-selected"
            )}
            role="row"
            style={{ gridTemplateColumns }}
          >
            <span className="ingest-source-check">
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={() => onToggle(source.source_id)}
              />
            </span>
            {copy.columns.map((column) => (
              <span key={`${source.source_id}-${String(column.key)}`}>
                {String(source[column.key] ?? "").trim() || "—"}
              </span>
            ))}
          </label>
        );
      })}
    </div>
  );
}

export function IngestPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Connector>("jira");
  const [jiraSelection, setJiraSelection] = useState<string[]>([]);
  const [helixSelection, setHelixSelection] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<Partial<Record<Connector, ConnectorFeedback>>>({});

  const settings = useQuery({
    queryKey: ["settings-ingest"],
    queryFn: async () =>
      normalizeSettingsPayload(await fetchJson<SettingsPayload>("/api/settings"))
  });

  const overview = useQuery({
    queryKey: ["ingest-overview"],
    queryFn: () => fetchJson<IngestOverviewPayload>("/api/ingest/overview")
  });

  useEffect(() => {
    if (!overview.data) {
      return;
    }
    setJiraSelection(overview.data.jira.selectedSourceIds);
    setHelixSelection(overview.data.helix.selectedSourceIds);
  }, [overview.data]);

  async function invalidateRadarData() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["bootstrap-shell"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-trend-detail"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-intelligence"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-issues"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-kanban"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-note-keys"] }),
      queryClient.invalidateQueries({ queryKey: ["settings"] }),
      queryClient.invalidateQueries({ queryKey: ["settings-ingest"] }),
      queryClient.invalidateQueries({ queryKey: ["ingest-overview"] })
    ]);
  }

  const jiraSelectionMutation = useMutation({
    mutationFn: (sourceIds: string[]) =>
      putJson<IngestOverviewPayload>("/api/ingest/jira/selection", { sourceIds }),
    onSuccess: (payload) => {
      queryClient.setQueryData(["ingest-overview"], payload);
      setJiraSelection(payload.jira.selectedSourceIds);
      void queryClient.invalidateQueries({ queryKey: ["settings-ingest"] });
    },
    onError: (error) => {
      setFeedback((current) => ({
        ...current,
        jira: {
          title: "No se pudo guardar la selección Jira",
          error: error instanceof Error ? error.message : "Error inesperado."
        }
      }));
    }
  });

  const helixSelectionMutation = useMutation({
    mutationFn: (sourceIds: string[]) =>
      putJson<IngestOverviewPayload>("/api/ingest/helix/selection", { sourceIds }),
    onSuccess: (payload) => {
      queryClient.setQueryData(["ingest-overview"], payload);
      setHelixSelection(payload.helix.selectedSourceIds);
      void queryClient.invalidateQueries({ queryKey: ["settings-ingest"] });
    },
    onError: (error) => {
      setFeedback((current) => ({
        ...current,
        helix: {
          title: "No se pudo guardar la selección Helix",
          error: error instanceof Error ? error.message : "Error inesperado."
        }
      }));
    }
  });

  const jiraTestMutation = useMutation({
    mutationFn: (sourceIds: string[]) =>
      postJson<IngestResult>("/api/ingest/jira/test", { sourceIds }),
    onSuccess: (result) => {
      setFeedback((current) => ({
        ...current,
        jira: {
          title: "Resultado test Jira",
          result
        }
      }));
    },
    onError: (error) => {
      setFeedback((current) => ({
        ...current,
        jira: {
          title: "Resultado test Jira",
          error: error instanceof Error ? error.message : "Error inesperado."
        }
      }));
    }
  });

  const helixTestMutation = useMutation({
    mutationFn: (sourceIds: string[]) =>
      postJson<IngestResult>("/api/ingest/helix/test", { sourceIds }),
    onSuccess: (result) => {
      setFeedback((current) => ({
        ...current,
        helix: {
          title: "Resultado test Helix",
          result
        }
      }));
    },
    onError: (error) => {
      setFeedback((current) => ({
        ...current,
        helix: {
          title: "Resultado test Helix",
          error: error instanceof Error ? error.message : "Error inesperado."
        }
      }));
    }
  });

  const jiraIngestMutation = useMutation({
    mutationFn: (sourceIds: string[]) =>
      postJson<IngestResult>("/api/ingest/jira", { sourceIds }),
    onSuccess: async (result) => {
      setFeedback((current) => ({
        ...current,
        jira: {
          title: "Resultado reingesta Jira",
          result
        }
      }));
      await invalidateRadarData();
    },
    onError: (error) => {
      setFeedback((current) => ({
        ...current,
        jira: {
          title: "Resultado reingesta Jira",
          error: error instanceof Error ? error.message : "Error inesperado."
        }
      }));
    }
  });

  const helixIngestMutation = useMutation({
    mutationFn: (sourceIds: string[]) =>
      postJson<IngestResult>("/api/ingest/helix", { sourceIds }),
    onSuccess: async (result) => {
      setFeedback((current) => ({
        ...current,
        helix: {
          title: "Resultado reingesta Helix",
          result
        }
      }));
      await invalidateRadarData();
    },
    onError: (error) => {
      setFeedback((current) => ({
        ...current,
        helix: {
          title: "Resultado reingesta Helix",
          error: error instanceof Error ? error.message : "Error inesperado."
        }
      }));
    }
  });

  if (settings.isLoading || overview.isLoading) {
    return (
      <section className="page-stack">
        <section className="surface-panel empty-panel">
          <h3>Cargando ingesta</h3>
          <p>Recuperando configuración y estado de las fuentes.</p>
        </section>
      </section>
    );
  }

  if (settings.isError || overview.isError || !settings.data || !overview.data) {
    const message =
      settings.error instanceof Error
        ? settings.error.message
        : overview.error instanceof Error
          ? overview.error.message
          : "No se ha podido cargar la pantalla de ingesta.";
    return (
      <section className="page-stack">
        <section className="surface-panel empty-panel">
          <h3>No se ha podido cargar la ingesta</h3>
          <p>{message}</p>
        </section>
      </section>
    );
  }

  const connector = activeTab;
  const copy = CONNECTOR_COPY[connector];
  const sourceRows =
    connector === "jira" ? settings.data.jiraSources : settings.data.helixSources;
  const selectedSourceIds = connector === "jira" ? jiraSelection : helixSelection;
  const selectionMutation =
    connector === "jira" ? jiraSelectionMutation : helixSelectionMutation;
  const testMutation = connector === "jira" ? jiraTestMutation : helixTestMutation;
  const ingestMutation = connector === "jira" ? jiraIngestMutation : helixIngestMutation;
  const connectorOverview = overview.data[connector];
  const selectionCount = selectedSourceIds.length;
  const isBusy =
    selectionMutation.isPending || testMutation.isPending || ingestMutation.isPending;
  const displayedLastIngest = ingestMutation.isPending
    ? resetLastIngest(connector, connectorOverview.lastIngest)
    : connectorOverview.lastIngest;

  function handleToggle(sourceId: string) {
    const current = connector === "jira" ? jiraSelection : helixSelection;
    const next = current.includes(sourceId)
      ? current.filter((item) => item !== sourceId)
      : [...current, sourceId];
    if (connector === "jira") {
      setJiraSelection(next);
      jiraSelectionMutation.mutate(next);
    } else {
      setHelixSelection(next);
      helixSelectionMutation.mutate(next);
    }
  }

  return (
    <section className="page-stack">
      <section className="surface-panel insights-tabs-shell">
        <nav className="subtab-strip" aria-label="Conectores de ingesta">
          {(["jira", "helix"] as Connector[]).map((item) => (
            <button
              key={item}
              type="button"
              className={classNames(
                "subtab-button",
                activeTab === item && "subtab-button-active"
              )}
              onClick={() => setActiveTab(item)}
            >
              {item === "jira" ? "Jira" : "Helix"}
            </button>
          ))}
        </nav>
      </section>

      <section className="surface-panel page-stack">
        <p className="inline-caption">
          {copy.configuredLabel}: {connectorOverview.configuredCount}
        </p>
        <div className="page-stack">
          <div>
            <h3>{copy.title}</h3>
            <p className="inline-caption">{copy.helpText}</p>
          </div>
          <IngestSourceTable
            connector={connector}
            sources={sourceRows}
            selectedSourceIds={selectedSourceIds}
            disabled={selectionMutation.isPending}
            onToggle={handleToggle}
          />
          <p className="inline-caption">
            {copy.selectionLabel}: {selectionCount}/{sourceRows.length}
          </p>
        </div>

        <div className="ingest-action-row">
          <button
            type="button"
            className="secondary-button"
            disabled={isBusy || selectionCount === 0}
            onClick={() => testMutation.mutate(selectedSourceIds)}
          >
            {testMutation.isPending ? `Probando ${activeTab}...` : copy.testLabel}
          </button>
          <button
            type="button"
            className="action-button"
            disabled={isBusy || selectionCount === 0}
            onClick={() => ingestMutation.mutate(selectedSourceIds)}
          >
            {ingestMutation.isPending ? `Reingestando ${activeTab}...` : copy.runLabel}
          </button>
        </div>

        {ingestMutation.isPending ? (
          <p className="inline-caption">
            Ingesta en curso. Solo en esta acción puede solicitarse acceso a navegador o cookies
            si la fuente lo requiere.
          </p>
        ) : null}

        <FeedbackPanel feedback={feedback[connector]} />
      </section>

      <section className="surface-panel page-stack">
        <div>
          <h3>{copy.lastRunTitle}</h3>
          {ingestMutation.isPending ? (
            <p className="inline-caption">
              Nueva ingesta en curso: se ocultan temporalmente los resultados de la ingesta
              previa.
            </p>
          ) : null}
        </div>
        <JsonBlock payload={displayedLastIngest} />
      </section>
    </section>
  );
}
