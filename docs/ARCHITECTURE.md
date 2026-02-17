# Architecture

## Objetivo
Aplicación Streamlit para gestión operativa de incidencias multi-fuente, con foco en análisis de backlog, insights accionables y navegación orientada a ejecución.

## Capas
- `src/bug_resolution_radar/config.py`: carga de configuración y fuentes por país/origen.
- `src/bug_resolution_radar/ui/app.py`: shell principal (hero, scope país/origen, navegación, tema).
- `src/bug_resolution_radar/ui/pages/*.py`: ruteo por secciones funcionales.
- `src/bug_resolution_radar/ui/dashboard/*.py`: lógica de vistas core (Resumen, Issues, Kanban, Tendencias, Notas).
- `src/bug_resolution_radar/ui/insights/*.py`: vistas analíticas especializadas (Top tópicos, Duplicados, Personas, Salud operativa).
- `src/bug_resolution_radar/ui/components/*.py`: componentes reutilizables (filtros, tabla/cards de issues).
- `src/bug_resolution_radar/ui/style.py`: tokens visuales, tema claro/oscuro y estilo Plotly.

## Flujo de datos
1. `ui/app.py` inicializa estado global y configuración.
2. Se aplica scope por país/origen (`workspace_country`, `workspace_source_id`).
3. `pages/dashboard_page.py` carga dataset y aplica filtros canónicos compartidos.
4. Cada sección consume `DashboardDataContext` para evitar recomputaciones innecesarias.
5. Acciones de insights pueden sincronizar filtros y navegar automáticamente a `Issues`.

## Estado de sesión clave
- Navegación: `workspace_mode`, `workspace_section`, `workspace_section_label`.
- Tema: `workspace_dark_mode`.
- Scope: `workspace_country`, `workspace_source_id`.
- Filtros canónicos: `FILTER_STATUS_KEY`, `FILTER_PRIORITY_KEY`, `FILTER_ASSIGNEE_KEY`.
- Deep-linking interno: `__jump_to_tab`, `__jump_to_insights_tab`.

## Principios de diseño técnico
- Fuente única de verdad para filtros (evita desalineación entre pestañas).
- Cálculo sobre dataframes ya filtrados (insights coherentes con lo que ve el usuario).
- UI con componentes reutilizables y estilos centralizados.
- Exportación mínima y consistente (CSV/HTML/SVG donde aplique).
