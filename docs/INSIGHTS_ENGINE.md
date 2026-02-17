# Insights Engine

## Objetivo
Generar mensajes ejecutivos dinamicos, no estaticos, adaptados al estado real del backlog filtrado.

## Dónde vive
- Motor unificado: `src/bug_resolution_radar/ui/insights/engine.py`
- Persistencia de aprendizaje: `src/bug_resolution_radar/ui/insights/learning_store.py`
- Consumo en tendencias: `src/bug_resolution_radar/ui/dashboard/trends.py`
- Consumo en resumen ejecutivo: `src/bug_resolution_radar/ui/dashboard/overview.py`
- Consumo en insights por pestaña:
  - `src/bug_resolution_radar/ui/insights/top_topics.py`
  - `src/bug_resolution_radar/ui/insights/duplicates.py`
  - `src/bug_resolution_radar/ui/insights/backlog_people.py`
  - `src/bug_resolution_radar/ui/insights/ops_health.py`

## Reglas de construcción
- Cada insight se calcula sobre el dataframe filtrado actual.
- Un insight solo es "accionable" si incluye filtros aplicables (`status`, `priority`, `assignee`).
- Insights sin filtro se muestran como explicación contextual (sin navegación forzada).
- Los insights se priorizan por puntuacion de relevancia (`score`) para que cambien con la situacion operativa.
- Capa de aprendizaje de sesion: la priorizacion se ajusta por interacciones (clicks en insights, cambios de filtro y navegacion entre graficos).
- Control de fatiga: los insights muy repetidos pierden prioridad y los no vistos ganan peso.
- Persistencia cross-session: el aprendizaje se guarda por cliente (`workspace_country` + `workspace_source_id`) y se recarga automaticamente al volver.

## Contrato del motor
`engine.py` expone tres tipos principales:
- `ActionInsight`: tarjeta ejecutiva con `title`, `body`, `score` y filtros opcionales.
- `InsightMetric`: metrica de cabecera (label + value).
- `TrendInsightPack`: paquete por grafico con metricas, tarjetas y `executive_tip`.

Flujo en tendencias:
1. `build_trend_insight_pack(chart_id, dff, open_df)` calcula metricas y tarjetas segun el grafico seleccionado.
2. La UI mantiene el formato actual (3 metricas + tarjetas accionables + caption).
3. Las tarjetas con filtros sincronizan automaticamente la pestaña `Issues`.
4. La capa de personalizacion reordena tarjetas segun contexto e historico de uso en sesion.

## Patrones de insights soportados
- Presión de flujo: entrada vs salida y backlog neto.
- Envejecimiento: cola >30 días y distribución de antigüedad.
- Cuellos de estado: concentración por estado y transición final (Accepted/Ready to deploy/Deployed).
- Riesgo por prioridad: concentración y criticidad sin arrancar.
- Higiene de backlog: duplicados exactos + clusters heuristicos.
- Temas funcionales: peso real por tema y señal de cola antigua por tema.
- Carga por persona: recomendacion quirurgica por owner (atasco, criticidad, salida).
- Salud operativa: lectura ejecutiva rapida con riesgo de flujo y bloqueos.

## Navegación desde insights
Cuando un insight es accionable:
1. Se cambia a pestaña `Issues`.
2. Se aplican filtros derivados automáticamente.
3. El usuario aterriza en el detalle donde validar el hallazgo.

## Homologacion de lenguaje
- Tono: negocio y ejecucion (directo, sin ruido tecnico innecesario).
- Forma: mensaje corto, impacto, y accion sugerida.
- Dinamica: el texto debe cambiar cuando cambian filtros, ventana temporal o concentracion del backlog.
