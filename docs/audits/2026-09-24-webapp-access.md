# Auditoría de acceso y permisos de la WebApp — 24/09/2026

Alcance: `apps-script/`, su cliente HTML y sus pruebas. No se modifica la aplicación de escritorio ni su frontend React. Las capturas aportadas son evidencia del incidente, no instrucciones operativas. Cambios preparados como WebApp `2026.09.24.1`; no desplegados en Google.

## Diagnóstico y límites de la evidencia

La captura muestra Resumen accesible y un error de acceso a documento al abrir Issues. La usuaria afirma haber autorizado los permisos y poder abrir la presentación. Esto no demuestra que falte consentimiento: autorización OAuth, rol de aplicación y ACL del documento son controles diferentes. Una respuesta cacheada puede funcionar aunque la siguiente lectura de Sheets falle. Poder abrir Slides tampoco prueba acceso al almacenamiento del snapshot.

El manifiesto del repositorio ya utiliza `DOMAIN` y `USER_DEPLOYING`. En este modelo Google autentica el acceso al dominio y el servidor utiliza la autorización del propietario. El lector no debe autorizar Drive, Sheets, Slides o Gmail ni recibir acceso directo a las hojas internas. Si se le presentan esos consentimientos, hay que verificar la configuración y versión de la URL `/exec` publicada; el repositorio no permite confirmar cuál sirve actualmente a la usuaria. Un despliegue antiguo o ejecutado como visitante es una hipótesis, no una causa demostrada.

