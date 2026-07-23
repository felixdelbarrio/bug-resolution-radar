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
`make CI` valida formato, tipado, cobertura, build frontend, `pip check` y guardias de documentación/código muerto.

`make run` y `make build` detienen la ejecución si la rama local está por detrás
de su upstream conocido, para evitar empaquetar un frontend antiguo. Actualiza
con `git pull --ff-only`; para reproducir deliberadamente un commit histórico se
puede usar `make ALLOW_STALE_SOURCE=1 run` o `make ALLOW_STALE_SOURCE=1 build`.

## Architecture

Resumen de capas:
- `src/bug_resolution_radar/config.py`: contrato único de configuración y persistencia `.env`.
- `frontend/src/`: SPA React/Vite, routing, estado URL-driven y consumo HTTP.
- `src/bug_resolution_radar/api/app.py`: contratos FastAPI, descargas y serving de la SPA.
- `src/bug_resolution_radar/ingest/`: conectores Jira/Helix y runtime de navegador.
- `src/bug_resolution_radar/analytics/`: KPIs, semántica de estado y ventana de análisis.
- `src/bug_resolution_radar/reports/executive_ppt.py`: export ejecutivo PPT alineado con filtros y scope.
- `src/bug_resolution_radar/services/`: notas, mantenimiento de fuentes, snapshots, merge/mapeo de ingesta, exportes e ingesta asíncrona.
- `src/bug_resolution_radar/services/data_transfer.py`: handoff `.brr` v2, compacto y verificable, desde escritorio hacia GPC.
- El runtime de presentación es 100% React/FastAPI; no queda shell Python legacy ni dependencia de UI obsoleta en el paquete.

Flujo cloud:
- Escritorio materializa el racional completo y genera el PPTX local autoritativo.
- El handoff solo contiene `projection.json` y ese PPTX, ambos con SHA-256.
- GPC publica un snapshot estático por geografía/vista, convierte el PPTX a Google Slides
  y sirve la WebApp sin filtros ni recálculos de negocio.
- La newsletter usa los hechos del mismo snapshot, enlaza Slides y adjunta el PPTX exacto.

Flujo clave de estados finalistas:
- El lookup ARSQL solo toma referencias `INC...` desde la descripción de Jira y descarta Jira ya finalistas (`Accepted`, `Ready to deploy`, `Deployed`/`Acepted`) antes de deduplicar por país/`Servicio Origen BU/UG`.
- Antes de lanzar ARSQL, el conjunto se cruza con el histórico Helix local. Los INC ya finalistas se reutilizan y se persisten bajo el origen canónico `Lookup estados finalistas Jira`.
- El cruce finalista usa el histórico Helix completo del país aunque la vista del reporte esté recortada por `ANALYSIS_LOOKBACK_MONTHS`; las filas Jira con Helix finalista quedan fuera de listas abiertas.
- Los PPT de seguimiento enlazan cualquier `INC...` visible en tablas cuando existe URL Helix en el dataset normalizado o en discrepancias finalistas, y las secciones `>30 días` usan días completos para evitar filas visibles como `30 días`.

## Documentation

Guía detallada por tema:
- [Arquitectura Runtime](docs/ARCHITECTURE.md)
- [Mapa de Código](docs/CODEBASE.md)
- [Motor de Insights](docs/INSIGHTS_ENGINE.md)
- [Theming y reglas visuales](docs/THEMING.md)
- [Handoff de escritorio a GPC](docs/CLOUD_HANDOFF.md)
- [Calidad y CI](docs/QUALITY.md)

## Desktop Runtime

Variables recomendadas para ejecución local/desktop:
- `BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=true` (contenedor embebido)
- `BUG_RESOLUTION_RADAR_HOME=/ruta/escribible` (opcional, para datos/config fuera del repo)

## Configuration

El proyecto usa `.env` (puedes partir de `.env.example`).

Variables clave:
- App: `APP_TITLE`, `DATA_PATH`, `NOTES_PATH`, `INSIGHTS_LEARNING_PATH`, `LOG_LEVEL`.
- Jira: `JIRA_BASE_URL`, `SUPPORTED_COUNTRIES`, `JIRA_SOURCES_JSON`, `JIRA_INGEST_DISABLED_SOURCES_JSON`, `JIRA_BROWSER`, `JIRA_BROWSER_LOGIN_URL`.
- Helix: `HELIX_SOURCES_JSON`, `HELIX_INGEST_DISABLED_SOURCES_JSON`, `HELIX_DATA_PATH`, `HELIX_BROWSER`, `HELIX_DASHBOARD_URL`, `HELIX_PROXY`, `HELIX_SSL_VERIFY`.
- ARSQL: `HELIX_ARSQL_BASE_URL`, `HELIX_ARSQL_DATASOURCE_UID`, `HELIX_ARSQL_SOURCE_SERVICE_N1`, `HELIX_ARSQL_LIMIT`, `HELIX_ARSQL_DASHBOARD_URL`, `HELIX_ARSQL_GRAFANA_ORG_ID`.
- Ventana de análisis: `ANALYSIS_LOOKBACK_MONTHS` (recomendado: `12`).
- Hardening de ingesta:
  - `INGEST_PROFILE_ENABLED`, `INGEST_PROFILE_JSONL_PATH`
  - `INGEST_CIRCUIT_ENABLED`, `INGEST_CIRCUIT_STATE_PATH`
  - `INGEST_CIRCUIT_FAILURE_THRESHOLD`, `INGEST_CIRCUIT_WINDOW_SECONDS`, `INGEST_CIRCUIT_COOLDOWN_SECONDS`

`SUPPORTED_COUNTRIES` se normaliza con acentos canónicos; por ejemplo `Peru` y `Perú` se consolidan como `Perú`.

## Quality

Comandos locales principales:

```bash
make setup
make CI
make test
```

`make CI` valida:
- `ruff format --check`
- `mypy src`
- `pip check`
- build frontend
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
- Historial de handoffs cloud: `data/data_transfer_history.json`
- Observabilidad de ingesta:
  - `data/observability/ingest_profiles.jsonl`
  - `data/observability/ingest_circuit_state.json`

Los handoffs cloud se crean desde `Ingesta > Exportar` y se guardan en la carpeta
configurada para Descargas de Informes. Son entregas unidireccionales para GPC:
incluyen la proyección inmutable de la vista activa y la presentación local exacta,
sin duplicar los datasets fuente.
