# Plan técnico de corrección de cartones híbridos de SIAB

Fecha: 2026-07-05  
Fase: 0.5 — planificación, sin cambios funcionales ni de PostgreSQL  
Fuente principal: `docs/AUDITORIA_TECNICA_SIAB.md`

## Alcance y reglas del plan

Este documento convierte la auditoría de la Fase 0 en una secuencia de
cambios pequeños, verificables y reversibles. En esta fase no se modifican
modelos, vistas, servicios, formularios, plantillas, rutas, permisos,
migraciones ni scripts SQL. Tampoco se consulta o altera la base real `bingo`.

El plan adopta estos invariantes como contrato de negocio:

1. cada `Carton` nuevo es un cartón maestro de un solo `Bingo`;
2. el cartón tiene una participación independiente en cada ronda de ese Bingo;
3. crear una ronda después de la venta no puede dejar fuera cartones válidos;
4. el resultado de una ronda se guarda en `CartonPartidaBingo`, no en los
   campos históricos del maestro;
5. un mismo maestro puede ganar rondas diferentes;
6. no puede existir más de una participación del mismo maestro en la misma
   ronda;
7. precio, compra y recaudación pertenecen al maestro y se contabilizan una
   sola vez;
8. `Pago` no se reutiliza porque actualmente representa pagos de préstamos;
9. toda escritura coordinada usa `transaction.atomic()`, bloqueos en orden
   estable, validación del servidor y manejo de `IntegrityError`.

La estructura física de PostgreSQL es una precondición, no una consecuencia
automática del código Django. Ningún paso de este plan autoriza ejecutar SQL.

## 1. Estado actual comprobado

### 1.1 Implementado en código

| Capacidad | Evidencia actual | Evaluación |
|---|---|---|
| Cartón maestro por Bingo | `Carton.idbingo` y `crear_carton_maestro_para_bingo()` | Implementado en el flujo nuevo |
| Relación histórica | `Carton.idpartida`, opcional | Conservada para compatibilidad |
| Participación por ronda | Modelo `CartonPartidaBingo` | Implementado en ORM |
| Un precio por maestro | `Carton.preciopagado`; la participación no tiene precio | Diseño correcto |
| Venta atómica | `transaction.atomic()` y bloqueos de Bingo/rondas | Implementada, con validaciones todavía parciales |
| Una participación por ronda actual | El servicio crea una fila por cada ronda existente | Implementado al vender |
| Ganador por participación | `validar_participacion_ganadora()` | Implementado |
| Victoria en rondas distintas | Índice y estado viven en cada participación | Soportado por el modelo lógico |
| Desempate por participación | `sortear_balota_desempate_participacion()` y `confirmar_y_finalizar_desempate_participaciones()` | Implementado como servicio aislado |
| Reporte general por maestros | `construir_resumenes_cartones_bingo()` | Deduplica maestros |
| Protección de mismo Bingo | Validaciones de servicios y constraints propuestos | Parcial hasta confirmar PostgreSQL |

### 1.2 Incompleto o conectado al flujo anterior

- `partida_nueva()` crea la ronda, pero no genera participaciones para los
  maestros ya vendidos.
- `partida_carton_nuevo()` todavía llama a `crear_y_asignar_carton()` y crea
  un cartón para una sola ronda.
- `/cartones/nuevo/` y las rutas de edición permiten guardar directamente
  matriz, precio, partida, estado e índice.
- el servicio legado no asigna `Carton.idbingo`, por lo que no cumple el
  contrato actual del modelo híbrido.
- las rutas de desempate llaman a los servicios legados por jugador, no a los
  servicios por participación.
- el desempate legado puede agrupar dos cartones del mismo jugador, perder el
  identificador de participación y finalizar la ronda sin actualizar las
  participaciones candidatas.
- el detalle de Bingo y el detalle de ronda consultan principalmente
  `Carton.idpartida`, por lo que omiten maestros híbridos o sus participaciones.
- los Excel por ronda vuelven a presentar y sumar el precio del maestro por
  cada participación.
- la venta nueva valida precio positivo, pero no el precio autorizado, estado
  del jugador ni estado de pago.

### 1.3 Dependencias físicas no confirmadas en `bingo`

El código actual presupone:

- columna no nula `carton.idbingo`;
- tabla `carton_partida_bingo`;
- PK autogenerada/IDENTITY para `idcartonpartidabingo`;
- FK de `carton.idbingo` hacia `bingo.idbingo`;
- coherencia de Bingo entre maestro, ronda y participación;
- `UNIQUE(idcarton, idpartida)`;
- estados e índices permitidos por CHECK;
- índices de búsqueda por Bingo, ronda y estado.

La auditoría solo encontró confirmación documental de estas estructuras en
`bingo_ensayo_hibridos`. El último preflight documentado sobre `bingo` indicó
que `carton.idbingo` y `carton_partida_bingo` no existían. No debe desplegarse
ningún cambio dependiente del esquema hasta resolver esta diferencia.

## 2. Riesgos actuales

### 2.1 Cartón excluido de una ronda creada después

Ejemplo:

1. el Bingo 10 tiene tres rondas;
2. se venden los cartones maestros A y B;
3. cada cartón recibe tres participaciones;
4. después se crea la cuarta ronda;
5. `partida_nueva()` solo guarda la ronda.

