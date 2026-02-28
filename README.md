# Bug Resolution Radar

Dashboard local para seguimiento de incidencias, rendimiento de resolución y salud operativa de backlog.

## CI/CD Status

### Rama `master`
[![Format (master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/format.yml/badge.svg?branch=master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/format.yml?query=branch%3Amaster)
[![Typecheck (master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/typecheck.yml/badge.svg?branch=master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/typecheck.yml?query=branch%3Amaster)
[![Coverage (master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/coverage.yml/badge.svg?branch=master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/coverage.yml?query=branch%3Amaster)
[![CodeQL (master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/codeql.yml/badge.svg?branch=master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/codeql.yml?query=branch%3Amaster)
[![Build Linux (master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-linux.yml/badge.svg?branch=master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-linux.yml?query=branch%3Amaster)
[![Build macOS (master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-macos.yml/badge.svg?branch=master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-macos.yml?query=branch%3Amaster)
[![Build Windows (master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-windows.yml/badge.svg?branch=master)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/build-windows.yml?query=branch%3Amaster)
[![Release Binaries](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/release-binaries.yml/badge.svg)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/release-binaries.yml)

### Rama `develop`
[![Format (develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/format.yml/badge.svg?branch=develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/format.yml?query=branch%3Adevelop)
[![Typecheck (develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/typecheck.yml/badge.svg?branch=develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/typecheck.yml?query=branch%3Adevelop)
[![Coverage (develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/coverage.yml/badge.svg?branch=develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/coverage.yml?query=branch%3Adevelop)
[![CodeQL (develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/codeql.yml/badge.svg?branch=develop)](https://github.com/felixdelbarrio/bug-resolution-radar/actions/workflows/codeql.yml?query=branch%3Adevelop)

## Objetivo

Centralizar en una sola aplicación local:
- Ingesta de incidencias desde Jira y Helix.
- KPIs operativos de backlog y resolución.
- Insights accionables para priorización, aging y cuellos de botella.
- Visualización ejecutiva y operativa en Streamlit.

## Funcionalidades principales

- Ingesta Jira con sesión de navegador o cookie manual en memoria.
- Ingesta Helix con controles de timeout, proxy y SSL.
- Dashboard con pestañas: resumen, issues, kanban, tendencias, insights y notas.
- Filtros globales sincronizados para evitar incoherencia entre tabs.
- Exportación CSV de issues filtradas.
- Persistencia local de datos y notas.
- Workflows de GitHub Actions para format, typecheck, coverage, CodeQL, build binario por entorno y release.

## Arquitectura (alto nivel)

- `src/bug_resolution_radar/ingest/`: conectores e ingesta (`jira_ingest.py`, `helix_ingest.py`).
- `src/bug_resolution_radar/ui/`: app Streamlit, páginas, componentes y dashboard modular.
- `src/bug_resolution_radar/kpis.py`: cálculo de métricas y gráficas base.
- `src/bug_resolution_radar/insights.py`: lógica de clustering e insights de incidencias similares.
- `src/bug_resolution_radar/ui/insights/engine.py`: motor de insights adaptativos para tendencias y pestañas analíticas.
- `src/bug_resolution_radar/security.py`: utilidades de endurecimiento y sanitización.
- `tests/`: suite de tests unitarios y de regresión.

## Requisitos

- Python `>=3.9`
- `pip` y entorno virtual (`venv`)
- Navegador Chrome/Edge para extracción automática de cookie (opcional)

## Instalación rápida

```bash
make setup
make run
```

App disponible en `http://localhost:8501`.

Las distribuciones binarias usan modo escritorio embebido en Windows/Linux.
En macOS, por defecto se abre en navegador del sistema para minimizar prompts
de permisos del sistema; se puede reactivar el contenedor embebido con
`BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=true`.
Para bootstrap de login, la app intenta abrir automáticamente Chrome/Edge
seleccionado por ejecutable directo (sin AppleScript), reduciendo prompts en
equipos corporativos bloqueados.

Para empaquetado local robusto, usa:

```bash
make sync-build-env
make build-macos   # o make build-linux
```

Esto valida explícitamente las dependencias de runtime desktop (`streamlit`,
`webview`) antes de generar binarios.

Si una build de escritorio falla al arrancar, revisa:

- macOS: `~/Library/Application Support/bug-resolution-radar/logs/desktop-launcher.log`

## Despliegue corporativo recomendado

Para máxima compatibilidad en equipos restringidos:

- `BUG_RESOLUTION_RADAR_CORPORATE_MODE=true`
- `BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW=false`
- `BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL=false`
- `BUG_RESOLUTION_RADAR_PREFER_SELECTED_BROWSER_BINARY=true`

Con esta combinación se evita automatización AppleScript y se mantiene la
apertura automática de URLs de login en el navegador seleccionado.

## Firma y notarización (opcional, preparado)

Sin coste puedes construir igual que hoy. Si más adelante contratas Apple
Developer, el `Makefile` ya acepta firma/notarización opcionales:

- `APPLE_CODESIGN_IDENTITY="Developer ID Application: ..."`
- `APPLE_NOTARY_PROFILE="nombre-perfil-notarytool"`

Comandos útiles:

```bash
make build-macos
make verify-macos-app
```

## Instalación manual

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
streamlit run app.py
```

## Configuración

El proyecto usa `.env` (puedes partir de `.env.example`).

Variables más relevantes:

- App: `APP_TITLE`, `DATA_PATH`, `NOTES_PATH`, `INSIGHTS_LEARNING_PATH`.
- Desktop/permisos (macOS): `BUG_RESOLUTION_RADAR_CORPORATE_MODE`,
  `BUG_RESOLUTION_RADAR_DESKTOP_WEBVIEW`, `BUG_RESOLUTION_RADAR_BROWSER_APP_CONTROL`,
  `BUG_RESOLUTION_RADAR_PREFER_SELECTED_BROWSER_BINARY`.
- Jira: `JIRA_BASE_URL`, `SUPPORTED_COUNTRIES`, `JIRA_SOURCES_JSON`, `JIRA_BROWSER`.
- Helix: `HELIX_SOURCES_JSON`, `HELIX_DATA_PATH`, `HELIX_BROWSER`, `HELIX_PROXY`, `HELIX_SSL_VERIFY`.
- Helix avanzado: `HELIX_QUERY_MODE` (`person_workitems|arsql|auto`), `HELIX_ARSQL_BASE_URL`,
  `HELIX_ARSQL_DATASOURCE_UID`, `HELIX_ARSQL_SOURCE_SERVICE_N1`, `HELIX_ARSQL_LIMIT`,
  `HELIX_ARSQL_DASHBOARD_URL`, `HELIX_DASHBOARD_URL`, `HELIX_BROWSER_LOGIN_WAIT_SECONDS`.
- KPIs: `KPI_FORTNIGHT_DAYS`, `KPI_OPEN_AGE_X_DAYS`, `KPI_AGE_BUCKETS`.
- Cache fuentes: `KEEP_CACHE_ON_SOURCE_DELETE`.

## Calidad de código y cobertura

Comandos locales:

```bash
make format
make lint
make typecheck
make test
```

Con cobertura:

```bash
pytest -q --cov=bug_resolution_radar --cov-report=term-missing
```

Umbral configurado de cobertura: `80%`.

## GitFlow

Modelo recomendado:

- `master`: rama estable/release.
- `develop`: integración continua de features.
- `feature/*`: ramas de desarrollo desde `develop`.
- `hotfix/*`: correcciones urgentes desde `master`.

## Seguridad

- Validación y sanitización de URLs/cookies en ingesta.
- Enmascarado de secretos en logs.
- Workflow CodeQL activo en CI.

Nota: el workflow de CodeQL está configurado para no fallar si el repositorio no tiene Code Scanning habilitado a nivel de GitHub Security.

## Datos locales

- Issues: `data/issues.json`
- Dump Helix: `data/helix_dump.json`
- Notas: `data/notes.json`
