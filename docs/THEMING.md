# Theming

## Objective

Mantener una identidad visual consistente entre modo claro/oscuro sin estilos dispersos ni hardcodes no trazables.

## Theme Tokens

Origen de tokens:
- `src/bug_resolution_radar/theme/design_tokens.py`
- `src/bug_resolution_radar/theme/semantic_colors.py`
- `frontend/src/styles/app.css`
- `frontend/src/lib/semanticColors.ts`

Tokens de referencia:
- Superficies: `--bbva-surface`, `--bbva-surface-elevated`, `--bbva-surface-2`
- Texto: `--bbva-text`, `--bbva-text-muted`
- Bordes: `--bbva-border`, `--bbva-border-strong`
- Navegación: `--bbva-tab-*`
- Estado objetivo (deployed): `--bbva-goal-green`, `--bbva-goal-green-bg`

Fundaciones BBVA Experience:
- Primarios: Midnight `#070E46`, Electric `#001391`, Royal Dark `#2165CA`,
  Royal `#0C6DFF`, Serene Dark `#53A9EF`, Serene `#85C8FF` y
  Blue Light `#D6E9F8`.
- Neutros: Black `#000519`, Grey 900 `#11192D`, Grey 800 `#222C42`,
  Grey 700 `#334056`, Grey 600 `#46536D`, Grey 500 `#ADB8C2`,
  Grey 400 `#CAD1D8`, Grey 300 `#E2E6EA`, Grey 200 `#F7F8F8` y White.
- Benton Sans es la tipografía funcional; Tiempos Headline Bold se reserva para
  titulares.
- La retícula usa incrementos de 8 px, margen/gutter de 24 px y ancho de contenido
  máximo de 1296 px.
- El radio principal es 16 px y el de elementos anidados o botones, 8 px.

Reglas:
- Cualquier componente nuevo debe consumir variables CSS, no valores hex directos salvo justificación explícita.
- Contraste mínimo legible en tablas, chips y ejes de gráficos.

## Plotly Rules

Aplicación de tema:
- `apply_plotly_bbva(...)` en `src/bug_resolution_radar/theme/plotly_style.py`

Criterios:
- Títulos y leyendas sin ruido visual.
- Colores semánticos estables (estado/prioridad).
- Margen y tipografía homogéneos para API, frontend y PPT.

## React Integration

- La preferencia visual vive en la SPA y se persiste a través de contratos de settings.
- `frontend/src/styles/app.css` define tokens claros/oscuros y superficies base.
- `frontend/src/lib/semanticColors.ts` concentra estilos de chips/botones por estado y prioridad.

## Select/Popover Rules

- Los controles de selección se estilizan en:
  - `frontend/src/styles/app.css`
- Reglas operativas:
  - truncado de texto en una sola línea (`overflow + ellipsis`)
  - popover con altura acotada y scroll (`max-height` + `overflow-y:auto`) para evitar paneles gigantes con hueco vacío
- Cualquier cambio de selectors en popovers debe validar:
  - `npm --prefix frontend run build`
  - `make CI`

## Safe Customization Checklist

Antes de mergear cambios visuales:
1. Revisar modo claro y oscuro.
2. Verificar chips de estado/prioridad y alertas.
3. Validar que exportes (HTML/PPT) mantienen legibilidad.
4. Ejecutar `make quality`.
