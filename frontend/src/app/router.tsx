import { lazy, Suspense } from "react";
import {
  createBrowserRouter,
  isRouteErrorResponse,
  Navigate,
  useLocation,
  useRouteError
} from "react-router-dom";
import { AppShell } from "../components/AppShell";

const DashboardPage = lazy(() =>
  import("../pages/DashboardPage").then((module) => ({ default: module.DashboardPage }))
);
const ReportsPage = lazy(() =>
  import("../pages/ReportsPage").then((module) => ({ default: module.ReportsPage }))
);
const IngestPage = lazy(() =>
  import("../pages/IngestPage").then((module) => ({ default: module.IngestPage }))
);
const SettingsPage = lazy(() =>
  import("../pages/SettingsPage").then((module) => ({ default: module.SettingsPage }))
);

function withSuspense(node: JSX.Element) {
  return <Suspense fallback={<div className="hero-panel"><h3>Cargando vista...</h3></div>}>{node}</Suspense>;
}

function RouteErrorScreen() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Se ha producido un error inesperado en la interfaz.";

  return (
    <section className="page-stack">
      <section className="hero-panel">
        <h3>No se ha podido cargar la vista</h3>
        <p className="hero-copy">{message}</p>
      </section>
      <section className="surface-panel empty-panel">
        <h3>Recuperación controlada</h3>
        <p>La aplicación ha interceptado el error y evita exponer la pantalla técnica del router.</p>
      </section>
    </section>
  );
}

function LegacyInsightsRedirect() {
  const location = useLocation();
  const next = new URLSearchParams(location.search);
  next.set("panel", "insights");
  return <Navigate to={`/dashboard?${next.toString()}`} replace />;
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteErrorScreen />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: withSuspense(<DashboardPage />) },
      { path: "intelligence", element: <LegacyInsightsRedirect /> },
      { path: "reports", element: withSuspense(<ReportsPage />) },
      { path: "ingest", element: withSuspense(<IngestPage />) },
      { path: "settings", element: withSuspense(<SettingsPage />) }
    ]
  }
]);
