import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useDashboardParams } from "../hooks/useDashboardParams";
import { fetchJson, type BootstrapPayload, type WorkspaceData } from "../lib/api";

const STORAGE_THEME_KEY = "bug-resolution-radar-theme";

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
  dashboardState: ReturnType<typeof useDashboardParams>;
  themeMode: "light" | "dark";
};

function classNames(...tokens: Array<string | false | null | undefined>) {
  return tokens.filter(Boolean).join(" ");
}

function persistedTheme(): "light" | "dark" | null {
  if (typeof window === "undefined") {
    return null;
  }
  const value = window.localStorage.getItem(STORAGE_THEME_KEY);
  return value === "dark" || value === "light" ? value : null;
}

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const dashboardState = useDashboardParams("overview");
  const defaultsBootstrapped = useRef(false);
  const [themeMode, setThemeMode] = useState<"light" | "dark">(
    () => persistedTheme() ?? "light"
  );

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
    refetchOnReconnect: false
  });

  const workspace = bootstrap.data?.workspace;
  const isDashboard = location.pathname === "/dashboard";
  const isReports = location.pathname === "/reports";
  const isIngest = location.pathname === "/ingest";
  const isSettings = location.pathname === "/settings";
  const reportMode = new URLSearchParams(location.search).get("reportMode") ?? "executive";

  useEffect(() => {
    const nextTheme = persistedTheme();
    if (nextTheme) {
      setThemeMode(nextTheme);
      return;
    }
    if (bootstrap.data?.theme === "dark") {
      setThemeMode("dark");
      return;
    }
    setThemeMode("light");
  }, [bootstrap.data?.theme]);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
    window.localStorage.setItem(STORAGE_THEME_KEY, themeMode);
  }, [themeMode]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void import("../pages/ReportsPage");
      void import("../pages/IngestPage");
      void import("../pages/SettingsPage");
    }, 120);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!workspace || !bootstrap.data) {
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

  const heroTitle = bootstrap.data?.appTitle?.trim() || "Cuadro de mando de incidencias";

  return (
    <div className="app-shell">
      <header className="bbva-hero">
        <div className="bbva-hero-copy">
          <h1 className="bbva-hero-title">{heroTitle}</h1>
          <p className="bbva-hero-sub">Análisis y seguimiento de incidencias</p>
        </div>
        <div className="bbva-hero-mark" aria-hidden="true">
          <img src="/brand/icons/spherica-no-draw.svg" alt="" />
        </div>
      </header>

      <section className="workspace-scope-bar surface-panel">
        <div className="workspace-country-field">
          <label className="field-label" htmlFor="workspace-country">
            País
          </label>
          <select
            id="workspace-country"
            value={workspace?.selectedCountry ?? ""}
            onChange={(event) =>
              handleScopeChange({
                country: event.target.value,
                sourceId: "",
                scopeMode: "source"
              })
            }
          >
            {(workspace?.countries ?? []).map((country) => (
              <option key={country.country} value={country.country}>
                {country.country}
              </option>
            ))}
          </select>
        </div>

        <div className="workspace-scope-detail">
          {workspace?.hasCountryRollup ? (
            <>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={(workspace?.scopeMode ?? "source") === "country"}
                  onChange={(event) =>
                    handleScopeChange({
                      scopeMode: event.target.checked ? "country" : "source"
                    })
                  }
                />
                <span>Vista agregada</span>
              </label>

              {(workspace?.scopeMode ?? "source") === "source" ? (
                <div className="workspace-source-field">
                  <label className="field-label" htmlFor="workspace-source">
                    Origen
                  </label>
                  <select
                    id="workspace-source"
                    value={workspace?.selectedSourceId ?? ""}
                    onChange={(event) =>
                      handleScopeChange({
                        sourceId: event.target.value
                      })
                    }
                  >
                    {(workspace?.sources ?? []).map((source) => (
                      <option key={source.source_id} value={source.source_id}>
                        {source.alias} · {String(source.source_type || "").toUpperCase()}
                      </option>
                    ))}
                  </select>
                </div>
              ) : (
                <p className="workspace-rollup-caption">
                  {rollupPreview ? `Agregado país activo: ${rollupPreview}` : "Agregado país activo"}
                </p>
              )}
            </>
          ) : (
            <div className="workspace-source-field">
              <label className="field-label" htmlFor="workspace-source">
                Origen
              </label>
              <select
                id="workspace-source"
                value={workspace?.selectedSourceId ?? ""}
                onChange={(event) =>
                  handleScopeChange({
                    sourceId: event.target.value
                  })
                }
              >
                {(workspace?.sources ?? []).map((source) => (
                  <option key={source.source_id} value={source.source_id}>
                    {source.alias} · {String(source.source_type || "").toUpperCase()}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </section>

      <section className="workspace-nav-bar surface-panel">
        <nav className="workspace-nav-tabs" aria-label="Navegación principal del radar">
          {dashboardTabs.map(([panel, label]) => (
            <button
              key={panel}
              type="button"
              className={classNames(
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
            className={classNames(
              "workspace-action",
              isReports && reportMode === "executive" && "workspace-action-active"
            )}
            title="Informe PPT ejecutivo"
            aria-label="Informe PPT ejecutivo"
            onClick={() => navigateWithParams("/reports", { reportMode: "executive" })}
          >
            <img src="/brand/icons/digital-press.svg" alt="" />
          </button>
          {workspace?.hasCountryRollup ? (
            <button
              type="button"
              className={classNames(
                "workspace-action",
                isReports && reportMode === "period" && "workspace-action-active"
              )}
              title="Informe seguimiento del periodo"
              aria-label="Informe seguimiento del periodo"
              onClick={() => navigateWithParams("/reports", { reportMode: "period" })}
            >
              <img src="/brand/icons/presentation.svg" alt="" />
            </button>
          ) : null}
          <button
            type="button"
            className={classNames("workspace-action", isIngest && "workspace-action-active")}
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
            onClick={() => setThemeMode((current) => (current === "dark" ? "light" : "dark"))}
          >
            <img
              src={themeMode === "dark" ? "/brand/icons/sun.svg" : "/brand/icons/moon.svg"}
              alt=""
            />
          </button>
          <button
            type="button"
            className={classNames("workspace-action", isSettings && "workspace-action-active")}
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
            dashboardState,
            themeMode
          } satisfies ShellContextValue}
        />
      </main>
    </div>
  );
}
