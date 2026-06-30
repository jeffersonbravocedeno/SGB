-- SOLO LECTURA.
-- VALIDACION PROPUESTA PARA DESPUES DE UNA MIGRACION AUTORIZADA.
-- NO EJECUTAR ANTES: referencia columnas y tablas que hoy no existen.
-- Este archivo contiene exclusivamente SELECT y CTE de diagnostico.

-- 0. Identidad de conexión y existencia de objetos esperados.
SELECT
    current_database() AS base_datos,
    current_user AS usuario_conexion,
    current_setting('transaction_read_only') AS transaccion_solo_lectura,
    to_regclass('public.carton') AS carton,
    to_regclass('public.carton_partida_bingo') AS carton_partida_bingo;

-- 1. Columnas físicas nuevas.
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

-- 2. Constraints e índices creados por la migración.
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

-- 3. Controles históricos. Con el corte del 2026-06-30 se esperan 12
-- cartones, 9 vendidos, recaudación vendida 41.00 y recaudación total 51.00.
SELECT
    COUNT(*) AS total_cartones,
    COUNT(*) FILTER (
        WHERE lower(btrim(estadocarton)) = 'vendido'
    ) AS vendidos,
    COALESCE(SUM(preciopagado) FILTER (
        WHERE lower(btrim(estadocarton)) = 'vendido'
    ), 0) AS recaudacion_vendida,
    COALESCE(SUM(preciopagado), 0) AS recaudacion_total,
    COUNT(*) FILTER (WHERE idbingo IS NULL) AS sin_bingo,
    COUNT(*) FILTER (WHERE idpartida IS NULL) AS sin_partida_historica
FROM carton;

-- 4. Cada cartón debe conservar la relación histórica y tener Bingo.
SELECT
    c.idcarton,
    c.codigocarton,
    c.idpartida,
    c.idbingo
FROM carton AS c
WHERE c.idbingo IS NULL OR c.idpartida IS NULL
ORDER BY c.idcarton;

-- 5. No deben existir referencias huérfanas en la tabla intermedia.
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
LEFT JOIN carton AS c
  ON c.idcarton = cpb.idcarton
LEFT JOIN partidabingo AS p
  ON p.idpartidabingo = cpb.idpartida
LEFT JOIN bingo AS b
  ON b.idbingo = cpb.idbingo
WHERE c.idcarton IS NULL
   OR p.idpartidabingo IS NULL
   OR b.idbingo IS NULL
ORDER BY cpb.idcartonpartidabingo;

-- 6. Cartón, partida y asignación deben pertenecer al mismo Bingo.
SELECT
    cpb.idcartonpartidabingo,
    cpb.idcarton,
    c.idbingo AS bingo_carton,
    cpb.idpartida,
    p.idbingo AS bingo_partida,
    cpb.idbingo AS bingo_asignacion
FROM carton_partida_bingo AS cpb
JOIN carton AS c
  ON c.idcarton = cpb.idcarton
JOIN partidabingo AS p
  ON p.idpartidabingo = cpb.idpartida
WHERE cpb.idbingo <> c.idbingo
   OR cpb.idbingo <> p.idbingo
ORDER BY cpb.idcartonpartidabingo;

-- 7. No debe repetirse ninguna pareja cartón/partida.
SELECT
    cpb.idcarton,
    cpb.idpartida,
    COUNT(*) AS repeticiones
FROM carton_partida_bingo AS cpb
GROUP BY cpb.idcarton, cpb.idpartida
HAVING COUNT(*) > 1
ORDER BY cpb.idcarton, cpb.idpartida;

-- 8. Conteo global esperado. Para el corte confirmado: 45 asignaciones,
-- 12 originales y 33 inferidas.
WITH esperado AS (
    SELECT COALESCE(SUM(cartones * partidas), 0) AS asignaciones_esperadas
    FROM (
        SELECT
            b.idbingo,
            COUNT(DISTINCT c.idcarton) AS cartones,
            COUNT(DISTINCT p.idpartidabingo) AS partidas
        FROM bingo AS b
        LEFT JOIN carton AS c ON c.idbingo = b.idbingo
        LEFT JOIN partidabingo AS p ON p.idbingo = b.idbingo
        GROUP BY b.idbingo
    ) AS por_bingo
), real AS (
    SELECT
        COUNT(*) AS asignaciones_reales,
        COUNT(*) FILTER (WHERE es_asignacion_original) AS originales,
        COUNT(*) FILTER (WHERE NOT es_asignacion_original) AS inferidas
    FROM carton_partida_bingo
)
SELECT
    e.asignaciones_esperadas,
    r.asignaciones_reales,
    r.originales,
    r.inferidas,
    r.asignaciones_reales = e.asignaciones_esperadas AS conteo_coincide
FROM esperado AS e
CROSS JOIN real AS r;

