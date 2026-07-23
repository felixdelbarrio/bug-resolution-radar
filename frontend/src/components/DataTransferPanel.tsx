import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchJson,
  postJson,
  type DataTransferExportPayload,
  type DataTransferHistoryPayload,
  type DownloadTargetPayload
} from "../lib/api";

type DataTransferPanelProps = {
  exportScope: {
    country: string;
    scopeMode: string;
    sourceIds: string[];
    sourceLabels: string[];
  };
};

const NUMBER_FORMATTER = new Intl.NumberFormat("es-ES");
const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("es-ES", {
  dateStyle: "medium",
  timeStyle: "short"
});

function formatNumber(value: number): string {
  return NUMBER_FORMATTER.format(Math.max(0, Number(value || 0)));
}

function formatFileSize(value: number): string {
  const bytes = Math.max(0, Number(value || 0));
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value || "—";
  return DATE_TIME_FORMATTER.format(parsed);
}

function DatasetExportStats({ result }: { result: DataTransferExportPayload }) {
  return (
    <section className="transfer-result transfer-result-success" aria-live="polite">
      <div className="transfer-result-head">
        <div>
          <span className="transfer-eyebrow">Traslado listo</span>
          <h3>{result.summary}</h3>
          <p className="inline-caption">
            {result.fileName} · {formatFileSize(result.fileSize)}
          </p>
        </div>
        <div className="transfer-total-orb">
          <strong>{formatNumber(result.totalRecords)}</strong>
          <span>artefactos incluidos</span>
        </div>
      </div>
      <div className="transfer-stat-grid">
        {result.stats.map((stat) => (
          <article key={stat.key} className="transfer-stat-card">
            <span>{stat.label}</span>
            <strong>{formatNumber(stat.count)}</strong>
            <small>incluidos</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function TransferHistory({ history }: { history?: DataTransferHistoryPayload }) {
  const operations = history?.operations ?? [];
  if (operations.length === 0) return null;
  return (
    <section className="surface-panel page-stack">
      <div>
        <span className="transfer-eyebrow">Trazabilidad</span>
        <h3>Actividad reciente</h3>
      </div>
      <div className="transfer-history">
        {operations.slice(0, 5).map((operation) => (
          <article key={operation.id} className="transfer-history-row">
            <span className="transfer-operation-mark">Salida</span>
            <div>
              <strong>{operation.headline}</strong>
              <p>{operation.fileName}</p>
            </div>
            <div className="transfer-history-side">
              <strong>{formatNumber(operation.totalRecords)}</strong>
              <span>{formatDate(operation.completedAt)}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function DataTransferPanel({ exportScope }: DataTransferPanelProps) {
  const queryClient = useQueryClient();
  const [exportResult, setExportResult] = useState<DataTransferExportPayload>();
  const [actionError, setActionError] = useState("");

  const downloadTarget = useQuery({
    queryKey: ["download-target"],
    queryFn: () => fetchJson<DownloadTargetPayload>("/api/downloads/target"),
    staleTime: 300_000,
    gcTime: 1_800_000,
    refetchOnWindowFocus: false
  });
  const history = useQuery({
    queryKey: ["data-transfer-history"],
    queryFn: () =>
      fetchJson<DataTransferHistoryPayload>("/api/data-transfer/history"),
    staleTime: 60_000,
    gcTime: 300_000,
    refetchOnWindowFocus: false
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      postJson<DataTransferExportPayload>("/api/data-transfer/export", {
        country: exportScope.country,
        sourceIds: exportScope.sourceIds,
        scopeMode: exportScope.scopeMode
      }),
    onSuccess: (payload) => {
      setExportResult(payload);
      setActionError("");
      void queryClient.invalidateQueries({ queryKey: ["data-transfer-history"] });
    },
    onError: (error) => {
      setExportResult(undefined);
      setActionError(
        error instanceof Error ? error.message : "No se ha podido crear el traslado."
      );
    }
  });

  const targetDir = downloadTarget.data?.directory || "Descargas de Informes";
  const exportScopeLabel = [
    exportScope.country || "sin país",
    exportScope.scopeMode === "country" ? "vista agregada" : "origen individual",
    exportScope.sourceLabels.join(" · ")
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <section className="page-stack">
      <section className="surface-panel transfer-hero">
        <div className="transfer-hero-copy">
          <span className="transfer-eyebrow">Salida segura</span>
          <h2>La vista activa, lista para viajar</h2>
          <p>
            Incluye la proyección inmutable de la vista activa y la presentación exacta
            generada por escritorio; sin duplicar datos fuente.
          </p>
        </div>
        <div className="transfer-route" aria-label="Ruta de exportación">
          <span className="transfer-route-step transfer-route-step-active">1</span>
          <i />
          <span className="transfer-route-step">2</span>
          <i />
          <span className="transfer-route-step">✓</span>
        </div>
      </section>

      <section className="surface-panel page-stack">
        <div className="transfer-action-head">
          <div>
            <h3>Crear traslado de la vista activa</h3>
            <p className="inline-caption">
              Alcance: <strong>{exportScopeLabel}</strong>. Se guardará en{" "}
              <strong>{targetDir}</strong>.
            </p>
          </div>
          <button
            type="button"
            className="action-button transfer-primary-action"
            disabled={exportMutation.isPending || !exportScope.country}
            onClick={() => exportMutation.mutate()}
          >
            {exportMutation.isPending ? "Preparando traslado…" : "Exportar vista activa"}
          </button>
        </div>
        {exportResult ? <DatasetExportStats result={exportResult} /> : null}
        {exportResult ? (
          <div className="ingest-action-row">
            <button
              type="button"
              className="secondary-button"
              onClick={() => {
                void postJson("/api/system/reveal-path", {
                  path: exportResult.savedPath
                });
              }}
            >
              Mostrar en Descargas de Informes
            </button>
          </div>
        ) : null}
      </section>

      {actionError ? (
        <section className="inline-notice inline-notice-error" role="alert">
          <strong>No se ha podido completar la operación</strong>
          <p className="inline-caption">{actionError}</p>
        </section>
      ) : null}

      <TransferHistory history={history.data} />
    </section>
  );
}
