# Contrato de Esquema PostgreSQL para Cartones Híbridos

Fecha de inspección: 2026-07-05

Fase: 0.6B — inspección física en base de ensayo

Estado: completada en modo de solo lectura

## 1. Resultado de seguridad de conexión

| Control | Resultado |
|---|---|
| Settings usados | `config.settings_ensayo_lectura` |
| Motor detectado | `django.db.backends.postgresql` |
| Base configurada y confirmada por PostgreSQL | `bingo_ensayo_hibridos` |
| Base real `bingo` | No fue usada, consultada ni modificada |
| Usuario configurado y usuario de sesión | `siab_auditor` |
| Perfil de privilegios observado | 28 tablas de `public` con `SELECT`; no se observaron otros privilegios de tabla ni privilegios delegables |
| Esquema actual | `public` |
| `transaction_read_only` | `on` |
| `default_transaction_read_only` | `on` |
| Check inicial | Correcto: `System check identified no issues (0 silenced)` |
| PostgreSQL alterado | No |

Antes de abrir el primer cursor se cargó el settings activo y se verificó, sin
mostrar secretos, que el nombre era exactamente `bingo_ensayo_hibridos`, el
motor era PostgreSQL, el usuario era `siab_auditor` y la opción
`default_transaction_read_only=on` estaba presente. El perfil no expuso una
contraseña en `DATABASES`.

El primer SELECT de la sesión confirmó nuevamente el nombre de la base, el
usuario y ambos indicadores de solo lectura. No se leyó ningún archivo `.env`,
archivo de contraseñas, token o cadena de conexión.

Se ejecutaron **22 SELECT de auditoría**:

- 1 preflight de base, usuario, esquema y modo de transacción;
- 1 descubrimiento de tablas;
- 7 consultas de columnas, identidad, constraints, índices y privilegios;
- 13 consultas de conteos agregados y distribuciones de estado.

Un primer intento de conexión desde el entorno restringido terminó antes de
abrir la sesión. La inspección continuó únicamente después de autorizar el
acceso al PostgreSQL de ensayo. No se ejecutaron DDL, DML, migraciones, scripts
SQL ni pruebas contra PostgreSQL.

## 2. Tablas físicas encontradas

PostgreSQL contiene 28 tablas en `public`. De ellas, **13 son relevantes** para
el alcance funcional solicitado.

| Esquema | Tabla física | Propósito físico inferido | Relación con SIAB / modelo Django |
|---|---|---|---|
| `public` | `bingo` | Evento principal, precio base y premio mayor | `apps.bingos.models.Bingo`; correspondencia identificada |
| `public` | `partidabingo` | Ronda de un Bingo, premio y ganador | `apps.bingos.models.Partidabingo`; correspondencia identificada |
| `public` | `carton` | Cartón vendido/maestro, jugador y precio pagado | `apps.bingos.models.Carton`; correspondencia identificada |
| `public` | `carton_partida_bingo` | Participación y resultado de un cartón en una ronda | `apps.bingos.models.CartonPartidaBingo`; correspondencia identificada |
| `public` | `jugador` | Cuenta de jugador, opcionalmente ligada a socio | `apps.jugadores.models.Jugador`; correspondencia identificada |
| `public` | `socio` | Socio de la cooperativa | `apps.socios.models.Socio`; correspondencia identificada |
| `public` | `pago` | Pago de una `deuda`, no de un cartón | Usa el mismo `db_table` que `apps.finanzas.models.Pago`, pero las columnas y FK físicas **no coinciden** con ese modelo |
| `public` | `prestamo` | Préstamo de un socio | `apps.finanzas.models.Prestamo`; correspondencia identificada |
| `public` | `ahorro` | Ahorro de un socio asociado a un Bingo | `apps.finanzas.models.Ahorro`; correspondencia identificada |
| `public` | `aportesemanal` | Aporte semanal, regalo y ronda opcional | `apps.finanzas.models.Aportesemanal`; correspondencia identificada |
| `public` | `metodopago` | Catálogo de métodos de pago | `apps.configuracion.models.Metodopago`; no está referenciado por la tabla física `pago` actual |
| `public` | `regalo` | Regalo de aportes semanales | `apps.configuracion.models.Regalo`; no es una tabla específica de premios de Bingo |
| `public` | `sesionjuego` | Sesión técnica de jugador y ronda | `apps.bingos.models.Sesionjuego`; correspondencia identificada |

