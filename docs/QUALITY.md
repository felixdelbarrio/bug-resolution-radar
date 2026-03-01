# Quality

## Objective

Asegurar que cada cambio sea verificable, reproducible y entendible antes de merge.

## Local Commands

Comandos recomendados (en este orden):

```bash
make setup
make quality
```

Desglose de targets:
- `make precommit`: ejecuta hooks sobre todos los ficheros.
- `make deadcode-private`: detecta helpers privados huérfanos en `src/`.
- `make docs-check`: valida documentación y referencias locales.
- `make typecheck`: `mypy src`.
- `make test-cov`: tests con cobertura.

Comando operativo adicional (observabilidad de ingesta):
- `python scripts/ingest_profile_report.py --connector jira`
- `python scripts/ingest_profile_report.py --connector helix`

## CI Pipeline

Workflow principal:
- `.github/workflows/quality-gate.yml`

Valida:
1. instalación de dependencias y `pip check`
2. `pre-commit run --all-files`
3. `python scripts/check_docs_references.py`
4. `python scripts/check_dead_private_helpers.py`
5. `ruff check src scripts tests`
6. `mypy src`
7. `pytest -q --cov=bug_resolution_radar --cov-report=term-missing --cov-report=xml`

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
