# Respaldo previo a cartones híbridos

Estado: **PROCEDIMIENTO PROPUESTO / NO EJECUTADO**.

Este documento define el respaldo obligatorio antes de cualquier ejecución de
`02_MIGRACION_CARTONES_HIBRIDOS_PROPUESTA.sql`. No crea respaldos ni autoriza
la migración.

## Alcance mínimo

El respaldo debe cubrir la base completa `bingo`, no solo `carton`, porque la
migración depende de `bingo`, `partidabingo`, `jugador`, `sesionjuego` y de las
tablas referenciadas por sus claves foráneas.

Además del archivo de respaldo, se deben conservar:

- salida final de `00_PREFLIGHT_CARTONES_HIBRIDOS.sql`;
- versión de PostgreSQL y fecha/hora de corte;
- commit desplegado de la aplicación;
- checksum SHA-256 del respaldo;
- listado de roles y privilegios necesarios para restaurar;
- responsable de autorizar el corte y responsable de restauración.

## Condiciones previas

1. Resolver o aceptar expresamente los bloqueos documentados en
   `DOCUMENTACION/ETAPA_9_5A_PREPARACION_CARTONES_HIBRIDOS.md`.
2. Desplegar primero una versión de aplicación compatible o mantener todas las
   escrituras detenidas durante el ensayo.
3. Repetir el preflight en modo solo lectura y comparar sus controles con los
   valores aprobados.
4. Confirmar espacio disponible para el dump y para una restauración completa.
5. Definir una base aislada de ensayo. Nunca ensayar la restauración sobre
   `bingo`.

## Comandos de referencia

Los siguientes comandos son ejemplos. **No fueron ejecutados en la Etapa
9.5A**. La contraseña debe suministrarse mediante `.pgpass`, un gestor de
secretos o una variable temporal; no debe escribirse en este documento.

```bash
# Respaldo lógico completo en formato custom.
pg_dump \
  --host=127.0.0.1 \
  --port=5432 \
  --username=jjbc \
  --dbname=bingo \
  --format=custom \
  --no-owner \
  --no-privileges \
  --verbose \
  --file=bingo_pre_cartones_hibridos_YYYYMMDD_HHMMSS.dump

# Inventario del archivo sin restaurarlo.
pg_restore \
  --list \
  bingo_pre_cartones_hibridos_YYYYMMDD_HHMMSS.dump \
  > bingo_pre_cartones_hibridos_YYYYMMDD_HHMMSS.list

# Integridad del artefacto.
sha256sum \
  bingo_pre_cartones_hibridos_YYYYMMDD_HHMMSS.dump \
  > bingo_pre_cartones_hibridos_YYYYMMDD_HHMMSS.dump.sha256
```

Si el entorno exige preservar propietarios y privilegios, se debe generar
adicionalmente el inventario global con una cuenta autorizada:

```bash
pg_dumpall \
  --host=127.0.0.1 \
  --port=5432 \
  --username=USUARIO_ADMINISTRATIVO \
  --globals-only \
  --file=postgres_globals_YYYYMMDD_HHMMSS.sql
```

## Ensayo obligatorio de restauración

La existencia del dump no demuestra que sea restaurable. Antes de autorizar la
migración se debe restaurar en una base aislada y ejecutar allí el preflight.

```bash
createdb \
  --host=127.0.0.1 \
  --port=5432 \
  --username=USUARIO_ADMINISTRATIVO \
  bingo_restore_cartones_hibridos

pg_restore \
  --host=127.0.0.1 \
  --port=5432 \
  --username=USUARIO_ADMINISTRATIVO \
  --dbname=bingo_restore_cartones_hibridos \
  --no-owner \
  --no-privileges \
  --exit-on-error \
  --verbose \
  bingo_pre_cartones_hibridos_YYYYMMDD_HHMMSS.dump
```

En la copia restaurada se debe comprobar como mínimo:

- 5 Bingos, 6 partidas, 12 cartones, 4 jugadores y 1 sesión, salvo cambios
  posteriores expresamente aprobados;
- 12 cartones con Bingo derivable;
- códigos y matrices sin pérdidas;
- 9 cartones vendidos y recaudación histórica vendida de `41.00`;
- constraints, índices y claves foráneas equivalentes al origen;
- ejecución completa del preflight sin errores.

Si los datos cambian antes de la ventana definitiva, estos valores dejan de ser
el control vigente: se debe generar un preflight y un respaldo nuevos.

## Criterios de aceptación del respaldo

El respaldo se considera aceptable únicamente cuando:

- `pg_dump` termina con código cero;
- `pg_restore --list` puede leer el archivo;
- el checksum se valida después de copiar el artefacto a su ubicación segura;
- la restauración aislada termina con código cero;
- los conteos y controles restaurados coinciden con el preflight de corte;
- el tiempo de restauración fue medido y cabe en la ventana acordada;
- el artefacto está fuera del repositorio y tiene acceso restringido.

## Elección del rollback

- Antes de que la aplicación escriba con el modelo híbrido, puede usarse el
  rollback expansivo propuesto en
  `04_ROLLBACK_CARTONES_HIBRIDOS_PROPUESTA.sql`.
- Después de aceptar escrituras nuevas, ese rollback deja de ser suficiente:
  se debe detener la aplicación, preservar los datos nuevos y ejecutar un plan
  de reversión específico o restaurar el respaldo completo.
- Una restauración completa reemplaza el estado de la base; requiere una
  autorización operativa independiente y no forma parte de la Etapa 9.5A.

## Registro de ejecución futura

| Dato | Valor |
|---|---|
| Inicio y fin del dump | Pendiente |
| Archivo | Pendiente |
| SHA-256 | Pendiente |
| Tamaño | Pendiente |
| Base restaurada de ensayo | Pendiente |
| Duración de restauración | Pendiente |
| Resultado del preflight restaurado | Pendiente |
| Responsable | Pendiente |
| Aprobación | Pendiente |
