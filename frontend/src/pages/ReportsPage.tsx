import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useLocation, useOutletContext } from "react-router-dom";
import { postJson, type SavedReportPayload } from "../lib/api";
import type { ShellContextValue } from "../components/AppShell";

function classNames(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(" ");
}

export function ReportsPage() {
  const { workspace, dashboardState } = useOutletContext<ShellContextValue>();
  const location = useLocation();
  const [feedback, setFeedback] = useState<{
    kind: "success" | "error";
    message: string;
    savedPath?: string;
  } | null>(null);
  const reportMode = new URLSearchParams(location.search).get("reportMode") ?? "executive";
  const periodSourceIds = workspace?.countryRollupSourceIds ?? [];

  const executive = useMutation({
    mutationFn: () =>
      postJson<SavedReportPayload>(
        "/api/reports/executive/save",
        {
          country: dashboardState.params.country,
          sourceId: dashboardState.params.sourceId,
          scopeMode: dashboardState.params.scopeMode,
          status: dashboardState.params.status,
          priority: dashboardState.params.priority,
          assignee: dashboardState.params.assignee,
          quincenalScope: dashboardState.params.quincenalScope
        }
      ),
    onSuccess: (payload) =>
      setFeedback({
        kind: "success",
        message: `Informe ejecutivo guardado en disco: ${payload.fileName}`,
        savedPath: payload.savedPath
      }),
    onError: (error) =>
      setFeedback({
        kind: "error",
        message:
          error instanceof Error ? error.message : "No se pudo generar el informe ejecutivo."
      })
  });

  const period = useMutation({
    mutationFn: () =>
      postJson<SavedReportPayload>(
        "/api/reports/period/save",
        {
          country: dashboardState.params.country,
          sourceIds: periodSourceIds,
          scopeMode: dashboardState.params.scopeMode,
          status: dashboardState.params.status,
          priority: dashboardState.params.priority,
          assignee: dashboardState.params.assignee,
          quincenalScope: dashboardState.params.quincenalScope,
          functionalityStatusFilters: dashboardState.params.insightsStatus,
          functionalityPriorityFilters: dashboardState.params.insightsPriority,
          functionalityFilters: dashboardState.params.insightsFunctionality,
          appliedFilterSummary: [
            `status=${dashboardState.params.status.join("|") || "all"}`,
            `priority=${dashboardState.params.priority.join("|") || "all"}`,
            `assignee=${dashboardState.params.assignee.join("|") || "all"}`,
            `quincena=${dashboardState.params.quincenalScope}`,
            `insights_status=${dashboardState.params.insightsStatus.join("|") || "all"}`,
            `insights_priority=${dashboardState.params.insightsPriority.join("|") || "all"}`,
            `insights_functionality=${dashboardState.params.insightsFunctionality.join("|") || "all"}`
          ].join(" · ")
        }
      ),
    onSuccess: (payload) =>
      setFeedback({
        kind: "success",
        message: `Seguimiento del periodo guardado en disco: ${payload.fileName}`,
        savedPath: payload.savedPath
      }),
    onError: (error) =>
      setFeedback({
        kind: "error",
        message:
          error instanceof Error ? error.message : "No se pudo generar el seguimiento del periodo."
      })
  });

  const revealPath = useMutation({
    mutationFn: (savedPath: string) => postJson<{ revealed: boolean; path: string }>("/api/system/reveal-path", { path: savedPath }),
    onError: (error) =>
      setFeedback((current) =>
        current
          ? {
              ...current,
              kind: "error",
              message:
                error instanceof Error
                  ? error.message
                  : "No se pudo abrir la carpeta del informe."
            }
          : null
      )
  });

  return (
    <section className="page-stack">
      <section className="surface-panel report-intro">
        <div>
          <p className="section-kicker">Reports</p>
          <h3>PPTs servidos desde backend, no desde el navegador</h3>
          <p className="minor-copy">
            La generación reutiliza los mismos cálculos del radar. Solo al pulsar se produce la
            escritura en el directorio configurado si el sistema lo exige.
          </p>
        </div>
      </section>

      <div className="report-grid">
        <article
          className={classNames(
            "surface-panel",
            reportMode === "executive" && "surface-panel-emphasis"
          )}
        >
          <div className="panel-head">
            <div>
              <p className="section-kicker">Executive</p>
              <h3>Informe ejecutivo</h3>
            </div>
          </div>
          <p className="minor-copy">
            Alcance: {dashboardState.params.country || "sin país"} ·{" "}
            {dashboardState.params.sourceId || "sin origen"}
          </p>
          <button
            type="button"
            className="action-button"
            disabled={executive.isPending || !dashboardState.params.country || !dashboardState.params.sourceId}
            onClick={() => {
              setFeedback(null);
              executive.mutate();
            }}
          >
            {executive.isPending ? "Generando..." : "Generar ejecutivo"}
          </button>
        </article>

        {workspace?.hasCountryRollup ? (
          <article
            className={classNames(
              "surface-panel",
              reportMode === "period" && "surface-panel-emphasis"
            )}
          >
            <div className="panel-head">
              <div>
                <p className="section-kicker">Period</p>
                <h3>Seguimiento del periodo</h3>
              </div>
            </div>
            <p className="minor-copy">
              Alcance: {dashboardState.params.country || "sin país"} ·{" "}
              {periodSourceIds.length} orígenes agregados configurados
            </p>
            <button
              type="button"
              className="action-button"
              disabled={period.isPending || !dashboardState.params.country || periodSourceIds.length < 2}
              onClick={() => {
                setFeedback(null);
                period.mutate();
              }}
            >
              {period.isPending ? "Generando..." : "Generar seguimiento"}
            </button>
          </article>
        ) : null}
      </div>

      {feedback ? (
        <section className={classNames("inline-notice", feedback.kind === "error" && "inline-notice-error")}>
          <strong>{feedback.message}</strong>
          {feedback.savedPath ? <p className="inline-caption">{feedback.savedPath}</p> : null}
          {feedback.savedPath ? (
            <button
              type="button"
              className="secondary-button"
              disabled={revealPath.isPending}
              onClick={() => revealPath.mutate(feedback.savedPath ?? "")}
            >
              {revealPath.isPending ? "Abriendo..." : "Abrir carpeta"}
            </button>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
