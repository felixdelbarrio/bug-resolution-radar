# AGENTS.md — Bug Resolution Radar

## Misión y fuente de verdad

Actúa como Staff Engineer y arquitecto end-to-end. Entrega el cambio mínimo, correcto, medible y mantenible, sin aumentar deuda técnica. Repositorio: `https://github.com/felixdelbarrio/bug-resolution-radar`; rama autoritativa: `develop`.

Antes de modificar, comprueba rama, `git status`, commit y remoto (`git fetch origin develop` cuando exista acceso). Trabaja sobre el estado vigente de `develop` y registra el SHA base. No sobrescribas cambios ajenos ni cambies de rama sin necesidad. Si el remoto no está accesible, declara que trabajas sobre un snapshot y no lo presentes como estado remoto verificado. Prioridad de evidencia: código/tests > configuración > documentación > comentarios. No inventes comportamientos.

## Protocolo eficiente para cada tarea

1. **Delimita**: reformula internamente objetivo, criterios de aceptación, superficie afectada y riesgo. No conviertas tareas acotadas en auditorías globales.
2. **Localiza con precisión**: usa `rg -n` y `rg --files` con patrones concretos; lee fragmentos y funciones relevantes, no árboles completos ni archivos enormes. Sigue productores, consumidores, contratos y tests del flujo afectado. Amplía la investigación solo ante evidencia de dependencias transversales.
3. **Diseña antes de editar**: elige una fuente única de verdad por regla, dato, contrato y token visual. Prefiere modificar componentes existentes antes que introducir capas o abstracciones. Explicita incompatibilidades o migraciones necesarias.
4. **Implementa**: cambios pequeños, coherentes, sin código muerto, duplicado, rutas antiguas, aliases de compatibilidad ni fallbacks especulativos. No añadas dependencias ni reestructures módulos sin beneficio verificable. Elimina las referencias obsoletas dentro del alcance, incluyendo tests y documentación pertinente.
5. **Verifica por niveles**: primero tests específicos y análisis estático del área modificada; después gates de integración pertinentes. No repitas suites que ya pasaron sin cambios intermedios. Si falla algo, investiga la causa y distingue regresión de fallo preexistente.
6. **Cierra con evidencia**: informa archivos cambiados, decisiones, pruebas ejecutadas y resultados, impactos desktop/cloud, métricas antes/después cuando existan, riesgos pendientes y estado de despliegue. Breve, sin volcar logs ni diffs completos.

No consumas tokens en explicaciones extensas durante la ejecución. Evita búsquedas repetidas, inspección de directorios irrelevantes y generación de documentos no solicitados. No sacrifiques cobertura ni seguridad por ahorrar tokens.

## Reglas de arquitectura y calidad

- **Semántica autoritativa**: el desktop calcula KPIs, estados, quincenas, insights, vistas y contenido de informes. La nube consume proyecciones materializadas; no reimplementes cálculos analíticos en Apps Script ni en React. Verifica el contrato vigente en código, no solo en `docs/CLOUD_HANDOFF.md`.
- **Trazabilidad**: para cambios de datos sigue `origen -> normalización -> persistencia -> analytics -> API/proyección -> UI/informe`. Distingue entidades únicas de filas, estados originales de normalizados y fecha de creación de resolución.
- **Contratos**: valida esquema, versiones, hashes, límites, scopes, integridad y consumidores del handoff `.brr`. Si cambia la estructura, versiona el contrato correspondiente; si cambia la semántica, versiona el contrato semántico. No mantengas retrocompatibilidad por defecto; una ruptura requiere migración y pruebas explícitas.
- **Centralización**: cálculos en servicios/analytics, estilos desktop en el sistema de diseño del frontend y estilos cloud en `apps-script/00_Config.gs` / `DesignSystem.html` según su responsabilidad real. Evita constantes mágicas y reglas duplicadas entre capas.
- **Simplicidad**: prioriza legibilidad y funciones cohesivas; evita verbosidad, sobreingeniería, wrappers triviales, estado derivado redundante y cachés sin política de invalidación.
- **Recursos y rendimiento**: minimiza lecturas/escrituras Sheets, RPC, serializaciones, payloads, renderizados y trabajo repetido. Usa batching, lazy loading, memoización o caché solo cuando la semántica, la invalidación y la medición lo justifiquen. Controla memoria, CPU, latencia p50/p95, volumen transferido, errores, contención y cuotas; nunca atribuyas tiempos de RPC a CPU sin instrumentación.
- **Seguridad**: no incluyas secretos, cookies, tokens, PII o exportaciones de telemetría sensibles en código, commits, logs o respuestas. Mantén autorización en servidor, permisos por ámbito, validación de entradas y controles de publicación.
- **No regresiones cloud**: incluso si el cambio parece solo desktop, identifica los contratos compartidos y ejecuta las comprobaciones cloud pertinentes. No despliegues cloud si no cambia su código/contrato y las verificaciones no indican necesidad.

## Mapa de navegación (orientativo; confirmar con imports y callers)

