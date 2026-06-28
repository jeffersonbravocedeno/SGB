# Etapa 2: extracción manual y segura de bolas

## Alcance

Esta etapa agrega la acción manual **Sacar siguiente bola** a la consola del
operador. No modifica cartones, no detecta ganadores, no ejecuta desempates y
no incorpora WebSockets ni procesos en segundo plano.

## Formato de `bolascantadas`

`Partidabingo.bolascantadas` continúa siendo el `TextField` de la tabla física
existente. Toda escritura nueva usa JSON compacto con una lista ordenada de
números enteros únicos:

```json
[12,24,39,55]
```

La letra no se duplica en la base. Se calcula al mostrar la bola:

- B: 1 a 15.
- I: 16 a 30.
- N: 31 a 45.
- G: 46 a 60.
- O: 61 a 75.

`ultimabola` guarda únicamente el entero de la última bola extraída.

### Compatibilidad con datos anteriores

El respaldo inspeccionado contiene `[]` en `bolascantadas` y `0` en
`ultimabola`. El campo es texto sin restricción de formato y el formulario/parser
de la etapa anterior permitía JSON libre o texto manual; esa es la causa de que
puedan existir valores legados.

El nuevo parser admite, sin modificar los registros al consultarlos:

- valores vacíos, `null` y `[]`;
- JSON con números o cadenas;
- JSON antiguo con objetos que tengan `numero` o `codigo`;
- códigos como `B-12` o `I-24`;
- texto separado por espacios, comas, punto y coma o barra vertical.

Los valores inválidos, fuera de 1 a 75 o duplicados se descartan al interpretar
el historial. Cuando se extrae una nueva bola, el historial válido se normaliza
al formato JSON canónico de enteros.

## Integridad y concurrencia

`extraer_siguiente_bola()` realiza el siguiente flujo:

1. Comprueba que el estado sea exactamente `En curso`.
2. Abre `transaction.atomic()`.
3. Recupera la partida con `select_for_update()`.
4. Vuelve a validar el estado con la fila bloqueada.
5. calcula `1..75` menos las bolas ya registradas.
6. Selecciona una disponible con `random.SystemRandom().choice()`.
7. Guarda conjuntamente `bolascantadas` y `ultimabola`.

El bloqueo de fila serializa pulsaciones concurrentes sobre la misma partida.
La segunda transacción lee el historial actualizado, por lo que no puede elegir
la bola que acaba de guardar la primera.

Si las 75 bolas ya fueron extraídas o el guardado falla, no se modifica ningún
campo.

## Estados

La extracción está permitida únicamente en:

- `En curso`.

Está bloqueada en:

- `Programada`;
- `En espera`;
- `Pausada`;
- `Desempate`;
- `Finalizada`;
- `Cancelada`.

La regla se valida en el servicio del backend. El botón deshabilitado es solo
una representación adicional en la interfaz.

## Ruta creada

```text
POST /partidas/<idpartidabingo>/sacar-bola/
```

Nombre Django: `bingos:sacar_bola`.

La ruta usa `admin_required`, acepta exclusivamente POST y está protegida por
CSRF. Solo usuarios `is_staff` o superusuarios pueden ejecutarla.

## Archivos modificados

- `apps/bingos/services.py`: parseo, formato, tablero, disponibilidad y
  extracción transaccional.
- `apps/bingos/views.py`: endpoint POST y contexto visual de la consola.
- `apps/bingos/urls.py`: ruta `sacar-bola`.
- `apps/bingos/tests.py`: pruebas unitarias y de permisos/método HTTP.
- `templates/bingos/consola_operador.html`: botón, última bola, historial,
  contadores y tablero B-I-N-G-O.
- `static/css/styles.css`: estilos del bolillero y tablero.
- `DOCUMENTACION/ETAPA_2_BOLAS.md`: este documento.

## Prueba manual

1. Iniciar sesión con un usuario staff o superusuario.
2. Abrir la consola de una partida.
3. Poner la partida en `En curso` mediante las acciones existentes.
4. Pulsar **Sacar siguiente bola**.
5. Comprobar el mensaje de éxito, la tarjeta de última bola, el historial, los
   contadores y el número resaltado en el tablero.
6. Pulsar nuevamente y comprobar que no se repite la bola anterior.
7. Pausar la partida y verificar que el historial sigue visible, pero el botón
   queda deshabilitado.
8. Intentar un GET directo a `/partidas/<id>/sacar-bola/` y comprobar que el
   servidor responde `405 Method Not Allowed`.

Validación automatizada:

```bash
python manage.py check
python manage.py test apps.bingos
```

## Pendiente antes de WebSockets

Antes de incorporar actualización en tiempo real se debe definir:

- el evento y carga útil canónica de una bola extraída;
- autenticación y autorización de conexiones ASGI;
- grupos por partida y reglas de reconexión;
- sincronización inicial del historial al conectar;
- control de eventos duplicados y orden de mensajes;
- infraestructura y operación de Channels/Redis/Daphne;
- pruebas de integración concurrente con PostgreSQL disponible;
- estrategia de despliegue, observabilidad y recuperación ante caídas.

Esta etapa no instala ni configura ninguno de esos componentes.
