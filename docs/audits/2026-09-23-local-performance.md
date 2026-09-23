# Optimización local basada en telemetría — 23 de septiembre de 2026

Origen: `radar_telemetria_codex_20260922_235755.json`. Base de código: `ade2dfd`.

## Hallazgos

El archivo contiene 5.000 eventos de frontend y backend. Las dos capas registran la misma petición: sus tiempos y errores no deben sumarse como operaciones independientes. Hay 26 errores backend, entre las 19:33 y las 19:40 UTC del 22 de septiembre, anteriores a la corrección del binario. Las peticiones backend de la sesión de las 21:57 UTC no tienen errores.

Los principales tiempos medios backend son workspace (13,34 s), incidencias (12,60 s), exportación GPC (13,58 s), dashboard (7,50 s) e intelligence (6,79 s). Hay 2.130 consultas backend de progreso de Helix. El archivo no contiene mediciones directas de RAM o CPU.

El perfil local identificó normalización de país por incidencia, conversión del dataframe completo a diccionarios para obtener metadatos de fuentes y recorridos repetidos del texto por cada palabra clave de taxonomía.

## Cambios

- Normalización de países una vez por valor distinto, manteniendo alias, acentos y criterios de selección.
- Inferencia de fuentes sobre las columnas de metadatos y pares país/origen distintos. Se conserva la primera aparición y no se materializan las descripciones de todas las incidencias como diccionarios.
- Filtrado por país, origen y periodo antes del enriquecimiento Helix. Los consumidores reciben las mismas descripciones, pero se evita enriquecer repetidamente los países que no se consultan.
- Un patrón compilado por categoría de taxonomía en lugar de uno por palabra clave. Se conservan la prioridad de categorías, los límites de palabra y el tratamiento literal de caracteres especiales.
- Normalización Unicode con traducción de marcas combinantes distintas y vía rápida ASCII. No se elimina texto no latino.
- Consultas de progreso cada 1,5 s durante los primeros 30 segundos; después cada 5 s. Se detienen al finalizar. La fase larga requiere aproximadamente un 70 % menos de consultas, a cambio de hasta 5 segundos de latencia para mostrar una actualización.

No se añaden cachés de textos de incidencias ni copias persistentes del conjunto de datos.

## Comparación

La comparación directa de los clasificadores anterior y nuevo sobre **48.099 registros locales** devuelve exactamente la misma columna de funcionalidad:

| Operación | Antes | Después |
| --- | ---: | ---: |
| Clasificación completa sin profiler | 25,470 s | 14,891 s |
| Workspace, primera petición con profiler | 25,128 s | 5,436 s |
| Workspace, repetición con profiler | 24,571 s | 4,890 s |
| Incidencias, primera petición con profiler | 16,033 s | 6,267 s |
| Incidencias, repetición con profiler | 0,049 s | 0,055 s |

Las peticiones de la tabla usan España y `scopeMode=country`, con el mismo archivo local. Los tiempos con profiler incluyen su sobrecoste. Son mediciones de esta máquina, no límites garantizados. La clasificación completa reduce su duración un 41,5 %; la primera consulta workspace reduce su tiempo perfilado un 78,4 %.

El dashboard completo con todos los gráficos sigue dedicando tiempo relevante a Plotly; no se atribuye una mejora general a ese endpoint ni a intelligence. Tampoco se ha medido nuevamente una exportación GPC completa o una ingesta remota autenticada.

## Validación

Pruebas de equivalencia Unicode, límites de palabra, prioridad y literales; normalización proporcional a países distintos; conservación de metadatos de fuentes. Pruebas de API, ámbito, taxonomías e informes, controles de Ruff/mypy, TypeScript y build de producción. El binario macOS se reconstruye con estas modificaciones.


Resultado final: **598 pruebas correctas**, **84,70 % de cobertura**. El ejecutable macOS, arrancado desde `/tmp` con su configuración de usuario, responde HTTP 200 en bootstrap, frontend, incidencias, Kanban y taxonomías para los cinco países. Las consultas iniciales de incidencias de las fuentes seleccionadas tardaron entre 0,11 y 1,80 segundos; estos ámbitos son distintos del agregado usado en la tabla perfilada. Firma local del paquete verificada. Aplicación y ZIP reconstruidos.