No existe una tabla física específica llamada `premio` o `gasto`. Los premios
del Bingo están representados por columnas de `bingo` y `partidabingo`.

La divergencia de `pago` es concreta: PostgreSQL expone `id_pago`, `id_deuda`,
`fecha_pago`, `monto_pagado`, `metodo_pago` y `observacion`, con FK a `deuda`.
El modelo Django espera `idpago`, `idprestamo`, `idmetodopago`, `montopagado`,
`numeroreferencia`, fechas, comprobante y `estadopago`. Por tanto, esa tabla no
debe interpretarse como soporte de pagos de cartones.

## 3. Estructura de Bingo, rondas, cartones y participaciones

Todos los objetos de esta sección pertenecen al esquema `public`.

### 3.1 `bingo`

| Columna | Tipo | NULL | Default | Clave / regla |
|---|---|---:|---|---|
| `idbingo` | `integer` | No | Sin default | PK; entero asignado por la aplicación |
| `titulobingo` | `varchar(150)` | No | Sin default | — |
| `fechaprogramadabingo` | `timestamp without time zone` | No | Sin default | — |
| `tipobingo` | `varchar(20)` | No | Sin default | — |
| `lugarbingo` | `varchar(255)` | Sí | Sin default | — |
| `urlsesionbingo` | `varchar(255)` | Sí | Sin default | — |
| `preciocarton` | `numeric(10,2)` | No | Sin default | Sin CHECK monetario |
| `premiomayor` | `numeric(10,2)` | No | Sin default | Sin CHECK monetario |
| `descripcionpremiomayor` | `varchar(100)` | No | Sin default | — |
| `estadobingo` | `varchar(20)` | No | Sin default | CHECK: `Programado`, `En Curso`, `Finalizado`, `Cancelado` |
| `rutaimagenpremiomayor` | `varchar(300)` | Sí | Sin default | — |
| `urlvideopromocional` | `varchar(300)` | Sí | Sin default | — |
| `descripcionpremios` | `varchar(500)` | Sí | Sin default | — |

Constraints: PK `bingo_pkey` y CHECK `chk_bingo_estadobingo`.

Índices: `bingo_pkey (idbingo)`.

### 3.2 `partidabingo`

| Columna | Tipo | NULL | Default | Clave / regla |
|---|---|---:|---|---|
| `idpartidabingo` | `integer` | No | Sin default | PK; entero asignado por la aplicación |
| `idbingo` | `integer` | No | Sin default | FK a `bingo(idbingo)` |
| `idjugadorganador` | `integer` | Sí | Sin default | FK a `jugador(idjugador)` |
| `nombreronda` | `varchar(100)` | No | Sin default | — |
| `valorefectivo` | `numeric(10,2)` | No | Sin default | Premio efectivo; sin CHECK monetario |
| `premiomaterial` | `varchar(150)` | No | Sin default | Descripción de premio material |
| `estadopartida` | `varchar(20)` | No | Sin default | CHECK de siete estados admitidos |
| `bolascantadas` | `text` | No | Sin default | — |
| `ultimabola` | `integer` | No | Sin default | — |
| `haydesempate` | `boolean` | Sí | Sin default | — |
| `idbingadores` | `text` | Sí | Sin default | Dato de compatibilidad/desempate |
| `bolamayordesempate` | `integer` | Sí | Sin default | — |
| `horainicio` | `timestamp without time zone` | No | Sin default | — |
| `horafin` | `timestamp without time zone` | Sí | Sin default | — |

Constraints:

- PK `partidabingo_pkey`;
- FK `fk_partidabingo_bingo` y `fk_partidabingo_jugador`;
- UNIQUE `uq_partidabingo_idpartida_idbingo`
  `(idpartidabingo, idbingo)`, necesario como destino de la FK compuesta de
  participaciones;
- CHECK `chk_partidabingo_estadopartida` para `Programada`, `En espera`,
  `En curso`, `Pausada`, `Desempate`, `Finalizada` y `Cancelada`.

Índices:

- PK por `idpartidabingo`;
- `idx_partidabingo_idbingo (idbingo)`;
- índice UNIQUE por `(idpartidabingo, idbingo)`.

### 3.3 `carton`

