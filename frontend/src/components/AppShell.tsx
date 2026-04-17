import { useEffect, useMemo, useRef, useState } from "react";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient
} from "@tanstack/react-query";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useDashboardParams } from "../hooks/useDashboardParams";
import {
  fetchJson,
  normalizeSettingsPayload,
  putJson,
  type BootstrapPayload,
  type SettingsPayload,
  type WorkspaceData
} from "../lib/api";
import { cn } from "../lib/cn";
import { configureSemanticColors } from "../lib/semanticColors";

const dashboardTabs = [
  ["overview", "Resumen"],
  ["insights", "Insights"],
  ["trends", "Tendencias"],
  ["issues", "Issues"],
  ["kanban", "Kanban"],
  ["notes", "Notas"]
] as const;

export type ShellContextValue = {
  bootstrap?: BootstrapPayload;
  workspace?: WorkspaceData;
  workspaceLoading: boolean;
  workspaceRefreshing: boolean;
  dashboardState: ReturnType<typeof useDashboardParams>;
  themeMode: "light" | "dark";
};

type ThemeContract = NonNullable<BootstrapPayload["designTokens"]>["theme"];

function applyThemeContract(
  contract: ThemeContract | undefined,
  themeMode: "light" | "dark"
) {
  if (!contract) {
    return;
  }
  const root = document.documentElement;
  const knownKeys = new Set([
    ...Object.keys(contract.light ?? {}),
    ...Object.keys(contract.dark ?? {})
  ]);
  for (const tokenName of knownKeys) {
    root.style.removeProperty(tokenName);
  }
  const selected = contract[themeMode] ?? {};
  for (const [tokenName, tokenValue] of Object.entries(selected)) {
    root.style.setProperty(tokenName, String(tokenValue));
  }
}

