# Etapa 3: validación de ganador y detección de empate

## Alcance

Esta etapa permite que un operador administrativo valide manualmente un cartón
desde la consola. No implementa reclamos del jugador, patrones parciales,
desempate automático, finalización automática ni comunicación por WebSockets.

## Regla de victoria

La regla implementada es **cartón completo**:

- la matriz debe ser de 5 filas por 5 columnas;
- debe respetar los rangos B-I-N-G-O;
- debe contener 24 números enteros únicos;
- la posición central `[2][2]` debe ser `"LIBRE"`;
- los 24 números reales deben estar en `Partidabingo.bolascantadas`.

No se consideran líneas, diagonales, esquinas ni otros patrones.

## Comparación de matriz y bolas

`obtener_numeros_carton()` valida la matriz y produce una lista ordenada de sus
24 enteros, excluyendo `"LIBRE"`. `parsear_bolas_cantadas()` convierte JSON y
formatos legados al conjunto efectivo de bolas entre 1 y 75.

Los números faltantes se calculan así:

```text
números del cartón - bolas extraídas
```

El cartón gana únicamente cuando esa diferencia está vacía. La casilla LIBRE se
marca automáticamente y nunca aparece en la lista de pendientes.

Las matrices dañadas, incluida la forma legada 2x3 encontrada en el respaldo,
no pueden ganar. La consola muestra un error controlado y el servicio registra
un `WARNING` con los identificadores de partida/cartón y la causa técnica.

## Validación transaccional

`validar_carton_ganador()`:

1. comprueba que la partida esté exactamente en `En curso`;
2. comprueba que el cartón corresponda a la partida de la URL;
3. abre `transaction.atomic()`;
4. bloquea la partida con `select_for_update()`;
5. vuelve a comprobar el estado;
6. bloquea todos los cartones de la partida con
   `select_for_update(of=("self",))`;
7. valida nuevamente pertenencia, asignación, estado y matriz;
8. busca todos los cartones completos con las bolas actuales;
9. guarda en una sola operación el ganador o los datos de empate.

Este orden evita resultados inconsistentes entre dos operadores y también
serializa la validación frente a la extracción de una nueva bola, porque ambas
operaciones bloquean la misma fila de partida.

El parámetro `of=("self",)` limita el bloqueo a las filas de `carton`. Esto
permite conservar `select_related("idjugador")` sin pedir a PostgreSQL que
bloquee el lado nullable del `OUTER JOIN` generado por esa relación.

## Ganador único

Cuando existe exactamente un cartón ganador:

- `Partidabingo.idjugadorganador` se asigna al jugador del cartón;
- `Partidabingo.haydesempate` se guarda como `false`;
- `Partidabingo.idbingadores` guarda una lista JSON con el cartón y jugador
  confirmados;
- `Partidabingo.estadopartida` permanece `En curso`;
- la partida no se finaliza automáticamente.

No existe un campo físico específico para el identificador del cartón ganador.
Por eso se usa el `TextField` relacionado `idbingadores` con el mismo formato
estructurado empleado en empates. `Carton.indicevictoria` no se reutiliza porque
esta etapa exige mantener los cartones sin modificaciones.

## Detección de empate

Si dos o más cartones vendidos y asignados están completos:

- `Partidabingo.idjugadorganador` queda en `NULL`;
- `Partidabingo.estadopartida` cambia a `Desempate`;
- `Partidabingo.haydesempate` se guarda como `true`;
- `Partidabingo.idbingadores` guarda los candidatos;
- `bolamayordesempate` no se modifica en esta etapa.

No se elige un jugador arbitrariamente, incluso si el operador pulsó validar
sobre uno de los cartones completos.

## Formato de `idbingadores`

`idbingadores` es un `TextField` nullable. El formato nuevo es JSON compacto,
ordenado por `idcarton`, con una lista de objetos. Contiene un elemento para un
ganador único y varios para un empate:

```json
[{"idcarton":31,"codigocarton":"P20-C-31","idjugador":41,"jugador":"Jugador 41"},{"idcarton":32,"codigocarton":"P20-C-32","idjugador":42,"jugador":"Jugador 42"}]
```

El parser de lectura también acepta valores vacíos, listas JSON antiguas de
identificadores y texto con identificadores separados por espacios, comas,
punto y coma o barra vertical.

## Estados

La validación solo está permitida en:

- `En curso`.

Está bloqueada en:

- `Programada`;
- `En espera`;
- `Pausada`;
- `Desempate`;
- `Finalizada`;
- `Cancelada`.

## Ruta creada

```text
POST /partidas/<idpartidabingo>/cartones/<idcarton>/validar/
```

Nombre Django: `bingos:validar_carton`.

La ruta usa `admin_required`, `require_POST` y CSRF. Solo usuarios `is_staff` o
superusuarios pueden ejecutarla. Un GET devuelve `405 Method Not Allowed`.

## Interfaz

La consola muestra:

- ganador confirmado;
- estado de empate;
- candidatos almacenados en `idbingadores`;
- una tabla B-I-N-G-O por cartón;
- números extraídos en verde;
- números pendientes diferenciados;
- casilla LIBRE resaltada;
- cantidad marcada y lista de pendientes;
- botón **Validar cartón**, activo únicamente en `En curso` y para matrices
  válidas de cartones vendidos/asignados.

Los cartones `Disponible`, `Cerrado` o sin jugador no aparecen en esta sección.
La ruta vuelve a exigir la misma elegibilidad y además obtiene el cartón
acotándolo desde el inicio a la partida incluida en la URL.

## Archivos modificados

- `apps/bingos/services.py`;
- `apps/bingos/views.py`;
- `apps/bingos/urls.py`;
- `apps/bingos/tests.py`;
- `templates/bingos/consola_operador.html`;
- `static/css/styles.css`;
- `DOCUMENTACION/ETAPA_3_VALIDACION_GANADOR.md`.

## Prueba manual

1. Iniciar sesión como staff o superusuario.
2. Crear y asignar uno o más cartones antes de iniciar la partida.
3. Abrir la consola y poner la partida en `En curso`.
4. Extraer bolas y observar cómo se marcan las matrices.
5. Validar un cartón incompleto y comprobar que el mensaje enumera pendientes
   sin cambiar el estado ni el ganador.
6. Completar las 24 bolas de un único cartón y validarlo; comprobar
   `idjugadorganador` y que la partida siga `En curso`.
7. Preparar dos cartones completos con el mismo historial y validar uno;
   comprobar estado `Desempate`, `haydesempate=true`, ganador nulo y candidatos.
8. Pausar o finalizar una partida y verificar que el botón queda deshabilitado.
9. Intentar un GET a la ruta de validación y comprobar la respuesta 405.

Validación automatizada:

```bash
python manage.py check
python manage.py test apps.bingos
```

## Pendiente antes de WebSockets

Antes de tiempo real todavía se debe definir:

- evento canónico de bola extraída, cartón validado y empate detectado;
- autenticación/autorización de conexiones ASGI;
- grupos por partida y sincronización inicial;
- orden, idempotencia y recuperación de eventos;
- reglas y pantalla de la ronda de desempate;
- reclamo de Bingo por parte del jugador;
- infraestructura Channels/Redis/Daphne y su observabilidad;
- pruebas concurrentes de integración contra PostgreSQL disponible.

Esta etapa no instala ni configura esos componentes.