| Columna | Tipo | NULL | Default | Clave / regla |
|---|---|---:|---|---|
| `idcarton` | `integer` | No | Sin default | PK; entero asignado por la aplicación |
| `idjugador` | `integer` | Sí | Sin default | FK a `jugador(idjugador)` |
| `idpartida` | `integer` | Sí | Sin default | FK opcional a `partidabingo(idpartidabingo)` |
| `codigocarton` | `varchar(30)` | No | Sin default | UNIQUE global |
| `matriznumeros` | `text` | No | Sin default | — |
| `indicevictoria` | `integer` | Sí | `0` | Resultado histórico/compatibilidad |
| `preciopagado` | `numeric(10,2)` | Sí | Sin default | CHECK `>= 0`; no confirma cobro |
| `fechacompra` | `timestamp without time zone` | Sí | Sin default | — |
| `estadocarton` | `varchar(20)` | No | Sin default | Sin CHECK de estados |
| `idbingo` | `integer` | No | Sin default | FK a `bingo(idbingo)` |

Constraints:

- PK `carton_pkey`;
- FK `fk_carton_bingo`, `fk_carton_jugador` y
  `fk_carton_partidabingo`;
- UNIQUE `uq_carton_codigocarton (codigocarton)`;
- UNIQUE `uq_carton_idcarton_idbingo (idcarton, idbingo)`, necesario como
  destino de la FK compuesta de participaciones;
- CHECK `chk_carton_preciopagado (preciopagado >= 0)`.

Índices:

- PK por `idcarton`;
- `idx_carton_idbingo (idbingo)`;
- `idx_carton_idjugador (idjugador)`;
- índices UNIQUE por `codigocarton` y `(idcarton, idbingo)`.

No existe índice específico por `idpartida`. Esto no afecta al maestro híbrido,
pero sí puede afectar consultas del flujo histórico si ese flujo se conserva.

### 3.4 `carton_partida_bingo`

| Columna | Tipo | NULL | Default | Clave / regla |
|---|---|---:|---|---|
| `idcartonpartidabingo` | `integer` | No | IDENTITY `BY DEFAULT` | PK |
| `idcarton` | `integer` | No | Sin default | Parte de FK compuesta a cartón |
| `idpartida` | `integer` | No | Sin default | Parte de FK compuesta a ronda |
| `idbingo` | `integer` | No | Sin default | Obliga a que cartón y ronda pertenezcan al mismo Bingo |
| `estado_participacion` | `varchar(20)` | No | Sin default | CHECK de estado |
| `indicevictoria` | `integer` | Sí | Sin default | CHECK: NULL o mayor que cero |
| `es_asignacion_original` | `boolean` | No | `false` | Coherente con `origen_asignacion` por CHECK |
| `origen_asignacion` | `varchar(24)` | No | Sin default | CHECK de origen |
| `motivoestado` | `varchar(255)` | Sí | Sin default | — |
| `fechacreacion` | `timestamp without time zone` | No | `CURRENT_TIMESTAMP` | — |
| `fechavalidacion` | `timestamp without time zone` | Sí | Sin default | — |

Constraints:

- PK `carton_partida_bingo_pkey`;
- UNIQUE `uq_cpb_carton_partida (idcarton, idpartida)`;
- FK compuesta `fk_cpb_carton_bingo (idcarton, idbingo) →
  carton(idcarton, idbingo)`;
- FK compuesta `fk_cpb_partida_bingo (idpartida, idbingo) →
  partidabingo(idpartidabingo, idbingo)`;
- CHECK `chk_cpb_estado`: `Pendiente`, `En juego`, `Cerrado`, `Ganador` o
  `Anulado`;
- CHECK `chk_cpb_indice`: índice NULL o positivo;
- CHECK `chk_cpb_origen`: `Historica original` o `Aplicacion`;
- CHECK `chk_cpb_origen_original`: coherencia entre el booleano y el origen.

Todas las constraints estaban validadas y ninguna era diferible.

Índices:

- PK por `idcartonpartidabingo`;
- UNIQUE por `(idcarton, idpartida)`; su prefijo también sirve para búsquedas
  por cartón;
- `idx_cpb_idpartida (idpartida)`;
- `idx_cpb_idbingo (idbingo)`;
- `idx_cpb_partida_estado (idpartida, estado_participacion)`.

### 3.5 Suficiencia de índices solicitados

