# Etapa 6: WebSockets publicos de solo lectura

## Objetivo

Esta etapa agrega actualizacion en tiempo real para las paginas publicas:

- `/juego/partidas/<idpartidabingo>/tablero/`
- `/juego/cartones/<codigocarton>/`

Cuando el operador saca una bola o cambia el estado de la partida, el tablero
publico y "Mi carton" pueden actualizarse sin presionar F5. Los botones de
actualizacion manual se conservan como respaldo.

## Conceptos

ASGI es la interfaz asincrona de Django. Permite atender HTTP y tambien
conexiones persistentes como WebSockets.

Django Channels agrega soporte ASGI para WebSockets, grupos de canales y envio
de eventos desde codigo Django normal hacia navegadores conectados.

Redis funciona como capa de canales compartida. En desarrollo o produccion,
Channels usa Redis para publicar un evento una vez y entregarlo a todos los
clientes unidos al grupo de una partida.

Daphne es el servidor ASGI que ejecuta `config.asgi:application`. A diferencia
de un servidor WSGI tradicional, Daphne puede mantener WebSockets abiertos.

## Archivos agregados o modificados

- `config/asgi.py`: expone `ProtocolTypeRouter` para HTTP y WebSocket.
- `config/settings.py`: agrega `ASGI_APPLICATION`, `daphne` y `CHANNEL_LAYERS`.
- `apps/bingos/routing.py`: define la ruta WebSocket publica.
- `apps/bingos/consumers.py`: consumidor publico de solo lectura.
- `apps/bingos/realtime.py`: construccion de payloads publicos y publicacion
  diferida hasta `transaction.on_commit`.
- `apps/bingos/views.py`: publica eventos despues de sacar bola, cambiar estado,
  detectar ganador o resolver desempate.
- `templates/bingos/tablero_publico.html`: marcadores `data-*` para actualizar
  tablero, resumen, historial y ganador.
- `templates/bingos/carton_publico.html`: marcadores `data-*` para actualizar
  estado, ultima bola, numeros marcados y progreso.
- `static/js/realtime_bingo.js`: cliente WebSocket con reconexion exponencial y
  sin recargar la pagina.
- `static/css/styles.css`: indicador visual de estado de conexion.
- `docker-compose.realtime.yml`: Redis local enlazado a `127.0.0.1:6379`.
- `requirements.txt` y `.env.example`: dependencias y `REDIS_URL`.

## Variable REDIS_URL

`REDIS_URL` define donde Channels encuentra Redis:

```bash
REDIS_URL=redis://127.0.0.1:6379/0
```

Si no se configura, `config/settings.py` usa ese valor por defecto.

## Levantar Redis

El compose de esta etapa levanta solo Redis y lo expone unicamente en localhost:

```bash
docker compose -f docker-compose.realtime.yml up -d redis
docker compose -f docker-compose.realtime.yml ps
```

No destruye contenedores ni volumenes existentes.

## Iniciar Daphne

Con el entorno virtual activo:

```bash
source .venv/bin/activate
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

Si el puerto `8000` esta ocupado, usar otro puerto, por ejemplo `-p 8001`.

## Volver a runserver

Para volver al flujo conocido de desarrollo:

```bash
source .venv/bin/activate
python manage.py runserver
```

Con `daphne` instalado en `INSTALLED_APPS`, `runserver` usa la aplicacion ASGI
en desarrollo. Redis debe seguir disponible si se quieren probar eventos entre
procesos.

## Ruta WebSocket

La ruta publica es:

```text
ws://<host>/ws/juego/partidas/<idpartidabingo>/
```

En HTTPS debe usarse `wss://`.

El consumidor valida que la partida exista. Si no existe, cierra la conexion con
codigo `4404`. El navegador no envia comandos administrativos por esta ruta; los
mensajes recibidos desde cliente se ignoran.

## Eventos publicos

Las acciones administrativas publican estos eventos despues de confirmar la
transaccion:

- `partida_iniciada`
- `partida_pausada`
- `partida_reanudada`
- `partida_finalizada`
- `bola_extraida`
- `desempate_detectado`
- `ganador_detectado`
- `desempate_finalizado`

El payload enviado al navegador tiene forma publica:

```json
{
  "tipo": "partida_actualizada",
  "evento": "bola_extraida",
  "partida": {
    "id": 20,
    "estado": "En curso",
    "estado_visible": "En curso",
    "mensaje_estado": "La partida esta en juego.",
    "mensaje_estado_carton": "La partida esta en juego.",
    "total_extraidas": 2,
    "cantidad_extraida": 2,
    "restantes": 73,
    "bolas_extraidas": [2, 23],
    "ultima_bola": {"numero": 23, "codigo": "I-23"},
    "ganador": null,
    "finalizada": false,
    "resuelta_por_desempate": false
  }
}
```

`ganador` solo se informa cuando la partida esta finalizada.

## Datos privados excluidos

El payload publico no incluye:

- `idbingadores`
- tiros de desempate
- codigos de cartones ajenos
- precio pagado
- datos internos de modelos o base de datos
- acciones administrativas disponibles

## Reconexion

`static/js/realtime_bingo.js` intenta reconectar con espera exponencial hasta
30 segundos. No recarga la pagina. Si el servidor cierra con `4404`, queda en
modo manual para evitar reconectar indefinidamente a una partida inexistente.

## Prueba manual con dos pestanas

1. Levantar Redis.
2. Iniciar Daphne o `python manage.py runserver`.
3. Abrir una pestana con `/juego/partidas/<idpartidabingo>/tablero/`.
4. Abrir otra pestana o navegador con `/juego/cartones/<codigocarton>/`.
5. En una sesion administrativa, sacar una bola desde la consola del operador.
6. Verificar que tablero y carton actualicen ultima bola, historial, marcados y
   progreso sin F5.
7. Pausar, reanudar o finalizar la partida y verificar que el estado publico
   cambie solo.

## Pruebas automatizadas

Las pruebas WebSocket no requieren Docker ni Redis real. Usan:

```text
channels.layers.InMemoryChannelLayer
```

El `asyncio.TimeoutError` visto durante el desarrollo se reproducia por esperas
asincronas de `WebsocketCommunicator` cuando se abrian varias conexiones reales
en el mismo proceso de test. La cobertura quedo dividida entre una prueba de
comunicacion real con `WebsocketCommunicator` y pruebas directas del consumidor
para cierre controlado, ruta, solo lectura y limpieza de grupos.

## Pendiente despues de esta etapa

- Definir despliegue real de Daphne/ASGI detras de proxy reverso.
- Configurar supervision del proceso ASGI y Redis en produccion.
- Agregar observabilidad de conexiones y errores WebSocket.
- Evaluar autenticacion futura para experiencias privadas de jugador, si el
  alcance del sistema lo requiere.