Resultado actual: A y B permanecen con tres participaciones. No aparecen en la
validación híbrida de la cuarta ronda, aunque su compra correspondía al Bingo
completo. La venta y la operación dejan de representar el mismo contrato.

### 2.2 Doble conteo de recaudación

Ejemplo: un cartón maestro pagó `$10.00` y participa en cuatro rondas. Su
recaudación real es `$10.00`. Si un resumen agrega el precio de cada
participación, informa `$40.00`.

El resumen final del Bingo ya suma maestros únicos, pero la hoja por rondas y
el Excel de ronda calculan subtotales desde filas de participación. Si esos
subtotales se suman o se usan para liquidación, se duplica el ingreso.

También debe definirse qué estados cuentan como recaudados. Sumar todo precio
no nulo puede incluir cartones disponibles o no confirmados. Hasta que exista
una entidad de venta/pago, el criterio de estado requiere decisión del usuario.

### 2.3 Rutas antiguas incompatibles

`/partidas/<id>/cartones/nuevo/` crea un nuevo `Carton` por ronda, guarda otro
precio y no establece `idbingo`. En un Bingo de tres rondas, repetir la acción
puede crear tres maestros y registrar tres precios para una compra que debía
ser única. Con `carton.idbingo NOT NULL`, el INSERT legado además puede fallar.

Las rutas genéricas `/cartones/nuevo/`, `/cartones/<id>/editar/` y la edición
por ronda evitan el servicio híbrido. Pueden alterar matriz, dueño, precio,
relación histórica o resultado sin bloquear el registro ni reconstruir sus
participaciones.

### 2.4 Desempate híbrido no conectado

La validación híbrida genera candidatos identificados por
`idcartonpartidabingo`. La interfaz actual sortea mediante `idjugador` y usa el
normalizador legado, que agrupa candidatos del mismo jugador.

Ejemplo: un jugador tiene dos cartones ganadores en la misma ronda. El modelo
híbrido reconoce dos participaciones candidatas; la ruta legada les asigna un
solo tiro por jugador. Al confirmar, actualiza `Partidabingo`, pero no marca una
participación como `Ganador` y las demás como `Cerrado`.

### 2.5 Participaciones duplicadas

La sincronización futura podría ejecutarse dos veces, recibir dos solicitudes
concurrentes o convivir con datos creados manualmente. Sin una restricción
física confirmada, dos procesos podrían insertar dos filas para el mismo
`(idcarton, idpartida)`.

La prevención debe tener dos capas:

- aplicación: bloquear, consultar las participaciones existentes y crear solo
  las faltantes dentro de una transacción;
- PostgreSQL: `UNIQUE(idcarton, idpartida)` como garantía final, capturando
  `IntegrityError` sin dejar datos parciales.

No se debe usar `ignore_conflicts=True`, porque ocultaría incoherencias en vez
de reportarlas.

### 2.6 Inconsistencia entre maestro, Bingo, ronda y participación

Una fila incoherente podría indicar:

- maestro del Bingo 1;
- ronda del Bingo 2;
- `idbingo` de participación igual al Bingo 1 o a un tercero.

El código híbrido valida esta relación, pero Django Admin, SQL manual o una
ruta genérica podrían eludirlo si las FK compuestas no existen. Las FK físicas
deben impedir la inconsistencia incluso si una capa de aplicación falla.

### 2.7 Carreras entre venta y creación de ronda

Una venta y una nueva ronda pueden ocurrir simultáneamente. Si ambas leen antes
de que la otra confirme, la venta no ve la ronda y la ronda no ve el cartón.
Para cerrar esa ventana, las dos operaciones deben adquirir primero el bloqueo
del mismo `Bingo` y respetar el mismo orden:

`Bingo` → rondas → cartones maestros → participaciones.

Así, la segunda operación siempre observa el resultado confirmado de la
primera y completa la relación faltante.

## 3. Flujo objetivo correcto

```text
Crear Bingo
    ↓
Crear las rondas iniciales
    ↓
Vender/generar un cartón maestro para el Bingo
    ↓
Registrar una sola compra y un solo precio en el maestro
    ↓
Crear una participación por cada ronda actual
    ↓
¿Se agrega otra ronda?
    ├─ No → continuar
    └─ Sí → crear, en la misma transacción, una participación para cada
            cartón maestro válido existente
    ↓
Operar una ronda y extraer bolas
    ↓
Validar matriz, propietario, Bingo, ronda y participación en el servidor
    ↓
¿Hay una sola participación ganadora?
    ├─ Sí → marcar esa participación como Ganador
    └─ No → desempatar por participación y cerrar las candidatas perdedoras
    ↓
Conservar intactas las participaciones del mismo cartón en otras rondas
    ↓
Permitir que el mismo maestro gane otra ronda
    ↓
Cerrar el Bingo y liquidar sobre cartones maestros únicos, nunca sobre
participaciones
```

### 3.1 Contratos por operación

**Venta de cartón**

- la entrada de contexto es el Bingo, no una ronda;
- el servidor obtiene el precio autorizado y valida al jugador;
- se bloquea el Bingo antes de consultar rondas;
- se crea un maestro y exactamente N participaciones para N rondas;
- un fallo revierte maestro, precio y participaciones.

**Creación de ronda**

