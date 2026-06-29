# Etapa 5: tablero público y vista de cartón

## Alcance

Esta etapa agrega una experiencia pública y de solo lectura para consultar
partidas, seguir el tablero 1–75 y revisar un cartón mediante su código. No
incluye reclamo de Bingo, acciones del operador, pagos ni actualización en
tiempo real.

La actualización se realiza recargando con F5 o mediante los botones
**Actualizar tablero** y **Actualizar cartón**, que ejecutan únicamente GET.

## Relación entre usuario Django y jugador

La inspección de `apps/seguridad`, el modelo `Jugador`, los modelos generados
por `inspectdb`, la configuración de autenticación y las rutas de login confirmó
que el proyecto usa el `User` estándar de Django y que no existe una FK ni una
relación OneToOne física entre `User` y `Jugador`.

Por ese motivo no se implementó **Mis cartones** y no se usa el alias o correo
del jugador como autenticación. El acceso demostrativo se realiza con el código
exacto del cartón. Una etapa posterior deberá definir una relación formal entre
la cuenta autenticada y el jugador antes de ofrecer un listado privado de sus
cartones.

## Páginas y rutas

```text
GET       /juego/
GET       /juego/partidas/<idpartidabingo>/tablero/
GET|POST  /juego/cartones/acceder/
GET       /juego/cartones/<codigocarton>/
```

Nombres Django:

- `bingos:sala_juego_publica`;
- `bingos:tablero_publico`;
- `bingos:acceder_carton_publico`;
- `bingos:carton_publico`.

El POST del formulario solo verifica si el código existe y redirige a la página
GET del cartón. Está protegido por CSRF y no escribe datos.

## Sala pública

La sala muestra todas las partidas y, para cada una:

- nombre del Bingo;
- nombre de ronda;
- estado;
- premio efectivo y material;
- cantidad de bolas extraídas;
- última bola disponible;
- enlace al tablero público.

No muestra jugadores, códigos de cartones, precios pagados, ganadores
provisionales, candidatos de desempate ni contenido de `idbingadores`.

## Tablero público

El tablero reutiliza el parser y formateador de bolas de las etapas anteriores.
Muestra:

- Bingo, ronda, estado y premio;
- total extraído y restante;
- última bola con letra B-I-N-G-O;
- historial de extracción;
- tablero de 75 números por columnas B, I, N, G y O;
- mensaje público según el estado.

Cuando la partida está `Finalizada`, muestra al ganador únicamente si
`idjugadorganador` existe. Si `haydesempate` es verdadero, solo informa que la
partida se resolvió mediante desempate; nunca expone candidatos, tiros o JSON.

## Consulta de cartón

El visitante introduce el código exacto entregado con el cartón. Un código
inexistente produce un mensaje genérico y no revela consultas, IDs internos ni
detalles de la base.

La pantalla del cartón muestra exclusivamente:

- código consultado;
- alias del jugador, si existe;
- Bingo, ronda y estado de la partida;
- matriz 5x5 B-I-N-G-O;
- casilla `LIBRE`;
- números extraídos y pendientes;
- contador de números reales marcados.

No muestra precio pagado, correo, saldo, otros jugadores, otros cartones,
identificadores internos ni acciones administrativas.

## Marcados y pendientes

`preparar_datos_carton_jugador()` usa los servicios existentes para validar la
matriz, interpretar `bolascantadas` y construir las casillas visuales.

Los números marcados se calculan como:

```text
24 - cantidad de números del cartón que aún no están en bolascantadas
```

`LIBRE` se resalta automáticamente, pero no suma al contador de 24 números
reales. Si la matriz es inválida, la página muestra un error controlado y se
registra un `WARNING` con el identificador técnico del cartón.

## Mensajes por estado

- `Programada` o `En espera`: la partida aún no ha comenzado.
- `En curso`: la partida está en juego.
- `Pausada`: la partida está pausada.
- `Desempate`: la partida está resolviendo un desempate.
- `Finalizada`: la partida terminó.
- `Cancelada`: la partida fue cancelada.

## Solo lectura y permisos

Las páginas públicas no requieren login ni permisos de staff. Sus vistas no
llaman a servicios de extracción, transición, validación o desempate y no usan
`save()`, `update()` ni transacciones de escritura.

Las rutas administrativas existentes conservan `admin_required`, por lo que
siguen limitadas a staff o superusuarios. La navegación pública muestra
**Sala de juego** y **Consultar cartón** sin reemplazar el menú administrativo
de usuarios autenticados.

## Prueba manual

1. Abrir `/juego/` en una ventana anónima.
2. Entrar al tablero de una partida y comprobar estado, última bola, historial
   y tablero 1–75.
3. Recargar con F5 y verificar que solo refleja los datos ya persistidos.
4. Abrir `/juego/cartones/acceder/` e introducir un código válido.
5. Comprobar matriz, `LIBRE`, números marcados y contador.
6. Probar un código inexistente y una matriz inválida.
7. Confirmar que no aparecen precios, otros cartones, candidatos de desempate
   ni botones administrativos.

## Pendiente antes de WebSockets

Antes de incorporar tiempo real se deben definir eventos públicos seguros,
grupos por partida, autenticación ASGI, sincronización inicial, orden e
idempotencia de eventos, recuperación después de desconexión y la
infraestructura Django Channels/Redis/Daphne. El login real de jugadores
también requiere primero una relación física formal entre `User` y `Jugador`.
