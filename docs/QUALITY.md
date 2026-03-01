# Quality

## Objective

Asegurar que cada cambio sea verificable, reproducible y entendible antes de merge.

## Local Commands

Comandos recomendados (en este orden):

```bash
make setup
make CI
```

Targets públicos disponibles:
- `make setup`: prepara venv + dependencias de desarrollo.
- `make CI`: cadena completa de calidad usada en local/CI.
- `make test`: ejecución rápida de tests.
- `make run`: arranque local de la app.
- `make build`: build oficial con regresión PPT previa y empaquetado por OS.

Detalle de la cadena `make CI`:
- `ruff format --check .`
- `black --check .`
- `ruff check .`
- `mypy src`
- `python scripts/check_dead_private_helpers.py`
- `python scripts/check_docs_references.py`
- `pytest -q --cov=bug_resolution_radar --cov-report=term-missing --cov-report=xml`

Comando operativo adicional (observabilidad de ingesta):
- `python scripts/ingest_profile_report.py --connector jira`
- `python scripts/ingest_profile_report.py --connector helix`

## CI Pipeline

Workflow principal:
- `.github/workflows/quality-gate.yml`

Valida:
1. instalación de dependencias y `pip check`
2. `ruff format --check .`
3. `black --check .`
4. `ruff check .`
5. `mypy src`
6. `python scripts/check_dead_private_helpers.py`
7. `python scripts/check_docs_references.py`
8. `pytest -q --cov=bug_resolution_radar --cov-report=term-missing --cov-report=xml`

## Dead Code Policy

- No se mantiene retrocompatibilidad de configuración fuera del contrato actual.
- Cualquier helper privado no referenciado en `src/` o `tests/` debe eliminarse.
- Los workflows y comandos duplicados se eliminan para evitar deriva.

## Documentation Policy

- Toda ruta de código documentada debe existir.
- `README.md` y `docs/` pasan por `scripts/check_docs_references.py`.
- No se aceptan referencias a módulos obsoletos.

## Release Safety

Además de `quality-gate`:
- builds por plataforma (`build-linux`, `build-macos`, `build-windows`)
- análisis estático de seguridad (`codeql`)
- empaquetado/release (`release-binaries`)

## Ingestion Hardening

Variables de entorno (opcional):
- `INGEST_PROFILE_ENABLED` (`true/false`, default `true`)
- `INGEST_PROFILE_JSONL_PATH` (default `data/observability/ingest_profiles.jsonl`)
- `INGEST_CIRCUIT_ENABLED` (`true/false`, default `true`)
- `INGEST_CIRCUIT_STATE_PATH` (default `data/observability/ingest_circuit_state.json`)
- `INGEST_CIRCUIT_FAILURE_THRESHOLD` (default `3`)
- `INGEST_CIRCUIT_WINDOW_SECONDS` (default `1800`)
- `INGEST_CIRCUIT_COOLDOWN_SECONDS` (default `900`)
