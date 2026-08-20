# Insights Engine

## Objective

Producir insights accionables, trazables y coherentes con el contexto visible en pantalla (scope + filtros activos).

## Pipeline

1. Entrada canónica:
- `dff` (dataset filtrado)
- `open_df` (subconjunto abierto)
- `kpis` (métricas agregadas)

2. Cálculo de packs por gráfico:
- `src/bug_resolution_radar/analytics/trend_insights.py`
- API principal: `build_trend_insight_pack(...)`
- Analítica transversal de duplicados exactos:
  - `src/bug_resolution_radar/analytics/duplicates.py`

3. Render por superficie:
- Snapshot backend: `src/bug_resolution_radar/services/dashboard_snapshot.py`
- API HTTP: `src/bug_resolution_radar/api/app.py`
- Presentación React: `frontend/src/components/InsightsPanel.tsx`

4. Navegación accionable:
- Tarjetas con filtros aplicables disparan salto a `Issues` con filtros sincronizados.

Esta interacción pertenece exclusivamente al escritorio. La proyección GPC se
materializa con filtros vacíos y elimina filtros sugeridos, `issueKeys`, combos y
drilldowns antes de exportar. GPC presenta el racional resultante, pero no modifica
el universo de incidencias ni recalcula insights.

## Domain Objects

- `ActionInsight`: unidad accionable con score, texto y filtros sugeridos.
- `InsightMetric`: métrica corta para cabecera.
- `TrendInsightPack`: contenedor completo por visualización.

## Scoring Rules

- Priorizar señales con impacto operativo inmediato (atascos, antigüedad, riesgo de backlog).
- Considerar críticas únicamente las prioridades P0/P1: `Supone un impedimento`, `Highest` y `High`; `Medium` nunca entra en este grupo.
- Penalizar repeticiones sin novedad contextual.
- Mantener lenguaje ejecutivo breve y verificable con evidencias numéricas.
- No crear tarjetas de relleno: si una regla no emite una señal material, la superficie deja el espacio vacío u omite la sección.

## Learning Store

- Persistencia por scope en:
  - `src/bug_resolution_radar/services/insights_learning_store.py`
- Objetivo:
  - guardar mediciones operativas distintas por `country/source_id` o agregado de país;
  - conservar la medición anterior como baseline estable aunque se abran varios gráficos;
  - producir comparación `WoW` solo con una separación de 5–9 días y usar `vs última medición` en el resto de cadencias;
  - no emitir narrativa histórica sin baseline o sin variación material.

La sincronización se realiza en backend mediante
`src/bug_resolution_radar/services/insights_history.py`; no depende del estado de la WebApp.
El mismo baseline alimenta tendencias, presentación de seguimiento y proyección cloud.

## Copilot Scope

El copilot operativo no reemplaza motor analítico ni llama LLM remoto: sintetiza el estado actual y propone acciones basadas en reglas y métricas internas.

## Extension Points

Para añadir un nuevo insight:
1. Añadir cálculo en `src/bug_resolution_radar/analytics/trend_insights.py` con contrato `ActionInsight`.
2. Exponer el pack en `src/bug_resolution_radar/services/dashboard_snapshot.py` o endpoint específico.
3. Añadir tests en el módulo analítico o contrato API correspondiente.
4. Validar navegación/filtros derivados cuando el insight sea accionable.

Para añadir una nueva vista de insights:
1. Crear componente en `frontend/src/components/` o `frontend/src/pages/`.
2. Reusar `frontend/src/lib/api.ts` y `frontend/src/lib/semanticColors.ts`.
3. Registrar acceso en `frontend/src/app/router.tsx`.

## Testing Strategy

- Tests de cálculo puro para reglas de scoring y métricas.
- Tests de integración ligera para navegación y filtros sincronizados.
- Cobertura obligatoria dentro del `quality-gate`.
