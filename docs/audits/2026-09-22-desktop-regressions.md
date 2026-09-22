# Auditoría de regresiones desktop — 22 de septiembre de 2026

Revisión del estado `0d0a3cf9dc5ad75c9215fe30079f6b350bbcd6fc`, con foco en los cambios de taxonomía y su administración, insights acumulados y presentación en WebApp. Se revisaron configuración y empaquetado, navegación React, persistencia, clasificación, cachés, informes, contratos API y controles de calidad del repositorio.

## Diagnóstico y correcciones

- **Países y datos ausentes en el binario.** Reproducido en un proceso nuevo con el directorio de usuario existente: `Settings` fallaba al validar `FUNCTIONALITY_TAXONOMY_MEXICO`. La búsqueda de valores por defecto prefería una `.env.example` de abril, sin taxonomías, a la incluida en la versión actual. La plantilla se resuelve ahora exclusivamente desde el código instalado o `_MEIPASS`. El `.env` activo y las rutas de datos conservan su ubicación. Se elimina la búsqueda entre directorios y plantillas antiguas.
- **Taxonomía fuera de Configuración.** Eliminados su botón en la barra y su ruta independiente. El editor se carga bajo demanda en la pestaña Taxonomías de Configuración, usando los estilos compartidos.
- **Vistas desactualizadas después de editar taxonomías.** Las claves `dashboard` e `intelligence` no coincidían con las consultas reales. Se centraliza la invalidación de las consultas de dashboard y bootstrap, compartida por Configuración y el editor.
- **Informes reutilizados con una clasificación anterior.** La clave de caché del PowerPoint no incorporaba las taxonomías. Dashboard e informes comparten ahora una revisión que incorpora tanto los valores configurados como el fichero de personalizaciones. La caché de contexto también distingue la profundidad de análisis.
- **Ediciones del editor perdidas o concurrentes.** Se bloquea la navegación con cambios sin guardar, se desactiva la recarga automática al recuperar foco/conexión y se deshabilita la edición durante guardado/restauración. El servidor serializa las modificaciones del documento de personalizaciones para conservar cambios simultáneos en países diferentes.
- **Compilación sin comprobación de tipos.** `build` ejecuta TypeScript antes de Vite. Corregidos los tipos de JSX/React, Plotly, registros de incidencias, parámetros de exportación, cuerpo binario y callbacks de Configuración. Se añaden las declaraciones de tipos oficiales de Plotly.
- **Código obsoleto de informes.** Retirado el ejecutor de subprocesos que solo tenía consumidores en sus propias pruebas. La aplicación ya renderiza con Pillow. Renombrado el helper de PNG para reflejar el motor actual y actualizados sus consumidores y controles de CI.
- **Carga innecesaria.** Eliminada la precarga indiscriminada de páginas tras el arranque. Inventario de caché y destino de descargas se consultan al abrir su pestaña. Se evita convertir la taxonomía a JSON estructurado y reconstruir sus tuplas para cada uso del clasificador.
- **Fallos de carga silenciosos.** Bootstrap muestra el error y permite reintentar; Configuración muestra los fallos de su consulta.
- **Dependencias frontend.** Actualizadas las versiones compatibles de Vite/PostCSS detectadas por `npm audit`; auditoría resultante sin vulnerabilidades conocidas.

## Verificación

- Regresión ejecutada en procesos aislados, en modo fuente y simulando el entorno congelado, con plantilla de usuario anterior a las taxonomías. Comprueba las cinco taxonomías y que `.env` y datos permanecen intactos.
- Pruebas de edición/restauración, validación de límites, persistencia concurrente e invalidación de caché de informes.
- Suite completa con cobertura, Ruff, mypy, TypeScript, compilación de producción, integridad de dependencias, referencias documentales y detector de helpers privados sin referencias.
- Quality gate GPC, composición local de la WebApp y pruebas de proyección cloud, transferencia, ingesta y seguridad.
- Navegador contra la API con el directorio real del binario: cinco países y fuentes visibles; pestaña de taxonomías sin icono adicional; cancelación de cambios y navegación protegida; sin errores JavaScript ni desbordamiento horizontal en la vista inspeccionada.
- Lecturas de bootstrap, taxonomías, incidencias y Kanban para los cinco países. Las mediciones incluyen trabajo concurrente de compilación/pruebas; no constituyen un benchmark controlado.

## Resultado final

- Suite final: **585 pruebas correctas**, cobertura **84,68 %** (umbral: 80 %).
- CI completo y validación GPC correctos; TypeScript, mypy y Ruff sin errores.
- Binario macOS ARM64 ejecutado desde `/tmp`, sin `BUG_RESOLUTION_RADAR_HOME`: bootstrap, frontend de producción y cinco taxonomías responden HTTP 200. Incidencias y Kanban responden HTTP 200 en los cinco países, con los mismos totales por fuente seleccionada que la ejecución desde código: México 107, España 3001, Perú 1068, Colombia 41 y Argentina 55. Son totales de las fuentes seleccionadas, no agregados nacionales.
- En esa comprobación, las lecturas iniciales de incidencias tardaron entre 2,5 y 4,8 segundos; Kanban reutilizó el contexto en 18–30 ms. Son mediciones locales durante otras tareas, no límites garantizados.
- Firma local verificada con `codesign --verify --deep --strict`.
- Entregables actualizados: `dist_app/bug-resolution-radar.app` y `build_bundle/bug-resolution-radar-macos.zip`.
- La comprobación del ejecutable utiliza su modo interno de API; la inspección visual se hizo con navegador contra el frontend de producción. No se automatizó la ventana nativa de pywebview.

## Alcance de la evidencia

El problema era de lectura y validación de configuración, no de borrado de incidencias. No se restauró el `.env` ni se reingestaron los datos para solucionar el arranque. Las comprobaciones cubren los contratos y escenarios ejecutados; no certifican ausencia absoluta de defectos ni rendimiento óptimo bajo cualquier carga. No se realizó una nueva ingesta autenticada contra Jira/Helix ni una publicación remota de Apps Script. El empaquetado ejecutado corresponde a macOS ARM64; Linux no se ejecutó en esta máquina.
