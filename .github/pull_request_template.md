## Objetivo

<!-- Explica el problema, la solución y el valor del cambio. -->

## Alcance y riesgo

<!-- Incluye componentes afectados, riesgo operativo y compatibilidad de contrato. -->

## Evidencia

- [ ] `make CI` finaliza correctamente.
- [ ] `make runWebapp` se ha probado si cambia GPC/WebApp.
- [ ] Se adjuntan capturas cuando cambia la presentación.
- [ ] Se documentan migraciones o una nueva importación `.brr` v3.
- [ ] Se describe el plan de rollback.
- [ ] No se incluyen secretos, datos personales ni artefactos generados.

## Promoción

- [ ] El destino es `develop`, o este es un PR exclusivo `develop → master`.
- [ ] Los checks requeridos están verdes y la rama está actualizada.
- [ ] Las conversaciones están resueltas y existe la aprobación requerida.
- [ ] Si se publica GPC, se registrarán versión, responsable, `dataVersion` y smoke test.