Fuentes oficiales: [ejecución y autorización de Web Apps](https://developers.google.com/apps-script/guides/web), [identidad activa y efectiva](https://developers.google.com/apps-script/reference/base/session), [URL del servicio](https://developers.google.com/apps-script/reference/script/service).

## Inventario de OAuth

Todos los permisos siguientes corresponden al ejecutor del servidor. Apps Script usa un manifiesto por proyecto, no un manifiesto por rol de la aplicación.

| Scope | Uso real | Resultado |
| --- | --- | --- |
| `userinfo.email` | Identidad activa para roles y atribución; identidad efectiva del remitente | Se conserva. Correo ausente o API de identidad fallida produce lector, nunca administrador. |
| `spreadsheets` | Lectura de snapshots y configuración; escritura de importaciones y telemetría | Se conserva para el propietario. No se solicita al lector en el despliegue previsto. |
| `drive` | Staging y publicación de PPTX/Slides, carpetas configurables y limpieza | Se conserva para operaciones administrativas. `drive.file` no es equivalente para carpetas arbitrarias ya configuradas. |
| `presentations` | Comprobación del número de diapositivas de la presentación convertida mediante `SlidesApp` | Se conserva: la ruta actual usa `openById` y `saveAndClose`. |
| `gmail.send` | Envío de prueba y definitivo mediante Gmail API | Se conserva exclusivamente en RPC administrativas. |
| `gmail.settings.basic` | Lectura de `Users.Settings.SendAs.list` para verificar el alias remitente | Se conserva para ese método; el código no modifica la configuración del buzón. |
| `script.scriptapp` | Sin uso de gestión de triggers en el código actual; solo existe `getService().getUrl()` | Se elimina el permiso innecesario. |

No existen scopes de lectura del correo, acceso HTTP externo o identidad suministrada por el navegador. No se introduce OAuth adicional para capturar adopción.

## Controles de autorización

- Identidad centralizada en `_domainViewer_`. Un correo explícitamente ajeno al dominio se rechaza siempre. Si Google omite el correo, se utiliza el acceso de dominio del despliegue como frontera y se concede únicamente lectura. Este diseño exige mantener `DOMAIN`: no publicar como acceso anónimo o abierto a cualquier cuenta.
- `_requireUser_` consulta roles únicamente si existe correo. Fallos de consulta producen lector. Administrador exige una fila activa con rol exacto `admin`.
- `_requireAdmin_` sigue protegiendo importación, cancelación, publicación, historial de importaciones, configuración de carpeta y gráficos, consola, analítica administrativa, newsletter y estado de informes. Ocultar controles del cliente no sustituye esta comprobación.
- `setupApplication()` era una excepción peligrosa: un correo vacío se sustituía por `initialAdmin`. Se elimina esa suplantación implícita. Ahora se exige la identidad real del administrador inicial antes de escribir.
- Los enlaces compartidos reutilizan la misma identidad de dominio y conservan sus validaciones de token activo, snapshot, informe, ámbito y huellas. Un token inválido o revocado no obtiene un fallback al dashboard general.
- La lectura continúa limitada al manifiesto autorizado. Se conserva la política existente de último snapshot publicado por país para lectores y la fijación de ámbito de enlaces compartidos. Las peticiones a ámbitos ajenos se deniegan en servidor. No se amplía la visibilidad de datos bajo la excusa de un fallback.
- Se mantiene Presentación como enlace de lectura para el lector. Sus ACL de Google Slides siguen siendo independientes. Los filtros por equipos y la generación de un nuevo informe mencionados en la conversación adjunta no forman parte de este cambio de permisos.

## Recuperación y comportamiento del cliente

| Fallo | Comportamiento |
| --- | --- |
| Correo vacío o excepción de identidad | Lector; no consulta roles ni utiliza la identidad efectiva del propietario como visitante. |
| Registro de roles inaccesible | Lector; RPC administrativas denegadas. |
| Configuración administrativa falla durante bootstrap | Se degrada la sesión de interfaz a lector y se reduce su manifiesto. Las RPC administrativas siguen validando identidad y rol de manera independiente. |
| Manifiesto/Sheets inaccesible | Shell de lectura navegable, estado explícito de datos no disponibles y botón de reintento. No se inventan datos. |
| Snapshot inicial falla | Se conserva el manifiesto y se abren las otras pestañas. No se repite automáticamente la misma lectura fallida durante el arranque. |
| Una pestaña falla | Error recuperable con reintento; las demás pestañas continúan disponibles. |
| Llega tarde un error de una navegación anterior | Se descarta por generación de navegación/ruta; no sustituye la pantalla actual. |
| IndexedDB bloqueado o rechazado | La carga usa RPC; se elimina la lectura duplicada y sin protección de `openPanel`. |
| Telemetría falla | No bloquea el arranque ni produce un rechazo sin manejar al abandonar la página. Los eventos pendientes conservan el reintento existente. |

Si Google bloquea la ejecución antes de llegar al código (consentimiento del propietario revocado, despliegue incorrecto o acceso al dominio denegado), JavaScript no puede reparar ese bloqueo. Si el servidor pierde acceso a Sheets, puede mantenerse la navegación, pero no garantizar datos que no puede leer. No se recurre a snapshots de otro ámbito ni a una identidad administrativa.

## Telemetría aportada y rendimiento

Fuente: `bug-resolution-radar-analytics-20260924T073937Z.json`. Ventana completa, 625 eventos, 54 sesiones, 3 usuarios identificados, 11 errores. Sin truncamiento ni eventos sin versión. El P95 global de 45.975 ms mezcla importaciones y versiones, por lo que no se utiliza como tiempo de navegación actual.

Para `2026.09.23.1`: 71 eventos, 3 usuarios identificados y cero errores registrados. No contiene el fallo de permisos de la captura; ausencia de evento no demuestra ausencia de fallo.

| RPC de esa versión | Muestras | Media ms | P95 ms | Máximo ms |
| --- | ---: | ---: | ---: | ---: |
| `getBootstrap` | 10 | 6101 | 11227 | 11346 |
| `queryDashboard` | 11 | 4857 | 6413 | 6545 |
| `getAdminConsole` | 6 | 5696 | 6159 | 9306 |
| `getAnalyticsReport` | 9 | 4620 | 5186 | 8059 |

P95 calculado con el mismo índice inferior del exportador. Muestras pequeñas; no prueban mejora cuantitativa del parche.

Mejoras acotadas: una sola ruta de lectura de caché por navegación; mantenimiento del agrupamiento de peticiones simultáneas; telemetría de apertura fuera de la espera del arranque; registro de adopción sin consultar la tabla de roles; evitación de repetir inmediatamente el snapshot inicial fallido. Se corrige además la comparación de ámbito al reutilizar el resumen del bootstrap: antes podía pintar datos iniciales de otro ámbito bajo la selección local de un administrador.

No se cambian cálculos de negocio ni tokens. El estado recuperable reutiliza `UI.empty`, `Charts.begin` y `secondary-button`, con los estilos y tokens existentes. No se añade dependencia, caché alternativa de datos o capa de compatibilidad.

La adopción conserva correo cuando está disponible, sesiones y eventos cuando no. Un correo desconocido queda vacío: no se inventa una identidad ni se atribuye actividad al propietario. El contador de usuarios por correo no cuenta esos lectores sin identidad; las sesiones sí. Los enlaces compartidos mantienen su política existente sin telemetría de cliente.

## Verificación y puesta en servicio

Pruebas ejecutables con Node desde pytest: correo vacío, excepción de identidad, dominio externo, lector, administrador activo/inactivo, fallo de roles, denegación de todas las RPC administrativas, inicialización sin identidad, fallo de almacenamiento, fallo de resumen, lectura de las cuatro pestañas, ámbito no autorizado y error tardío de navegación. Se conservan los tests de contrato y de deduplicación de lecturas/RPC.

Antes de dar por resuelto el incidente en producción: actualizar la versión del despliegue `/exec` con todos los archivos HTML/GS y el manifiesto; confirmar ejecución como propietario y acceso solo al dominio corporativo; verificar los permisos del propietario sobre Sheets y artefactos; abrir la URL con un lector sin autorizar scopes administrativos y recorrer Resumen, Insights, Tendencias, Issues y Presentación. Verificar también una RPC administrativa desde ese lector: debe responder `FORBIDDEN`. Estos pasos externos no se han ejecutado desde este repositorio.

Resultado local: 99 pruebas de la suite GPC y regresiones de acceso superadas; composición HTML y gate `check_gpc_quality.mjs` correctos. Comprobación con `agent-browser` sobre los HTML reales y servicios Google simulados: lector sin correo, resumen inicialmente inaccesible y telemetría fallida; Insights, Tendencias e Issues navegables, sin controles administrativos ni errores JavaScript sin manejar. El cambio de tema conserva el estado recuperable. Esta simulación no valida OAuth ni ACL reales de Google.