| Consulta | Evidencia | Resultado |
|---|---|---|
| Cartones por Bingo | `idx_carton_idbingo` | Cubierta |
| Participaciones por cartón | UNIQUE con prefijo `idcarton` | Cubierta |
| Participaciones por ronda | `idx_cpb_idpartida` | Cubierta |
| Cartones por jugador | `idx_carton_idjugador` | Cubierta |
| Resultados de una ronda | `idx_cpb_partida_estado` | Cubierta para filtrar ronda/estado |
| Rondas por Bingo | `idx_partidabingo_idbingo` | Cubierta |

## 4. Contrato físico actual de cartones híbridos

| Pregunta | Categoría | Evidencia física |
|---|---|---|
| ¿Cartón pertenece directamente a Bingo? | **Confirmado.** | `carton.idbingo` es NOT NULL y FK a `bingo` |
| ¿Cartón puede referenciar una partida? | **Confirmado.** | Existe `carton.idpartida` con FK a `partidabingo` |
| ¿La referencia a partida admite NULL? | **Confirmado.** | `carton.idpartida` es nullable; los 3 cartones inspeccionados la tienen NULL |
| ¿El uso de `idpartida` parece histórico? | **Parcialmente confirmado.** | El ORM lo documenta como compatibilidad y no se usa en los 3 cartones de ensayo; la columna sigue físicamente activa |
| ¿Existe participación por ronda? | **Confirmado.** | Existe `carton_partida_bingo` con FK coherentes a cartón, ronda y Bingo |
| ¿Puede un cartón tener varias participaciones? | **Confirmado.** | La unicidad es por cartón+ronda; los 3 cartones tienen participación en 3 rondas |
| ¿Se impiden participaciones duplicadas? | **Confirmado.** | UNIQUE físico `(idcarton,idpartida)` y 0 duplicados observados |
| ¿Puede un mismo cartón ganar varias rondas? | **Confirmado.** | El estado e índice viven en cada participación; no existe unicidad global por cartón. No había ganadores en los datos de ensayo |
| ¿Puede registrarse el valor una sola vez por Bingo? | **Parcialmente confirmado.** | `preciopagado` vive en `carton` y no en participaciones, pero admite NULL y no existe confirmación de pago |
| ¿La estructura evita por sí sola duplicar recaudación en reportes? | **Requiere corrección.** | Un JOIN a participaciones repite el precio del maestro una vez por ronda; 3 cartones presentan ese riesgo |

El esquema híbrido central está **confirmado físicamente**. Las FK compuestas
son especialmente importantes: impiden registrar una participación con un
cartón y una ronda de Bingos diferentes.

La estructura de participación registra estado, índice de victoria, origen,
motivo y fechas. No registra una cantidad de aciertos, valor de participación,
premio monetario propio, pago ni gasto. “Ganador” se representa mediante
`estado_participacion='Ganador'`, no mediante un booleano separado.

## 5. Diagnóstico de integridad de datos

Solo se obtuvieron conteos agregados. No se mostraron socios, jugadores,
cuentas, pagos, códigos de cartón, matrices ni otros datos personales.

| Diagnóstico | Resultado |
|---|---:|
| Bingos | 1 |
| Rondas/partidas | 3 |
| Cartones | 3 |
| Participaciones | 9 |
| Cartones con Bingo nulo | 0 |
| Cartones sin jugador | 0 |
| Cartones maestros (`idpartida IS NULL`) | 3 |
| Cartones históricos (`idpartida IS NOT NULL`) | 0 |
| Participaciones sin cartón válido | 0 |
| Participaciones sin ronda válida | 0 |
| Participaciones sin Bingo válido | 0 |
| Pares cartón+ronda duplicados | 0 |
| Filas duplicadas excedentes | 0 |
| Cartones maestros sin participaciones | 0 |
| Rondas incompletas | 0 |
| Participaciones faltantes en rondas | 0 |
| Cartones ligados a ronda sin Bingo | 0 |
| Cartones cuya ronda pertenece a otro Bingo | 0 |
| Cartones con varias participaciones | 3 |
| Máximo de rondas por cartón | 3 |
| Cartones con riesgo de doble conteo de precio al hacer JOIN | 3 |
| Apariciones adicionales del precio en ese JOIN | 6 |
| Participaciones ganadoras | 0 |
| Cartones ganadores en más de una ronda | 0 |
| Ganadores duplicados para el mismo cartón+ronda | 0 |

Participaciones por ronda:

| ID de ronda | Participaciones | Maestros válidos esperados | Faltantes |
|---:|---:|---:|---:|
| 1 | 3 | 3 | 0 |
| 2 | 3 | 3 | 0 |
| 3 | 3 | 3 | 0 |

