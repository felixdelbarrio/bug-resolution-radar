import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchJson,
  postJson,
  type DataTransferExportPayload,
  type DataTransferHistoryPayload,
  type DataTransferImportPayload,
  type DataTransferMergeStat,
  type DataTransferPackagesPayload,
  type DataTransferValidationPayload,
  type DownloadTargetPayload
} from "../lib/api";
import { cn } from "../lib/cn";

type DataTransferPanelProps = {
  mode: "export" | "import";
  onDataImported: () => Promise<void>;
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat("es-ES").format(Math.max(0, Number(value || 0)));
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
  return new Intl.DateTimeFormat("es-ES", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parsed);
}

function DatasetExportStats({ result }: { result: DataTransferExportPayload }) {
  return (
    <section className="transfer-result transfer-result-success" aria-live="polite">
      <div className="transfer-result-head">
        <div>
          <span className="transfer-eyebrow">Respaldo listo</span>
          <h3>{result.summary}</h3>
          <p className="inline-caption">
            {result.fileName} · {formatFileSize(result.fileSize)}
          </p>
        </div>
        <div className="transfer-total-orb">
          <strong>{formatNumber(result.totalRecords)}</strong>
          <span>registros protegidos</span>
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

function MergeStats({
  stats,
  preview
}: {
  stats: DataTransferMergeStat[];
  preview: boolean;
}) {
  return (
    <div className="transfer-merge-table" role="table" aria-label="Balance de importación">
      <div className="transfer-merge-row transfer-merge-head" role="row">
        <span>Ámbito</span>
        <span>Altas</span>
        <span>Actualizaciones</span>
        <span>Sin cambios</span>
        <span>{preview ? "Quedarán" : "Total final"}</span>
      </div>
      {stats.map((stat) => (
        <div className="transfer-merge-row" role="row" key={stat.key}>
          <strong>{stat.label}</strong>
          <span className="transfer-positive">+{formatNumber(stat.newCount)}</span>
          <span>{formatNumber(stat.updatedCount)}</span>
          <span>{formatNumber(stat.unchangedCount)}</span>
          <strong>{formatNumber(stat.finalCount)}</strong>
        </div>
      ))}
    </div>
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
            <span
              className={cn(
                "transfer-operation-mark",
                operation.operation === "import" && "transfer-operation-import"
              )}
            >
              {operation.operation === "import" ? "Entrada" : "Salida"}
            </span>
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

export function DataTransferPanel({
  mode,
  onDataImported
}: DataTransferPanelProps) {
  const queryClient = useQueryClient();
  const [selectedFile, setSelectedFile] = useState("");
  const [exportResult, setExportResult] = useState<DataTransferExportPayload>();
  const [validation, setValidation] = useState<DataTransferValidationPayload>();
  const [importResult, setImportResult] = useState<DataTransferImportPayload>();
  const [actionError, setActionError] = useState("");

  const downloadTarget = useQuery({
    queryKey: ["download-target"],
    queryFn: () => fetchJson<DownloadTargetPayload>("/api/downloads/target")
  });
  const packages = useQuery({
    queryKey: ["data-transfer-packages"],
    queryFn: () =>
      fetchJson<DataTransferPackagesPayload>("/api/data-transfer/packages"),
    enabled: mode === "import"
  });
  const history = useQuery({
    queryKey: ["data-transfer-history"],
    queryFn: () =>
      fetchJson<DataTransferHistoryPayload>("/api/data-transfer/history")
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      postJson<DataTransferExportPayload>("/api/data-transfer/export", {}),
    onSuccess: (payload) => {
      setExportResult(payload);
      setActionError("");
      void queryClient.invalidateQueries({ queryKey: ["data-transfer-packages"] });
      void queryClient.invalidateQueries({ queryKey: ["data-transfer-history"] });
    },
    onError: (error) => {
      setExportResult(undefined);
      setActionError(
        error instanceof Error ? error.message : "No se ha podido crear el respaldo."
      );
    }
  });

  const validationMutation = useMutation({
    mutationFn: (fileName: string) =>
      postJson<DataTransferValidationPayload>("/api/data-transfer/validate", {
        fileName
      }),
    onSuccess: (payload) => {
      setValidation(payload);
      setImportResult(undefined);
      setActionError("");
    },
    onError: (error) => {
      setValidation(undefined);
      setActionError(
        error instanceof Error ? error.message : "No se ha podido revisar el respaldo."
      );
    }
  });

  const importMutation = useMutation({
    mutationFn: (fileName: string) =>
      postJson<DataTransferImportPayload>("/api/data-transfer/import", {
        fileName
      }),
    onSuccess: async (payload) => {
      setImportResult(payload);
      setValidation(undefined);
      setActionError("");
      await onDataImported();
      await queryClient.invalidateQueries({ queryKey: ["data-transfer-history"] });
    },
    onError: (error) => {
      setActionError(
        error instanceof Error ? error.message : "No se ha podido completar la importación."
      );
    }
  });

  function handleFileSelection(fileName: string) {
    setSelectedFile(fileName);
    setValidation(undefined);
    setImportResult(undefined);
    setActionError("");
    if (fileName) validationMutation.mutate(fileName);
  }

  const targetDir =
    downloadTarget.data?.directory || packages.data?.directory || "Descargas de Informes";

  return (
    <section className="page-stack">
      <section className="surface-panel transfer-hero">
        <div className="transfer-hero-copy">
          <span className="transfer-eyebrow">
            {mode === "export" ? "Salida segura" : "Entrada controlada"}
          </span>
          <h2>
            {mode === "export"
              ? "Todo el radar, listo para viajar"
              : "Trae un respaldo sin perder lo que ya existe"}
          </h2>
          <p>
            {mode === "export"
              ? "Agrupa incidencias, histórico Helix, anotaciones y aprendizaje en un único respaldo verificado."
              : "Primero comprobamos el fichero completo. Después sumamos lo nuevo y actualizamos solo lo que corresponda."}
          </p>
        </div>
        <div className="transfer-route" aria-label="Ruta del proceso">
          <span className="transfer-route-step transfer-route-step-active">1</span>
          <i />
          <span className="transfer-route-step">2</span>
          <i />
          <span className="transfer-route-step">✓</span>
        </div>
      </section>

      {mode === "export" ? (
        <section className="surface-panel page-stack">
          <div className="transfer-action-head">
            <div>
              <h3>Crear respaldo completo</h3>
              <p className="inline-caption">
                Se guardará en <strong>{targetDir}</strong>. No incluye credenciales ni
                modifica la configuración del equipo.
              </p>
            </div>
            <button
              type="button"
              className="action-button transfer-primary-action"
              disabled={exportMutation.isPending}
              onClick={() => exportMutation.mutate()}
            >
              {exportMutation.isPending ? "Preparando respaldo…" : "Exportar todos los datos"}
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
      ) : (
        <section className="surface-panel page-stack">
          <div className="transfer-picker-head">
            <div>
              <h3>Elegir respaldo</h3>
              <p className="inline-caption">
                Ficheros disponibles en <strong>{targetDir}</strong>
              </p>
            </div>
            <button
              type="button"
              className="secondary-button"
              disabled={packages.isFetching}
              onClick={() =>
                void queryClient.invalidateQueries({
                  queryKey: ["data-transfer-packages"]
                })
              }
            >
              {packages.isFetching ? "Actualizando…" : "Actualizar lista"}
            </button>
          </div>

          <label className="transfer-file-picker">
            <span>Fichero que quieres importar</span>
            <select
              value={selectedFile}
              disabled={packages.isLoading || validationMutation.isPending}
              onChange={(event) => handleFileSelection(event.target.value)}
            >
              <option value="">Selecciona un respaldo…</option>
              {(packages.data?.packages ?? []).map((item) => (
                <option value={item.fileName} key={item.fileName}>
                  {item.fileName} · {formatFileSize(item.fileSize)} ·{" "}
                  {formatDate(item.modifiedAt)}
                </option>
              ))}
            </select>
          </label>

          {!packages.isLoading && (packages.data?.packages.length ?? 0) === 0 ? (
            <div className="inline-notice">
              <strong>No hay respaldos disponibles</strong>
              <p className="inline-caption">
                Copia un fichero .brr en Descargas de Informes o crea uno desde Exportar.
              </p>
            </div>
          ) : null}

          {validationMutation.isPending ? (
            <div className="transfer-validation-running" aria-live="polite">
              <span className="ingest-pulse-dot" />
              <div>
                <strong>Comprobando el respaldo de principio a fin</strong>
                <p>Inventario, integridad, contenido y compatibilidad.</p>
              </div>
            </div>
          ) : null}

          {validation && !validation.valid ? (
            <section className="transfer-result transfer-result-error" role="alert">
              <span className="transfer-eyebrow">Importación bloqueada</span>
              <h3>{validation.summary}</h3>
              <ul className="signal-list">
                {(validation.errors ?? []).map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
              <p className="inline-caption">No se ha modificado ningún dato del radar.</p>
            </section>
          ) : null}

          {validation?.valid ? (
            <section className="transfer-result transfer-result-success" aria-live="polite">
              <div className="transfer-validation-badge">
                <span>✓</span>
                <div>
                  <strong>Verificación superada</strong>
                  <p>{validation.summary}</p>
                </div>
              </div>
              <div className="transfer-impact-strip">
                <article>
                  <strong>+{formatNumber(validation.totalNewRecords)}</strong>
                  <span>altas previstas</span>
                </article>
                <article>
                  <strong>{formatNumber(validation.totalUpdatedRecords)}</strong>
                  <span>se actualizarán</span>
                </article>
                <article>
                  <strong>{formatNumber(validation.totalUnchangedRecords)}</strong>
                  <span>ya coinciden</span>
                </article>
              </div>
              <MergeStats stats={validation.stats} preview />
              <div className="transfer-import-commit">
                <div>
                  <strong>Importación incremental</strong>
                  <p>
                    Lo existente se conserva; las coincidencias se actualizan con el
                    respaldo validado.
                  </p>
                </div>
                <button
                  type="button"
                  className="action-button transfer-primary-action"
                  disabled={importMutation.isPending}
                  onClick={() => importMutation.mutate(validation.fileName)}
                >
                  {importMutation.isPending
                    ? "Incorporando datos…"
                    : "Importar este respaldo"}
                </button>
              </div>
            </section>
          ) : null}

          {importResult ? (
            <section className="transfer-result transfer-complete page-stack" aria-live="polite">
              <div className="transfer-complete-head">
                <span className="transfer-complete-mark">✓</span>
                <div>
                  <span className="transfer-eyebrow">Proceso completado</span>
                  <h3>{importResult.summary}</h3>
                  <p className="inline-caption">
                    El radar ya refleja un total de{" "}
                    {formatNumber(importResult.totalFinalRecords)} registros de negocio.
                  </p>
                </div>
              </div>
              <MergeStats stats={importResult.stats} preview={false} />
            </section>
          ) : null}
        </section>
      )}

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