- se bloquea primero el Bingo;
- se crea la ronda y se identifican los maestros válidos del mismo Bingo;
- se crean solo las participaciones faltantes;
- la ronda y todas sus participaciones se confirman o se revierten juntas;
- una segunda ejecución es idempotente y no duplica filas.

**Ganador y desempate**

- el candidato es una participación, no solo un jugador;
- se valida que maestro, participación y ronda pertenezcan al mismo Bingo;
- el resultado modifica únicamente la participación de esa ronda;
- el maestro y sus otras participaciones siguen disponibles para otras rondas.

**Liquidación**

- el conjunto económico se construye desde `Carton` filtrado por Bingo y por
  el estado de venta/pago aprobado;
- las participaciones solo aportan métricas deportivas: presencia, estado,
  victoria y fecha;
- ningún subtotal por ronda se suma para calcular la recaudación del Bingo.

## 4. Propuesta de corrección por subfases

### A. Confirmación de esquema PostgreSQL en base de ensayo

**Objetivo:** demostrar que `bingo_ensayo_hibridos` cumple exactamente el
contrato que usa Django, sin escribir datos.

Acciones planificadas:

1. exigir `current_database() = 'bingo_ensayo_hibridos'` y
   `transaction_read_only = on`;
2. inventariar columnas, nulabilidad, tipos, defaults e IDENTITY;
3. inventariar PK, FK, UNIQUE, CHECK e índices con sus nombres reales;
4. verificar conteos y buscar maestros sin Bingo, participaciones huérfanas,
   relaciones entre Bingos distintos y duplicados cartón-ronda;
5. comparar el resultado con `apps/bingos/models.py` y con las expectativas de
   los servicios;
6. detener el plan si hay cualquier diferencia. No “adaptar” el código a una
   anomalía sin decisión del usuario.

**Salida:** matriz de compatibilidad firmada en documentación. No hay cambio de
esquema ni datos.

### B. Normalización de creación de cartones nuevos

**Objetivo:** consolidar `crear_carton_maestro_para_bingo()` como único servicio
autorizado para cartones nuevos.

Acciones planificadas:

1. fijar pruebas de contrato antes de cambiar el servicio;
2. validar Bingo, jugador, estado del jugador, rondas y precio autorizado en el
   servidor;
3. mantener generación de código y matriz exclusivamente en el servidor;
4. conservar `transaction.atomic()` y ordenar bloqueos desde el Bingo;
5. encapsular la creación de participaciones con una validación común de
   pertenencia al mismo Bingo;
6. capturar colisiones de código y `IntegrityError` sin confirmar operaciones
   parciales;
7. dejar `Carton.idpartida` e `indicevictoria` en `NULL` para nuevos maestros;
8. no introducir una relación con `Pago`.

**Salida:** un cartón nuevo solo puede representar una compra de Bingo y su
precio se registra una vez.

### C. Compatibilidad de rutas heredadas por partida

**Objetivo:** impedir nuevas escrituras legadas sin romper enlaces guardados ni
ocultar datos históricos.

Estrategia recomendada, sujeta a autorización:

1. conservar temporalmente los nombres y patrones de URL;
2. transformar el GET de generación por partida en una redirección o aviso que
   lleve a “Vender cartón para el Bingo” usando el Bingo obtenido en servidor;
3. rechazar el POST legado sin crear registros y mostrar un mensaje de negocio;
4. retirar de las plantillas los botones que promueven el flujo por partida;
5. convertir el alta genérica de cartón en selección de Bingo o redirección al
   flujo normalizado;
6. separar edición histórica de edición de maestro y limitar los campos que se
   puedan cambiar;
7. mantener consulta de cartones antiguos sin convertirlos automáticamente;
8. registrar intentos de uso legado para decidir cuándo puede retirarse.

No se eliminará ninguna ruta en esta subfase. Retirarla posteriormente requiere
otra autorización explícita.

### D. Sincronización de participaciones al agregar una ronda

**Objetivo:** crear la ronda y todas las participaciones faltantes como una sola
operación atómica.

Acciones planificadas:

1. crear un servicio de dominio para “crear ronda con participaciones”;
2. bloquear el `Bingo` antes de guardar la ronda;
3. bloquear y ordenar los maestros válidos por `idcarton`;
4. consultar/bloquear participaciones existentes de la ronda;
5. crear una fila por maestro faltante, con el mismo `idbingo`;
6. depender de `UNIQUE(idcarton,idpartida)` como última defensa;
7. manejar `IntegrityError` y revertir también la ronda;
8. hacer que `partida_nueva()` use exclusivamente el servicio;
9. definir una operación separada de diagnóstico para participaciones ya
   faltantes. Cualquier backfill existente necesitará autorización y ensayo;
10. aplicar el mismo orden de bloqueos en venta y creación de ronda para evitar
    la carrera venta–ronda.

La definición de “maestro válido” no se decidirá automáticamente. La propuesta
base es: mismo Bingo, `idpartida IS NULL`, jugador asignado, precio válido y
estado de cartón aprobado para participación. Los estados concretos deben ser
confirmados por el usuario.

### E. Integración del desempate híbrido

**Objetivo:** conectar la consola con los servicios que ya operan por
participación, manteniendo el desempate histórico.

Acciones planificadas:

1. identificar en servidor si los candidatos son históricos o híbridos;
2. para híbridos, preparar la pantalla desde
   `idcartonpartidabingo`, sin agrupar por jugador;
3. agregar una ruta de sorteo por participación y conservar la ruta antigua por
   jugador para datos históricos;
4. hacer que la confirmación despache al servicio correcto después de validar
   el formato de candidatos;
5. bloquear ronda, candidatas y maestros en orden estable;
6. marcar una participación `Ganador` y las candidatas perdedoras `Cerrado`;
7. no escribir `Carton.indicevictoria` para maestros híbridos;
8. no modificar participaciones de otras rondas;
9. publicar el evento en tiempo real únicamente con `transaction.on_commit`;
10. mostrar códigos y alias de negocio, no IDs internos.

### F. Corrección de consultas y reportes de recaudación

**Objetivo:** separar métricas de participación de las transacciones
económicas.

Acciones planificadas:

1. definir un único cálculo de recaudación por maestros únicos;
2. filtrar por el estado de venta/pago acordado, no solo por precio no nulo;
3. eliminar “Recaudación total” de las filas por ronda o renombrarla como dato
   no liquidable sin subtotal;
4. eliminar el subtotal monetario del Excel de ronda;
5. mantener en reportes de ronda únicamente cantidad de cartones,
   participaciones y resultados;
6. mantener una hoja de liquidación del Bingo con una fila por maestro;
7. impedir que una misma PK de cartón entre dos veces al total, aunque tenga
   varias participaciones;
8. conservar históricos sin inventar pagos o participaciones;
9. documentar que los reportes por ronda no son fuente de liquidación general.

Mientras no exista una entidad de venta/pago de cartón, el plan no propondrá
reutilizar `Pago`. Si la trazabilidad económica exige método, referencia y
confirmación, se necesitará una decisión de diseño y posiblemente una tabla
nueva en otra fase.

### G. Pruebas automatizadas

**Objetivo:** convertir cada invariante en una prueba antes de desplegar.

Se dividirán en dos capas:

- pruebas unitarias `SimpleTestCase` con mocks para servicios, rutas, reportes,
  manejo de errores y orden de bloqueos;
- pruebas de integración PostgreSQL únicamente en una base de ensayo aprobada,
  nunca derivadas automáticamente de `bingo`.

Las primeras pruebas se escribirán antes de los cambios funcionales. La suite
existente debe permanecer verde y cada subfase agregará sus propias regresiones.

### H. Pruebas manuales en entorno de ensayo

**Objetivo:** comprobar el flujo completo sobre PostgreSQL real de ensayo.

Precondiciones:

1. autorización para escribir exclusivamente en `bingo_ensayo_hibridos`;
2. respaldo o restauración recreable de la base de ensayo;
3. comprobación explícita de `current_database()` antes de cada sesión;
4. usuario sin acceso a DDL ni a la base `bingo`;
5. instantánea de conteos y recaudación antes de probar.

Escenario mínimo:

1. crear un Bingo de prueba y tres rondas;
2. vender al menos dos maestros;
3. comprobar seis participaciones;
4. agregar una cuarta ronda y comprobar dos filas nuevas, no ocho copias;
5. repetir la sincronización y comprobar cero filas nuevas;
6. validar el mismo maestro como ganador de dos rondas distintas;
7. provocar un empate con dos participaciones, incluso del mismo jugador;
8. confirmar que solo la candidata exacta gana;
9. generar reportes y conciliar el total contra maestros únicos;
10. verificar que los enlaces heredados no crean cartones por ronda.

Las secuencias PostgreSQL no se revierten al hacer rollback de una transacción.
Por ello, el ensayo debe ser restaurable y se deben verificar también los
valores de IDENTITY. No se restaurará ni alterará una secuencia de `bingo`.

### I. Plan de despliegue seguro a la base real

**Objetivo:** desplegar solo después de demostrar compatibilidad y reversión.

Puertas de aprobación:

1. obtener autorización para una inspección de solo lectura de `bingo`;
2. comparar su esquema y datos con el ensayo;
3. si falta estructura, crear —sin ejecutar— un SQL nuevo y versionado en
   `sql/migraciones/`, con preflight, guards de base, comentarios, validaciones
   y reversión;
4. restaurar un respaldo reciente de `bingo` en
   `bingo_ensayo_hibridos` y ensayar exactamente el artefacto propuesto;
5. ejecutar pruebas automatizadas y manuales, y conciliar maestros,
   participaciones y recaudación;
6. solicitar autorización independiente para ventana, respaldo y aplicación
   manual del SQL en `bingo`;
7. aplicar primero la expansión física compatible y después el código que la
   usa;
8. ejecutar smoke tests controlados, verificar logs y monitorizar duplicados,
   ausencias y totales;
9. no ejecutar `migrate` ni `makemigrations` sobre las tablas de negocio.

La reversión preferida es volver al código anterior dejando la estructura
aditiva sin usar. Eliminar `carton_partida_bingo` o `carton.idbingo` después de
crear maestros híbridos perdería información y no debe formar parte de un
rollback rutinario. Una reversión física solo sería admisible con respaldo,
precondiciones que demuestren reconstrucción completa y autorización separada.

## 5. Archivos exactos involucrados