-- 9. Control por Bingo: real debe ser cartones × partidas.
WITH cartones AS (
    SELECT idbingo, COUNT(*) AS cantidad
    FROM carton
    GROUP BY idbingo
), partidas AS (
    SELECT idbingo, COUNT(*) AS cantidad
    FROM partidabingo
    GROUP BY idbingo
), asignaciones AS (
    SELECT idbingo, COUNT(*) AS cantidad
    FROM carton_partida_bingo
    GROUP BY idbingo
)
SELECT
    b.idbingo,
    b.titulobingo,
    COALESCE(c.cantidad, 0) AS cartones,
    COALESCE(p.cantidad, 0) AS partidas,
    COALESCE(c.cantidad, 0) * COALESCE(p.cantidad, 0)
        AS asignaciones_esperadas,
    COALESCE(a.cantidad, 0) AS asignaciones_reales,
    COALESCE(a.cantidad, 0)
        = COALESCE(c.cantidad, 0) * COALESCE(p.cantidad, 0)
        AS conteo_coincide
FROM bingo AS b
LEFT JOIN cartones AS c ON c.idbingo = b.idbingo
LEFT JOIN partidas AS p ON p.idbingo = b.idbingo
LEFT JOIN asignaciones AS a ON a.idbingo = b.idbingo
ORDER BY b.idbingo;

-- 10. Debe existir exactamente una asignación original por cartón y debe
-- coincidir con carton.idpartida.
SELECT
    c.idcarton,
    c.idpartida AS partida_historica,
    COUNT(cpb.idcartonpartidabingo) FILTER (
        WHERE cpb.es_asignacion_original
    ) AS asignaciones_originales,
    COUNT(cpb.idcartonpartidabingo) FILTER (
        WHERE cpb.es_asignacion_original
          AND cpb.idpartida = c.idpartida
    ) AS originales_coincidentes
FROM carton AS c
LEFT JOIN carton_partida_bingo AS cpb
  ON cpb.idcarton = c.idcarton
GROUP BY c.idcarton, c.idpartida
HAVING COUNT(cpb.idcartonpartidabingo) FILTER (
           WHERE cpb.es_asignacion_original
       ) <> 1
    OR COUNT(cpb.idcartonpartidabingo) FILTER (
           WHERE cpb.es_asignacion_original
             AND cpb.idpartida = c.idpartida
       ) <> 1
ORDER BY c.idcarton;

-- 11. El índice histórico no debe replicarse a asignaciones inferidas.
SELECT
    cpb.idcartonpartidabingo,
    cpb.idcarton,
    cpb.idpartida,
    cpb.indicevictoria,
    cpb.origen_asignacion
FROM carton_partida_bingo AS cpb
WHERE NOT cpb.es_asignacion_original
  AND cpb.indicevictoria IS NOT NULL
ORDER BY cpb.idcartonpartidabingo;

-- 12. Vocabulario real de estados y orígenes después de migrar.
SELECT
    estado_participacion,
    origen_asignacion,
    es_asignacion_original,
    COUNT(*) AS cantidad
FROM carton_partida_bingo
GROUP BY estado_participacion, origen_asignacion, es_asignacion_original
ORDER BY origen_asignacion, estado_participacion;

-- 13. Ganadores por jugador que siguen sin un cartón original demostrable.
SELECT
    p.idpartidabingo,
    p.idbingo,
    p.idjugadorganador
FROM partidabingo AS p
WHERE p.idjugadorganador IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM carton_partida_bingo AS cpb
      JOIN carton AS c ON c.idcarton = cpb.idcarton
      WHERE cpb.idpartida = p.idpartidabingo
        AND cpb.es_asignacion_original
        AND c.idjugador = p.idjugadorganador
  )
ORDER BY p.idpartidabingo;

-- 14. Datos de prueba que quedaron dentro del alcance migrado.
SELECT
    b.idbingo,
    b.titulobingo,
    p.idpartidabingo,
    p.nombreronda,
    COUNT(DISTINCT c.idcarton) AS cartones,
    COUNT(DISTINCT cpb.idcartonpartidabingo) AS asignaciones
FROM bingo AS b
LEFT JOIN partidabingo AS p ON p.idbingo = b.idbingo
LEFT JOIN carton AS c ON c.idbingo = b.idbingo
LEFT JOIN carton_partida_bingo AS cpb ON cpb.idbingo = b.idbingo
WHERE concat_ws(' ', b.titulobingo, b.tipobingo, p.nombreronda)
      ~* '(prueba|test|demo|ensayo|simulaci[oó]n)'
GROUP BY b.idbingo, b.titulobingo, p.idpartidabingo, p.nombreronda
ORDER BY b.idbingo, p.idpartidabingo;

-- 15. Generación de la nueva PK. Debe mostrar la secuencia de IDENTITY.
SELECT
    pg_get_serial_sequence(
        'public.carton_partida_bingo',
        'idcartonpartidabingo'
    ) AS secuencia_asociada,
    MAX(idcartonpartidabingo) AS maximo_id,
    COUNT(*) AS filas
FROM carton_partida_bingo;
