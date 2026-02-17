# Insights Engine

## Objetivo
Generar mensajes ejecutivos dinámicos, no estáticos, adaptados al estado real del backlog filtrado.

## Dónde vive
- Tendencias: `src/bug_resolution_radar/ui/dashboard/trends.py`
- Resumen ejecutivo: `src/bug_resolution_radar/ui/dashboard/overview.py`
- Cálculos reutilizables: `src/bug_resolution_radar/ui/dashboard/insights.py`

## Reglas de construcción
- Cada insight se calcula sobre el dataframe filtrado actual.
- Un insight solo es "accionable" si incluye filtros aplicables (`status`, `priority`, `assignee`).
- Insights sin filtro se muestran como explicación contextual (sin navegación forzada).
- Los insights se priorizan por puntuación de relevancia (`score`) para que cambien con la situación operativa.

## Patrones de insights soportados
- Presión de flujo: entrada vs salida y backlog neto.
- Envejecimiento: cola >30 días y distribución de antigüedad.
- Cuellos de estado: concentración por estado y transición final (Accepted/Ready to deploy/Deployed).
- Riesgo por prioridad: concentración y criticidad sin arrancar.

## Navegación desde insights
Cuando un insight es accionable:
1. Se cambia a pestaña `Issues`.
2. Se aplican filtros derivados automáticamente.
3. El usuario aterriza en el detalle donde validar el hallazgo.