Esta tabla identifica archivos futuros; no autoriza modificarlos en la Fase
0.5.

| Subfase | Python, servicios y formularios | Plantillas y rutas | Pruebas | Modelos y SQL potencial | Riesgo |
|---|---|---|---|---|---|
| A | `config/settings.py` (solo lectura), `apps/bingos/models.py` (contrato de comparación) | Ninguna | Ninguna escritura; controles de solo lectura | Revisar `DATABASE/00_PREFLIGHT_CARTONES_HIBRIDOS.sql` y `DATABASE/03_VALIDACION_CARTONES_HIBRIDOS.sql`; no crear SQL aún | Bajo si se garantiza ensayo/solo lectura; crítico si se apunta a otra base |
| B | `apps/bingos/services.py`, `apps/bingos/forms.py`, `apps/bingos/views.py`; referencia a `apps/jugadores/models.py` | `templates/bingos/bingo_carton_generar.html`, `templates/bingos/detalle.html`; ruta existente en `apps/bingos/urls.py` | `apps/bingos/tests.py` | Modelos afectados lógicamente: `Bingo`, `Jugador`, `Partidabingo`, `Carton`, `CartonPartidaBingo`; SQL solo si A detecta faltantes | Alto: creación y cobro; exige atomicidad y locks |
| C | `apps/bingos/views.py`, `apps/bingos/forms.py`, `apps/bingos/services.py` | `apps/bingos/urls.py`, `templates/bingos/partida_carton_generar.html`, `partida_carton_formulario.html`, `carton_formulario.html`, `partida_detalle.html`, `consola_operador.html`, `cartones_lista.html` | `apps/bingos/tests.py` | `Carton` histórico y maestro; no se requiere DDL para redirecciones | Medio-alto: compatibilidad de enlaces y operación histórica |
| D | `apps/bingos/services.py`, `apps/bingos/views.py`, `apps/bingos/forms.py`; posible reutilización de `apps/common/ids.py` | `templates/bingos/partida_formulario.html`, `templates/bingos/detalle.html`; ruta `bingos:partida_nueva` en `apps/bingos/urls.py` | `apps/bingos/tests.py` | `Bingo`, `Partidabingo`, `Carton`, `CartonPartidaBingo`; potencial SQL de constraints o reconciliación solo tras aprobación | Crítico: carrera venta–ronda y creación masiva de relaciones |
| E | `apps/bingos/services.py`, `apps/bingos/views.py`, `apps/bingos/realtime.py` | `apps/bingos/urls.py`, `templates/bingos/desempate_operador.html`, `templates/bingos/consola_operador.html` | `apps/bingos/tests.py` | `Partidabingo`, `Carton`, `CartonPartidaBingo`; no debería requerir nueva tabla si A confirma contrato | Alto: determina ganador y cierre de ronda |
| F | `apps/bingos/reportes.py`, `apps/bingos/views.py` | Botones existentes en `templates/bingos/detalle.html` y `partida_detalle.html`; normalmente sin nueva ruta | `apps/bingos/tests.py` | Lectura de `Carton`, `CartonPartidaBingo`, `Partidabingo`; una tabla de venta sería otra decisión, no parte automática | Alto: exactitud económica |
| G | Solo `apps/bingos/tests.py`; si se separa, futuro `apps/bingos/tests/` requeriría refactor autorizado | Plantillas inspeccionadas desde pruebas | Mismo archivo y clases nuevas de contrato/regresión | Sin DDL; integración solo contra ensayo aprobado | Bajo para unitarias; medio para integración con PostgreSQL |
| H | Sin cambio funcional; posibles comandos de diagnóstico revisados | Sin cambios | Protocolo manual documentado en `docs/` | Escrituras temporales solo en `bingo_ensayo_hibridos` y con autorización | Medio; secuencias y datos de ensayo deben controlarse |
| I | Posibles ajustes de despliegue en `config/settings.py`, sin cambiar el motor | Sin cambios de interfaz obligatorios | Suite completa y smoke | Futuro `sql/migraciones/<version>_cartones_hibridos.sql` y reversión asociada, solo si A demuestra necesidad | Crítico: base real y continuidad operativa |

### 5.1 Funciones y rutas que requieren atención directa

| Elemento actual | Acción futura prevista |
|---|---|
| `crear_carton_maestro_para_bingo()` | Reforzar validaciones y convertirlo en única escritura para nuevos cartones |
| `crear_y_asignar_carton()` | Mantener solo para compatibilidad histórica interna o dejar de invocarlo desde rutas; no eliminar sin autorización |
| `partida_nueva()` | Delegar en servicio atómico de ronda + participaciones |
| `partida_carton_nuevo()` | Convertir en compatibilidad/redirección sin INSERT legado |
| `carton_nuevo()` | Redirigir a flujo por Bingo o restringir según decisión |
| `carton_editar()` y `partida_carton_editar()` | Separar campos editables por tipo y bloquear operaciones críticas |
| `validar_participacion_ganadora()` | Conservar como base de validación híbrida e integrar con desempate |
| `sortear_desempate()` | Despachar por tipo; no usar `idjugador` para híbridos |
| `confirmar_desempate()` | Usar confirmación por participación para candidatos híbridos |
| `generar_excel_cartones_partida()` | Eliminar subtotal de recaudación por participación |
| `generar_excel_resumen_bingo()` | Mantener liquidación única por maestro y retirar recaudación agregada por ronda |

