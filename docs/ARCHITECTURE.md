# Architecture

## Objective

Definir un flujo único y explícito desde configuración hasta visualización/exportación, evitando caminos implícitos o contratos duplicados.

## Runtime Flow

1. `run_streamlit.py` prepara runtime (modo local o binario).
2. `src/bug_resolution_radar/ui/app.py` carga `Settings`, sincroniza `os.environ` y selecciona scope (`country` + `source_id`).
3. `src/bug_resolution_radar/ui/pages` enruta por secciones (Ingesta, Dashboard, Reporte, Configuración).
4. `src/bug_resolution_radar/ui/pages/dashboard_page.py` construye `DashboardDataContext` una sola vez por rerun.
5. Tabs del dashboard consumen `dff/open_df/kpis` compartidos (sin recomputar por tab).
6. Exportes (CSV/PPT) usan exactamente el mismo scope/filtros activos en UI.

## Module Layers

- Configuración
  - `src/bug_resolution_radar/config.py`
  - Responsabilidad: parseo `.env`, validación de schema y persistencia de settings.

- Ingesta
  - `src/bug_resolution_radar/ingest/jira_ingest.py`
  - `src/bug_resolution_radar/ingest/helix_ingest.py`
  - `src/bug_resolution_radar/ingest/browser_runtime.py`
  - Responsabilidad: autenticación vía cookies de navegador, extracción y normalización inicial.

- Modelo y repositorios
  - `src/bug_resolution_radar/models/schema.py`
  - `src/bug_resolution_radar/models/schema_helix.py`
  - `src/bug_resolution_radar/repositories/helix_repo.py`

- Analítica
  - `src/bug_resolution_radar/analytics/kpis.py`
  - `src/bug_resolution_radar/analytics/analysis_window.py`
  - `src/bug_resolution_radar/analytics/status_semantics.py`
  - `src/bug_resolution_radar/analytics/insights.py`

- UI
  - `src/bug_resolution_radar/ui/app.py`
  - `src/bug_resolution_radar/ui/pages`
  - `src/bug_resolution_radar/ui/dashboard`
  - `src/bug_resolution_radar/ui/insights`
  - `src/bug_resolution_radar/ui/components`

- Servicios de soporte
  - `src/bug_resolution_radar/services/notes.py`
  - `src/bug_resolution_radar/services/source_maintenance.py`

- Reporting ejecutivo
  - `src/bug_resolution_radar/reports/executive_ppt.py`

## Session State Contract

Claves canónicas:
- Scope: `workspace_country`, `workspace_source_id`
- Modo/sección: `workspace_mode`, `workspace_section`
- Tema: `workspace_dark_mode`
- Filtros globales: `filter_status`, `filter_priority`, `filter_assignee`

Regla operativa: una única fuente de verdad por concepto. Si una sección necesita estado derivado, se recalcula desde el estado canónico.

## Data Contracts

- Ingesta persiste en JSON local con `source_id` obligatorio por issue/item.
- Dashboard, Insights y Reporte operan sobre el mismo dataframe ya scopeado y filtrado.
- `ANALYSIS_LOOKBACK_MONTHS` es la única palanca de profundidad temporal.

## Non-Goals

- No hay compatibilidad con rutas legacy de configuración.
- No hay múltiples contratos para el mismo comportamiento.
