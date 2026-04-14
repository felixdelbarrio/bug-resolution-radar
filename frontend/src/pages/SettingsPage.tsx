import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOutletContext } from "react-router-dom";
import type { ShellContextValue } from "../components/AppShell";
import {
  downloadSourcesExcel,
  fetchJson,
  importSourcesExcel,
  normalizeSettingsPayload,
  postJson,
  putJson,
  type CacheInventoryRow,
  type SettingsSourcesImportPayload,
  type SettingsPayload,
  type WorkspaceSource
} from "../lib/api";
import { cn } from "../lib/cn";

type SettingsTabId =
  | "preferences"
  | "jira"
  | "helix"
  | "rollups"
  | "cache"
  | "performance";

type SourceDraftRow = WorkspaceSource & {
  markedForDeletion?: boolean;
};

const settingsTabs: Array<{ id: SettingsTabId; label: string }> = [
  { id: "preferences", label: "Preferencias" },
  { id: "jira", label: "Jira" },
  { id: "helix", label: "Helix" },
  { id: "rollups", label: "Agregados" },
  { id: "cache", label: "Cache" },
  { id: "performance", label: "Performance" }
];

const trendChartCatalog = [
  ["timeseries", "Evolución (últimos 90 días)"],
  ["age_buckets", "Distribución antigüedad (abiertas)"],
  ["resolution_hist", "Días abiertas por prioridad"],
  ["open_priority_pie", "Issues abiertos por prioridad (pie)"],
  ["open_status_bar", "Issues por Estado (bar)"]
] as const;

function asText(value: string | number | undefined) {
  return String(value ?? "");
}

function asciiFold(value: string) {
  return value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
}

function slugToken(value: string) {
  const token = asciiFold(String(value || ""))
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return token || "default";
}

function buildSourceId(sourceType: string, country: string, alias: string) {
  return `${slugToken(sourceType)}:${slugToken(country)}:${slugToken(alias)}`;
}

