# Etapa 1: partidas y cartones sin WebSockets

Fecha de cierre: 2026-06-27.

## Alcance implementado

Se implemento el nucleo funcional de partidas y cartones reutilizando los modelos existentes:

- `Bingo`.
- `Partidabingo`.
- `Jugador`.
- `Carton`.
- `Sesionjuego`.
- `Plataformajuego`.

No se crearon migraciones y no se modifico la estructura fisica de PostgreSQL.

## Archivos creados o modificados

### Codigo Python

- `apps/common/decorators.py`: decorador `admin_required` para exigir usuario autenticado con `is_staff` o `is_superuser`.
- `apps/bingos/services.py`: estados centralizados de partida, transiciones, acciones de consola y lectura de `bolascantadas`.
- `apps/bingos/forms.py`: `PartidaBingoForm` usa estados aprobados; `CartonPartidaForm` permite asignar cartones a jugadores dentro de una partida.
- `apps/bingos/views.py`: lista de partidas, consola de operador, creacion/edicion de cartones por partida y permisos administrativos.
- `apps/bingos/urls.py`: rutas nuevas para partidas, consola y cartones por partida.
- `apps/bingos/tests.py`: pruebas basicas de estados y permisos.
- `apps/common/templatetags/siab_tags.py`: clases visuales para los nuevos estados.

### Templates

- `templates/bingos/partidas_lista.html`: lista general de partidas.
- `templates/bingos/consola_operador.html`: consola basica del operador.
- `templates/bingos/partida_carton_formulario.html`: crear/asignar cartones a jugadores en una partida.
- `templates/bingos/lista.html`: enlace a lista de partidas.
- `templates/bingos/detalle.html`: enlaces a partidas y consola.
- `templates/bingos/partida_detalle.html`: enlaces a consola/asignacion y visualizacion de bolas extraidas.

### Documentacion

- `DOCUMENTACION/DIAGNOSTICO_BINGO_ACTUAL.md`: diagnostico previo.
- `DOCUMENTACION/ETAPA_1_PARTIDAS.md`: resumen de esta etapa.

## Estados de partida

Los estados de `Partidabingo.estadopartida` quedan centralizados en `apps/bingos/services.py`:

- `Programada`.
- `En espera`.
- `En curso`.
- `Pausada`.
- `Desempate`.
- `Finalizada`.
- `Cancelada`.

La consola permite estas acciones:

- iniciar: `Programada` o `En espera` a `En curso`.
- pausar: `En curso` a `Pausada`.
- reanudar: `Pausada` a `En curso`.
- finalizar: `En curso`, `Pausada` o `Desempate` a `Finalizada`.

Los estados heredados `En Juego` y `Verificando` se normalizan en codigo hacia `En curso` y `En espera` cuando se procesa el estado.

## Rutas creadas

- `/partidas/`: lista de partidas.
- `/partidas/<idpartidabingo>/consola/`: consola basica del operador.
- `/partidas/<idpartidabingo>/cartones/nuevo/`: crear/asignar carton a jugador dentro de una partida.
- `/partidas/<idpartidabingo>/cartones/<idcarton>/editar/`: editar asignacion de carton dentro de una partida.

Rutas existentes reutilizadas:

- `/bingos/<idbingo>/partidas/nueva/`: crear partida dentro de un bingo.
- `/partidas/<idpartidabingo>/`: detalle de partida.
- `/partidas/<idpartidabingo>/editar/`: editar partida.
- `/cartones/`: lista global de cartones.

## Como probar manualmente

1. Iniciar sesion con un usuario administrativo (`is_staff` o `is_superuser`).
2. Entrar a `/bingos/`.
3. Abrir un bingo existente.
4. Usar `+ Nueva partida` para crear una partida.
5. Confirmar que el estado inicial sugerido es `Programada`.
6. Entrar al detalle de la partida.
7. Usar `Asignar cartón` para registrar un carton con jugador.
8. Volver al detalle y confirmar que el carton aparece en la tabla.
9. Entrar a `Consola`.
10. Usar `Iniciar partida`; debe cambiar a `En curso`.
11. Usar `Pausar partida`; debe cambiar a `Pausada`.
12. Usar `Reanudar partida`; debe volver a `En curso`.
13. Usar `Finalizar partida`; debe cambiar a `Finalizada` y llenar `horafin`.
14. Iniciar sesion con un usuario autenticado sin staff y verificar que no puede acceder a `/partidas/`.

## Verificacion ejecutada

Comandos ejecutados:

```bash
python manage.py check
python manage.py test apps.bingos
python manage.py shell -c "from django.urls import reverse; print(reverse('bingos:partidas_lista')); print(reverse('bingos:consola_operador', args=[1])); print(reverse('bingos:partida_carton_nuevo', args=[1])); print(reverse('bingos:partida_carton_editar', args=[1, 2]))"
```

Resultados:

- `python manage.py check`: sin errores.
- `python manage.py test apps.bingos`: 6 pruebas ejecutadas, todas correctas.
- Las rutas nuevas resuelven correctamente.

## Pendiente para la siguiente etapa

- Registrar bolas manualmente desde la consola.
- Validar rango y repeticion de bolas.
- Actualizar `bolascantadas` y `ultimabola`.
- Mostrar tablero completo de bolas cantadas/faltantes.
- Validar cartones contra bolas cantadas.
- Confirmar ganador manualmente.
- Diseñar flujo de desempate sin automatizarlo todavia.
- Agregar WebSockets con Django Channels, Daphne y Redis en una etapa posterior.
