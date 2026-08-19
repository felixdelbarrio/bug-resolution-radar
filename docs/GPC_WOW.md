# WoW de cambios y promociones

## Objetivo

Este Way of Working controla cualquier cambio desde una rama de trabajo hasta
`develop` y desde `develop` hasta `master`. El mismo modelo cubre backend, escritorio,
proyección cloud y WebApp GPC.

## Flujo feature → develop

1. Crear una rama corta desde el último `develop`, con prefijo `codex/`, `feature/` o
   `fix/`.
2. Ejecutar `make CI`. Para iterar solo sobre cloud puede usarse primero
   `make ci-gpc`.
3. Probar visualmente la WebApp con `make runWebapp`. El simulador usa las plantillas
   reales, contrato v3 y RPC locales; no envía correos, no escribe Sheets y no accede
   a Drive.
4. Abrir PR draft hacia `develop` con motivación, impacto, riesgos, pruebas y capturas
   cuando cambie presentación. La plantilla de PR convierte esta evidencia en una
   lista de control obligatoria y `CODEOWNERS` solicita revisión de las superficies
   críticas de GPC, contrato, seguridad y automatización.
5. Convertirlo a ready únicamente cuando todos los checks requeridos estén verdes y
   las conversaciones estén resueltas.
6. Hacer merge mediante squash. No se permiten pushes directos a `develop`.

Checks requeridos para `develop`:

- `GPC Quality Gate / GPC contract, Apps Script and local WebApp`
- `Quality Gate / quality-gate`
- `Coverage / coverage`
- `Format / format`
- `Typecheck / typecheck`
- `CodeQL / Analyze (Python)`

La GPC Quality Gate valida contrato `.brr` v3, proyección, newsletter, Apps Script,
manifest, ausencia de runtime retirado, JavaScript servidor/cliente, funciones
globales duplicadas y composición completa de la WebApp local.

## Flujo develop → master

1. La promoción se realiza mediante un PR exclusivo `develop → master`; nunca con
   push directo.
2. El PR solo contiene cambios ya integrados y estabilizados en `develop`.
3. Además de los checks anteriores, deben finalizar correctamente:

- `Build Binary (Linux)`
- `Build Binary (macOS)`
- `Build Binary (Windows)`

4. Se requiere al menos una aprobación de una persona distinta del autor para
   cambios de contrato, seguridad, persistencia, newsletter o despliegue.
5. Tras el merge se crea un tag `v*` solo si se quiere publicar binarios. El workflow
   de release comprueba que el commit etiquetado pertenece a `master`.

## Reglas de protección en GitHub

Configurar rulesets para `develop` y `master` con:

- Bloquear pushes directos y force-push.
- Exigir pull request antes de merge.
- Exigir resolución de conversaciones.
- Activar **Require branches to be up to date before merging**.
- Exigir todos los checks enumerados para cada rama.
- Exigir una aprobación en `develop` y dos en `master` cuando el equipo lo permita.
- Exigir aprobación de `CODEOWNERS` para las rutas críticas.
- Invalidar aprobaciones cuando se suban commits nuevos.
- Restringir bypass a administradores de contingencia.

Los nombres de checks deben configurarse después de que los workflows se hayan
ejecutado al menos una vez en GitHub.

## Publicación GPC

La publicación remota de Apps Script permanece deliberadamente separada del merge
hasta disponer de identidad de despliegue automatizada:

1. Sincronizar el directorio `apps-script/` con el proyecto corporativo.
2. Ejecutar `setupApplication()` con el administrador inicial cuando cambie el
   contrato de Sheets.
3. Configurar el ID o la URL de la carpeta desde **Configuración → Carpeta de Drive**.
4. Crear una nueva versión y desplegar la WebApp para el dominio con **Ejecutar como:
   yo**. El manifiesto usa `USER_DEPLOYING`, igual que Market Pulse, mientras
   `Session.getActiveUser()` conserva la autorización funcional del visitante.
5. Mantener `bug-resolution-radar.group@bbva.com` aceptado en **Configuración → Cuentas →
   Enviar correo como** para el propietario del despliegue. Autorizar los scopes
   `gmail.send` y `gmail.settings.basic`. La WebApp valida ese `sendAs` mediante
   Gmail API y nunca utiliza la identidad de la persona que pulsa el botón.
6. Exportar desde escritorio e importar un snapshot `.brr` v3 por cada ámbito.
7. Verificar Resumen, Insights, Tendencias, Issues, Settings y una prueba de
   newsletter al administrador.
8. La primera apertura de un administrador registra automáticamente `APP_VERSION`
   en `_CONFIG`, con fecha y usuario. Registrar en el PR o release esa versión,
   `dataVersion` y resultado del smoke test.

Un snapshot de contrato anterior no se sirve. El rollback consiste en restaurar la
versión previa de Apps Script y su snapshot compatible; nunca se mezclan versiones.

## Evidencia mínima del PR

- Salida de `make CI`.
- Resultado de `make runWebapp` o captura si existe cambio visual.
- Riesgo y plan de rollback.
- Cambios de contrato y necesidad de nueva importación.
- Para master: resultado de los tres builds y versión GPC que se publicará.