## 6. Cambios de PostgreSQL requeridos

No se crea ni ejecuta ningún script en esta fase. Primero se debe verificar si
el esquema de ensayo ya contiene todo lo siguiente.

### 6.1 Tablas y columnas que deben verificarse

| Tabla | Columnas relevantes |
|---|---|
| `bingo` | `idbingo`, `preciocarton`, `estadobingo` |
| `partidabingo` | `idpartidabingo`, `idbingo`, `estadopartida`, ganador, desempate, inicio y fin |
| `carton` | `idcarton`, `idbingo`, `idpartida`, `idjugador`, `codigocarton`, `matriznumeros`, `preciopagado`, `fechacompra`, `estadocarton`, `indicevictoria` |
| `carton_partida_bingo` | PK, `idcarton`, `idpartida`, `idbingo`, estado, índice, origen, motivo, creación y validación |
| `jugador` | `idjugador`, `estadocuentajugador` |

Se debe confirmar especialmente:

- `carton.idbingo NOT NULL` para el diseño definitivo;
- `carton.idpartida` e `indicevictoria` admitiendo `NULL` para maestros nuevos;
- PK de participación con `GENERATED BY DEFAULT AS IDENTITY` o mecanismo
  compatible con `AutoField`;
- columnas de participación no nulas donde corresponda;
- ausencia de duplicados y relaciones huérfanas antes de validar constraints.

### 6.2 Restricciones recomendadas

1. PK de cada tabla en su identificador actual.
2. `UNIQUE(carton.codigocarton)`.
3. `UNIQUE(carton_partida_bingo.idcarton,
   carton_partida_bingo.idpartida)`.
4. FK `carton.idbingo → bingo.idbingo`.
5. FK `carton.idjugador → jugador.idjugador`, conservando la nulabilidad
   histórica que se confirme.
6. FK `carton.idpartida → partidabingo.idpartidabingo` para legado.
7. `UNIQUE(carton.idcarton, carton.idbingo)` y
   `UNIQUE(partidabingo.idpartidabingo, partidabingo.idbingo)` como claves
   objetivo de las FK compuestas.
8. FK compuesta `(idcarton,idbingo)` de participación hacia `carton`.
9. FK compuesta `(idpartida,idbingo)` de participación hacia `partidabingo`.
10. CHECK de estados permitidos de participación.
11. CHECK `indicevictoria IS NULL OR indicevictoria > 0`.
12. CHECK de origen y coherencia de `es_asignacion_original`.

No se recomienda agregar todavía un CHECK global sobre precio pagado: los datos
históricos incluyen cartones disponibles con precio nulo y valores que pueden
representar descuentos. La política debe definirse antes.

### 6.3 Índices recomendados

- `carton(idbingo)` para inventario y liquidación del Bingo;
- `carton(idjugador)` para cartones privados;
- `partidabingo(idbingo)` para rondas del Bingo;
- `carton_partida_bingo(idpartida)` para operación de ronda;
- `carton_partida_bingo(idbingo)` para conciliación;
- `carton_partida_bingo(idpartida, estado_participacion)` para ganadores y
  consola;
- el UNIQUE `(idcarton,idpartida)` ya sirve como índice con prefijo
  `idcarton`.

Los índices se agregarían solo si el catálogo de PostgreSQL demuestra que no
existen índices equivalentes.

### 6.4 Estrategia de reversión

1. respaldo y conteos antes de cualquier cambio;
2. expansión aditiva antes de cambiar comportamiento;
3. posibilidad de volver al código anterior sin eliminar columnas o tabla;
4. registro de filas creadas por aplicación frente a relaciones históricas;
5. script de reversión separado, con guardas que aborten si existen maestros
   híbridos no reconstruibles;
6. nunca borrar participaciones para “volver atrás” si ya contienen resultados;
7. preferir corrección hacia adelante sobre DROP de estructuras con datos.

### 6.5 Ensayo obligatorio

En `bingo_ensayo_hibridos` se probaría:

- preflight de estructura y datos;
- aplicación del SQL únicamente si un script nuevo fue autorizado;
- validación post-esquema;
- creación concurrente de venta y ronda;
- unicidad ante reintentos;
- backfill controlado de faltantes;
- ganadores y desempate por participación;
- conciliación de precios y recaudación;
- rollback de código y, solo si es seguro, reversión física ensayada.

## 7. Pruebas obligatorias

### 7.1 Matriz de casos

