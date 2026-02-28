# Bug Resolution Radar

Aplicación local para ingesta, análisis y seguimiento operativo de incidencias Jira/Helix con foco en ejecución diaria y reporting ejecutivo.

## CI/CD Status

[![Quality Gate](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/quality-gate.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/quality-gate.yml)
[![CodeQL](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/codeql.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/codeql.yml)
[![Build Linux](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-linux.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-linux.yml)
[![Build macOS](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-macos.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-macos.yml)
[![Build Windows](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-windows.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-windows.yml)
[![Release Binaries](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/release-binaries.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/release-binaries.yml)

## Quick Start

Requisitos:
- Python `>=3.9`
- `pip`
- Navegador Chrome o Edge (opcional, para bootstrap automático de sesión)

Instalación y ejecución:

```bash
make setup
make run
```

La app queda disponible en `http://localhost:8501`.

## Architecture

Resumen de capas:
- `src/bug_resolution_radar/config.py`: contrato único de configuración y persistencia `.env`.
- `src/bug_resolution_radar/ingest/`: conectores Jira/Helix y runtime de navegador.
- `src/bug_resolution_radar/analytics/`: KPIs, semántica de estado y ventana de análisis.
- `src/bug_resolution_radar/ui/`: shell Streamlit, páginas, dashboard, componentes e insights.
- `src/bug_resolution_radar/reports/executive_ppt.py`: export ejecutivo PPT alineado con filtros y scope.
- `src/bug_resolution_radar/services/`: notas y mantenimiento de cachés/fuentes.

Documentación completa:
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/CODEBASE.md`](docs/CODEBASE.md)
- [`docs/INSIGHTS_ENGINE.md`](docs/INSIGHTS_ENGINE.md)
- [`docs/THEMING.md`](docs/THEMING.md)
- [`docs/QUALITY.md`](docs/QUALITY.md)

## Corporate Deployment

Perfil recomendado para equipos corporativos restringidos:

- `BUG_RESOLUTION_RADAR_CORPORATE_MODE=true`
- `BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=false`
- `BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL=false`
- `BUG_RESOLUTION_RADAR_PREFER_SELECTED_BROWSER_BINARY=true`
- `BUG_RESOLUTION_RADAR_BROWSER_BOOTSTRAP_MAX_TABS=3`

Opcional (si Chrome/Edge están fuera de rutas estándar):
- `BUG_RESOLUTION_RADAR_CHROME_BINARY=/ruta/a/chrome`
- `BUG_RESOLUTION_RADAR_EDGE_BINARY=/ruta/a/msedge`

Con esta configuración se minimizan prompts de permisos en macOS corporativo y se mantiene apertura automática de URLs de login en el navegador seleccionado.

## Configuration

El proyecto usa `.env` (puedes partir de `.env.example`).

Variables clave:
- App: `APP_TITLE`, `DATA_PATH`, `NOTES_PATH`, `INSIGHTS_LEARNING_PATH`, `LOG_LEVEL`.
- Jira: `JIRA_BASE_URL`, `JIRA_SOURCES_JSON`, `JIRA_BROWSER`, `JIRA_BROWSER_LOGIN_URL`.
- Helix: `HELIX_SOURCES_JSON`, `HELIX_DATA_PATH`, `HELIX_BROWSER`, `HELIX_DASHBOARD_URL`, `HELIX_PROXY`, `HELIX_SSL_VERIFY`.
- ARSQL: `HELIX_ARSQL_BASE_URL`, `HELIX_ARSQL_DATASOURCE_UID`, `HELIX_ARSQL_SOURCE_SERVICE_N1`, `HELIX_ARSQL_LIMIT`, `HELIX_ARSQL_DASHBOARD_URL`.
- Ventana de análisis: `ANALYSIS_LOOKBACK_MONTHS` (`0` = máxima profundidad disponible).

## Quality

Comandos locales principales:

```bash
make format
make lint
make typecheck
make test
make test-cov
make deadcode-private
make docs-check
make precommit
make quality
```

Qué valida `make quality`:
- Hooks completos de pre-commit (Ruff + guardias de código/documentación).
- Integridad de documentación y referencias internas.
- `mypy` estricto sobre `src`.
- Suite de tests con cobertura.

## Build and Packaging

Para empaquetado local robusto:

```bash
make sync-build-env
make build-macos   # o make build-linux
```

Firma/notarización (opcional, preparado):
- `APPLE_CODESIGN_IDENTITY="Developer ID Application: ..."`
- `APPLE_NOTARY_PROFILE="nombre-perfil-notarytool"`

Comando de verificación en macOS:

```bash
make verify-macos-app
```

## Local Data

- Issues: `data/issues.json`
- Helix dump: `data/helix_dump.json`
- Insights learning: `data/insights_learning.json`
- Notas: `data/notes.json`
