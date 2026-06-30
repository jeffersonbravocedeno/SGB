# Etapa 9.5A: preparación segura de cartones híbridos

Fecha del preflight real: 2026-06-30.

Estado: **PREFLIGHT COMPLETADO / MIGRACIÓN NO AUTORIZADA**.

Esta etapa confirma el esquema y los datos reales de SIAB / CoopBingo y deja
artefactos de respaldo, migración, validación y rollback para revisión. No
aplica cambios estructurales ni cambios de datos en PostgreSQL.

## 1. Alcance y garantías de ejecución

La conexión y el preflight se ejecutaron con:

```bash
PGOPTIONS='-c default_transaction_read_only=on'
```

Django confirmó mediante una consulta `SELECT`:

| Control | Resultado real |
|---|---|
| Base | `bingo` |
| Usuario | `jjbc` |
| Servidor | `127.0.0.1:5432` |
| Esquema | `public` |
| PostgreSQL | `16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)` |
| `default_transaction_read_only` | `on` |
| `transaction_read_only` | `on` |
| Tabla `carton` | existente |

Después se ejecutó completo
[`DATABASE/00_PREFLIGHT_CARTONES_HIBRIDOS.sql`](../DATABASE/00_PREFLIGHT_CARTONES_HIBRIDOS.sql)
con `psql -X`, `ON_ERROR_STOP=1` y la misma opción de solo lectura. Terminó con
código cero. Sus 37 sentencias son consultas `SELECT` o CTE de lectura.

La tabla objetivo `carton_partida_bingo` **no existe** en el corte analizado.

## 2. Estructura física confirmada

### 2.1 Tablas y columnas relevantes

| Tabla | Estructura confirmada relevante |
|---|---|
| `carton` | PK `idcarton integer`; `idjugador integer NULL`; `idpartida integer NULL`; `codigocarton varchar(30) NOT NULL`; `matriznumeros text NOT NULL`; `indicevictoria integer NULL DEFAULT 0`; `preciopagado numeric(10,2) NULL`; `fechacompra timestamp NULL`; `estadocarton varchar(20) NOT NULL` |
| `partidabingo` | PK `idpartidabingo integer`; `idbingo integer NOT NULL`; `idjugadorganador integer NULL`; nombre, premios, estado, bolas, desempate y fechas de ronda |
| `bingo` | PK `idbingo integer`; título, fecha, tipo, ubicación/URL, precio, premios, estado y recursos promocionales |
| `jugador` | PK `idjugador integer`; socio opcional, identidad visible, fecha, saldo y estado de cuenta |
| `sesionjuego` | PK `idsesion integer`; plataforma, jugador y partida obligatorios, fechas, conexión, estado y token |

Ninguna de las cinco PK es `IDENTITY`, tiene default ni posee secuencia
asociada. La aplicación y la propuesta futura deben tratar explícitamente esta
diferencia si la PK nueva usa `IDENTITY`.

### 2.2 Constraints reales

Se confirmaron 22 constraints, todas validadas:

- PK: `bingo_pkey`, `carton_pkey`, `jugador_pkey`, `partidabingo_pkey` y
  `sesionjuego_pkey`;
- FK de `carton`: `fk_carton_jugador` y `fk_carton_partidabingo`;
- FK de `partidabingo`: `fk_partidabingo_bingo` y
  `fk_partidabingo_jugador`;
- FK de `sesionjuego`: jugador, partida y plataforma;
- UNIQUE: `uq_carton_codigocarton`, alias/correo del jugador y token de sesión;
- CHECK de `carton`: solo `chk_carton_preciopagado`, que exige precio mayor o
  igual a cero cuando no es nulo;
- CHECK de estado en `bingo`, `partidabingo`, `jugador` y `sesionjuego`.

`carton.estadocarton` no tiene CHECK físico. Los únicos valores presentes son
`Disponible` y `Vendido`.

### 2.3 Índices reales

Hay 9 índices físicos, todos válidos y listos: cinco de PK y cuatro UNIQUE.
No existen índices independientes para las FK `carton.idpartida`,
`carton.idjugador`, `partidabingo.idbingo` o las FK de `sesionjuego`.

## 3. Inventario real

| Entidad | Cantidad |
|---|---:|
| Bingo | 5 |
| Partida | 6 |
| Cartón | 12 |
| Jugador | 4 |
| Sesión de juego | 1 |

### 3.1 Calidad de cartones

| Control | Resultado |
|---|---:|
| Sin partida | 0 |
| Sin Bingo derivable | 0 |
| Sin jugador o con jugador huérfano | 0 |
| Sin matriz | 0 |
| Sin precio | 1 |
| Precio negativo | 0 |
| Vendido sin precio positivo | 0 |
| Código duplicado exacto | 0 |
| Código duplicado normalizado | 0 |
| Estado inesperado | 0 |
| Índice de victoria negativo | 0 |
| Posible maestro duplicado por Bingo/jugador/matriz | 0 |

