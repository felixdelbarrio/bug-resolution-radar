# Theming

## Objetivo
Mantener una identidad visual coherente en modo claro y oscuro con un único sistema de tokens.

## Implementación
- `src/bug_resolution_radar/ui/app.py`: toggle de tema en barra superior (`workspace_dark_mode`).
- `src/bug_resolution_radar/ui/style.py`: inyección de variables CSS para ambos modos.
- `apply_plotly_bbva(...)`: adapta tipografía, rejilla y leyendas de gráficos según tema activo.

## Tokens clave
- Superficies: `--bbva-surface`, `--bbva-surface-2`
- Texto: `--bbva-text`, `--bbva-text-muted`
- Borde: `--bbva-border`, `--bbva-border-strong`
- Navegación: `--bbva-tab-*`

## Reglas
- Evitar estilos hardcoded en componentes nuevos; usar variables.
- Mantener contraste suficiente para lectura de KPIs y etiquetas.
- Los iconos de acciones globales deben ser discretos y consistentes.
