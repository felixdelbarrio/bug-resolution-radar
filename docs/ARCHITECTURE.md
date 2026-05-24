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

## Finalist Lookup Flow

1. Jira es la fuente de referencias funcionales: el lookup finalista que consulta ARSQL extrae `INC...` solo desde la descripción y excluye Jira con estado `Accepted`, `Ready to deploy`, `Deployed` o el legado `Acepted`.
2. La colección se deduplica por país y `Servicio Origen BU/UG`; no se particiona por origen Jira porque las mismas INC pueden aparecer en varios orígenes del país.
3. Antes de llamar a ARSQL, el backend cruza las INC contra el histórico Helix local. Si la incidencia ya está en estado finalista, se reutiliza, se normaliza al origen canónico `Lookup estados finalistas Jira` y se evita la llamada.
4. Solo las INC pendientes o no finalistas se envían a ARSQL en lotes explícitos. El lookup exacto no hereda IDs pendientes de cache ni filtros amplios de ingesta regular.
5. Dashboard y reportes aplican el estado efectivo finalista al scope visible usando el histórico Helix completo del país, no solo el subconjunto recortado por ventana de análisis.
6. Los reportes PPT consumen el dataset normalizado completo para resolver URLs Helix y linkifican cualquier `INC...` visible en tablas cuando existe URL localizada.
7. Las listas de incidencias abiertas por antigüedad filtran y renderizan por días completos para que una sección `>30 días` no muestre filas como `30 días`.

## Module Layers

- Frontend
  - `frontend/src`
  - Responsabilidad: navegación, estado de vista, maquetación, interacción y consumo de contratos HTTP.

- API
  - `src/bug_resolution_radar/api/app.py`
  - Responsabilidad: serialización, validación HTTP, descarga de artefactos y serving de la SPA.

- Servicios backend
  - `src/bug_resolution_radar/services`
  - Responsabilidad: snapshots, orquestación de ingesta, lookup finalista, settings, notas, exportes y mantenimiento.

- Analítica
  - `src/bug_resolution_radar/analytics`
  - Responsabilidad: filtros, scopes, KPIs, insights, duplicados y chart specs.

- Persistencia y reporting
  - `src/bug_resolution_radar/repositories`
  - `src/bug_resolution_radar/reports`
  - Responsabilidad: almacenamiento local, read models y generación de PPT/artefactos con enlaces Jira/Helix.

## Permission Policy

- No se accede a carpetas de exportación durante render o carga inicial.
- No se abren navegadores ni se consultan cookies salvo en acciones de ingesta o apertura explícita.
- La descarga de informes se entrega como stream HTTP; la decisión de guardar ocurre en el clic del usuario.

## Packaging

- `make run` compila React y abre la shell desktop autocontenida.
- `make CI` replica localmente los checks de GitHub (`format`, `typecheck`, `coverage`, `quality-gate`).
- `make build` compila React y empaqueta `run_desktop.py`.
- Los workflows de Linux, macOS y Windows construyen la SPA antes del binario.
