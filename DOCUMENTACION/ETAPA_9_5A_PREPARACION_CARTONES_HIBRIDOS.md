# Etapas 9.5A y 9.5B: preparación de cartones híbridos

Preflight real: 2026-06-30.

Última revisión: **Etapa 9.5B — estrategia histórica corregida**.

Estado: **DOCUMENTACIÓN Y PROPUESTAS / MIGRACIÓN NO AUTORIZADA**.

La Etapa 9.5A confirmó el esquema y los datos reales. La Etapa 9.5B corrige la
propuesta para preservar únicamente evidencia histórica existente. Ninguna de
las dos etapas aplica cambios estructurales o de datos en PostgreSQL.

## 1. Verificaciones de la Etapa 9.5B

Antes de editar se ejecutaron:

```text
git status --short
git log --oneline -5
source .venv/bin/activate
python manage.py check
```

Resultados iniciales:

- el árbol de trabajo estaba limpio;
- commit actual: `4e15a63 docs: preparar migracion de cartones hibridos`;
- `python manage.py check`: `System check identified no issues (0 silenced)`.

No se volvió a ejecutar el preflight ni ningún script SQL en la Etapa 9.5B.
Esta corrección utiliza exclusivamente los resultados reales ya confirmados.

## 2. Base física confirmada por el preflight

| Control | Resultado real |
|---|---|
| PostgreSQL | 16.14 |
| Base / esquema | `bingo` / `public` |
| Bingos | 5 |
| Partidas | 6 |
| Cartones | 12 |
| Jugadores | 4 |
| Sesiones | 1 |
| Cartones con Bingo derivable | 12 |
| `carton_partida_bingo` | No existe |

Las cinco PK revisadas son `integer` sin secuencia, default ni `IDENTITY`. Se
confirmaron 22 constraints validadas y 9 índices físicos válidos. No existen
índices independientes para varias FK, entre ellas `carton.idjugador`,
`carton.idpartida` y `partidabingo.idbingo`.

No hay cartones sin partida, jugador o matriz; tampoco códigos duplicados,
precios negativos, estados inesperados, relaciones huérfanas ni partidas sin
Bingo.

## 3. Advertencias que se preservan y no bloquean

Estas situaciones son datos históricos, no precondiciones de rechazo:

1. El cartón 3, código `23`, está `Disponible` y no tiene precio. Se conserva
   sin cambios.
2. El cartón 4 pagó `1.00` frente al precio de lista `5.00`. Puede ser descuento
   o valor histórico; no se normaliza.
3. `indicevictoria` vale `0` en 11 cartones y `NULL` en uno. El cero es el
   default histórico y no demuestra victoria ni resultado.
4. La partida 2 tiene hora final anterior a la inicial. Se documenta, pero no
   se usan sus fechas para deducir participación.
5. Existen Bingos y partidas cuyos nombres contienen `prueba`. Se conservan y
   entran en la migración cuando tengan un cartón histórico asociado.
6. Los cinco Bingos figuran `Programado` aunque existen partidas finalizadas,
   en curso o pausadas. La expansión no corrige ese ciclo de vida.
7. `idjugadorganador` identifica a un jugador, no de forma inequívoca al cartón
   ganador. La migración no marca ganadores.

Hay 9 cartones `Vendido` y 3 `Disponible`. La recaudación vendida confirmada es
`41.00` y la suma histórica de todos los precios no nulos es `51.00`. Ambas
cifras deben permanecer idénticas.

## 4. Decisión funcional: historia y futuro son reglas distintas

### 4.1 Migración histórica

Los 12 cartones existentes nacieron bajo la regla antigua:

```text
Cartón antiguo ──────> partida original solamente
       └─────────────> Bingo derivado de esa partida
```

La migración histórica, por tanto:

- agrega `carton.idbingo` derivándolo de la partida original;
- conserva temporalmente `carton.idpartida` y `carton.indicevictoria`;
- crea exactamente una fila de `carton_partida_bingo` por cartón;
- hace coincidir esa fila con `carton.idpartida`;
- no crea filas para otras partidas históricas del mismo Bingo;
- no infiere participación, ausencia, ganador ni resultado desde fechas o
  `idjugadorganador`;
- no modifica precios, códigos, matrices, propietarios ni estados de los 12
  cartones.

### 4.2 Modelo híbrido futuro

Después de adaptar Django, un cartón nuevo sí nace para un Bingo completo:

```text
Cartón maestro nuevo ─────> Bingo
          │
          └───────────────> todas las partidas del Bingo
                             mediante carton_partida_bingo
```

Si el Bingo tiene `N` partidas, la aplicación deberá crear `N` filas para ese
cartón nuevo dentro de la misma operación transaccional. Esta regla corresponde
a escrituras futuras de la aplicación, no al script histórico.

La proyección anterior de 45 filas representa únicamente la capacidad teórica
de aplicar la regla futura sobre la distribución actual: 12 relaciones
originales más 33 relaciones adicionales. **La migración histórica no crea
esas 33 filas y su resultado esperado no es 45.**

## 5. Conteos esperados

### Después de la migración histórica propuesta

| Control | Esperado |
|---|---:|
| Cartones maestros | 12 |
| Asignaciones reales | 12 |
| Asignaciones históricas originales | 12 |
| Asignaciones históricas inferidas | 0 |
| Filas creadas por la aplicación | 0 |

Por Bingo, el número de asignaciones históricas debe ser igual al número de
cartones históricos, no al producto cartones × partidas.

### Para cada cartón futuro

| Partidas existentes en su Bingo | Filas nuevas esperadas |
|---:|---:|
| `N` | `N` |