function parseCsv(raw: string | number | undefined) {
  return String(raw ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeBool(value: string | number | undefined, fallback = false) {
  const token = String(value ?? "").trim().toLowerCase();
  if (!token) {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(token);
}

function normalizeCookieSource(value: string | number | undefined, fallback = "browser") {
  const token = String(value ?? "")
    .trim()
    .toLowerCase();
  if (["browser", "manual", "auto"].includes(token)) {
    return token;
  }
  return fallback;
}

function withSourceDrafts(rows: WorkspaceSource[]) {
  return rows.map((row) => ({ ...row, markedForDeletion: false }));
}

function emptyJiraRow(country: string): SourceDraftRow {
  return {
    source_id: buildSourceId("jira", country, ""),
    source_type: "jira",
    country,
    alias: "",
    jql: "",
    markedForDeletion: false
  };
}

function emptyHelixRow(country: string): SourceDraftRow {
  return {
    source_id: buildSourceId("helix", country, ""),
    source_type: "helix",
    country,
    alias: "",
    service_origin_buug: "BBVA México",
    service_origin_n1: "ENTERPRISE WEB",
    service_origin_n2: "",
    markedForDeletion: false
  };
}

function SourceTable({
  title,
  caption,
  rows,
  countries,
  isJira,
  onChange,
  onAddRow
}: {
  title: string;
  caption: string;
  rows: SourceDraftRow[];
  countries: string[];
  isJira: boolean;
  onChange: (rows: SourceDraftRow[]) => void;
  onAddRow: () => void;
}) {
  function updateRow(index: number, patch: Partial<SourceDraftRow>) {
    onChange(
      rows.map((row, rowIndex) => {
        if (rowIndex !== index) {
          return row;
        }
        const nextRow = { ...row, ...patch };
        return {
          ...nextRow,
          source_id: buildSourceId(nextRow.source_type, nextRow.country, nextRow.alias)
        };
      })
    );
  }

  return (
    <section className="surface-card page-stack">
      <div className="section-head">
        <div>
          <h3>{title}</h3>
          <p>{caption}</p>
        </div>
        <button type="button" className="secondary-button" onClick={onAddRow}>
          Añadir fila
        </button>
      </div>

      <div className="source-table-grid">
        <div className="source-table-head">
          <span>Eliminar</span>
          <span>País</span>
          <span>Alias</span>
          {isJira ? <span>JQL</span> : null}
          {!isJira ? <span>Servicio Origen BU/UG</span> : null}
          {!isJira ? <span>Servicio Origen N1</span> : null}
          {!isJira ? <span>Servicio Origen N2</span> : null}
        </div>
        {rows.map((row, index) => (
          <div className="source-table-row" key={`${row.source_id}-${index}`}>
            <label className="table-checkbox">
              <input
                type="checkbox"
                checked={Boolean(row.markedForDeletion)}
                onChange={(event) => updateRow(index, { markedForDeletion: event.target.checked })}
              />
              <span />
            </label>
            <select
              value={row.country}
              onChange={(event) => updateRow(index, { country: event.target.value })}
            >
              {countries.map((country) => (
                <option key={country} value={country}>
                  {country}
                </option>
              ))}
            </select>
            <input
              value={row.alias}
              onChange={(event) => updateRow(index, { alias: event.target.value })}
            />
            {isJira ? (
              <input
                value={row.jql ?? ""}
                onChange={(event) => updateRow(index, { jql: event.target.value })}
              />
            ) : null}
            {!isJira ? (
              <input
                value={row.service_origin_buug ?? ""}
                onChange={(event) =>
                  updateRow(index, { service_origin_buug: event.target.value })
                }
              />
            ) : null}
            {!isJira ? (
              <input
                value={row.service_origin_n1 ?? ""}
                onChange={(event) => updateRow(index, { service_origin_n1: event.target.value })}
              />
            ) : null}
            {!isJira ? (
              <input
                value={row.service_origin_n2 ?? ""}
                onChange={(event) => updateRow(index, { service_origin_n2: event.target.value })}
              />
            ) : null}
          </div>
        ))}
      </div>
      <p className="inline-caption">
        Las filas marcadas se eliminarán al guardar y se purgará la cache asociada a ese origen.
      </p>
    </section>
  );
}

function RollupSourceSelector({
  country,
  sources,
  selectedIds,
  onChange
}: {
  country: string;
  sources: WorkspaceSource[];
  selectedIds: string[];
  onChange: (nextIds: string[]) => void;
}) {
  const selectedLabels = sources
    .filter((source) => selectedIds.includes(source.source_id))
    .map((source) => `${source.alias} · ${String(source.source_type || "").toUpperCase()}`);
  const summary =
    selectedLabels.length === 0
      ? "Selecciona hasta 2 orígenes"
      : selectedLabels.length === 1
        ? selectedLabels[0]
        : `${selectedLabels.length} orígenes seleccionados`;

  return (
    <article className="rollup-country-card">
      <div>
        <strong>{country}</strong>
        <p>Selecciona hasta 2 orígenes por país.</p>
      </div>

      {sources.length === 0 ? (
        <span className="issue-list-empty">Sin orígenes disponibles.</span>
      ) : (
        <details className="filter-combo rollup-select">
          <summary className="filter-combo-summary">
            <span>{country}</span>
            <strong
              className={selectedLabels.length === 0 ? "filter-combo-summary-placeholder" : undefined}
            >
              {summary}
            </strong>
          </summary>
          <div className="filter-combo-menu rollup-select-menu">
            {sources.map((source) => {
              const checked = selectedIds.includes(source.source_id);
              const maxReached = !checked && selectedIds.length >= 2;
              return (
                <label
                  key={source.source_id}
                  className={cn(
                    "filter-check rollup-select-option",
                    checked && "rollup-select-option-active",
                    maxReached && "rollup-select-option-disabled"
                  )}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={maxReached}
                    onChange={() => {
                      const nextIds = checked
                        ? selectedIds.filter((item) => item !== source.source_id)
                        : [...selectedIds, source.source_id].slice(0, 2);
                      onChange(nextIds);
                    }}
                  />
                  <span className="filter-check-value">
                    {source.alias} · {String(source.source_type || "").toUpperCase()}
                  </span>
                </label>
              );
            })}
          </div>
        </details>
      )}
    </article>
  );
}

export function SettingsPage() {
  const { dashboardState } = useOutletContext<ShellContextValue>();
  const queryClient = useQueryClient();
  const activeTab = settingsTabs.some((tab) => tab.id === dashboardState.params.settingsTab)
    ? (dashboardState.params.settingsTab as SettingsTabId)
    : "preferences";

  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: async () =>
      normalizeSettingsPayload(await fetchJson<SettingsPayload>("/api/settings"))
  });
  const cache = useQuery({
    queryKey: ["cache-inventory"],
    queryFn: () => fetchJson<CacheInventoryRow[]>("/api/cache/inventory")
  });

  const [draft, setDraft] = useState<SettingsPayload | null>(null);
  const [savedPayload, setSavedPayload] = useState<SettingsPayload | null>(null);
  const [jiraRows, setJiraRows] = useState<SourceDraftRow[]>([]);
  const [helixRows, setHelixRows] = useState<SourceDraftRow[]>([]);
  const [flashMessage, setFlashMessage] = useState<string>("");
  const [jiraExcelBusy, setJiraExcelBusy] = useState<boolean>(false);
  const [jiraExcelInputKey, setJiraExcelInputKey] = useState<number>(0);
  const [helixExcelBusy, setHelixExcelBusy] = useState<boolean>(false);
  const [helixExcelInputKey, setHelixExcelInputKey] = useState<number>(0);

  useEffect(() => {
    if (!settings.data) {
      return;
    }
    const normalized = normalizeSettingsPayload(settings.data);
    setDraft(normalized);
    setSavedPayload(normalized);
    setJiraRows(withSourceDrafts(normalized.jiraSources));
    setHelixRows(withSourceDrafts(normalized.helixSources));
  }, [settings.data]);

  const saveSettings = useMutation({
    mutationFn: (payload: SettingsPayload) => putJson<SettingsPayload>("/api/settings", payload)
  });
  const restoreSettings = useMutation({
    mutationFn: () =>
      postJson<{ restoredFrom: string; settings: SettingsPayload }>("/api/settings/restore-from-example", {})
  });
  const resetCache = useMutation({
    mutationFn: (cacheId: string) => postJson("/api/cache/reset", { cacheId })
  });

  const countries = draft?.supportedCountries ?? [];

  const configuredSourcesByCountry = useMemo(() => {
    const out = new Map<string, WorkspaceSource[]>();
    const activeSources = Object.entries(savedPayload?.rollupEligibleSourcesByCountry ?? {}).flatMap(
      ([country, rows]) =>
        (rows ?? []).map((row) => ({
          ...row,
          country: row.country || country
        }))
    );
    activeSources.forEach((row) => {
      const existing = out.get(row.country) ?? [];
      if (existing.some((source) => source.source_id === row.source_id)) {
        return;
      }
      out.set(row.country, [...existing, row]);
    });
    return out;
  }, [savedPayload?.rollupEligibleSourcesByCountry]);

  if (!draft || !savedPayload) {
    return (
      <section className="hero-panel">
        <h3>Cargando configuración...</h3>
      </section>
    );
  }

  const values = draft.values;
  const savedFavorites = parseCsv(
    asText(values.DASHBOARD_SUMMARY_CHARTS || values.TREND_SELECTED_CHARTS)
  );
  const themeValue = asText(values.THEME || "light").toLowerCase() === "dark" ? "dark" : "light";
  const chartIds = trendChartCatalog.map(([id]) => id);
  const favorites = [
    savedFavorites[0] ?? chartIds[0],
    savedFavorites[1] ?? chartIds[1] ?? chartIds[0],
    savedFavorites[2] ?? chartIds[2] ?? chartIds[0]
  ];
  const analysisLookbackOptions = Array.from(
    new Set([1, 3, 6, 12, 18, 24, Number.parseInt(asText(values.ANALYSIS_LOOKBACK_MONTHS), 10) || 12])
  ).sort((left, right) => left - right);

  function setValue(key: string, next: string | number) {
    setDraft({
      ...draft,
      values: {
        ...draft.values,
        [key]: next
      }
    });
  }

  function syncFromSaved(next: SettingsPayload, flash: string) {
    const normalized = normalizeSettingsPayload(next);
    setSavedPayload(normalized);
    setDraft(normalized);
    setJiraRows(withSourceDrafts(normalized.jiraSources));
    setHelixRows(withSourceDrafts(normalized.helixSources));
    setFlashMessage(flash);
    [
      ["settings"],
      ["settings-ingest"],
      ["bootstrap-shell"],
      ["dashboard-overview"],
      ["dashboard-trend-detail"],
      ["dashboard-intelligence"],
      ["dashboard-issues"],
      ["dashboard-kanban"],
      ["dashboard-note-keys"],
      ["cache-inventory"]
    ].forEach((queryKey) => {
      void queryClient.invalidateQueries({ queryKey });
    });
  }

  async function purgeDeletedSources(sourceIds: string[]) {
    const uniqueSourceIds = Array.from(
      new Set(sourceIds.map((sourceId) => sourceId.trim()).filter(Boolean))
    );
    await Promise.all(
      uniqueSourceIds.map((sourceId) =>
        postJson("/api/cache/purge-source", {
          sourceId
        })
      )
    );
  }

  async function savePreferences() {
    const summaryCsv = favorites.join(",");
    const payload: SettingsPayload = {
      ...savedPayload,
      values: {
        ...savedPayload.values,
        THEME: themeValue,
        ANALYSIS_LOOKBACK_MONTHS: Number.parseInt(asText(values.ANALYSIS_LOOKBACK_MONTHS), 10) || 12,
        QUINCENA_LAST_FINISHED_ONLY: normalizeBool(values.QUINCENA_LAST_FINISHED_ONLY)
          ? "true"
          : "false",
        OPEN_ISSUES_FOCUS_MODE: asText(values.OPEN_ISSUES_FOCUS_MODE || "criticidad_alta"),
        REPORT_PPT_DOWNLOAD_DIR: asText(values.REPORT_PPT_DOWNLOAD_DIR),
        PERIOD_PPT_TEMPLATE_PATH: asText(values.PERIOD_PPT_TEMPLATE_PATH),
        DASHBOARD_SUMMARY_CHARTS: summaryCsv,
        TREND_SELECTED_CHARTS: summaryCsv
      }
    };
    const saved = await saveSettings.mutateAsync(payload);
    syncFromSaved(saved, "Preferencias guardadas.");
  }

  async function saveJira() {
    const deletedSourceIds = jiraRows
      .filter((row) => row.markedForDeletion)
      .map((row) => row.source_id);
    const payload: SettingsPayload = {
      ...savedPayload,
      values: {
        ...savedPayload.values,
        JIRA_BASE_URL: asText(values.JIRA_BASE_URL),
        JIRA_BROWSER: asText(values.JIRA_BROWSER || "chrome"),
        JIRA_COOKIE_SOURCE: normalizeCookieSource(values.JIRA_COOKIE_SOURCE, "browser"),
        JIRA_COOKIE_HEADER: asText(values.JIRA_COOKIE_HEADER)
      },
      jiraSources: jiraRows.filter((row) => !row.markedForDeletion),
    };
    const saved = await saveSettings.mutateAsync(payload);
    await purgeDeletedSources(deletedSourceIds);
    syncFromSaved(
      saved,
      deletedSourceIds.length > 0
        ? "Configuración Jira y saneado de fuentes aplicados."
        : "Configuración Jira guardada."
    );
  }

  async function saveHelix() {
    const deletedSourceIds = helixRows
      .filter((row) => row.markedForDeletion)
      .map((row) => row.source_id);
    const payload: SettingsPayload = {
      ...savedPayload,
      values: {
        ...savedPayload.values,
        HELIX_PROXY: asText(values.HELIX_PROXY),
        HELIX_BROWSER: asText(values.HELIX_BROWSER || "chrome"),
        HELIX_SSL_VERIFY: normalizeBool(values.HELIX_SSL_VERIFY, true) ? "true" : "false",
        HELIX_DASHBOARD_URL: asText(values.HELIX_DASHBOARD_URL),
        HELIX_COOKIE_SOURCE: normalizeCookieSource(values.HELIX_COOKIE_SOURCE, "browser"),
        HELIX_COOKIE_HEADER: asText(values.HELIX_COOKIE_HEADER)
      },
      helixSources: helixRows.filter((row) => !row.markedForDeletion)
    };
    const saved = await saveSettings.mutateAsync(payload);
    await purgeDeletedSources(deletedSourceIds);
    syncFromSaved(
      saved,
      deletedSourceIds.length > 0
        ? "Configuración Helix y saneado de fuentes aplicados."
        : "Configuración Helix guardada."
    );
  }

  async function downloadJiraSourcesExcel() {
    await downloadSourcesExcel("jira", "fuentes_jira.xlsx");
  }

  async function importJiraSourcesExcel(file: File | null) {
    if (!file) {
      return;
    }
    setJiraExcelBusy(true);
    try {
      const imported: SettingsSourcesImportPayload = await importSourcesExcel("jira", file);
      setJiraRows(withSourceDrafts(imported.rows));
      if (imported.settingsValues) {
        setDraft((current) =>
          current
            ? {
                ...current,
                values: {
                  ...current.values,
                  ...imported.settingsValues
                }
              }
            : current
        );
      }
      const warnings = imported.warnings.length;
      setFlashMessage(
        `Excel Jira cargado: ${imported.importedRows} filas importadas, ` +
          `${imported.skippedRows} omitidas${warnings > 0 ? `, ${warnings} advertencias` : ""}. ` +
          "Revisa y guarda la configuración."
      );
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error ?? "Error desconocido");
      setFlashMessage(`No se pudo cargar el Excel Jira: ${detail}`);
    } finally {
      setJiraExcelBusy(false);
      setJiraExcelInputKey((prev) => prev + 1);
    }
  }

  async function downloadHelixSourcesExcel() {
    await downloadSourcesExcel("helix", "fuentes_helix.xlsx");
  }

  async function importHelixSourcesExcel(file: File | null) {
    if (!file) {
      return;
    }
    setHelixExcelBusy(true);
    try {
      const imported: SettingsSourcesImportPayload = await importSourcesExcel("helix", file);
      setHelixRows(withSourceDrafts(imported.rows));
      if (imported.settingsValues) {
        setDraft((current) =>
          current
            ? {
                ...current,
                values: {
                  ...current.values,
                  ...imported.settingsValues
                }
              }
            : current
        );
      }
      const warnings = imported.warnings.length;
      setFlashMessage(
        `Excel Helix cargado: ${imported.importedRows} filas importadas, ` +
          `${imported.skippedRows} omitidas${warnings > 0 ? `, ${warnings} advertencias` : ""}. ` +
          "Revisa y guarda la configuración."
      );
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error ?? "Error desconocido");
      setFlashMessage(`No se pudo cargar el Excel Helix: ${detail}`);
    } finally {
      setHelixExcelBusy(false);
      setHelixExcelInputKey((prev) => prev + 1);
    }
  }

  async function saveRollups() {
    const sanitizedRollups = Object.fromEntries(
      Object.entries(draft.countryRollupSources).flatMap(([country, sourceIds]) => {
        const allowedSourceIds = new Set(
          (configuredSourcesByCountry.get(country) ?? []).map((source) => source.source_id)
        );
        const selected = sourceIds.filter((sourceId) => allowedSourceIds.has(sourceId)).slice(0, 2);
        return selected.length > 0 ? [[country, selected]] : [];
      })
    );
    const saved = await saveSettings.mutateAsync({
      ...savedPayload,
      countryRollupSources: sanitizedRollups
    });
    syncFromSaved(saved, "Agregados guardados.");
  }

  async function handleRestore() {
    const restored = await restoreSettings.mutateAsync();
    syncFromSaved(restored.settings, "Configuración restaurada desde la plantilla base.");
  }

  function setFavorite(index: number, nextValue: string) {
    const nextFavorites = [...favorites];
    nextFavorites[index] = nextValue;
    setValue("DASHBOARD_SUMMARY_CHARTS", nextFavorites.join(","));
    setValue("TREND_SELECTED_CHARTS", nextFavorites.join(","));
  }

  return (
    <section className="page-stack">
      <section className="surface-panel settings-tabs-shell">
        <div className="panel-head">
          <div>
            <p className="section-kicker">Configuración</p>
            <h3>Distribución funcional alineada con Streamlit</h3>
          </div>
        </div>
        <nav className="subtab-strip" aria-label="Navegación de configuración">
          {settingsTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={cn("subtab-button", activeTab === tab.id && "subtab-button-active")}
              onClick={() => dashboardState.update({ settingsTab: tab.id })}
            >
              {tab.label}
            </button>
          ))}
        </nav>
        {flashMessage ? <p className="inline-caption">{flashMessage}</p> : null}
      </section>

      {activeTab === "preferences" ? (
        <section className="page-stack">
          <section className="settings-grid-stack">
            <article className="surface-card page-stack">
              <h3>Ambiente de trabajo</h3>
              <div className="toggle-group">
                <button
                  type="button"
                  className={cn(
                    "toggle-pill",
                    themeValue === "light" && "toggle-pill-active"
                  )}
                  onClick={() => setValue("THEME", "light")}
                >
                  Claro
                </button>
                <button
                  type="button"
                  className={cn(
                    "toggle-pill",
                    themeValue === "dark" && "toggle-pill-active"
                  )}
                  onClick={() => setValue("THEME", "dark")}
                >
                  Oscuro
                </button>
              </div>
            </article>

            <article className="surface-card page-stack">
              <h3>Profundidad del análisis</h3>
              <label className="field">
                <span>Meses analizados en backlog</span>
                <select
                  value={asText(values.ANALYSIS_LOOKBACK_MONTHS || 12)}
                  onChange={(event) =>
                    setValue(
                      "ANALYSIS_LOOKBACK_MONTHS",
                      Number.parseInt(event.target.value, 10) || 12
                    )
                  }
                >
                  {analysisLookbackOptions.map((option) => (
                    <option key={option} value={option}>
                      {option} {option === 1 ? "mes" : "meses"}
                    </option>
                  ))}
                </select>
              </label>
            </article>

            <article className="surface-card page-stack">
              <h3>Alcance quincenal</h3>
              <label className="checkbox-field checkbox-field-panel">
                <input
                  type="checkbox"
                  checked={normalizeBool(values.QUINCENA_LAST_FINISHED_ONLY)}
                  onChange={(event) =>
                    setValue("QUINCENA_LAST_FINISHED_ONLY", event.target.checked ? "true" : "false")
                  }
                />
                <span>Usar última quincena finalizada</span>
              </label>
            </article>

            <article className="surface-card page-stack">
              <h3>Criterio de foco en abiertas</h3>
              <div className="radio-stack">
                <label className="radio-card">
                  <input
                    type="radio"
                    checked={asText(values.OPEN_ISSUES_FOCUS_MODE || "criticidad_alta") === "criticidad_alta"}
                    onChange={() => setValue("OPEN_ISSUES_FOCUS_MODE", "criticidad_alta")}
                  />
                  <span>Criticidad alta (Impedimento / High / Highest)</span>
                </label>
                <label className="radio-card">
                  <input
                    type="radio"
                    checked={asText(values.OPEN_ISSUES_FOCUS_MODE || "criticidad_alta") === "maestras"}
                    onChange={() => setValue("OPEN_ISSUES_FOCUS_MODE", "maestras")}
                  />
                  <span>Incidencias maestras</span>
                </label>
              </div>
            </article>
          </section>

          <section className="surface-card page-stack">
            <h3>Descargas del informe PPT</h3>
            <div className="settings-form-grid">
              <label className="field">
                <span>Carpeta de guardado</span>
                <input
                  value={asText(values.REPORT_PPT_DOWNLOAD_DIR)}
                  onChange={(event) => setValue("REPORT_PPT_DOWNLOAD_DIR", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Plantilla informe seguimiento</span>
                <input
                  value={asText(values.PERIOD_PPT_TEMPLATE_PATH)}
                  onChange={(event) => setValue("PERIOD_PPT_TEMPLATE_PATH", event.target.value)}
                />
              </label>
            </div>
          </section>

          <section className="surface-card page-stack">
            <h3>Define los 3 gráficos favoritos</h3>
            <div className="settings-form-grid favorites-grid">
              {[0, 1, 2].map((index) => (
                <label className="field" key={index}>
                  <span>Favorito {index + 1}</span>
                  <select
                    value={favorites[index]}
                    onChange={(event) => setFavorite(index, event.target.value)}
                  >
                    {trendChartCatalog.map(([chartId, label]) => (
                      <option key={chartId} value={chartId}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </section>

          <section className="surface-card page-stack">
            <div className="settings-actions-row">
              <button
                type="button"
                className="action-button"
                disabled={saveSettings.isPending}
                onClick={() => void savePreferences()}
              >
                {saveSettings.isPending ? "Guardando..." : "Guardar configuración"}
              </button>
              <button
                type="button"
                className="secondary-button"
                disabled={restoreSettings.isPending}
                onClick={() => void handleRestore()}
              >
                {restoreSettings.isPending ? "Restaurando..." : "Restaurar ejemplo"}
              </button>
            </div>
          </section>
        </section>
      ) : null}

      {activeTab === "jira" ? (
        <section className="page-stack">
          <section className="settings-grid-stack">
            <article className="surface-card page-stack">
              <h3>Jira global</h3>
              <div className="settings-form-grid">
                <label className="field">
                  <span>Jira Base URL (global)</span>
                  <input
                    value={asText(values.JIRA_BASE_URL)}
                    onChange={(event) => setValue("JIRA_BASE_URL", event.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Navegador Jira</span>
                  <select
                    value={asText(values.JIRA_BROWSER || "chrome")}
                    onChange={(event) => setValue("JIRA_BROWSER", event.target.value)}
                  >
                    <option value="chrome">Chrome</option>
                    <option value="edge">Edge</option>
                  </select>
                </label>
                <label className="field">
                  <span>Modo sesión Jira</span>
                  <select
                    value={normalizeCookieSource(values.JIRA_COOKIE_SOURCE, "browser")}
                    onChange={(event) => setValue("JIRA_COOKIE_SOURCE", event.target.value)}
                  >
                    <option value="browser">Browser (lectura local de sesión)</option>
                    <option value="auto">Auto (manual si existe; si no browser)</option>
                    <option value="manual">Manual (sin leer cookies del navegador)</option>
                  </select>
                </label>
                {normalizeCookieSource(values.JIRA_COOKIE_SOURCE, "browser") !== "browser" ? (
                  <label className="field field-wide">
                    <span>Cookie Jira manual (opcional)</span>
                    <input
                      type="password"
                      value={asText(values.JIRA_COOKIE_HEADER)}
                      onChange={(event) => setValue("JIRA_COOKIE_HEADER", event.target.value)}
                    />
                  </label>
                ) : null}
              </div>
            </article>
          </section>

          <SourceTable
            title="Fuentes Jira por país"
            caption="Alias y JQL son obligatorios."
            rows={jiraRows}
            countries={countries}
            isJira
            onChange={setJiraRows}
            onAddRow={() => setJiraRows([...jiraRows, emptyJiraRow(countries[0] ?? "")])}
          />

          <section className="surface-card page-stack">
            <h3>Excel de Fuentes Jira</h3>
            <p className="inline-caption">
              Descarga la configuración actual o carga un Excel para reemplazar la tabla de fuentes.
            </p>
            <div className="settings-actions-row">
              <button
                type="button"
                className="secondary-button"
                disabled={jiraExcelBusy}
                onClick={() => void downloadJiraSourcesExcel()}
              >
                Descargar Excel
              </button>
              <label className={cn("secondary-button", "file-upload-button", jiraExcelBusy && "is-disabled")}>
                {jiraExcelBusy ? "Cargando..." : "Cargar Excel"}
                <input
                  key={jiraExcelInputKey}
                  type="file"
                  accept=".xlsx"
                  disabled={jiraExcelBusy}
                  onChange={(event) =>
                    void importJiraSourcesExcel(event.target.files?.[0] ?? null)
                  }
                />
              </label>
            </div>
          </section>

          <section className="surface-card page-stack">
            <div className="settings-actions-row">
              <button
                type="button"
                className="action-button"
                disabled={saveSettings.isPending}
                onClick={() => void saveJira()}
              >
                {saveSettings.isPending ? "Guardando..." : "Guardar configuración"}
              </button>
            </div>
          </section>
        </section>
      ) : null}

      {activeTab === "helix" ? (
        <section className="page-stack">
          <section className="surface-card page-stack">
            <h3>Helix</h3>
            <p className="inline-caption">
              Configuración común de conexión y autenticación para todas las fuentes Helix.
            </p>
            <div className="settings-form-grid">
              <label className="field">
                <span>Proxy</span>
                <input
                  value={asText(values.HELIX_PROXY)}
                  onChange={(event) => setValue("HELIX_PROXY", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Browser</span>
                <select
                  value={asText(values.HELIX_BROWSER || "chrome")}
                  onChange={(event) => setValue("HELIX_BROWSER", event.target.value)}
                >
                  <option value="chrome">Chrome</option>
                  <option value="edge">Edge</option>
                </select>
              </label>
              <label className="field">
                <span>SSL verify</span>
                <select
                  value={normalizeBool(values.HELIX_SSL_VERIFY, true) ? "true" : "false"}
                  onChange={(event) => setValue("HELIX_SSL_VERIFY", event.target.value)}
                >
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </label>
              <label className="field">
                <span>Modo sesión Helix</span>
                <select
                  value={normalizeCookieSource(values.HELIX_COOKIE_SOURCE, "browser")}
                  onChange={(event) => setValue("HELIX_COOKIE_SOURCE", event.target.value)}
                >
                  <option value="browser">Browser (lectura local de sesión)</option>
                  <option value="auto">Auto (manual si existe; si no browser)</option>
                  <option value="manual">Manual (sin leer cookies del navegador)</option>
                </select>
              </label>
              <label className="field field-wide">
                <span>Helix Dashboard URL</span>
                <input
                  value={asText(values.HELIX_DASHBOARD_URL)}
                  onChange={(event) => setValue("HELIX_DASHBOARD_URL", event.target.value)}
                />
              </label>
              {normalizeCookieSource(values.HELIX_COOKIE_SOURCE, "browser") !== "browser" ? (
                <label className="field field-wide">
                  <span>Cookie Helix manual (opcional)</span>
                  <input
                    type="password"
                    value={asText(values.HELIX_COOKIE_HEADER)}
                    onChange={(event) => setValue("HELIX_COOKIE_HEADER", event.target.value)}
                  />
                </label>
              ) : null}
            </div>
          </section>

          <section className="surface-card page-stack">
            <h3>Excel de Fuentes Helix</h3>
            <p className="inline-caption">
              Descarga la configuración actual o carga un Excel para reemplazar la tabla de fuentes.
            </p>
            <div className="settings-actions-row">
              <button
                type="button"
                className="secondary-button"
                disabled={helixExcelBusy}
                onClick={() => void downloadHelixSourcesExcel()}
              >
                Descargar Excel
              </button>
              <label className={cn("secondary-button", "file-upload-button", helixExcelBusy && "is-disabled")}>
                {helixExcelBusy ? "Cargando..." : "Cargar Excel"}
                <input
                  key={helixExcelInputKey}
                  type="file"
                  accept=".xlsx"
                  disabled={helixExcelBusy}
                  onChange={(event) =>
                    void importHelixSourcesExcel(event.target.files?.[0] ?? null)
                  }
                />
              </label>
            </div>
          </section>

          <SourceTable
            title="Fuentes Helix por país"
            caption="Alias y filtros de servicio por fuente. La conexión Helix se define arriba."
            rows={helixRows}
            countries={countries}
            isJira={false}
            onChange={setHelixRows}
            onAddRow={() => setHelixRows([...helixRows, emptyHelixRow(countries[0] ?? "")])}
          />

          <section className="surface-card page-stack">
            <div className="settings-actions-row">
              <button
                type="button"
                className="action-button"
                disabled={saveSettings.isPending}
                onClick={() => void saveHelix()}
              >
                {saveSettings.isPending ? "Guardando..." : "Guardar configuración"}
              </button>
            </div>
          </section>
        </section>
      ) : null}

      {activeTab === "rollups" ? (
        <section className="page-stack">
          <section className="surface-card page-stack">
            <h3>Orígenes agregados por país</h3>
            <p className="inline-caption">
              Esta selección se usa en Vista País, Insights quincenal y el informe de seguimiento del periodo.
            </p>
            <p className="inline-caption">
              Igual que en Streamlit, aquí eliges hasta 2 orígenes por país.
            </p>
            <div className="rollup-country-stack">
              {countries.map((country) => {
                const countrySources = configuredSourcesByCountry.get(country) ?? [];
                const selectedIds = draft.countryRollupSources[country] ?? [];
                return (
                  <RollupSourceSelector
                    key={country}
                    country={country}
                    sources={countrySources}
                    selectedIds={selectedIds}
                    onChange={(nextIds) =>
                      setDraft({
                        ...draft,
                        countryRollupSources: {
                          ...draft.countryRollupSources,
                          [country]: nextIds
                        }
                      })
                    }
                  />
                );
              })}
            </div>
          </section>

          <section className="surface-card page-stack">
            <div className="settings-actions-row">
              <button
                type="button"
                className="action-button"
                disabled={saveSettings.isPending}
                onClick={() => void saveRollups()}
              >
                {saveSettings.isPending ? "Guardando..." : "Guardar configuración"}
              </button>
            </div>
          </section>
        </section>
      ) : null}

      {activeTab === "cache" ? (
        <section className="page-stack">
          <section className="surface-card page-stack">
            <h3>Caches</h3>
            <p className="inline-caption">
              Resetea caches persistentes de la aplicación sin tocar la configuración.
            </p>
            <div className="summary-list">
              {(cache.data ?? []).map((row) => (
                <article className="summary-item" key={row.cache_id}>
                  <div>
                    <strong>{row.label}</strong>
                    <span>
                      {row.records} registros · {row.path}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="ghost-button"
                    disabled={resetCache.isPending}
                    onClick={async () => {
                      await resetCache.mutateAsync(row.cache_id);
                      setFlashMessage(`Cache ${row.label} reseteada.`);
                      queryClient.invalidateQueries({ queryKey: ["cache-inventory"] });
                    }}
                  >
                    Resetear
                  </button>
                </article>
              ))}
            </div>
          </section>
        </section>
      ) : null}

      {activeTab === "performance" ? (
        <section className="page-stack">
          <section className="surface-card page-stack">
            <h3>Performance</h3>
            <p className="inline-caption">
              Panel técnico reservado para snapshots de performance por vista.
            </p>
            <section className="surface-panel empty-panel">
              <h3>Sin muestras en esta sesión</h3>
              <p>
                La pestaña mantiene la misma ubicación funcional que en Streamlit. Cuando existan
                snapshots expuestos por la shell React aparecerán aquí.
              </p>
            </section>
          </section>
        </section>
      ) : null}
    </section>
  );
}
