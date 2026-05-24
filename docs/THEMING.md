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