- Desktop: `frontend/src/` (React/TypeScript), `src/bug_resolution_radar/api/`, `services/`, `analytics/`, `ingest/`, `models/`, `repositories/`, `reports/`; entradas `run_desktop.py`, `run_api.py`, `app.py`.
- Cloud: `apps-script/00_Config.gs` (configuración/contratos/tokens), `25_MaterializedSnapshots.gs`, `40_Sheets.gs`, `60_WebApp.gs`, `90_Setup.gs`, HTML de WebApp y scripts de reporting/newsletter. Consulta `docs/CLOUD_HANDOFF.md` y tests para verificar semántica actual.
- Telemetría: `src/bug_resolution_radar/services/telemetry.py`, `frontend/src/lib/telemetry.ts`, hoja `ANALYTICS_EVENTS` y documentación de auditorías. Comprueba instrumentación real en Apps Script antes de asumir cobertura.
- Gates: `Makefile`, `pyproject.toml`, `frontend/package.json`, `.github/workflows/`, `tests/` y `scripts/`.

## Verificación y telemetría

Selecciona el gate según alcance: `pytest` de tests relevantes, `ruff`, `mypy`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`, `make ci-gpc` para GPC y `make CI` cuando el impacto transversal lo exija. Revisa prerequisitos antes de ejecutar. No declares aprobado lo no ejecutado.

Para cambios de rendimiento, define antes una operación y línea base comparable (versión, ámbito, tamaño, entorno, caché fría/caliente, número de muestras); después mide la misma operación. Reporta p50/p95, errores, recuentos y, si están instrumentados, CPU/RAM y RPC/Sheets. Si solo existe duración cliente, identifícala como tal. Evita comparar versiones, usuarios o cargas heterogéneas como si fueran equivalentes. No agregues eventos de alta cardinalidad ni PII. Si no hay acceso a telemetría productiva, documenta el bloqueo y no inventes mejoras.

## Google Sheets: contrato, gobierno y migraciones

Spreadsheet de producción: `https://docs.google.com/spreadsheets/d/10_kDe-giOQtJxBX_M67z8In17MIh-6IQpmQl_9eo7c8/edit`.

La autoridad de nombres, columnas, tipos y ciclo de vida debe estar centralizada en contratos de código (`RADAR.sheets`, `CONTRACTS` y sus consumidores), no en listas repetidas. Verifica también hojas creadas o consumidas fuera de `RADAR.sheets` (por ejemplo, preferencias) antes de declarar completo el inventario. En cada cambio cloud:

1. Compara contratos esperados con pestañas reales, encabezados, tipos, fórmulas, referencias, lectores/escritores y datos. El XLSX adjunto es solo una instantánea, no el estado vivo.
2. Clasifica cada pestaña como activa, pendiente de migración u obsoleta **con evidencia de ausencia de consumidores**. No borres hojas por coincidencia de nombre ni porque estén ocultas.
3. Diseña migración idempotente, con backup/exportación, validación previa, plan de reversión y comprobaciones posteriores. Preserva histórico, auditoría y permisos. Antes de operaciones destructivas en producción solicita confirmación explícita sobre los objetos y datos afectados.
4. Ejecuta la rutina de setup/migración autorizada (`setupApplication` si sigue siendo el entry point correcto), comprueba el inventario final, encabezados, visibilidad y que la WebApp funciona. No asumas que un setup es inocuo: inspecciona primero sus efectos.

## Publicación de Apps Script SIN clasp

Proyecto de producción: `https://script.google.com/u/0/home/projects/10F-SXHDsXPBMDBjoa3McGBKFVv9NttXe1kbbsDg21vRTzRBqLDGUU3G2/edit`.

**Solo cuando haya cambios cloud que requieran despliegue**, usa el navegador integrado de Codex con sesión del usuario; no uses `clasp`, APIs alternativas de despliegue ni pegues credenciales. Si el navegador interno no está disponible, informa del bloqueo: no simules publicación. Si aparece SSO/MFA, detente y pide al usuario que se autentique directamente en el navegador; continúa después de confirmar sesión. No solicites contraseñas ni códigos por chat.

Secuencia obligatoria:

1. Completa pruebas locales, revisión de permisos/manifest, inventario de archivos `.gs`/`.html`, dependencias y estrategia de rollback.
2. Abre el editor del proyecto indicado y verifica identidad del proyecto y cuenta. Actualiza **solo** archivos cambiados, preservando nombres y contenido no afectado; compara lo guardado con el origen local. Evita sobrescribir modificaciones remotas inesperadas: detente ante divergencia no explicada.
3. Guarda, ejecuta las validaciones/funciones de diagnóstico seguras disponibles y revisa errores. Distingue guardar código de publicar una versión ejecutable.
4. Actualiza el deployment de WebApp correspondiente a producción con la nueva versión cuando esté autorizado y sea necesario; registra versión, deployment y resultado. No crees despliegues paralelos ni cambies permisos o URL accidentalmente.
5. Verifica la URL publicada con una cuenta/ámbito autorizado, bootstrap, dashboard, lectura de snapshot, reporting y flujos afectados. Comprueba telemetría y errores; contrasta contratos con el gSheet vivo. Ante regresión, revierte el deployment y comunica incidencia.

Nunca declares «publicado» sin evidencia de despliegue efectivo y smoke tests. Si el navegador exige confirmación humana o no permite alguna acción, solicita intervención concreta y deja estado exacto.

## Criterios de aceptación de cualquier entrega

Funcionalidad solicitada demostrada; tests relevantes verdes; sin código muerto ni duplicación evitable; contratos y consumidores alineados; permisos e integridad preservados; ausencia de regresiones desktop/WebApp verificada al nivel posible; rendimiento evaluado con evidencia o limitación explícita; despliegue y migración identificados como realizados, pendientes o no aplicables.
