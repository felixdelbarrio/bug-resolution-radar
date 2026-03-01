# Theming

## Objective

Mantener una identidad visual consistente entre modo claro/oscuro sin estilos dispersos ni hardcodes no trazables.

## Theme Tokens

Origen de tokens:
- `src/bug_resolution_radar/theme/design_tokens.py`
- `src/bug_resolution_radar/ui/style.py`

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
- `apply_plotly_bbva(...)` en `src/bug_resolution_radar/ui/style.py`

Criterios:
- Títulos y leyendas sin ruido visual.
- Colores semánticos estables (estado/prioridad).
- Margen y tipografía homogéneos para export (UI + PPT).

## Streamlit Integration

- La preferencia se gestiona en `workspace_dark_mode`.
- `ui/app.py` sincroniza la preferencia en estado y runtime.
- `config_page.py` persiste el modo visual en `.env`.

## Safe Customization Checklist

Antes de mergear cambios visuales:
1. Revisar modo claro y oscuro.
2. Verificar chips de estado/prioridad y alertas.
3. Validar que exportes (HTML/PPT) mantienen legibilidad.
4. Ejecutar `make quality`.