export function AppShell() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const dashboardState = useDashboardParams("overview");
  const defaultsBootstrapped = useRef(false);
  const [themeMode, setThemeMode] = useState<"light" | "dark">("light");

  const bootstrap = useQuery({
    queryKey: [
      "bootstrap-shell",
      dashboardState.params.country,
      dashboardState.params.sourceId,
      dashboardState.params.scopeMode
    ],
    queryFn: () =>
      fetchJson<BootstrapPayload>("/api/bootstrap", {
        country: dashboardState.params.country,
        sourceId: dashboardState.params.sourceId,
        scopeMode: dashboardState.params.scopeMode
      }),
    staleTime: 45_000,
    gcTime: 300_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    placeholderData: keepPreviousData
  });

  const workspace = bootstrap.data?.workspace;
  const workspaceLoading = bootstrap.isLoading && !bootstrap.data;
  const workspaceRefreshing = bootstrap.isFetching;
  const isDashboard = location.pathname === "/dashboard";
  const isReports = location.pathname === "/reports";
  const isIngest = location.pathname === "/ingest";
  const isSettings = location.pathname === "/settings";
  const reportMode = new URLSearchParams(location.search).get("reportMode") ?? "executive";
  const heroTitle = bootstrap.data?.appTitle?.trim() || "Cuadro de mando de incidencias";

  const persistTheme = useMutation({
    mutationFn: async (nextTheme: "light" | "dark") => {
      const settings = normalizeSettingsPayload(
        await fetchJson<SettingsPayload>("/api/settings")
      );
      const currentTheme = String(settings.values?.THEME ?? "").trim().toLowerCase();
      if (currentTheme === nextTheme) {
        return settings;
      }
      return normalizeSettingsPayload(
        await putJson<SettingsPayload>("/api/settings", {
          ...settings,
          values: {
            ...settings.values,
            THEME: nextTheme
          }
        })
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
      void queryClient.invalidateQueries({ queryKey: ["bootstrap-shell"] });
    }
  });

  useEffect(() => {
    setThemeMode(bootstrap.data?.theme === "dark" ? "dark" : "light");
  }, [bootstrap.data?.theme]);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
    applyThemeContract(bootstrap.data?.designTokens?.theme, themeMode);
  }, [bootstrap.data?.designTokens?.theme, themeMode]);

  useEffect(() => {
    configureSemanticColors(bootstrap.data?.designTokens?.semantic ?? null);
  }, [bootstrap.data?.designTokens?.semantic]);

  useEffect(() => {
    document.title = heroTitle;
  }, [heroTitle]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void import("../pages/ReportsPage");
      void import("../pages/IngestPage");
      void import("../pages/SettingsPage");
    }, 120);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!workspace || !bootstrap.data || bootstrap.isPlaceholderData) {
      return;
    }
    const patch: Record<string, string | string[]> = {};
    if (dashboardState.params.country !== workspace.selectedCountry) {
      patch.country = workspace.selectedCountry;
    }
    if (dashboardState.params.sourceId !== workspace.selectedSourceId) {
      patch.sourceId = workspace.selectedSourceId;
    }
    if (dashboardState.params.scopeMode !== workspace.scopeMode) {
      patch.scopeMode = workspace.scopeMode;
    }
    if (
      !defaultsBootstrapped.current &&
      dashboardState.params.status.length === 0 &&
      bootstrap.data.defaultFilters.status.length > 0
    ) {
      patch.status = bootstrap.data.defaultFilters.status;
    }
    if (
      !defaultsBootstrapped.current &&
      dashboardState.params.priority.length === 0 &&
      bootstrap.data.defaultFilters.priority.length > 0
    ) {
      patch.priority = bootstrap.data.defaultFilters.priority;
    }
    if (
      !defaultsBootstrapped.current &&
      dashboardState.params.assignee.length === 0 &&
      bootstrap.data.defaultFilters.assignee.length > 0
    ) {
      patch.assignee = bootstrap.data.defaultFilters.assignee;
    }
    if (Object.keys(patch).length > 0) {
      defaultsBootstrapped.current = true;
      dashboardState.update(patch);
    }
  }, [
    bootstrap.data,
    dashboardState,
    dashboardState.params.assignee.length,
    dashboardState.params.country,
    dashboardState.params.priority.length,
    dashboardState.params.scopeMode,
    dashboardState.params.sourceId,
    dashboardState.params.status.length,
    workspace
  ]);

  function navigateWithParams(pathname: string, patch: Record<string, string> = {}) {
    const next = dashboardState.buildNextSearch(patch);
    navigate(
      {
        pathname,
        search: next.size > 0 ? `?${next.toString()}` : ""
      },
      { replace: true }
    );
  }

  function handleScopeChange(patch: Record<string, string>) {
    dashboardState.update({
      ...patch,
      status: [],
      priority: [],
      assignee: []
    });
  }

  function handleThemeToggle() {
    const nextTheme = themeMode === "dark" ? "light" : "dark";
    setThemeMode(nextTheme);
    persistTheme.mutate(nextTheme);
  }

  const rollupPreview = useMemo(() => {
    if (!workspace?.hasCountryRollup) {
      return "";
    }
    const labels = workspace.sources
      .filter((source) => workspace.countryRollupSourceIds.includes(source.source_id))
      .slice(0, 2)
      .map((source) => `${source.alias} · ${String(source.source_type || "").toUpperCase()}`);
    return labels.join(" · ");
  }, [workspace]);

  const countryOptions = workspace?.countries ?? [];
  const sourceOptions = workspace?.sources ?? [];
  const isCountryRollupActive =
    Boolean(workspace?.hasCountryRollup) && (workspace?.scopeMode ?? "source") === "country";
  const selectedCountryValue =
    countryOptions.some((country) => country.country === dashboardState.params.country)
      ? dashboardState.params.country
      : (workspace?.selectedCountry ?? "");
  const selectedSourceValue =
    dashboardState.params.sourceId === ""
      ? ""
      : sourceOptions.some((source) => source.source_id === dashboardState.params.sourceId)
        ? dashboardState.params.sourceId
        : (workspace?.selectedSourceId ?? "");
  const sourceSelectDisabled =
    workspaceLoading ||
    workspaceRefreshing ||
    !workspace?.selectedCountry ||
    sourceOptions.length === 0;

  return (
    <div className="app-shell">
      <header className="bbva-hero">
        <div className="bbva-hero-copy">
          <h1 className="bbva-hero-title">{heroTitle}</h1>
          <p className="bbva-hero-sub">Análisis y seguimiento de incidencias</p>
        </div>
      </header>

      <section
        className={cn("workspace-scope-bar", "surface-panel", workspaceRefreshing && "is-loading")}
        aria-busy={workspaceRefreshing}
      >
        <div className="workspace-country-field">
          <label className="field-label" htmlFor="workspace-country">
            País
          </label>
          <select
            id="workspace-country"
            value={selectedCountryValue}
            disabled={workspaceLoading || workspaceRefreshing || countryOptions.length === 0}
            onChange={(event) =>
              handleScopeChange({
                country: event.target.value,
                sourceId: "",
                scopeMode: "source"
              })
            }
          >
            {countryOptions.length > 0 ? (
              countryOptions.map((country) => (
                <option key={country.country} value={country.country}>
                  {country.country}
                </option>
              ))
            ) : (
              <option value="">{workspaceLoading ? "Cargando países..." : "Sin países"}</option>
            )}
          </select>
        </div>

        <div className="workspace-scope-detail">
          <div className="workspace-rollup-slot">
            {workspace?.hasCountryRollup ? (
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={(workspace?.scopeMode ?? "source") === "country"}
                  disabled={workspaceRefreshing}
                  onChange={(event) =>
                    handleScopeChange({
                      scopeMode: event.target.checked ? "country" : "source"
                    })
                  }
                />
                <span>Vista agregada</span>
              </label>
            ) : (
              <div className="workspace-rollup-placeholder">
                <span className="field-label">Vista agregada</span>
                <small>No disponible en este alcance</small>
              </div>
            )}
          </div>

          <div className="workspace-source-slot">
            {(workspace?.hasCountryRollup && (workspace?.scopeMode ?? "source") === "country") ? (
              <p className="workspace-rollup-caption">
                {rollupPreview ? `Agregado país activo: ${rollupPreview}` : "Agregado país activo"}
              </p>
            ) : (
              <div className="workspace-source-field">
                <label className="field-label" htmlFor="workspace-source">
                  Origen
                </label>
                <select
                  id="workspace-source"
                  value={selectedSourceValue}
                  disabled={sourceSelectDisabled}
                  onChange={(event) =>
                    handleScopeChange({
                      sourceId: event.target.value
                    })
                  }
                >
                  {selectedSourceValue === "" ? (
                    <option value="">
                      {workspaceRefreshing ? "Actualizando orígenes..." : "Selecciona un origen"}
                    </option>
                  ) : null}
                  {sourceOptions.length > 0 ? (
                    sourceOptions.map((source) => (
                      <option key={source.source_id} value={source.source_id}>
                        {source.alias} · {String(source.source_type || "").toUpperCase()}
                      </option>
                    ))
                  ) : (
                    <option value="">
                      {workspaceLoading ? "Cargando orígenes..." : "Sin origen disponible"}
                    </option>
                  )}
                </select>
              </div>
            )}
          </div>

          <div className="workspace-scope-status">
            {workspaceRefreshing ? (
              <span className="workspace-loading-pill">Actualizando alcance…</span>
            ) : null}
          </div>
        </div>
      </section>

      <section className="workspace-nav-bar surface-panel">
        <nav className="workspace-nav-tabs" aria-label="Navegación principal del radar">
          {dashboardTabs.map(([panel, label]) => (
            <button
              key={panel}
              type="button"
              className={cn(
                "workspace-tab",
                isDashboard && dashboardState.params.panel === panel && "workspace-tab-active"
              )}
              onClick={() => navigateWithParams("/dashboard", { panel })}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="workspace-nav-actions">
          <button
            type="button"
            className={cn(
              "workspace-action",
              isReports && "workspace-action-active"
            )}
            title="Informes"
            aria-label="Informes"
            onClick={() =>
              navigateWithParams("/reports", {
                reportMode: isCountryRollupActive ? "period" : "executive"
              })
            }
          >
            <img src="/brand/icons/presentation.svg" alt="" />
          </button>
          <button
            type="button"
            className={cn("workspace-action", isIngest && "workspace-action-active")}
            title="Ingesta"
            aria-label="Ingesta"
            onClick={() => navigateWithParams("/ingest")}
          >
            <img src="/brand/icons/spherica-down-cloud.svg" alt="" />
          </button>
          <button
            type="button"
            className="workspace-action"
            title={themeMode === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
            aria-label={themeMode === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
            onClick={handleThemeToggle}
          >
            <img
              src={themeMode === "dark" ? "/brand/icons/sun.svg" : "/brand/icons/moon.svg"}
              alt=""
            />
          </button>
          <button
            type="button"
            className={cn("workspace-action", isSettings && "workspace-action-active")}
            title="Configuración"
            aria-label="Configuración"
            onClick={() => navigateWithParams("/settings")}
          >
            <img src="/brand/icons/spherica-simulator.svg" alt="" />
          </button>
        </div>
      </section>

      <main className="workspace-content">
        <Outlet
          context={{
            bootstrap: bootstrap.data,
            workspace,
            workspaceLoading,
            workspaceRefreshing,
            dashboardState,
            themeMode
          } satisfies ShellContextValue}
        />
      </main>
    </div>
  );
}
