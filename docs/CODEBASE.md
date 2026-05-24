# Codebase Map

## Objective

Servir como mapa operativo del repositorio para onboarding y mantenimiento sin ambigüedades.

## Core Package Map

- `src/bug_resolution_radar/config.py`
  - Carga/persistencia de settings y normalización de fuentes.

- `src/bug_resolution_radar/common/security.py`
  - Sanitización de secretos y validación de URLs.

- `src/bug_resolution_radar/common/issue_links.py`
  - Normalización de claves Jira/Helix y mapas de URLs para UI y PPT.

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

- `src/bug_resolution_radar/services/ingest_profiler.py`
  - Perfilado de ingestas por fase (latencia/CPU/memoria) y persistencia JSONL.

- `src/bug_resolution_radar/services/ingest_circuit_breaker.py`
  - Circuit breaker persistente por fuente con ventana de fallos y cooldown.

- `src/bug_resolution_radar/services/ingest_runner.py`
  - Orquestación síncrona de ingesta Jira/Helix y lookup finalista por país/BU-UG, incluyendo el filtro central de candidatos ARSQL desde descripciones Jira no finalistas.

- `src/bug_resolution_radar/services/ingest_merge.py`
  - Merge y mapeo compartido de snapshots Jira/Helix para evitar lógica duplicada entre runner backend y contratos de presentación.

- `src/bug_resolution_radar/analytics/analysis_window.py`
  - Ventana global de análisis por meses.

- `src/bug_resolution_radar/analytics/kpis.py`
  - KPIs principales para dashboard/reportes.

- `src/bug_resolution_radar/analytics/status_semantics.py`
  - Semántica canónica de estados finales/no finales.

- `src/bug_resolution_radar/analytics/finalist_discrepancies.py`
  - Fuente única para extraer `INC...`, cruzar Jira con Helix histórico, calcular discrepancias finalistas y aplicar estado efectivo al scope visible.

- `src/bug_resolution_radar/analytics/period_risk_issue_lists.py`
  - Listas de riesgo del seguimiento; las antigüedades se filtran y muestran con días completos.

- `src/bug_resolution_radar/analytics/insights.py`
  - Utilidades analíticas para clustering/similaridad.

## Ingestion Package Map

- `src/bug_resolution_radar/ingest/browser_runtime.py`
  - Apertura de navegador, control de permisos y bootstrap multi-URL.

- `src/bug_resolution_radar/ingest/cookie_utils.py`
  - Utilidades compartidas para extracción de cookies Chromium y armado de header `Cookie`.

- `src/bug_resolution_radar/ingest/jira_session.py`
  - Extracción de cookies Jira desde navegador.

- `src/bug_resolution_radar/ingest/jira_ingest.py`
  - Pipeline Jira (auth, query, paginado, normalización).

- `src/bug_resolution_radar/ingest/helix_session.py`
  - Extracción de cookies Helix/SmartIT.

- `src/bug_resolution_radar/ingest/helix_mapper.py`
  - Mapeo de columnas ARSQL a modelo normalizado.

- `src/bug_resolution_radar/ingest/helix_ingest.py`
  - Pipeline Helix ARSQL (preflight, extracción, normalización y lookup exacto de INC).

## Frontend Package Map

- `frontend/src/app/router.tsx`
  - Router React y composición de páginas dentro de la shell.

- `frontend/src/components/AppShell.tsx`
  - Layout principal, navegación y estado global de interfaz.

- `frontend/src/pages/`
  - Pantallas de dashboard, issues, ingesta, settings y reportes consumiendo contratos HTTP.

- `frontend/src/components/`
  - Componentes reutilizables de tabla, filtros, paneles, gráficos e insights.

- `frontend/src/lib/api.ts`
  - Cliente HTTP tipado para FastAPI.

- `frontend/src/lib/semanticColors.ts`
  - Contrato de colores semánticos compartido con backend.

- `frontend/src/styles/app.css`
  - Tema visual, layout responsive y reglas CSS de la SPA.

## Reporting and Theme

- `src/bug_resolution_radar/reports/executive_ppt.py`
  - Construcción de slides, cache y export binario PPT.

- `src/bug_resolution_radar/reports/period_followup_ppt.py`
  - Reporte de seguimiento quincenal con rollups, secciones de riesgo, estado efectivo finalista y enlaces Jira/Helix.

- `src/bug_resolution_radar/theme/design_tokens.py`
  - Tokens visuales y resolución de tipografías.

- `src/bug_resolution_radar/theme/plotly_style.py`
  - Adaptación de tema para figuras Plotly usadas por API y reportes.

## Test Map

- `tests/`
  - tests unitarios e integración ligera por módulo.
  - todos se ejecutan en `quality-gate`.

## Operations

- `scripts/ingest_profile_report.py`
  - CLI para inspeccionar el último perfil de ingesta y revisar p50/p95 por fase.
