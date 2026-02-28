# Codebase Map

## Objective

Servir como mapa operativo del repositorio para onboarding y mantenimiento sin ambigüedades.

## Core Package Map

- `src/bug_resolution_radar/config.py`
  - Carga/persistencia de settings y normalización de fuentes.

- `src/bug_resolution_radar/common/security.py`
  - Sanitización de secretos y validación de URLs.

- `src/bug_resolution_radar/common/utils.py`
  - Utilidades transversales de fechas/parsing.

- `src/bug_resolution_radar/models/schema.py`
  - Modelo canónico de incidencias normalizadas.

- `src/bug_resolution_radar/models/schema_helix.py`
  - Modelo canónico de payload Helix.

- `src/bug_resolution_radar/repositories/helix_repo.py`
  - Persistencia del dump Helix en disco.

- `src/bug_resolution_radar/services/notes.py`
  - Persistencia de notas operativas.

- `src/bug_resolution_radar/services/source_maintenance.py`
  - Eliminación de fuentes y limpieza de cachés asociadas.

- `src/bug_resolution_radar/analytics/analysis_window.py`
  - Ventana global de análisis por meses.

- `src/bug_resolution_radar/analytics/kpis.py`
  - KPIs principales para dashboard/reportes.

- `src/bug_resolution_radar/analytics/status_semantics.py`
  - Semántica canónica de estados finales/no finales.

- `src/bug_resolution_radar/analytics/insights.py`
  - Utilidades analíticas para clustering/similaridad.

## Ingestion Package Map

- `src/bug_resolution_radar/ingest/browser_runtime.py`
  - Apertura de navegador, control de permisos y bootstrap multi-URL.

- `src/bug_resolution_radar/ingest/jira_session.py`
  - Extracción de cookies Jira desde navegador.

- `src/bug_resolution_radar/ingest/jira_ingest.py`
  - Pipeline Jira (auth, query, paginado, normalización).

- `src/bug_resolution_radar/ingest/helix_session.py`
  - Extracción de cookies Helix/SmartIT.

- `src/bug_resolution_radar/ingest/helix_mapper.py`
  - Mapeo de columnas ARSQL a modelo normalizado.

- `src/bug_resolution_radar/ingest/helix_ingest.py`
  - Pipeline Helix ARSQL (preflight, extracción, normalización).

## UI Package Map

- `src/bug_resolution_radar/ui/app.py`
  - Shell principal de navegación, tema y scope.

- `src/bug_resolution_radar/ui/pages/ingest_page.py`
  - Orquestación de tests de conexión e ingestas por fuente.

- `src/bug_resolution_radar/ui/pages/dashboard_page.py`
  - Router de secciones del dashboard y construcción del contexto.

- `src/bug_resolution_radar/ui/pages/insights_page.py`
  - Entry point de vistas analíticas especializadas.

- `src/bug_resolution_radar/ui/pages/report_page.py`
  - Generación de reporte ejecutivo PPT desde scope activo.

- `src/bug_resolution_radar/ui/pages/config_page.py`
  - Gestión de settings, fuentes y perfil corporativo.

- `src/bug_resolution_radar/ui/cache.py`
  - Caché de agregaciones por firma de dataframe.

- `src/bug_resolution_radar/ui/common.py`
  - Carga/guardado de issues y helpers de color/normalización.

- `src/bug_resolution_radar/ui/components/filters.py`
  - Filtros canónicos y sincronización de estado.

- `src/bug_resolution_radar/ui/components/issues.py`
  - Tabla/cards de issues filtradas.

- `src/bug_resolution_radar/ui/dashboard/data_context.py`
  - Contexto compartido (`dff`, `open_df`, `kpis`) por rerun.

- `src/bug_resolution_radar/ui/dashboard/registry.py`
  - Registro de gráficos y render functions de tendencias.

- `src/bug_resolution_radar/ui/dashboard/tabs`
  - Render específico de Overview/Issues/Kanban/Trends/Notes.

- `src/bug_resolution_radar/ui/insights/engine.py`
  - Motor de insights y scoring contextual.

- `src/bug_resolution_radar/ui/insights/learning_store.py`
  - Memoria cross-session por scope.

- `src/bug_resolution_radar/ui/insights/copilot.py`
  - Resumen operativo y Q&A guiado por evidencia.

## Reporting and Theme

- `src/bug_resolution_radar/reports/executive_ppt.py`
  - Construcción de slides, cache y export binario PPT.

- `src/bug_resolution_radar/theme/design_tokens.py`
  - Tokens visuales y resolución de tipografías.

- `src/bug_resolution_radar/ui/style.py`
  - CSS global y adaptación de tema para Plotly/Streamlit.

## Test Map

- `tests/`
  - tests unitarios e integración ligera por módulo.
  - todos se ejecutan en `quality-gate`.