| ID | Caso | Preparación y acción | Resultado obligatorio |
|---|---|---|---|
| HIB-01 | Maestro en Bingo con tres rondas | Crear Bingo, tres rondas y vender un cartón | Un `Carton` con `idbingo`, históricos nulos, un precio y exactamente tres participaciones |
| HIB-02 | Cuarta ronda posterior | Partiendo de HIB-01, crear otra ronda | La ronda y una participación nueva se confirman juntas |
| HIB-03 | Todos los maestros reciben la cuarta participación | Vender varios maestros antes de HIB-02 | Cada maestro válido recibe exactamente una participación en la nueva ronda |
| HIB-04 | Idempotencia | Ejecutar dos veces la sincronización de HIB-02 | La segunda ejecución crea cero filas y no cambia las existentes |
| HIB-05 | Duplicado concurrente | Simular dos intentos para el mismo cartón-ronda | Una sola fila; el conflicto se maneja sin datos parciales |
| HIB-06 | Inconsistencia de Bingo | Intentar relacionar maestro de Bingo A con ronda de Bingo B | Rechazo de servidor y de FK física |
| HIB-07 | Mismo maestro gana dos rondas | Completar la matriz en rondas 1 y 2 y validar | Dos participaciones `Ganador`; maestro único y precio sin cambios |
| HIB-08 | No gana dos veces la misma ronda | Repetir validación de la misma participación | No se crea otro resultado ni se duplica premio/índice; respuesta idempotente o error de negocio claro |
| HIB-09 | Otra ronda no se altera | Validar ronda 1 | Estados, índice y validación de ronda 2 permanecen intactos |
| HIB-10 | Recaudación única | Un maestro de `$10` con cuatro participaciones | Total general `$10`, nunca `$40` |
| HIB-11 | Varios maestros | Maestros de `$10`, `$15` y `$20` con varias rondas | Total aprobado `$45`, sujeto al filtro de estado acordado |
| HIB-12 | Reporte de ronda no liquida | Generar PDF/Excel de una ronda | No contiene subtotal reutilizable como recaudación general; identifica que es reporte operativo |
| HIB-13 | Resumen de Bingo | Generar Excel general | Una fila económica por maestro y total deduplicado |
| HIB-14 | Ruta heredada GET | Abrir generación por partida | Redirige o informa el flujo por Bingo sin escribir |
| HIB-15 | Ruta heredada POST | Enviar el formulario antiguo | No crea cartón por ronda y entrega mensaje controlado |
| HIB-16 | Edición genérica | Intentar cambiar Bingo, partida, matriz o índice de maestro vendido | Campo no expuesto o rechazo del servidor; registro intacto |
| HIB-17 | Desempate híbrido | Dos participaciones candidatas en una ronda | Un tiro independiente por participación y ganador exacto |
| HIB-18 | Dos cartones del mismo jugador | Ambos entran al desempate híbrido | Se conservan dos candidatas, no se agrupan por jugador |
| HIB-19 | Confirmación de desempate | Confirmar HIB-17 | Ganadora en `Ganador`, perdedoras en `Cerrado`, ronda finalizada |
| HIB-20 | Compatibilidad histórica | Operar/desempatar una ronda con cartones antiguos | Sigue usando la relación histórica sin inventar participaciones |
| HIB-21 | Fallo parcial al crear ronda | Forzar error al insertar una participación | No queda ronda ni participaciones parciales |
| HIB-22 | Carrera venta–ronda | Ejecutar ambas operaciones de forma concurrente en ensayo | Al finalizar, el nuevo maestro tiene participación en la nueva ronda |

### 7.2 Pruebas de validación del servidor

También deben cubrirse:

- jugador suspendido, moroso, inexistente o sin alias según la política que se
  apruebe;
- precio alterado en POST;
- Bingo sin rondas;
- ronda no vendible;
- matriz inválida o manipulada;
- participación anulada;
- índice de victoria no positivo;
- candidato de desempate de otra ronda o Bingo;
- `IntegrityError` de código y de unicidad;
- no publicación WebSocket antes del commit;
- mensaje claro sin exponer tabla, constraint o SQL.

### 7.3 Condiciones para ejecutar pruebas

- unitarias: no deben abrir ni preparar PostgreSQL;
- integración: solo en `bingo_ensayo_hibridos` después de autorización;
- jamás usar el nombre `bingo` como base de pruebas;
- comprobar la base efectiva antes y después;
- conciliar conteos, precios y secuencias;
- no usar `--keepdb` si no se ha confirmado qué base conserva;
- ninguna prueba debe ejecutar automáticamente scripts en la base real.

## 8. Orden recomendado de implementación

| Orden | Trabajo | Motivo |
|---:|---|---|
| 1 | Subfase A: confirmar esquema en ensayo | Evita escribir código contra una estructura supuesta |
| 2 | Primera parte de G: agregar pruebas de contrato que fallen por las brechas conocidas | Fija los invariantes sin alterar comportamiento productivo |
| 3 | Subfase B: normalizar el servicio de venta | Establece una única fuente segura para nuevos maestros y participaciones |
| 4 | Subfase C: convertir rutas heredadas en compatibilidad sin escritura | Cierra entradas alternativas antes de agregar más automatización |
| 5 | Subfase D: ronda + participaciones atómicas | Resuelve la pérdida de participación y la carrera con ventas |
| 6 | Subfase E: conectar desempate híbrido | Hace coherente el resultado por participación |
| 7 | Subfase F: corregir recaudación y reportes | Separa definitivamente liquidación de operación por ronda |
| 8 | Segunda parte de G: regresión completa y pruebas de integración autorizadas | Valida interacción entre todas las correcciones |
| 9 | Subfase H: recorrido manual en ensayo | Comprueba ORM, constraints, concurrencia y reportes reales |
| 10 | Subfase I: despliegue por puertas de aprobación | Protege la base real y permite reversión controlada |

El **primer cambio de repositorio** debe ser agregar pruebas de contrato en
`apps/bingos/tests.py`, porque documenta de forma ejecutable las reglas sin
cambiar la operación actual.

