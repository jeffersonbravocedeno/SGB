-- SOLO LECTURA.
-- VALIDACION PROPUESTA PARA DESPUES DE UNA MIGRACION AUTORIZADA.
-- NO EJECUTAR ANTES: referencia columnas y tablas que hoy no existen.
-- Este archivo contiene exclusivamente SELECT y CTE de diagnostico.

-- 0. Identidad de conexion y existencia de objetos esperados.
SELECT
    current_database() AS base_datos,
    current_user AS usuario_conexion,
    current_setting('transaction_read_only') AS transaccion_solo_lectura,
    to_regclass('public.carton') AS carton,
    to_regclass('public.carton_partida_bingo') AS carton_partida_bingo;

-- 1. Columnas fisicas nuevas.
SELECT
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.data_type,
    c.is_nullable,
    c.column_default,
    c.is_identity,
    c.identity_generation
FROM information_schema.columns AS c
WHERE c.table_schema = 'public'
  AND (
      c.table_name = 'carton_partida_bingo'
      OR (c.table_name = 'carton' AND c.column_name = 'idbingo')
  )
ORDER BY c.table_name, c.ordinal_position;

-- 2. Constraints e indices creados por la migracion.
SELECT
    tbl.relname AS table_name,
    con.conname AS constraint_name,
    con.contype AS constraint_type,
    con.convalidated AS validada,
    pg_get_constraintdef(con.oid, true) AS definicion
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS tbl
  ON tbl.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns
  ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'public'
  AND (
      tbl.relname = 'carton_partida_bingo'
      OR con.conname IN (
          'fk_carton_bingo',
          'uq_carton_idcarton_idbingo',
          'uq_partidabingo_idpartida_idbingo'
      )
  )
ORDER BY tbl.relname, con.conname;

SELECT
    i.tablename,
    i.indexname,
    ix.indisunique AS es_unico,
    ix.indisvalid AS es_valido,
    ix.indisready AS esta_listo,
    i.indexdef AS definicion
FROM pg_catalog.pg_indexes AS i
JOIN pg_catalog.pg_namespace AS ns
  ON ns.nspname = i.schemaname
JOIN pg_catalog.pg_class AS idx
  ON idx.relnamespace = ns.oid
 AND idx.relname = i.indexname
JOIN pg_catalog.pg_index AS ix
  ON ix.indexrelid = idx.oid
WHERE i.schemaname = 'public'
  AND (
      i.tablename = 'carton_partida_bingo'
      OR i.indexname IN (
          'idx_carton_idbingo',
          'idx_carton_idjugador',
          'idx_partidabingo_idbingo'
      )
  )
ORDER BY i.tablename, i.indexname;

-- 3. Controles historicos inmutables del corte 2026-06-30.
-- Se esperan 12 cartones, 9 vendidos, 41.00 vendidos y 51.00 en total.
SELECT
    COUNT(*) AS total_cartones,
    COUNT(*) = 12 AS total_cartones_correcto,
    COUNT(*) FILTER (
        WHERE lower(btrim(estadocarton)) = 'vendido'
    ) AS vendidos,
    COUNT(*) FILTER (
        WHERE lower(btrim(estadocarton)) = 'vendido'
    ) = 9 AS vendidos_correcto,
    COALESCE(SUM(preciopagado) FILTER (
        WHERE lower(btrim(estadocarton)) = 'vendido'
    ), 0) AS recaudacion_vendida,
    COALESCE(SUM(preciopagado) FILTER (
        WHERE lower(btrim(estadocarton)) = 'vendido'
    ), 0) = 41.00::numeric AS recaudacion_vendida_correcta,
    COALESCE(SUM(preciopagado), 0) AS recaudacion_total,
    COALESCE(SUM(preciopagado), 0) = 51.00::numeric
        AS recaudacion_total_correcta,
    COUNT(*) FILTER (WHERE idbingo IS NULL) AS sin_bingo,
    COUNT(*) FILTER (WHERE idpartida IS NULL) AS sin_partida_historica
FROM carton;

-- 4. Cada carton debe conservar su partida historica y tener Bingo.
SELECT
    c.idcarton,
    c.codigocarton,
    c.idpartida,
    c.idbingo
FROM carton AS c
WHERE c.idbingo IS NULL OR c.idpartida IS NULL
ORDER BY c.idcarton;