Para este diagnóstico se definió “maestro válido” de forma explícita como un
cartón con `idpartida IS NULL`, jugador asignado y
`estadocarton='Vendido'`. Los 3 cartones cumplen esa condición. Esta definición
debe convertirse en política formal antes de automatizar un backfill.

El riesgo de recaudación no representa 6 ventas duplicadas en los datos. Es un
riesgo de consulta: unir los 3 maestros con sus 9 participaciones produce 6
apariciones de precio adicionales respecto de contar una vez cada maestro.

### Soporte físico para reportes y liquidación

| Concepto | Soporte físico | Evaluación |
|---|---|---|
| Valor de lista del cartón | `bingo.preciocarton` | Disponible |
| Valor pagado por el cartón | `carton.preciopagado` | Disponible, pero nullable y sin confirmación de pago |
| Valor de participación | No existe | No soportado como concepto separado |
| Premio por ronda | `partidabingo.valorefectivo`, `premiomaterial` | Disponible como premio programado |
| Premio mayor | `bingo.premiomayor`, descripción | Disponible como premio programado |
| Estado de pago de cartón | No existe | No soportado |
| Método/transacción de venta | No existe relación desde cartón | No soportado |
| Ganador | `partidabingo.idjugadorganador` y estado `Ganador` por participación | Disponible |
| Gasto | No existe tabla/columna relevante | No soportado |

Consecuencias:

- los cartones pueden contarse una sola vez consultando `carton` por Bingo;
- la suma de `carton.preciopagado` por Bingo produce recaudación **registrada**,
  pero no prueba recaudación real cobrada;
- los premios programados por ronda pueden calcularse, pero no consta si
  fueron efectivamente pagados;
- la utilidad bruta solo puede estimarse bajo una política externa que defina
  qué precios y premios cuentan;
- la utilidad neta no puede calcularse correctamente porque no existen gastos
  de Bingo ni estados de cobro/pago suficientes.

La tabla `pago` física pertenece a deudas y no corrige estas carencias.

## 6. Comparación contra la regla de negocio de SIAB

| Regla | Estado frente a la evidencia |
|---:|---|
| 1. Un cartón maestro pertenece a un Bingo | **Confirmado.** FK NOT NULL `carton.idbingo`; los 3 maestros son coherentes |
| 2. Un cartón participa en todas las rondas del Bingo | **Parcialmente confirmado.** Los datos actuales cumplen 3 de 3, pero el flujo `partida_nueva` no crea participaciones para maestros existentes |
| 3. Un mismo cartón puede ganar más de una ronda | **Confirmado estructuralmente.** El resultado es por participación; todavía no hay ganadores para demostrar un caso real |
| 4. Un cartón no puede tener dos participaciones en la misma ronda | **Confirmado.** UNIQUE físico y 0 duplicados |
| 5. El valor pagado se registra una sola vez por cartón y Bingo | **Parcialmente confirmado.** La columna está solo en el maestro, pero es nullable y no tiene estado de cobro |
| 6. La liquidación no puede sumar el precio desde participaciones por ronda | **Pendiente de código.** PostgreSQL no puede impedir una consulta que multiplique el precio; existen 3 cartones expuestos a ese error |
| 7. Una nueva ronda genera participaciones para cartones válidos existentes | **Pendiente de código.** `partida_nueva` guarda la ronda sin sincronización; el servicio inverso sí crea participaciones al vender un maestro |

El reporte global de Bingo ya dispone de una suma final por maestros, pero sus
filas de recaudación por ronda vuelven a incluir el precio del mismo cartón en
cada participación. Es válido como vista de cobertura por ronda, pero no debe
sumarse para liquidar el Bingo.

## 7. Brechas detectadas

