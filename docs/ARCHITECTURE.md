# Architecture

## Objective

Separar completamente presentación, runtime desktop y lógica de negocio:

1. React renderiza la experiencia de usuario.
2. FastAPI expone contratos estables para dashboard, insights, reportes, notas, ingestas y configuración.
3. El backend concentra cálculo, normalización, persistencia y exportación.
4. El contenedor desktop solo hospeda la SPA local y no ejecuta lógica de UI.

## Runtime Flow

1. `run_desktop.py` arranca una API local interna y abre una shell desktop ligera con `pywebview`.
2. `run_api.py` sirve `src/bug_resolution_radar/api/app.py`.
3. La SPA React compilada en `frontend/dist` se sirve como estático local.
4. React consume `/api/*` y mantiene el estado de filtros/scope en la URL.
5. Ingesta, apertura de navegador y descargas solo ocurren bajo acción explícita del usuario.

## Module Layers

- Frontend
  - `frontend/src`
  - Responsabilidad: navegación, estado de vista, maquetación, interacción y consumo de contratos HTTP.

- API
  - `src/bug_resolution_radar/api/app.py`
  - Responsabilidad: serialización, validación HTTP, descarga de artefactos y serving de la SPA.

- Servicios backend
  - `src/bug_resolution_radar/services`
  - Responsabilidad: snapshots, orquestación de ingesta, settings, notas, exportes y mantenimiento.

- Analítica
  - `src/bug_resolution_radar/analytics`
  - Responsabilidad: filtros, scopes, KPIs, insights, duplicados y chart specs.

- Persistencia y reporting
  - `src/bug_resolution_radar/repositories`
  - `src/bug_resolution_radar/reports`
  - Responsabilidad: almacenamiento local y generación de PPT/artefactos.

## Permission Policy

- No se accede a carpetas de exportación durante render o carga inicial.
- No se abren navegadores ni se consultan cookies salvo en acciones de ingesta o apertura explícita.
- La descarga de informes se entrega como stream HTTP; la decisión de guardar ocurre en el clic del usuario.

## Packaging

- `make run` compila React y abre la shell desktop autocontenida.
- `make run-dev` levanta API y frontend Vite para desarrollo en navegador.
- `make build` compila React y empaqueta `run_desktop.py`.
- Los workflows de Linux, macOS y Windows construyen la SPA antes del binario.