-- 5. No deben existir referencias huerfanas en la tabla intermedia.
SELECT
    cpb.idcartonpartidabingo,
    cpb.idcarton,
    cpb.idpartida,
    cpb.idbingo,
    CASE
        WHEN c.idcarton IS NULL THEN 'Carton inexistente'
        WHEN p.idpartidabingo IS NULL THEN 'Partida inexistente'
        WHEN b.idbingo IS NULL THEN 'Bingo inexistente'
        ELSE 'Sin clasificar'
    END AS motivo
FROM carton_partida_bingo AS cpb
LEFT JOIN carton AS c ON c.idcarton = cpb.idcarton
LEFT JOIN partidabingo AS p ON p.idpartidabingo = cpb.idpartida
LEFT JOIN bingo AS b ON b.idbingo = cpb.idbingo
WHERE c.idcarton IS NULL
   OR p.idpartidabingo IS NULL
   OR b.idbingo IS NULL
ORDER BY cpb.idcartonpartidabingo;

-- 6. Carton, partida y asignacion deben pertenecer al mismo Bingo.
SELECT
    cpb.idcartonpartidabingo,
    cpb.idcarton,
    c.idbingo AS bingo_carton,
    cpb.idpartida,
    p.idbingo AS bingo_partida,
    cpb.idbingo AS bingo_asignacion
FROM carton_partida_bingo AS cpb
JOIN carton AS c ON c.idcarton = cpb.idcarton
JOIN partidabingo AS p ON p.idpartidabingo = cpb.idpartida
WHERE cpb.idbingo <> c.idbingo
   OR cpb.idbingo <> p.idbingo
ORDER BY cpb.idcartonpartidabingo;

-- 7. No debe repetirse ninguna pareja carton/partida.
SELECT
    cpb.idcarton,
    cpb.idpartida,
    COUNT(*) AS repeticiones
FROM carton_partida_bingo AS cpb
GROUP BY cpb.idcarton, cpb.idpartida
HAVING COUNT(*) > 1
ORDER BY cpb.idcarton, cpb.idpartida;

-- 8. Conteo global de la migracion historica.
-- Resultado esperado: 12 cartones, 12 filas, 12 originales y 0 inferidas.
WITH control AS (
    SELECT
        COUNT(*) AS asignaciones_reales,
        COUNT(*) FILTER (WHERE es_asignacion_original) AS originales,
        COUNT(*) FILTER (WHERE NOT es_asignacion_original) AS no_originales,
        COUNT(*) FILTER (
            WHERE origen_asignacion = 'Historica inferida'
        ) AS historicas_inferidas
    FROM carton_partida_bingo
)
SELECT
    (SELECT COUNT(*) FROM carton) AS cartones_maestros,
    asignaciones_reales,
    originales,
    no_originales,
    historicas_inferidas,
    (SELECT COUNT(*) FROM carton) = 12
        AND asignaciones_reales = 12
        AND originales = 12
        AND no_originales = 0
        AND historicas_inferidas = 0 AS conteo_historico_correcto
FROM control;

-- 9. Por Bingo, el numero de asignaciones historicas debe ser igual al numero
-- de cartones existentes, no cartones multiplicados por partidas.
WITH cartones AS (
    SELECT idbingo, COUNT(*) AS cantidad
    FROM carton
    GROUP BY idbingo
), asignaciones AS (
    SELECT idbingo, COUNT(*) AS cantidad
    FROM carton_partida_bingo
    GROUP BY idbingo
)
SELECT
    b.idbingo,
    b.titulobingo,
    COALESCE(c.cantidad, 0) AS cartones_historicos,
    COALESCE(c.cantidad, 0) AS asignaciones_historicas_esperadas,
    COALESCE(a.cantidad, 0) AS asignaciones_historicas_reales,
    COALESCE(a.cantidad, 0) = COALESCE(c.cantidad, 0)
        AS conteo_historico_coincide
FROM bingo AS b
LEFT JOIN cartones AS c ON c.idbingo = b.idbingo
LEFT JOIN asignaciones AS a ON a.idbingo = b.idbingo
ORDER BY b.idbingo;

-- 10. Debe existir exactamente una asignacion original por carton y debe
-- coincidir con carton.idpartida.
SELECT
    c.idcarton,
    c.idpartida AS partida_historica,
    COUNT(cpb.idcartonpartidabingo) AS asignaciones_totales,
    COUNT(cpb.idcartonpartidabingo) FILTER (
        WHERE cpb.es_asignacion_original
    ) AS asignaciones_originales,
    COUNT(cpb.idcartonpartidabingo) FILTER (
        WHERE cpb.es_asignacion_original
          AND cpb.idpartida = c.idpartida
    ) AS originales_coincidentes