| Brecha | Clasificación | Evidencia / efecto |
|---|---|---|
| PK, FK compuestas y UNIQUE del núcleo híbrido | **Lista.** | Existen y están validadas |
| Índices requeridos por Bingo, cartón, ronda y resultado | **Lista.** | Todos los accesos solicitados están cubiertos |
| Datos híbridos actuales | **Lista.** | Cobertura completa, sin huérfanos ni duplicados |
| Sincronizar maestros al crear una ronda | **Pendiente de código.** | `partida_nueva` no genera participaciones |
| Flujo heredado de venta por partida | **Pendiente de código.** | Sigue expuesto y no representa la regla “un cartón para todo el Bingo” |
| Recaudación por ronda frente a recaudación del Bingo | **Pendiente de código.** | El precio se repite por participación al agrupar por ronda |
| Confirmación de pago de una venta | **Requiere decisión del usuario.** | `preciopagado` no equivale a pago confirmado |
| Política formal de estados de cartón | **Requiere decisión del usuario.** | `estadocarton` no tiene CHECK; “Vendido” fue la regla operativa usada |
| CHECK monetarios adicionales | **Pendiente de SQL PostgreSQL.** | Precios/premios carecen de varias reglas; solo deben añadirse tras decidir la política y auditar históricos |
| Índice de `carton.idpartida` | **Requiere decisión del usuario.** | Solo sería necesario si se mantienen consultas históricas por ronda |
| Backfill de participaciones en ensayo | **Lista.** | No hace falta para los 3 maestros actuales |
| Backfill fuera de ensayo | **Pendiente de datos históricos.** | Esta fase no inspeccionó `bingo` y no permite extrapolar resultados |
| Modelo Django `Pago` frente a tabla física `pago` | **Requiere decisión del usuario.** | El contrato ORM y PostgreSQL no coinciden |
| Ventas, métodos y estado de cobro de cartones | **Requiere decisión del usuario.** | No existe entidad física de venta/pago de cartón |
| Gastos y utilidad neta | **Requiere decisión del usuario.** | No existe soporte físico de gastos de Bingo |

## 8. Recomendaciones técnicas

### UNIQUE y claves foráneas

No se recomienda crear una nueva UNIQUE o FK para el núcleo híbrido: ya están
presentes las reglas correctas.

- conservar `UNIQUE(idcarton,idpartida)`;
- conservar las FK compuestas cartón+Bingo y ronda+Bingo;
- conservar las UNIQUE auxiliares `(idcarton,idbingo)` y
  `(idpartidabingo,idbingo)` que soportan esas FK;
- no agregar una FK redundante de `carton_partida_bingo.idbingo` mientras las
  dos FK compuestas permanezcan activas y validadas.

Después de decidir la política y revisar datos históricos, evaluar:

- CHECK de estados permitidos para `carton.estadocarton`;
- endurecer `carton.preciopagado` de `>= 0` a `> 0` para ventas, sin romper
  cartones históricos que legítimamente puedan ser gratuitos;
- CHECK no negativo para `bingo.preciocarton`, `bingo.premiomayor` y
  `partidabingo.valorefectivo`;
- reglas de coherencia temporal y de ganador en el servidor, cuando no puedan
  expresarse como CHECK de una sola fila.

### Índices

Los índices requeridos por esta fase son suficientes. Solo considerar
`carton(idpartida)` si el usuario decide conservar rutas/reportes históricos
que filtran directamente por esa columna. No se recomienda duplicar el índice
por cartón en participaciones, porque ya lo cubre el prefijo de la UNIQUE.

### Validaciones de servidor y servicios atómicos

- crear una única operación atómica para registrar una ronda y generar una
  participación por cada maestro válido del mismo Bingo;
- bloquear el Bingo y los maestros relevantes antes de crear la ronda y sus
  participaciones, con orden estable;
- mantener atómica la venta del maestro más sus participaciones actuales;
- tratar `IntegrityError` de la UNIQUE como conflicto, no como éxito silencioso;
- validar en servidor el estado válido del cartón, jugador, precio, Bingo y
  ronda; no confiar en valores enviados por formularios o JavaScript;
- retirar o redirigir el POST heredado por partida antes de declarar el flujo
  híbrido como único;
- calcular recaudación desde maestros deduplicados por `idcarton`, nunca desde
  filas de participación;
- no reutilizar `pago`, porque físicamente pertenece a `deuda`.

### Posibles scripts SQL futuros

No se creó ni ejecutó ningún script. Solo después de decisiones expresas
podrían prepararse, por separado:

1. auditoría/backfill de participaciones históricas;
2. CHECK de estado y montos;
3. índice histórico `carton(idpartida)`, si sigue siendo necesario;
4. reconciliación del contrato de `pago` o una entidad nueva de venta/cobro de
   cartones.

Cada script futuro debe tener preflight de base/esquema, conteos previos,
transacción, verificación posterior y reversión probada primero en ensayo.

### Estrategia de reversión

- el cambio de código de creación de ronda debe poder revertirse sin borrar
  participaciones que ya contengan resultados;
