# Bug Resolution Radar

Aplicación local para ingesta, análisis y seguimiento operativo de incidencias Jira/Helix con foco en ejecución diaria y reporting ejecutivo.

## CI/CD Status

[![Quality Gate (develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/quality-gate.yml/badge.svg?branch=develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/quality-gate.yml?query=branch%3Adevelop)
[![Quality Gate (master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/quality-gate.yml/badge.svg?branch=master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/quality-gate.yml?query=branch%3Amaster)
[![CodeQL](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/codeql.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/codeql.yml)
[![Build Linux](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-linux.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-linux.yml)
[![Build macOS](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-macos.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-macos.yml)
[![Build Windows](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-windows.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-windows.yml)
[![Release Binaries](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/release-binaries.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/release-binaries.yml)

## Support / Donaciones

[![Sponsor](https://img.shields.io/badge/Sponsor-GitHub%20Sponsors-2ea44f.svg)](https://github.com/sponsors/felixdelbarrio)
[![Donate](https://img.shields.io/badge/Donate-PayPal-blue.svg)](https://paypal.me/felixdelbarrio)

Si este proyecto te aporta valor, puedes apoyarlo por GitHub Sponsors o PayPal.

## Quick Start

Requisitos:
- Python `>=3.9`
- `pip`
- Navegador Chrome o Edge (opcional, para bootstrap automático de sesión)

Instalación y ejecución:

```bash
make setup
make CI
make run
```

`make run` abre el contenedor desktop local.
Para servir la SPA React + FastAPI sin shell desktop:

```bash
make run-api
```

La app queda disponible en `http://127.0.0.1:8000`.
`make CI` valida formato, lint, tipado, guardias de documentación/código muerto y tests con cobertura.

## Architecture

Resumen de capas:
- `src/bug_resolution_radar/config.py`: contrato único de configuración y persistencia `.env`.
- `frontend/src/`: SPA React/Vite, routing, estado URL-driven y consumo HTTP.
- `src/bug_resolution_radar/api/app.py`: contratos FastAPI, descargas y serving de la SPA.
- `src/bug_resolution_radar/ingest/`: conectores Jira/Helix y runtime de navegador.
- `src/bug_resolution_radar/analytics/`: KPIs, semántica de estado y ventana de análisis.
- `src/bug_resolution_radar/ui/`: módulos legacy de Streamlit aún presentes como referencia de migración y utilidades de exportación históricas; el runtime activo ya no depende de esta shell.
- `src/bug_resolution_radar/reports/executive_ppt.py`: export ejecutivo PPT alineado con filtros y scope.
- `src/bug_resolution_radar/services/`: notas, mantenimiento de fuentes, snapshots, exportes e ingesta asíncrona.

## Documentation

Guía detallada por tema:
- [Arquitectura Runtime](docs/ARCHITECTURE.md)
- [Mapa de Código](docs/CODEBASE.md)
- [Motor de Insights](docs/INSIGHTS_ENGINE.md)
- [Theming y reglas visuales](docs/THEMING.md)
- [Calidad y CI](docs/QUALITY.md)

## Desktop Runtime

Variables recomendadas para ejecución local/desktop:
- `BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=true` (contenedor embebido)
- `BUG_RESOLUTION_RADAR_HOME=/ruta/escribible` (opcional, para datos/config fuera del repo)

## Configuration

El proyecto usa `.env` (puedes partir de `.env.example`).

Variables clave:
- App: `APP_TITLE`, `DATA_PATH`, `NOTES_PATH`, `INSIGHTS_LEARNING_PATH`, `LOG_LEVEL`.
- Jira: `JIRA_BASE_URL`, `JIRA_SOURCES_JSON`, `JIRA_INGEST_DISABLED_SOURCES_JSON`, `JIRA_BROWSER`, `JIRA_BROWSER_LOGIN_URL`.
- Helix: `HELIX_SOURCES_JSON`, `HELIX_INGEST_DISABLED_SOURCES_JSON`, `HELIX_DATA_PATH`, `HELIX_BROWSER`, `HELIX_DASHBOARD_URL`, `HELIX_PROXY`, `HELIX_SSL_VERIFY`.
- ARSQL: `HELIX_ARSQL_BASE_URL`, `HELIX_ARSQL_DATASOURCE_UID`, `HELIX_ARSQL_SOURCE_SERVICE_N1`, `HELIX_ARSQL_LIMIT`, `HELIX_ARSQL_DASHBOARD_URL`, `HELIX_ARSQL_GRAFANA_ORG_ID`.
- Ventana de análisis: `ANALYSIS_LOOKBACK_MONTHS` (recomendado: `12`).
- Hardening de ingesta:
  - `INGEST_PROFILE_ENABLED`, `INGEST_PROFILE_JSONL_PATH`
  - `INGEST_CIRCUIT_ENABLED`, `INGEST_CIRCUIT_STATE_PATH`
  - `INGEST_CIRCUIT_FAILURE_THRESHOLD`, `INGEST_CIRCUIT_WINDOW_SECONDS`, `INGEST_CIRCUIT_COOLDOWN_SECONDS`

## Quality

Comandos locales principales:

```bash
make setup
make CI
make test
```

`make CI` valida:
- `ruff format --check`, `black --check`, `ruff check`
- `mypy src`
- `scripts/check_dead_private_helpers.py`
- `scripts/check_docs_references.py`
- `pytest --cov`

Para revisar el último perfil de ingesta:

```bash
python3 scripts/ingest_profile_report.py --connector jira
python3 scripts/ingest_profile_report.py --connector helix
```

## Build and Packaging

Para empaquetado local robusto:

```bash
make build
```

Firma/notarización (opcional, macOS):
- `APPLE_CODESIGN_IDENTITY="Developer ID Application: ..."`
- `APPLE_NOTARY_PROFILE="nombre-perfil-notarytool"`

## Local Data

- Issues: `data/issues.json`
- Read model de issues: `data/issues.parquet`
- Índice ligero de workspace: `data/issues.workspace.json`
- Helix dump: `data/helix_dump.json`
- Read model raw de Helix: `data/helix_dump.raw.parquet`
- Metadatos ligeros de Helix: `data/helix_dump.meta.json`
- Insights learning: `data/insights_learning.json`
- Notas: `data/notes.json`
- Observabilidad de ingesta:
  - `data/observability/ingest_profiles.jsonl`
  - `data/observability/ingest_circuit_state.json`
