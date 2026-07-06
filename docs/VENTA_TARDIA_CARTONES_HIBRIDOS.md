# Venta tardía de cartones híbridos

## Problema anterior

La validación de venta por Bingo exigía que todas sus rondas estuvieran en
estado `Programada` o `En espera`. La presencia de una sola ronda iniciada,
finalizada, cancelada o en otro estado bloqueaba toda la venta, aunque todavía
existieran rondas futuras disponibles.

Además, el servicio recorría todas las rondas al crear las participaciones. El
contrato anterior evitaba que esto generara participaciones retroactivas solo
porque rechazaba previamente el Bingo completo.

## Regla actual

- La venta se permite si existe al menos una ronda en estado oficial
  `Programada` o `En espera`.
- Se crea un solo cartón maestro, con un código, una matriz, un jugador y un
  precio registrado.
- Las participaciones iniciales se crean únicamente para las rondas elegibles.
- Las rondas iniciadas, pausadas, en desempate, finalizadas, canceladas o en
  cualquier otro estado no reciben participaciones retroactivas.
- Si no queda ninguna ronda elegible, el servicio rechaza la operación antes de
  crear el maestro o sus participaciones.

## Atomicidad y concurrencia

La operación conserva `transaction.atomic()` y el orden de bloqueo existente:
primero bloquea el Bingo y después sus rondas. La selección definitiva de
rondas elegibles se realiza sobre esas filas bloqueadas antes de crear el
maestro.

La creación posterior de una ronda mantiene la sincronización existente:
bloquea el mismo Bingo, incorpora los maestros vendidos y evita duplicar una
participación ya registrada. De este modo, un cartón vendido tarde puede entrar
en una ronda futura creada después de la compra sin modificar rondas previas.

## Interfaz administrativa

La pantalla de venta indica cuántas rondas futuras se incluirán y cuántas
rondas no elegibles quedarán fuera. Si no existen rondas futuras disponibles,
muestra una advertencia y deshabilita el envío del formulario. Estos conteos
son informativos; la validación transaccional del servicio sigue siendo la
fuente definitiva ante cambios concurrentes.

## Compatibilidad y alcance

No se modificaron cartones, participaciones ni rondas históricas. Tampoco se
modificaron modelos, migraciones, PostgreSQL, reportes, WebSockets, pagos,
permisos o rutas. La ruta heredada por ronda permanece normalizada y no recupera
capacidad de escritura.

## Pruebas ejecutadas

- `./.venv/bin/python manage.py check`: sin incidencias.
- Pruebas focalizadas de venta, sincronización, interfaz y ruta heredada: 27
  pruebas, resultado `OK`.
- `./.venv/bin/python manage.py test apps.bingos.tests`: 282 pruebas, resultado
  `OK`.
- `./.venv/bin/python manage.py test`: 312 pruebas, resultado `OK`.
- `git diff --check`: sin errores.
