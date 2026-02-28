# Insights Engine

## Objective

Producir insights accionables, trazables y coherentes con el contexto visible en pantalla (scope + filtros activos).

## Pipeline

1. Entrada canónica:
- `dff` (dataset filtrado)
- `open_df` (subconjunto abierto)
- `kpis` (métricas agregadas)

2. Cálculo de packs por gráfico:
- `src/bug_resolution_radar/ui/insights/engine.py`
- API principal: `build_trend_insight_pack(...)`

3. Render por superficie:
- Dashboard (tendencias/resumen): `src/bug_resolution_radar/ui/dashboard/tabs`
- Insights especializados: `src/bug_resolution_radar/ui/insights`
- Copilot operativo: `src/bug_resolution_radar/ui/insights/copilot.py`

4. Navegación accionable:
- Tarjetas con filtros aplicables disparan salto a `Issues` con filtros sincronizados.

## Domain Objects

- `ActionInsight`: unidad accionable con score, texto y filtros sugeridos.
- `InsightMetric`: métrica corta para cabecera.
- `TrendInsightPack`: contenedor completo por visualización.

## Scoring Rules

- Priorizar señales con impacto operativo inmediato (atascos, antigüedad, riesgo de backlog).
- Penalizar repeticiones sin novedad contextual.
- Mantener lenguaje ejecutivo breve y verificable con evidencias numéricas.

## Learning Store

- Persistencia por scope en:
  - `src/bug_resolution_radar/ui/insights/learning_store.py`
- Objetivo:
  - recordar patrones de interacción por `country/source_id`
  - ajustar orden de sugerencias entre sesiones

## Copilot Scope

`copilot.py` no reemplaza motor analítico ni llama LLM remoto: sintetiza el estado actual y propone acciones basadas en reglas y métricas internas.

## Extension Points

Para añadir un nuevo insight:
1. Añadir cálculo en `engine.py` con contrato `ActionInsight`.
2. Conectar render en la página/tab correspondiente.
3. Añadir tests en `tests/test_insights_engine.py` o módulo específico.
4. Validar navegación/filtros derivados cuando el insight sea accionable.

Para añadir una nueva vista de insights:
1. Crear módulo en `src/bug_resolution_radar/ui/insights/`.
2. Reusar helpers de `helpers.py`, `chips.py` y `learning_store.py`.
3. Registrar acceso desde `insights_page.py`.

## Testing Strategy

- Tests de cálculo puro (sin Streamlit) para reglas de scoring y métricas.
- Tests de integración ligera para navegación y filtros sincronizados.
- Cobertura obligatoria dentro del `quality-gate`.
