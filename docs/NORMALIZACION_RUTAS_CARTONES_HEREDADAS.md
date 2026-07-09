# Normalización de la ruta heredada de cartones por ronda

## Motivo

Un cartón maestro pertenece a un Bingo y participa de manera independiente en
sus rondas. Crear cartones desde una ronda permitía mantener un flujo contrario
a esa regla y podía registrar ventas limitadas a una sola partida.

## Comportamiento anterior

La ruta `partidas/<idpartidabingo>/cartones/nuevo/` mostraba un formulario en
`GET`; su `POST` podía generar y asignar un cartón directamente a la ronda
indicada.

## Comportamiento nuevo

La misma ruta conserva el permiso administrativo existente, obtiene la partida
y su Bingo, informa que los cartones se administran para todo el Bingo y
redirige al detalle de ese Bingo. Tanto `GET` como `POST` son operaciones sin
escritura: no crean ni modifican cartones, participaciones o jugadores.

## Compatibilidad e históricos

La URL y su nombre `bingos:partida_carton_nuevo` se mantienen para que los
enlaces históricos sigan resolviendo. El destino es `bingos:detalle`, usando el
`idbingo` asociado a la partida.

Este cambio no migra, reasigna, elimina ni actualiza cartones, participaciones,
partidas, jugadores u otros datos históricos existentes.
