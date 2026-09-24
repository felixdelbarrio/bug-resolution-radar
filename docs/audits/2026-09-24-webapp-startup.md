# Arranque WebApp 2026.09.24.3

Incidente comunicado: la publicación `2026.09.24.2`, configurada según el usuario como propietario y dominio, permanece bloqueada durante 30 minutos. La captura mencionada y la URL no llegaron en el mensaje; no se dispone de consola ni ejecuciones de Google de esa sesión. No se atribuye el incidente a OAuth sin esa evidencia.

## Hallazgos confirmados en el código .2

- El timeout de `getBootstrap` terminaba en `showAccessError`, ocultando toda la aplicación. El fallback del servidor solo funcionaba si la RPC llegaba a devolver una respuesta. No cubría una RPC interrumpida o que nunca respondiera.
- El watchdog independiente se cancelaba al entrar en `App.init`, antes de terminar el arranque. Si actuaba antes de iniciar App, mostraba reintento pero mantenía `auth-pending` y su animación de carga.
- La pantalla inicial no mostraba la versión servida ni capturaba errores JavaScript anteriores al arranque de App.

Estos problemas son verificables, pero no prueban cuál ocasionó los 30 minutos de espera en producción. Con JavaScript operativo, el timeout de la versión .2 ya debía cambiar el mensaje a los 30 segundos. Si el mensaje inicial nunca cambia, es necesario comprobar el código efectivamente servido, la ejecución de JavaScript y los errores de esa sesión.

## Corrección

- RPC inicial sin respuesta: a los 30 segundos se abre la shell sin datos, con rol de interfaz lector, cuatro pestañas y reintento manual. Se descarta cualquier respuesta tardía del intento vencido. No se reutilizan ámbitos locales ni datos de otro usuario para construir ese fallback.
- Fallo de transporte o error interno inicial: misma recuperación. La ausencia de `google.script.run` se clasifica como fallo de transporte.
- `FORBIDDEN`, errores de contrato/respuesta y enlaces compartidos no verificados conservan el bloqueo; el fallback no concede acceso a datos ni capacidades administrativas.
- El watchdog permanece activo hasta que hay interfaz o error terminal; a los 35 segundos detecta que App no ha completado el arranque. Los errores JavaScript previos a App se muestran inmediatamente. El estado deja de parecer una espera en curso.
- La pantalla de acceso muestra `2026.09.24.3`. Los metadatos mínimos proceden de la configuración del servidor embebida al entregar HTML, sin depender de la primera RPC.
- El renderer local utiliza ese mismo generador de metadatos y tokens, eliminando la copia independiente que antes existía en el simulador.

No cambia el manifiesto OAuth, la frontera del dominio, la autorización del servidor, los cálculos ni los estilos. La navegación sin datos no equivale a recuperar el almacenamiento ni a autenticar una identidad que Google no ha confirmado.

## Validación

104 pruebas superadas; gate de calidad GPC, composición HTML y comprobación del diff correctos.

Pruebas ejecutables con timers controlados: RPC sin resolver, timeout real del cliente, respuesta administrativa tardía descartada, fallos de transporte/internos, falta del puente Google, denegaciones explícitas, enlaces compartidos y error de JavaScript anterior a App. Se mantienen las pruebas anteriores de roles, datos y navegación.

Navegador sobre HTML real, con servicios Google simulados:

- `getBootstrap` sin callback: tras 30 segundos, `auth-ready`, cuatro pestañas, aviso de datos no disponibles y reintento; una sola llamada inicial, sin controles administrativos.
- Clic en Insights, Tendencias e Issues tras el timeout: navegación disponible, sin errores JavaScript sin manejar.
- Error de sintaxis inyectado en App: `auth-denied`, versión visible, error concreto y botón Reintentar; sin animación indefinida.
- Respuesta `FORBIDDEN`: acceso denegado; no entra en modo de lectura.

No se ha desplegado ni verificado la URL de producción. Para comprobar esta publicación hay que actualizar juntos los archivos modificados de Apps Script y abrir la URL `/exec`. La pantalla de acceso debe identificar la versión .3. Si permanece en el mensaje inicial más de 35 segundos, la captura, URL y consola del iframe de la aplicación son necesarias para identificar el bloqueo previo al código probado.

## Causa confirmada en producción y corrección .4

El 24/09/2026 se inspeccionó la publicación autenticada `.3`, dentro de `#sandboxFrame > #userHtmlFrame`. La consola registraba `SyntaxError: Invalid regular expression: missing /`. Se extrajo el texto de los scripts del DOM, sin ejecutarlos, y se comprobó su sintaxis con `vm.Script`.

Los scripts de metadatos, recursos, watchdog, componentes, dominio, caché y gráficos eran válidos. El script de App fallaba en la línea 1614, en la validación del enlace de presentación:

```javascript
// Repositorio .3
if (!/^https:\/\//i.test(slidesUrl)) {
```

La línea recibida terminaba después de `if (!/^https:` y los caracteres `\/\`: faltaban el cierre de la expresión regular y el resto de la condición. La comparación completa con App.html solo encontró esa diferencia. No se trataba de una denegación de identidad, acceso a Sheets ni una respuesta lenta: el script principal no podía interpretarse.

La versión `.4` utiliza una expresión equivalente sin la secuencia de barras escapadas adyacentes:

```javascript
if (!/^https:[/][/]/i.test(slidesUrl)) {
```

Al sustituir únicamente esa línea en el script capturado, el script completo compila y coincide exactamente con el código local corregido. Las pruebas reproducen el SyntaxError de la línea truncada, validan el script completo y comprueban que el lector sigue pudiendo abrir enlaces HTTPS (incluidas mayúsculas), pero no HTTP, javascript, FTP ni una URL con una sola barra.

Esta comprobación confirma la reparación del código observado. La versión `.4` todavía debe publicarse para verificar que HtmlService la entrega intacta y que el arranque y la lectura de datos funcionan en producción. No se han cambiado permisos, roles, datos ni estilos.