El único cartón sin precio es `idcarton=3`, código `23`, estado `Disponible`,
asociado a la partida 3 y al Bingo 4 (`prueba2`). No incumple la regla vigente
de cartón vendido, pero requiere decidirse junto con los datos de prueba.

Hay 9 cartones `Vendido` y 3 `Disponible`. Nueve vendidos suman `41.00`; la
suma de todos los precios no nulos es `51.00`.

El cartón 4 (`P4-C-31827E8E8F`) tiene `preciopagado=1.00` frente a
`bingo.preciocarton=5.00`. Puede representar descuento o dato de prueba, pero
no debe normalizarse automáticamente.

`indicevictoria` vale `0` en 11 cartones y es nulo en uno. Los cartones 1 y 2
están `Disponible` pero tienen índice `0`, debido al default físico. Esto
confirma que `0` no puede interpretarse automáticamente como victoria ni como
resultado calculado.

### 3.2 Relación cartón → partida → Bingo

Las 12 relaciones son completas y derivables:

- Bingo 1, `Bingo de Verano`: 4 partidas y 11 cartones actuales;
- Bingo 4, `prueba2`: 1 partida y 1 cartón;
- los Bingos 2, 3 y 5 no tienen cartones.

No hay partidas sin Bingo, sesiones con jugador/partida huérfanos ni ganadores
que carezcan de al menos un cartón del mismo jugador en su partida original.

### 3.3 Proyección de `carton_partida_bingo`

La regla proyectada genera una pareja por cada cartón y cada partida de su
Bingo:

| Bingo | Cartones | Partidas | Asignaciones | Originales | Adicionales |
|---|---:|---:|---:|---:|---:|
| 1 — Bingo de Verano | 11 | 4 | 44 | 11 | 33 |
| 2 — bingo 1 | 0 | 1 | 0 | 0 | 0 |
| 3 — prueba | 0 | 0 | 0 | 0 | 0 |
| 4 — prueba2 | 1 | 1 | 1 | 1 | 0 |
| 5 — prueba cartones | 0 | 0 | 0 | 0 | 0 |
| **Total** | **12** | — | **45** | **12** | **33** |

La simulación no produce parejas `(idcarton, idpartida)` duplicadas.

Las 33 asignaciones adicionales no son todas participación histórica
demostrada. Varios cartones se compraron para rondas posteriores a otras ya
finalizadas. La propuesta conserva este hecho mediante origen de asignación y
el estado `No participo`; ambos requieren aprobación funcional.

## 4. Partidas, Bingos y datos de prueba

Estados reales de las 6 partidas:

| Estado | Cantidad |
|---|---:|
| `Finalizada` | 4 |
| `En curso` | 1 |
| `Pausada` | 1 |

La heurística de prueba detectó:

- partida 6, `Prueba Desempate`, finalizada dentro del Bingo 1;
- Bingo 3, `prueba`, sin partidas;
- Bingo 4, `prueba2`, con la partida 3 `En curso` y el cartón 3;
- Bingo 5, `prueba cartones`, sin partidas.

También se detectaron estas inconsistencias históricas o semánticas:

1. La partida 2 está `Finalizada`, pero `horafin=2026-06-27 23:07:10.666736`
   es anterior a `horainicio=2026-06-28 04:05:00`.
2. Los cinco Bingos figuran `Programado` aunque los Bingos 1, 2 y 4 contienen
   partidas finalizadas, en curso o pausadas.
3. Los cartones 1 y 2 siguen `Disponible` aunque su partida original está
   finalizada; el cartón 1 corresponde al jugador ganador de esa ronda.
4. La partida 5 está finalizada sin ganador; esto puede ser válido, pero no
   permite inferir resultados por cartón.
5. `idjugadorganador` identifica al jugador, no necesariamente cuál de sus
   cartones ganó. La migración no debe fabricar estados `Ganador`.

## 5. Bloqueos para ejecutar una migración

La integridad referencial base está limpia, pero la migración **no es segura
para ejecutar todavía**. Deben resolverse o aprobarse expresamente:

1. **Datos de prueba:** decidir si los Bingos 3, 4 y 5 y la partida 6 entran en
   el histórico definitivo. El Bingo 4 tiene un cartón real en el alcance.
2. **Mapa de estados:** aprobar estados de maestro y de participación, incluido
   `No participo` para rondas anteriores a la compra y el tratamiento de rondas
   finalizadas sin resultado demostrable.
3. **Índice histórico:** confirmar que los valores `0` son default y no una
   victoria. Solo la asignación original puede recibir el valor existente.
4. **Precio distinto:** aceptar el `1.00` del cartón 4 como histórico legítimo
   o corregirlo en una etapa autorizada independiente.
5. **Cronología:** resolver la hora invertida de la partida 2 antes de usar
   fechas para clasificar participaciones históricas.
