# Visibilidad de cartones híbridos en administración

## Problema corregido

Los detalles administrativos de Bingo y ronda consultaban únicamente la
relación heredada `Carton.idpartida`. Como los cartones maestros del flujo
híbrido dejan ese campo en `NULL`, podían existir y participar correctamente
sin aparecer en esas pantallas.

## Modelo maestro y participación

- Un cartón maestro pertenece a un Bingo mediante `Carton.idbingo` y conserva
  `Carton.idpartida` en `NULL`.
- Cada intervención del maestro en una ronda se representa con una
  participación independiente, que conserva su propio estado, índice de
  victoria y fecha de validación.
- Un cartón heredado continúa relacionado directamente con su ronda mediante
  `Carton.idpartida`.

## Pantallas afectadas

- **Detalle de ronda:** combina los cartones heredados de la ronda con las
  participaciones híbridas obtenidas por el servicio existente. Los dos tipos
  se identifican visualmente y el vacío solo aparece cuando ambas colecciones
  están vacías.
- **Detalle de Bingo:** consulta los cartones por `Carton.idbingo`, cuenta sus
  participaciones sin consultas por fila y pagina el resultado. Ya no existe
  el corte silencioso de 50 cartones.
- **Listado global de cartones:** muestra el Bingo, el tipo y la cantidad de
  rondas de cada maestro. Para un registro heredado conserva el Bingo y la
  ronda asociados.

## Compatibilidad histórica

Los cartones con `Carton.idpartida` asignada siguen apareciendo como “Cartón
heredado por ronda”. No se convierten en maestros, no se reasignan y no se
crean participaciones para ellos.

## Cambios no realizados

No se modificaron modelos, migraciones, base de datos, reportes, WebSockets,
servicios de creación o venta, pagos, permisos ni rutas. Tampoco se crearon,
editaron, eliminaron, migraron o repararon datos históricos.

## Pruebas ejecutadas

- `./.venv/bin/python manage.py check`: sin incidencias.
- Pruebas específicas de visibilidad administrativa: 4 pruebas, resultado
  `OK`.
- `./.venv/bin/python manage.py test apps.bingos.tests`: 278 pruebas, resultado
  `OK`.
- `./.venv/bin/python manage.py test`: 308 pruebas, resultado `OK`.
