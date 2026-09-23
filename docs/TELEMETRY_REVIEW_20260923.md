# Revisión de telemetría del 23 de septiembre de 2026

Fuente: `bug-resolution-radar-analytics-20260923T050459Z.json`, captura de las
05:04:59 UTC. SHA-256 verificado contra el contenido canónico, excluyendo
`integrity`. El archivo original no se incorpora al repositorio porque contiene
identificadores personales.

## Alcance y resultados

La exportación contiene 516 eventos de 43 sesiones y 2 usuarios, repartidos entre
8 versiones. No hay truncamiento ni eventos sin versión. Las duraciones corresponden
a RPC medidas desde el cliente, no al tiempo de renderizado ni a Web Vitals.
El p95 global de 47,85 s mezcla operaciones y versiones; no es una medida de la
latencia de navegación actual.

La última versión del archivo, `2026.09.22.4`, tiene 36 eventos y 24 RPC en 2
sesiones. No registra errores. La muestra es pequeña y no permite atribuir cada
segundo a CPU, Drive, Sheets, red o espera de bloqueo.

| Operación en 2026.09.22.4 | Muestras | Media | Máximo |
| --- | ---: | ---: | ---: |
| Validar importación | 2 | 47,35 s | 57,83 s |
| Publicar importación | 2 | 70,46 s | 86,60 s |
| Bootstrap | 4 | 6,89 s | 9,91 s |
| Consultar dashboard | 3 | 6,64 s | 7,64 s |
| Listar importaciones | 4 | 3,66 s | 4,10 s |
| Registrar versión | 4 | 2,70 s | 3,70 s |

Las dos parejas validación/publicación suman 144,43 s y 91,20 s,
respectivamente, excluyendo la espera del usuario y las consultas auxiliares.
Los 11 errores del conjunto pertenecen a versiones anteriores. Dos son
`LOCK_TIMEOUT` de publicación en `2026.09.22.3`; no demuestran por sí solos
un fallo equivalente en la versión actual.

## Cambios implementados

Versión de código propuesta: `2026.09.23.1`.

- Normalizar la identidad de las vistas tanto en cliente como en servidor:
  solo Tendencias depende de `chartId`, solo Insights de `insightsId` y solo
  Issues de `page`. Cambiar otro panel ya no fragmenta la caché de una vista
  idéntica. Se conservan ámbito, snapshot, versión, contrato y generación de caché.
- Compartir la promesa de lectura de IndexedDB y de RPC desde el inicio de
  `fetchDashboard`. Antes, dos llamadas concurrentes podían atravesar la consulta
  de caché y lanzar dos RPC. Una caché local fallida permite consultar el servidor;
  un fallo remoto libera la petición para que pueda reintentarse.
- Incluir en bootstrap si la versión ya está registrada. El mantenimiento ocioso
  omite esa RPC cuando no hace falta, manteniendo autorización en servidor y
  posibilidad de reintento si falla. En la muestra se ejecutó cuatro veces;
  esto consume recursos aunque ocurre fuera de la ruta inicial de renderizado.
- Subir los dos archivos temporales de validación antes de adquirir el bloqueo
  global. El token y su auditoría siguen publicándose bajo bloqueo y se limpian
  los archivos si falla la adquisición o la escritura. La publicación del snapshot
  mantiene su bloqueo y su secuencia atómica. Este cambio reduce la sección
  bloqueada, pero no elimina el coste de subida ni de conversión de Slides.

## Verificación y límites

Pruebas ejecutables en Node verifican equivalencia y separación de claves de caché,
una sola RPC ante solicitudes concurrentes, reintentos, recuperación de IndexedDB,
registro condicional de versión y limpieza de staging al fallar el bloqueo o Sheets.
La comprobación GPC también valida sintaxis, composición local y contratos existentes.
La suite completa pasa 601 pruebas con cobertura del 84,70 %; también pasan
el formato, el tipado y la compilación del frontend.

No se ha desplegado en Apps Script ni medido una mejora de latencia en producción.
Tras publicar, comparar la telemetría de `2026.09.23.1` con operaciones equivalentes:
volver a Resumen después de cambiar una variante, repetir navegación durante carga,
abrir sesiones de administrador tras registrar la versión e importar paquetes de
similar tamaño. Mantener separadas las mediciones de validación y publicación.
Para localizar el coste restante de importación hace falta medir las fases de
Drive, validación, escritura de partes y conversión; el archivo actual solo ofrece
la duración total de cada RPC.