6. **Ciclo de vida:** reconciliar Bingos `Programado` con partidas avanzadas y
   cartones `Disponible` asociados a partidas finalizadas.
7. **Ganadores:** definir un procedimiento de identificación por cartón; no es
   seguro derivarlo solo desde `idjugadorganador`.
8. **PK nueva:** aprobar `IDENTITY` para `idcartonpartidabingo` y adaptar la
   futura capa Django, o definir una estrategia consistente con las PK manuales
   actuales. `MAX(id)+1` no es seguro bajo concurrencia.
9. **Compatibilidad de aplicación:** el código actual sigue leyendo y
   escribiendo `carton.idpartida`; la fase expansiva debe conservarlo hasta que
   una etapa posterior adapte y pruebe todo el flujo.
10. **Respaldo:** generar y restaurar con éxito un respaldo completo del corte
    definitivo antes de cualquier DDL o DML.

## 6. Diseño físico propuesto

La propuesta mantiene el cartón como maestro de un Bingo y usa:

```text
Bingo 1 --- N Carton
Bingo 1 --- N Partidabingo
Carton 1 --- N carton_partida_bingo N --- 1 Partidabingo
```

`carton_partida_bingo` incluye también `idbingo`. Dos FK compuestas contra
`carton(idcarton, idbingo)` y
`partidabingo(idpartidabingo, idbingo)` impiden físicamente relacionar un
cartón con una partida de otro Bingo. No depende de un trigger.

La fase expansiva propuesta:

- agrega y puebla `carton.idbingo`;
- conserva `carton.idpartida` e `indicevictoria`;
- agrega los índices de FK que hoy faltan para las rutas principales;
- crea 12 asignaciones originales y 33 inferidas con trazabilidad separada;
- no marca ganadores automáticamente;
- mantiene `preciopagado` solo en el cartón maestro para no duplicar
  recaudación.

## 7. Archivos preparados

- [`00_PREFLIGHT_CARTONES_HIBRIDOS.sql`](../DATABASE/00_PREFLIGHT_CARTONES_HIBRIDOS.sql):
  preflight real de solo lectura; no requirió correcciones.
- [`01_RESPALDO_CARTONES_HIBRIDOS.md`](../DATABASE/01_RESPALDO_CARTONES_HIBRIDOS.md):
  procedimiento de dump, checksum y restauración aislada; no ejecutado.
- [`02_MIGRACION_CARTONES_HIBRIDOS_PROPUESTA.sql`](../DATABASE/02_MIGRACION_CARTONES_HIBRIDOS_PROPUESTA.sql):
  **PROPUESTA / NO EJECUTAR**, con bloqueo intencional al inicio.
- [`03_VALIDACION_CARTONES_HIBRIDOS.sql`](../DATABASE/03_VALIDACION_CARTONES_HIBRIDOS.sql):
  consultas de solo lectura para una migración futura; no se ejecutó porque los
  objetos nuevos todavía no existen.
- [`04_ROLLBACK_CARTONES_HIBRIDOS_PROPUESTA.sql`](../DATABASE/04_ROLLBACK_CARTONES_HIBRIDOS_PROPUESTA.sql):
  **PROPUESTA / NO EJECUTAR**, aplicable solo antes de escrituras híbridas y con
  bloqueo intencional al inicio.

## 8. Orden obligatorio para una etapa futura

1. Resolver los diez bloqueos y aprobar el mapa de estados y la PK.
2. Congelar escrituras y repetir el preflight de solo lectura.
3. Generar el respaldo completo y validar su checksum.
4. Restaurarlo en una base aislada.
5. Copiar y habilitar deliberadamente la propuesta de migración solo en esa
   copia.
6. Ejecutar `03_VALIDACION_CARTONES_HIBRIDOS.sql` en modo solo lectura y
   reconciliar los controles 12/45/41.00/51.00 con el nuevo corte.
7. Ensayar el rollback antes de cualquier escritura híbrida y repetir el
   preflight original.
8. Preparar la etapa de compatibilidad Django y sus pruebas sin retirar todavía
   los campos históricos.
9. Autorizar una ventana productiva independiente; esta documentación no es
   una autorización de ejecución.

## 9. Confirmación de no modificación

Durante esta continuación de la Etapa 9.5A:

- no se ejecutó `ALTER`, `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `DROP` ni
  `TRUNCATE` en PostgreSQL;
- no se ejecutaron migraciones ni scripts de migración/rollback;
- no se modificaron código Django, modelos, templates, URLs, tests, `.env` ni
  requirements;
- no se hizo commit ni push;
- los únicos cambios del repositorio son los cinco artefactos autorizados de
  `DATABASE/` y este documento.

Verificaciones finales:

| Comando | Resultado |
|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `git diff --check` | Sin errores ni salida |
| `git status --short` | Solo los seis archivos autorizados, todos sin seguimiento |