La aplicación adaptada será responsable de mantener atomicidad, unicidad y
pertenencia al mismo Bingo al crear esas filas.

## 6. Estados e índice históricos

La asignación original usa exclusivamente este mapa:

| Estado de la partida | Estado de participación |
|---|---|
| `Finalizada` | `Cerrado` |
| `En curso` o `Desempate` | `En juego` |
| `Cancelada` | `Anulado` |
| Cualquier otro | `Pendiente` |

`Ganador` queda disponible para el modelo futuro, pero ninguna fila recibe ese
estado durante la migración histórica. No existe un estado para representar
rondas sin evidencia porque esas filas no se crean.

`carton.indicevictoria` se conserva intacto. En la tabla intermedia:

- un valor histórico mayor que cero se copia a la asignación original;
- `0` o `NULL` se convierte en `NULL`;
- nunca se copia un índice a otra partida.

## 7. Integridad de mismo Bingo y PK nueva

La protección física propuesta se mantiene:

- `idbingo` obligatorio en `carton`;
- `idbingo` obligatorio en `carton_partida_bingo`;
- FK compuesta `(idcarton, idbingo)` hacia
  `carton(idcarton, idbingo)`;
- FK compuesta `(idpartida, idbingo)` hacia
  `partidabingo(idpartidabingo, idbingo)`;
- `UNIQUE(idcarton, idpartida)`.

La nueva PK se mantiene como:

```sql
idcartonpartidabingo integer GENERATED BY DEFAULT AS IDENTITY
```

Justificación:

- las tablas antiguas conservan sus IDs manuales sin alteración;
- una tabla nueva puede usar `IDENTITY` independientemente de esas PK;
- evita calcular manualmente el siguiente ID y elimina el riesgo de
  `MAX(id)+1` bajo concurrencia;
- el futuro modelo Django `managed=False` deberá mapearla correctamente como
  campo autogenerado antes de habilitar escrituras híbridas.

## 8. Bloqueos reales

Solo estas condiciones impiden la expansión estructural:

1. algún cartón sin Bingo derivable;
2. algún cartón sin matriz;
3. códigos duplicados al normalizar espacios y mayúsculas;
4. algún precio negativo;
5. algún cartón `Vendido` sin jugador;
6. algún cartón `Vendido` sin precio positivo;
7. referencias huérfanas relevantes;
8. `carton_partida_bingo` ya existente.

En el preflight confirmado, los siete primeros controles dieron cero y la tabla
destino no existe. Por tanto, actualmente no hay un bloqueo de datos detectado.
La ejecución sigue sin estar autorizada porque todavía faltan el respaldo, la
restauración de ensayo, la ventana controlada y la posterior adaptación Django.

Precio distinto al listado, cartón disponible sin precio, nombres de prueba,
índice cero en un cartón disponible y fechas históricas incoherentes son
advertencias preservadas; no aparecen como excepciones en la propuesta 9.5B.

## 9. Artefactos corregidos en la Etapa 9.5B

- [`00_PREFLIGHT_CARTONES_HIBRIDOS.sql`](../DATABASE/00_PREFLIGHT_CARTONES_HIBRIDOS.sql):
  separa la migración histórica 12/12/0 del escenario futuro teórico 45.
- [`01_RESPALDO_CARTONES_HIBRIDOS.md`](../DATABASE/01_RESPALDO_CARTONES_HIBRIDOS.md):
  mantiene el respaldo como paso posterior y fija controles 12/12/0.
- [`02_MIGRACION_CARTONES_HIBRIDOS_PROPUESTA.sql`](../DATABASE/02_MIGRACION_CARTONES_HIBRIDOS_PROPUESTA.sql):
  **PROPUESTA / NO EJECUTAR**, crea solo asignaciones originales y conserva su
  bloqueo intencional al inicio.
- [`03_VALIDACION_CARTONES_HIBRIDOS.sql`](../DATABASE/03_VALIDACION_CARTONES_HIBRIDOS.sql):
  valida conteos, relación original, índice, ganador, Bingo y recaudación; deja
  el escenario futuro en una sección separada.
- [`04_ROLLBACK_CARTONES_HIBRIDOS_PROPUESTA.sql`](../DATABASE/04_ROLLBACK_CARTONES_HIBRIDOS_PROPUESTA.sql):
  **PROPUESTA / NO EJECUTAR**, solo admite 12 filas históricas originales y
  ninguna escritura híbrida.

## 10. Orden para una etapa futura autorizada

1. Repetir el preflight en solo lectura y confirmar los bloqueos reales.
2. Congelar escrituras.
3. Crear y verificar el respaldo completo descrito en `01`.
4. Restaurarlo en una base aislada.
5. Ensayar allí una copia deliberadamente habilitada de la propuesta `02`.
6. Ejecutar `03` en modo solo lectura y verificar 12/12/0, `41.00` y `51.00`.
7. Ensayar `04` antes de cualquier escritura de la aplicación híbrida.
8. Adaptar Django y probar que cada cartón nuevo crea `N` filas para las `N`
   partidas de su Bingo.
9. Autorizar en una etapa independiente la ventana productiva.

## 11. Confirmación de alcance

Durante la Etapa 9.5B:

- no se ejecutó ningún script SQL;
- no se ejecutó SQL mutante ni migraciones;
- no se creó ningún respaldo ni se ejecutó `pg_dump`;
- no se modificó PostgreSQL;
- no se modificaron código Django, modelos, servicios, vistas, templates, URLs,
  WebSockets, tests, requirements ni `.env`;
- no se hizo commit ni push.

Verificaciones finales:

| Comando | Resultado |
|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `git diff --check` | Sin errores ni salida |
| `git status --short` | Solo los seis archivos autorizados aparecen modificados |
