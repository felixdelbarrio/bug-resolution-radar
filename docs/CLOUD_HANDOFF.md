# Desktop to GPC handoff

## Authority

El escritorio es la única fuente de verdad para KPIs, quincenas, estados, cierres,
prioridades, funcionalidades, insights y contenido del informe. GPC no contiene una
segunda implementación de esas reglas: publica una proyección inmutable calculada por
el backend local.

La exportación `.brr` es un handoff unidireccional de escritorio a GPC. No es un
respaldo incremental ni un mecanismo para reimportar datos en el escritorio.

## Transfer contract

El contrato v3 contiene exclusivamente:

- `manifest.json`
- `data/projection.json`
- `artifacts/period_followup.pptx`

El manifest declara formato, versión, ámbito, contrato semántico y descriptores
`path`, `sha256`, `bytes` y `records` para los dos artefactos. La proyección usa
`semanticContract: "desktop-authoritative-v2"` y expone:

- ámbito inmutable, país, geografía/vista, orígenes, versión y fecha de referencia;
- trazabilidad de las reglas semánticas aplicadas por escritorio;
- vistas ya materializadas de overview, insights, tendencias e incidencias;
- texto, métricas y agrupaciones por responsable de la newsletter, calculados localmente;
- fuentes Jira del ámbito con PO/Team Leader y enlace opcional al cuadro de mando;
- metadatos y huella del PPTX exacto generado localmente.

No viajan copias de issues, Helix, notas o aprendizaje. Tampoco existe un campo de
filtros de incidencias: la proyección representa una única vista estática.

## Publication lifecycle

1. Tras la carga manual de datos, escritorio calcula todas las vistas con filtros
   vacíos para el ámbito seleccionado.
2. El mismo servicio local que usa la aplicación genera el PPTX de seguimiento.
3. GPC valida inventario ZIP, tamaños, esquema, ámbito y SHA-256 antes de publicar.
4. GPC conserva el PPTX original y crea Google Slides mediante conversión de ese
   binario; no reconstruye diapositivas.
5. La proyección se escribe en chunks durables y se activa cambiando un único puntero
   de ámbito. Una publicación incompleta nunca queda visible.
6. WebApp, enlace compartido y newsletter leen el snapshot activo. La newsletter
   renderiza sin IA el texto local inmutable, enlaza Google Slides y adjunta el PPTX
   original.

## Cache and performance

Sheets actúa como caché L2 durable por ámbito. `CacheService` es solo L1 y puede
expirar o ser expulsada: un miss vuelve a leer la proyección L2 y nunca recalcula
analítica ni recorre datasets fuente.

Solo se permiten operaciones de presentación sobre datos ya materializados:
selección de página, orden de filas, elección de gráfico o cambio de sección. Los
controles de ámbito y la configuración son exclusivos del administrador. No se
admiten búsquedas, filtros por estado, prioridad, responsable, funcionalidad,
quincena ni drilldowns que alteren el universo de incidencias.

El snapshot permanece estático hasta que una nueva importación válida publica la
misma geografía/vista. Los artefactos anteriores se pueden auditar por sus hashes,
pero no participan en el serving normal.

La UI carga Plotly bajo demanda, prelee las vistas principales y muestra el estado de
carga en el primer clic. Sheets actúa como almacén materializado; la analítica de uso
se registra en lotes pequeños y nunca interviene en la lectura del dashboard.

## Versioning and tests

No se mantiene retrocompatibilidad con traslados anteriores. Cualquier cambio de forma
requiere incrementar la versión de transferencia; cualquier cambio de racional
requiere un nuevo contrato semántico.

Las guardas automáticas comprueban:

- contrato ZIP estricto, hashes, tamaños y determinismo;
- quincenas 1–14 y 15–fin y semántica de cierre/resolución del escritorio;
- ausencia de filtros y de cálculo de negocio bajo demanda en GPC;
- ausencia de funciones globales duplicadas en Apps Script;
- igualdad entre el hash del PPTX empaquetado y el artefacto local;
- newsletter determinista sin servicios generativos, adjunto canónico y auditoría del
  texto exacto enviado;
- ausencia de las vistas retiradas del contrato cloud y sintaxis válida de Apps Script.