FROM carton AS c
LEFT JOIN carton_partida_bingo AS cpb ON cpb.idcarton = c.idcarton
GROUP BY c.idcarton, c.idpartida
HAVING COUNT(cpb.idcartonpartidabingo) <> 1
    OR COUNT(cpb.idcartonpartidabingo) FILTER (
           WHERE cpb.es_asignacion_original
       ) <> 1
    OR COUNT(cpb.idcartonpartidabingo) FILTER (
           WHERE cpb.es_asignacion_original
             AND cpb.idpartida = c.idpartida
       ) <> 1
ORDER BY c.idcarton;

-- 11. indicevictoria debe copiarse solo si el valor historico es mayor que 0.
-- Los once ceros historicos deben producir NULL, nunca un resultado.
SELECT
    c.idcarton,
    c.indicevictoria AS indice_historico,
    cpb.indicevictoria AS indice_migrado,
    CASE
        WHEN c.indicevictoria > 0 THEN c.indicevictoria
        ELSE NULL
    END AS indice_esperado
FROM carton AS c
JOIN carton_partida_bingo AS cpb
  ON cpb.idcarton = c.idcarton
 AND cpb.es_asignacion_original
WHERE cpb.indicevictoria IS DISTINCT FROM
      CASE
          WHEN c.indicevictoria > 0 THEN c.indicevictoria
          ELSE NULL
      END
ORDER BY c.idcarton;

-- 12. La migracion historica no debe inferir ganadores.
SELECT
    cpb.idcartonpartidabingo,
    cpb.idcarton,
    cpb.idpartida,
    cpb.estado_participacion
FROM carton_partida_bingo AS cpb
WHERE cpb.estado_participacion = 'Ganador'
ORDER BY cpb.idcartonpartidabingo;

-- 13. Vocabulario real de estados y origenes despues de migrar.
SELECT
    estado_participacion,
    origen_asignacion,
    es_asignacion_original,
    COUNT(*) AS cantidad
FROM carton_partida_bingo
GROUP BY estado_participacion, origen_asignacion, es_asignacion_original
ORDER BY origen_asignacion, estado_participacion;

-- 14. Advertencia preservada: datos con nombre de prueba dentro del alcance.
-- Su presencia no invalida la migracion historica.
SELECT
    b.idbingo,
    b.titulobingo,
    p.idpartidabingo,
    p.nombreronda,
    COUNT(DISTINCT c.idcarton) AS cartones,
    COUNT(DISTINCT cpb.idcartonpartidabingo) AS asignaciones_historicas
FROM bingo AS b
LEFT JOIN partidabingo AS p ON p.idbingo = b.idbingo
LEFT JOIN carton AS c ON c.idbingo = b.idbingo
LEFT JOIN carton_partida_bingo AS cpb ON cpb.idbingo = b.idbingo
WHERE concat_ws(' ', b.titulobingo, b.tipobingo, p.nombreronda)
      ~* '(prueba|test|demo|ensayo|simulaci[oó]n)'
GROUP BY b.idbingo, b.titulobingo, p.idpartidabingo, p.nombreronda
ORDER BY b.idbingo, p.idpartidabingo;

-- 15. Generacion de la nueva PK. Debe mostrar la secuencia de IDENTITY.
SELECT
    pg_get_serial_sequence(
        'public.carton_partida_bingo',
        'idcartonpartidabingo'
    ) AS secuencia_asociada,
    MAX(idcartonpartidabingo) AS maximo_id,
    COUNT(*) AS filas
FROM carton_partida_bingo;

-- 16. ESCENARIO FUTURO, separado de la migracion historica.
-- Cuando Django cree un carton nuevo para un Bingo con N partidas, la
-- aplicacion debera crear N filas. Esta consulta informa N por Bingo; no exige
-- que los cartones historicos tengan ese numero de asignaciones.
SELECT
    b.idbingo,
    b.titulobingo,
    COUNT(p.idpartidabingo) AS partidas_del_bingo,
    COUNT(p.idpartidabingo) AS filas_por_cada_carton_nuevo
FROM bingo AS b
LEFT JOIN partidabingo AS p ON p.idbingo = b.idbingo
GROUP BY b.idbingo, b.titulobingo
ORDER BY b.idbingo;