- una reversión funcional debe desactivar la nueva ruta y conservar los datos;
- constraints nuevas deben aplicarse solo tras limpiar datos y, cuando sea
  viable, validarse de forma separada;
- ningún rollback rutinario debe eliminar maestros, participaciones o
  resultados;
- cualquier backfill necesita tabla de control o criterio determinista para
  distinguir filas creadas por el proceso.

### Orden recomendado de corrección

1. fijar con pruebas el contrato de creación de una ronda con maestros previos;
2. implementar el servicio atómico ronda+participaciones;
3. conectar `partida_nueva` exclusivamente a ese servicio;
4. retirar o redirigir la venta heredada por partida;
5. blindar reportes/liquidación para sumar una vez por maestro;
6. decidir estados, precios y confirmación de pagos;
7. resolver la divergencia de `pago`;
8. evaluar SQL adicional y backfill solo con autorización separada.

## 9. Primer cambio de código recomendado

El siguiente cambio real debe ser agregar pruebas de contrato y un servicio
atómico de **creación de ronda con sincronización de participaciones**.

La evidencia es directa:

- el esquema físico ya soporta y protege las participaciones correctas;
- los 3 maestros actuales tienen cobertura completa en las 3 rondas;
- `crear_carton_maestro_para_bingo()` ya cubre el caso “nuevo maestro frente a
  rondas existentes”;
- `partida_nueva` no cubre el caso inverso “nueva ronda frente a maestros
  existentes”.

El servicio debe crear la ronda y, dentro de la misma transacción, insertar una
participación para cada maestro válido del Bingo. Si cualquier inserción falla,
deben revertirse tanto la ronda como sus participaciones. La definición de
“válido” debe fijarse primero en pruebas; la usada por esta auditoría fue
`idpartida IS NULL`, jugador presente y estado `Vendido`.

No se recomienda empezar por SQL: las constraints centrales ya existen y el
faltante inmediato está en el flujo de aplicación.

## 10. Decisiones pendientes del usuario

### Aplicar SQL

- autorizar o no CHECK nuevos de estado y montos;
- decidir si se mantiene `carton.idpartida` y, en consecuencia, si necesita
  índice;
- decidir cómo reconciliar la tabla `pago` con el modelo Django;
- autorizar cada script y cada ejecución por separado. Esta fase no autoriza
  cambios en `bingo`.

### Backfill de participaciones

- en `bingo_ensayo_hibridos` no hace falta backfill para los 3 maestros
  actuales;
- decidir si un futuro diagnóstico histórico debe incluir anulados,
  disponibles, gratuitos o cartones sin jugador;
- decidir si el backfill abarca todas las rondas o solo rondas no finalizadas.

### Comportamiento de cartones históricos

- mantenerlos ligados a una sola ronda, convertirlos en maestros o dejarlos
  solo para consulta;
- definir si `indicevictoria` histórico se conserva indefinidamente;
- prohibir ampliar cartones históricos a otras rondas sin una decisión expresa.

### Retirar o redirigir rutas antiguas

- decidir si la venta por partida se elimina, se deja solo en lectura o se
  redirige a la venta por Bingo;
- decidir la compatibilidad de formularios y enlaces históricos.

### Restricciones nuevas

- catálogo permitido de `estadocarton`;
- tratamiento de precio cero, precio NULL y cartones gratuitos;
- reglas para montos de premio y coherencia de ganador.

### Política de estados

- qué estados hacen a un maestro elegible para una ronda nueva;
- cuándo una participación pasa a `En juego`, `Cerrado`, `Ganador` o `Anulado`;
- qué ocurre al cancelar una ronda o un Bingo.

### Política de precios

- si `preciopagado` debe igualar `bingo.preciocarton` o admite descuento;
- qué fecha fija el precio y cómo se manejan devoluciones;
- si la recaudación incluye cartones pendientes o solo cobros confirmados.

### Módulos de ventas y pagos

- crear o no una entidad específica de venta/cobro de cartón;
- relación con `metodopago`, comprobante y confirmación administrativa;
- tratamiento contable de premios pagados y gastos;
- definición de utilidad bruta y neta antes de implementar liquidación.

Al cierre de la fase no se modificaron modelos, migraciones, servicios, vistas,
formularios, rutas, plantillas, settings, scripts SQL ni PostgreSQL. El único
archivo actualizado fue este contrato.