El **primer cambio funcional** debe ser reforzar y centralizar
`crear_carton_maestro_para_bingo()` como único servicio para cartones nuevos.
La sincronización de rondas y la compatibilidad de rutas deben reutilizar ese
contrato; implementarlas antes produciría dos definiciones distintas de
“cartón válido” y aumentaría el riesgo de nuevas inconsistencias.

Cada subfase debe terminar con:

1. `python manage.py check` usando configuración protegida;
2. pruebas unitarias relacionadas sin base real;
3. revisión de que no se generaron migraciones;
4. documentación de archivos, comandos, errores y riesgos;
5. confirmación de que `bingo` no fue alterada.

## 9. Decisiones que requieren autorización del usuario

No se tomarán automáticamente estas decisiones:

1. consultar, incluso en solo lectura, la base real `bingo`;
2. crear un nuevo script SQL en `sql/migraciones/`;
3. ejecutar cualquier SQL, DDL, DML o backfill en PostgreSQL;
4. agregar, retirar o modificar columnas, FK, CHECK, UNIQUE o índices;
5. crear una tabla de venta o pago de cartones;
6. aplicar la expansión híbrida a `bingo`;
7. retirar rutas heredadas o cambiar definitivamente sus contratos;
8. permitir que las rutas antiguas solo redirijan o rechacen POST;
9. decidir qué estados de `Carton` representan una venta válida y qué maestros
   reciben participaciones en una ronda nueva;
10. decidir si el precio debe ser exactamente `Bingo.preciocarton` o admite
    descuentos, y quién puede autorizarlos;
11. definir un estado de pago confirmado y la fuente de liquidación mientras no
    exista entidad de venta;
12. modificar estados permitidos de Bingo, ronda, cartón o participación;
13. crear participaciones faltantes para datos ya existentes;
14. ampliar cartones históricos a rondas que no constaban en su relación
    original;
15. cambiar `Carton.idpartida` o `indicevictoria`, hacerlos no utilizables o
    retirarlos;
16. convertir automáticamente cartones antiguos en maestros híbridos;
17. elegir si el desempate se realiza por participación o por jugador para
    historia anterior; para nuevos híbridos el plan recomienda participación;
18. definir si cartones `Cerrado`, `Disponible`, anulados, sin jugador o sin
    precio participan y cuentan en recaudación;
19. ejecutar pruebas con escritura en `bingo_ensayo_hibridos`;
20. programar respaldo, mantenimiento, despliegue o rollback en `bingo`.

La autorización para crear un artefacto SQL no implica autorización para
ejecutarlo. La autorización para probar en ensayo tampoco implica autorización
para aplicar cambios en `bingo`.

## 10. Criterios de salida del plan completo

La corrección híbrida solo puede considerarse terminada cuando:

- el esquema físico efectivo está confirmado;
- todas las escrituras nuevas parten de un Bingo;
- venta y creación de ronda comparten orden de bloqueos;
- cada maestro válido tiene exactamente una participación por ronda;
- rutas heredadas no crean datos incompatibles;
- ganador y desempate operan sobre la participación exacta;
- el mismo maestro puede ganar otra ronda sin reutilizar el resultado anterior;
- la recaudación se calcula una vez por maestro elegible;
- los reportes por ronda no funcionan como liquidación;
- la suite automatizada y el ensayo manual concilian datos y totales;
- existe un procedimiento de despliegue y reversión aprobado;
- ninguna acción se ejecutó en `bingo` sin autorización explícita.

## 11. Verificación de la Fase 0.5

Esta fase solo creó documentación. Para impedir cualquier uso accidental de
la base real, el check se ejecutó con `DB_NAME=bingo_ensayo_hibridos` y
`PGOPTIONS='-c default_transaction_read_only=on'`.

| Comando o control | Resultado |
|---|---|
| Lectura de la auditoría con `sed` y búsquedas con `rg` | Correcto; sin escrituras |
| `DB_NAME=bingo_ensayo_hibridos PGOPTIONS='-c default_transaction_read_only=on' .venv/bin/python manage.py check` | Correcto: `System check identified no issues (0 silenced)` |
| Verificación de encabezados obligatorios con `rg` | Presentes las secciones 1–9 y las subfases A–I |
| `git status --short` | Solo aparecen los documentos nuevos de Fase 0 y Fase 0.5 |

No se ejecutaron pruebas funcionales ni de integración: no hubo cambios de
código que validar y esta fase no autoriza escrituras en PostgreSQL. La suite
segura de 284 `SimpleTestCase` ya había quedado aprobada en la Fase 0 y no fue
necesario repetirla. No se encontraron errores nuevos durante esta fase.

## 12. Cambios realizados en la Fase 0.5

- Archivo creado: `docs/PLAN_CORRECCION_HIBRIDA_SIAB.md`.
- Código funcional modificado: ninguno.
- Modelos o migraciones modificados: ninguno.
- Scripts SQL creados o modificados: ninguno.
- Variables de entorno y `.env` modificados: ninguno.
- Base real `bingo` consultada o modificada: no.
- Cambios de PostgreSQL propuestos para ejecución inmediata: ninguno; la
  sección 6 enumera únicamente verificaciones y estructuras potenciales
  sujetas a autorización.
