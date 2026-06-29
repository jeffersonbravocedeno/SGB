# Etapa 4: desempate por balota mayor

## Alcance y regla aplicada

Esta etapa implementa el desempate administrativo entre los jugadores que
quedaron candidatos después de validar varios cartones completos.

- Cada **jugador** candidato recibe un único tiro, aunque tenga varios cartones
  ganadores.
- Cada tiro es una balota aleatoria entre 1 y 75 generada en el backend con
  `random.SystemRandom()`.
- Una balota no puede asignarse a dos candidatos del mismo desempate.
- Gana el jugador que obtiene el número más alto.
- Completar los tiros solo produce un resultado provisional.
- La partida se finaliza únicamente cuando el operador confirma el ganador.

No se implementan pagos, liquidación de premios, reportes ni tiempo real.

## Persistencia utilizada

La inspección de `Partidabingo` y del `inspectdb` existente confirmó que la
tabla física no tiene un campo `sorteodesempate`. No se agregaron campos,
migraciones ni tablas. Los candidatos, sus cartones y sus tiros se conservan en
el `TextField` existente `Partidabingo.idbingadores`.

Después del primer tiro se guarda JSON compacto con esta estructura exacta:

```json
[{"idjugador":41,"jugador":"juan123","cartones":[{"idcarton":31,"codigocarton":"P20-C-31"}],"tiro_desempate":67},{"idjugador":42,"jugador":"maria456","cartones":[{"idcarton":32,"codigocarton":"P20-C-32"}],"tiro_desempate":null}]
```

Los candidatos conservan su orden de aparición. Los cartones repetidos se
eliminan por `idcarton` sin descartar su código.

## Compatibilidad con formatos anteriores

La lectura acepta:

1. La lista plana de Etapa 3, con un objeto por cartón:

   ```json
   [{"idcarton":31,"codigocarton":"P20-C-31","idjugador":41,"jugador":"juan123"}]
   ```

2. Listas JSON antiguas de IDs.
3. Texto con IDs separados por comas, espacios, punto y coma o barra vertical,
   por ejemplo `41,42`.
4. El formato agrupado de esta etapa.

Antes de operar, `normalizar_candidatos_desempate()` agrupa todas las entradas
por `idjugador`, combina sus cartones y conserva el tiro existente. Si un mismo
jugador tiene dos tiros contradictorios o dos jugadores comparten una balota,
la operación se rechaza sin guardar cambios.

## Separación respecto de las bolas normales

Los tiros de desempate no representan extracciones del bolillero normal. Por
eso nunca se agregan a `bolascantadas` ni sustituyen `ultimabola`. Ambos campos
se mantienen exactamente como estaban antes del desempate.

El formato B-I-N-G-O solo se usa para mostrar el tiro:

- B: 1–15;
- I: 16–30;
- N: 31–45;
- G: 46–60;
- O: 61–75.

## Seguridad y concurrencia

`sortear_balota_desempate()` y `confirmar_y_finalizar_desempate()`:

1. exigen el estado `Desempate`;
2. abren `transaction.atomic()`;
3. bloquean la partida con `select_for_update()`;
4. vuelven a comprobar el estado y los candidatos después del bloqueo;
5. validan todos los tiros persistidos;
6. guardan todos los cambios en una única operación.

El bloqueo hace que dos operadores sobre la misma partida se atiendan en
secuencia. El segundo operador siempre vuelve a leer los tiros guardados por el
primero, por lo que no puede repetir jugador ni balota.

Todos los endpoints requieren staff o superusuario. Los cambios usan POST y
CSRF. Los GET de las rutas de sorteo y confirmación devuelven 405.

## Confirmación final

Solo se permite confirmar cuando todos los candidatos tienen tiro. La
confirmación guarda conjuntamente:

- `idjugadorganador`: jugador con la balota más alta;
- `bolamayordesempate`: número del tiro ganador;
- `estadopartida`: `Finalizada`;
- `horafin`: hora actual;
- `haydesempate`: `true`;
- `idbingadores`: candidatos, cartones y tiros como evidencia.

No modifica `bolascantadas` ni `ultimabola`.

## Estados

Los tiros y la confirmación solo se permiten en `Desempate`.

Se bloquean en:

- `Programada`;
- `En espera`;
- `En curso`;
- `Pausada`;
- `Finalizada`;
- `Cancelada`.

La consola normal también bloquea extracción, validación, generación de
cartones y finalización genérica mientras la partida está en `Desempate`.

## Rutas

```text
GET  /partidas/<idpartidabingo>/desempate/
POST /partidas/<idpartidabingo>/desempate/<idjugador>/sortear/
POST /partidas/<idpartidabingo>/desempate/confirmar/
```

Nombres Django:

- `bingos:desempate_operador`;
- `bingos:sortear_desempate`;
- `bingos:confirmar_desempate`.

## Persistencia después de F5

La vista reconstruye todas las tarjetas desde `idbingadores`. Un candidato que
ya tiene `tiro_desempate` aparece con su código B-I-N-G-O y con el botón
deshabilitado. Cuando todos han tirado, el resultado provisional se vuelve a
calcular usando los valores persistidos. Recargar la página no genera números
ni ejecuta escrituras.

## Prueba manual

1. Iniciar sesión como staff o superusuario.
2. Provocar un empate validando varios cartones completos.
3. Desde la consola pulsar **Ir al desempate**.
4. Verificar que los cartones del mismo jugador estén agrupados en una tarjeta.
5. Sortear una balota y recargar con F5; el tiro debe permanecer y su botón debe
   estar deshabilitado.
6. Sortear los candidatos restantes; ninguna balota debe repetirse.
7. Comprobar el resultado provisional y que la partida continúe en
   `Desempate`.
8. Pulsar **Confirmar ganador y finalizar partida**.
9. Verificar ganador, balota mayor, hora de finalización y estado `Finalizada`.
10. Confirmar que el historial de bolas normales y `ultimabola` no cambiaron.

Validación automatizada:

```bash
source .venv/bin/activate
python manage.py check
python manage.py test apps.bingos
git diff --check
```

## Etapas posteriores

Quedan fuera de este alcance la liquidación de premios, pagos, reportes,
reclamos del jugador, eventos en tiempo real, autenticación ASGI y la
infraestructura Django Channels/Redis/Daphne.
