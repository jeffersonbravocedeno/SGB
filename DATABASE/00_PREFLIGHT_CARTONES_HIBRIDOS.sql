-- SOLO LECTURA.
-- NO MODIFICA DATOS NI ESTRUCTURA.
-- EJECUTAR ANTES DE LA MIGRACIÓN.
--
-- ETAPA 9.5A / SIAB - CoopBingo.
-- Este archivo contiene exclusivamente consultas SELECT y CTE de diagnóstico.
-- Se recomienda ejecutarlo con una cuenta de auditoría que tenga solo permiso
-- SELECT o dentro de una transacción configurada externamente como READ ONLY.

-- 0. Identidad de la conexión y existencia de las tablas esperadas.
SELECT
    current_database() AS base_datos,
    current_user AS usuario_conexion,
    current_schema() AS esquema_actual,
    current_setting('server_version') AS version_postgresql,
    current_setting('transaction_read_only') AS transaccion_solo_lectura;

SELECT
    nombre_tabla,
    to_regclass(format('public.%I', nombre_tabla)) AS relacion_fisica
FROM (
    VALUES
        ('carton'),
        ('partidabingo'),
        ('bingo'),
        ('jugador'),
        ('sesionjuego'),
        ('carton_partida_bingo')
) AS tablas(nombre_tabla)
ORDER BY nombre_tabla;

-- 1. Columnas, tipos, nullability, defaults e identidad.
SELECT
    c.table_schema,
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.data_type,
    c.udt_name,
    c.character_maximum_length,
    c.numeric_precision,
    c.numeric_scale,
    c.is_nullable,
    c.column_default,
    c.is_identity,
    c.identity_generation,
    c.is_generated,
    c.generation_expression
FROM information_schema.columns AS c
WHERE c.table_schema = 'public'
  AND c.table_name IN (
      'carton', 'partidabingo', 'bingo', 'jugador', 'sesionjuego'
  )
ORDER BY c.table_name, c.ordinal_position;

-- 2. Nombres reales y definiciones de PK, FK, UNIQUE y CHECK.
SELECT
    ns.nspname AS table_schema,
    tbl.relname AS table_name,
    con.conname AS constraint_name,
    CASE con.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'f' THEN 'FOREIGN KEY'
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'c' THEN 'CHECK'
        WHEN 'x' THEN 'EXCLUDE'
        ELSE con.contype::text
    END AS constraint_type,
    con.convalidated AS validada,
    pg_get_constraintdef(con.oid, true) AS definicion
FROM pg_catalog.pg_constraint AS con
JOIN pg_catalog.pg_class AS tbl
  ON tbl.oid = con.conrelid
JOIN pg_catalog.pg_namespace AS ns
  ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'public'
  AND tbl.relname IN (
      'carton', 'partidabingo', 'bingo', 'jugador', 'sesionjuego'
  )
ORDER BY tbl.relname, constraint_type, con.conname;

-- 3. Índices físicos y definición completa.
SELECT
    i.schemaname AS table_schema,
    i.tablename AS table_name,
    i.indexname AS index_name,
    ix.indisprimary AS es_primary,
    ix.indisunique AS es_unique,
    ix.indisvalid AS es_valido,
    ix.indisready AS esta_listo,
    i.indexdef AS definicion
FROM pg_catalog.pg_indexes AS i
JOIN pg_catalog.pg_namespace AS ns
  ON ns.nspname = i.schemaname
JOIN pg_catalog.pg_class AS tbl
  ON tbl.relnamespace = ns.oid
 AND tbl.relname = i.tablename
JOIN pg_catalog.pg_class AS idx
  ON idx.relnamespace = ns.oid
 AND idx.relname = i.indexname
JOIN pg_catalog.pg_index AS ix
  ON ix.indexrelid = idx.oid
WHERE i.schemaname = 'public'
  AND i.tablename IN (
      'carton', 'partidabingo', 'bingo', 'jugador', 'sesionjuego'
  )
ORDER BY i.tablename, i.indexname;

-- 4. Secuencia asociada a cada columna de PK entera, si existe.
WITH columnas_pk AS (
    SELECT
        ns.nspname AS table_schema,
        tbl.relname AS table_name,
        att.attname AS column_name,
        format_type(att.atttypid, att.atttypmod) AS data_type
    FROM pg_catalog.pg_constraint AS con
    JOIN pg_catalog.pg_class AS tbl
      ON tbl.oid = con.conrelid
    JOIN pg_catalog.pg_namespace AS ns
      ON ns.oid = tbl.relnamespace
    JOIN pg_catalog.pg_attribute AS att
      ON att.attrelid = tbl.oid
     AND att.attnum = ANY (con.conkey)
    WHERE con.contype = 'p'
      AND ns.nspname = 'public'
      AND tbl.relname IN (
          'carton', 'partidabingo', 'bingo', 'jugador', 'sesionjuego'
      )
)
SELECT
    table_schema,
    table_name,
    column_name,
    data_type,
    pg_get_serial_sequence(
        format('%I.%I', table_schema, table_name),
        column_name
    ) AS secuencia_asociada
FROM columnas_pk
ORDER BY table_name, column_name;

-- 5. Conteos base.
SELECT 'bingo' AS entidad, COUNT(*) AS cantidad FROM bingo
UNION ALL
SELECT 'partidabingo', COUNT(*) FROM partidabingo
UNION ALL
SELECT 'carton', COUNT(*) FROM carton
UNION ALL
SELECT 'jugador', COUNT(*) FROM jugador
UNION ALL
SELECT 'sesionjuego', COUNT(*) FROM sesionjuego
ORDER BY entidad;

-- 6. Resumen integral de calidad de cartones.
SELECT
    COUNT(*) AS total_cartones,
    COUNT(*) FILTER (WHERE c.idpartida IS NULL) AS sin_partida,
    COUNT(*) FILTER (WHERE c.idjugador IS NULL) AS sin_jugador,
    COUNT(*) FILTER (
        WHERE c.matriznumeros IS NULL OR btrim(c.matriznumeros) = ''
    ) AS sin_matriz,
    COUNT(*) FILTER (WHERE c.preciopagado IS NULL) AS sin_precio,
    COUNT(*) FILTER (WHERE c.preciopagado < 0) AS precio_negativo,
    COUNT(*) FILTER (
        WHERE lower(btrim(c.estadocarton)) = 'vendido'
          AND (c.preciopagado IS NULL OR c.preciopagado <= 0)
    ) AS vendidos_sin_precio_positivo,
    COUNT(*) FILTER (WHERE c.indicevictoria IS NOT NULL) AS con_indice_victoria,
    COUNT(*) FILTER (WHERE c.indicevictoria < 0) AS indice_victoria_negativo
FROM carton AS c;

-- 7. Cartones sin partida.
SELECT
    c.idcarton,
    c.codigocarton,
    c.idjugador,
    c.estadocarton,
    c.fechacompra
FROM carton AS c
WHERE c.idpartida IS NULL
ORDER BY c.idcarton;

-- 8. Cartones cuyo Bingo no se puede derivar por carton -> partida -> Bingo.
SELECT
    c.idcarton,
    c.codigocarton,
    c.idpartida,
    p.idbingo,
    CASE
        WHEN c.idpartida IS NULL THEN 'Cartón sin partida'
        WHEN p.idpartidabingo IS NULL THEN 'Partida referenciada inexistente'
        WHEN b.idbingo IS NULL THEN 'Partida sin Bingo existente'
        ELSE 'Sin clasificar'
    END AS motivo
FROM carton AS c
LEFT JOIN partidabingo AS p
  ON p.idpartidabingo = c.idpartida
LEFT JOIN bingo AS b
  ON b.idbingo = p.idbingo
WHERE c.idpartida IS NULL
   OR p.idpartidabingo IS NULL
   OR b.idbingo IS NULL
ORDER BY c.idcarton;

-- 9. Cartones sin jugador y referencias a jugadores inexistentes.
SELECT
    c.idcarton,
    c.codigocarton,
    c.idjugador,
    c.estadocarton,
    CASE
        WHEN c.idjugador IS NULL THEN 'Sin propietario'
        ELSE 'Jugador referenciado inexistente'
    END AS motivo
FROM carton AS c
LEFT JOIN jugador AS j
  ON j.idjugador = c.idjugador
WHERE c.idjugador IS NULL
   OR j.idjugador IS NULL
ORDER BY c.idcarton;

-- 10. Cartones sin matriz.
SELECT
    c.idcarton,
    c.codigocarton,
    c.idpartida,
    c.idjugador,
    c.estadocarton
FROM carton AS c
WHERE c.matriznumeros IS NULL
   OR btrim(c.matriznumeros) = ''
ORDER BY c.idcarton;

-- 11. Códigos duplicados exactos y duplicados al normalizar espacios/mayúsculas.
SELECT
    c.codigocarton,
    COUNT(*) AS cantidad,
    array_agg(c.idcarton ORDER BY c.idcarton) AS ids_carton
FROM carton AS c
GROUP BY c.codigocarton
HAVING COUNT(*) > 1
ORDER BY cantidad DESC, c.codigocarton;

SELECT
    upper(btrim(c.codigocarton)) AS codigo_normalizado,
    COUNT(*) AS cantidad,
    array_agg(c.idcarton ORDER BY c.idcarton) AS ids_carton,
    array_agg(DISTINCT c.codigocarton ORDER BY c.codigocarton) AS codigos_originales
FROM carton AS c
GROUP BY upper(btrim(c.codigocarton))
HAVING COUNT(*) > 1
ORDER BY cantidad DESC, codigo_normalizado;

-- 12. Estados existentes y estados no contemplados por la aplicación actual.
SELECT
    c.estadocarton,
    COUNT(*) AS cantidad
FROM carton AS c
GROUP BY c.estadocarton
ORDER BY c.estadocarton;

SELECT
    c.idcarton,
    c.codigocarton,
    c.estadocarton
FROM carton AS c
WHERE c.estadocarton IS NULL
   OR btrim(c.estadocarton) = ''
   OR c.estadocarton NOT IN ('Disponible', 'Vendido', 'Cerrado')
ORDER BY c.estadocarton NULLS FIRST, c.idcarton;

-- 13. Índices de victoria existentes y casos sospechosos.
SELECT
    c.indicevictoria,
    COUNT(*) AS cantidad
FROM carton AS c
GROUP BY c.indicevictoria
ORDER BY c.indicevictoria NULLS FIRST;

SELECT
    c.idcarton,
    c.codigocarton,
    c.idpartida,
    c.estadocarton,
    c.indicevictoria,
    p.estadopartida
FROM carton AS c
LEFT JOIN partidabingo AS p
  ON p.idpartidabingo = c.idpartida
WHERE c.indicevictoria < 0
   OR (
       c.indicevictoria IS NOT NULL
       AND lower(btrim(c.estadocarton)) <> 'vendido'
   )
ORDER BY c.idcarton;

-- 14. Precios pagados existentes, inválidos y diferencias frente al precio del Bingo.
SELECT
    c.preciopagado,
    COUNT(*) AS cantidad
FROM carton AS c
GROUP BY c.preciopagado
ORDER BY c.preciopagado NULLS FIRST;

SELECT
    c.idcarton,
    c.codigocarton,
    c.estadocarton,
    c.preciopagado,
    b.idbingo,
    b.preciocarton AS precio_lista_bingo,
    CASE
        WHEN c.preciopagado < 0 THEN 'Precio negativo'
        WHEN lower(btrim(c.estadocarton)) = 'vendido'
             AND c.preciopagado IS NULL THEN 'Vendido sin precio'
        WHEN lower(btrim(c.estadocarton)) = 'vendido'
             AND c.preciopagado = 0 THEN 'Vendido con precio cero'
        WHEN c.preciopagado IS NOT NULL
             AND b.preciocarton IS NOT NULL
             AND c.preciopagado <> b.preciocarton THEN 'Difiere del precio de lista; revisar descuento o histórico'
        ELSE 'Sin clasificar'
    END AS observacion
FROM carton AS c
LEFT JOIN partidabingo AS p
  ON p.idpartidabingo = c.idpartida
LEFT JOIN bingo AS b
  ON b.idbingo = p.idbingo
WHERE c.preciopagado < 0
   OR (
       lower(btrim(c.estadocarton)) = 'vendido'
       AND (c.preciopagado IS NULL OR c.preciopagado = 0)
   )
   OR (
       c.preciopagado IS NOT NULL
       AND b.preciocarton IS NOT NULL
       AND c.preciopagado <> b.preciocarton
   )
ORDER BY b.idbingo NULLS FIRST, c.idcarton;

-- 15. Bingos y sus partidas, incluidos los Bingos sin rondas.
SELECT
    b.idbingo,
    b.titulobingo,
    b.tipobingo,
    b.estadobingo,
    b.fechaprogramadabingo,
    b.preciocarton,
    p.idpartidabingo,
    p.nombreronda,
    p.estadopartida,
    p.horainicio,
    p.horafin,
    p.idjugadorganador
FROM bingo AS b
LEFT JOIN partidabingo AS p
  ON p.idbingo = b.idbingo
ORDER BY b.idbingo, p.horainicio NULLS LAST, p.idpartidabingo;

-- 16. Partidas sin Bingo existente.
SELECT
    p.idpartidabingo,
    p.idbingo,
    p.nombreronda,
    p.estadopartida,
    p.horainicio
FROM partidabingo AS p
LEFT JOIN bingo AS b
  ON b.idbingo = p.idbingo
WHERE b.idbingo IS NULL
ORDER BY p.idpartidabingo;

-- 17. Cartones agrupados por partida.
SELECT
    p.idpartidabingo,
    p.nombreronda,
    p.estadopartida,
    COUNT(c.idcarton) AS total_cartones,
    COUNT(c.idcarton) FILTER (
        WHERE lower(btrim(c.estadocarton)) = 'vendido'
    ) AS vendidos,
    COUNT(c.idcarton) FILTER (WHERE c.idjugador IS NULL) AS sin_jugador,
    COUNT(c.idcarton) FILTER (
        WHERE c.matriznumeros IS NULL OR btrim(c.matriznumeros) = ''
    ) AS sin_matriz
FROM partidabingo AS p
LEFT JOIN carton AS c
  ON c.idpartida = p.idpartidabingo
GROUP BY
    p.idpartidabingo,
    p.nombreronda,
    p.estadopartida
ORDER BY p.idpartidabingo;

-- 18. Cartones agrupados por Bingo derivado.
SELECT
    b.idbingo,
    b.titulobingo,
    b.estadobingo,
    COUNT(DISTINCT p.idpartidabingo) AS total_partidas,
    COUNT(c.idcarton) AS total_cartones_actuales,
    COUNT(c.idcarton) FILTER (
        WHERE lower(btrim(c.estadocarton)) = 'vendido'
    ) AS vendidos,
    COALESCE(SUM(c.preciopagado) FILTER (
        WHERE lower(btrim(c.estadocarton)) = 'vendido'
    ), 0) AS recaudacion_actual
FROM bingo AS b
LEFT JOIN partidabingo AS p
  ON p.idbingo = b.idbingo
LEFT JOIN carton AS c
  ON c.idpartida = p.idpartidabingo
GROUP BY b.idbingo, b.titulobingo, b.estadobingo
ORDER BY b.idbingo;

-- 19. Estados reales de partidas y clasificación finalizada/en curso/otra.
SELECT
    p.estadopartida,
    COUNT(*) AS cantidad
FROM partidabingo AS p
GROUP BY p.estadopartida
ORDER BY p.estadopartida;

SELECT
    CASE
        WHEN p.estadopartida = 'Finalizada' THEN 'Finalizadas'
        WHEN p.estadopartida IN ('En curso', 'En Juego') THEN 'En curso'
        ELSE 'Otros estados'
    END AS clasificacion,
    COUNT(*) AS cantidad
FROM partidabingo AS p
GROUP BY clasificacion
ORDER BY clasificacion;

-- 20. Posibles Bingos/partidas de prueba. Es heurística: revisar manualmente.
SELECT
    b.idbingo,
    b.titulobingo,
    b.tipobingo,
    b.estadobingo,
    p.idpartidabingo,
    p.nombreronda,
    p.estadopartida
FROM bingo AS b
LEFT JOIN partidabingo AS p
  ON p.idbingo = b.idbingo
WHERE concat_ws(' ', b.titulobingo, b.tipobingo, p.nombreronda)
      ~* '(prueba|test|demo|ensayo|simulaci[oó]n)'
ORDER BY b.idbingo, p.idpartidabingo;

-- 21. Relación detallada cartón -> partida -> Bingo que sería migrada.
SELECT
    c.idcarton,
    c.codigocarton,
    c.idjugador,
    c.idpartida AS partida_original,
    p.nombreronda,
    p.estadopartida,
    p.idbingo AS bingo_derivado,
    b.titulobingo,
    b.estadobingo,
    c.estadocarton,
    c.indicevictoria,
    c.preciopagado,
    c.fechacompra
FROM carton AS c
LEFT JOIN partidabingo AS p
  ON p.idpartidabingo = c.idpartida
LEFT JOIN bingo AS b
  ON b.idbingo = p.idbingo
ORDER BY p.idbingo NULLS FIRST, c.idcarton;

-- 22. Simulación: asignaciones carton_partida_bingo por Bingo.
-- Cada cartón válido se asignaría a todas las partidas del Bingo derivado.
WITH cartones_derivables AS (
    SELECT
        c.idcarton,
        c.idpartida AS partida_original,
        p.idbingo
    FROM carton AS c
    JOIN partidabingo AS p
      ON p.idpartidabingo = c.idpartida
    JOIN bingo AS b
      ON b.idbingo = p.idbingo
), asignaciones_simuladas AS (
    SELECT
        cd.idcarton,
        cd.partida_original,
        cd.idbingo,
        p.idpartidabingo
    FROM cartones_derivables AS cd
    JOIN partidabingo AS p
      ON p.idbingo = cd.idbingo
), resumen_cartones AS (
    SELECT
        idbingo,
        COUNT(*) AS cartones_maestros
    FROM cartones_derivables
    GROUP BY idbingo
), resumen_partidas AS (
    SELECT
        idbingo,
        COUNT(*) AS partidas
    FROM partidabingo
    GROUP BY idbingo
), resumen_asignaciones AS (
    SELECT
        idbingo,
        COUNT(*) AS asignaciones_totales_simuladas,
        COUNT(*) FILTER (
            WHERE idpartidabingo = partida_original
        ) AS asignaciones_historicas_originales,
        COUNT(*) FILTER (
            WHERE idpartidabingo <> partida_original
        ) AS asignaciones_adicionales
    FROM asignaciones_simuladas
    GROUP BY idbingo
)
SELECT
    b.idbingo,
    b.titulobingo,
    COALESCE(rc.cartones_maestros, 0) AS cartones_maestros,
    COALESCE(rp.partidas, 0) AS partidas,
    COALESCE(ra.asignaciones_totales_simuladas, 0)
        AS asignaciones_totales_simuladas,
    COALESCE(ra.asignaciones_historicas_originales, 0)
        AS asignaciones_historicas_originales,
    COALESCE(ra.asignaciones_adicionales, 0) AS asignaciones_adicionales
FROM bingo AS b
LEFT JOIN resumen_cartones AS rc
  ON rc.idbingo = b.idbingo
LEFT JOIN resumen_partidas AS rp
  ON rp.idbingo = b.idbingo
LEFT JOIN resumen_asignaciones AS ra
  ON ra.idbingo = b.idbingo
ORDER BY b.idbingo;

-- 23. Total global de asignaciones que se crearían.
WITH asignaciones_simuladas AS (
    SELECT
        c.idcarton,
        c.idpartida AS partida_original,
        destino.idpartidabingo AS partida_destino,
        origen.idbingo
    FROM carton AS c
    JOIN partidabingo AS origen
      ON origen.idpartidabingo = c.idpartida
    JOIN bingo AS b
      ON b.idbingo = origen.idbingo
    JOIN partidabingo AS destino
      ON destino.idbingo = origen.idbingo
)
SELECT
    COUNT(*) AS asignaciones_totales_simuladas,
    COUNT(*) FILTER (
        WHERE partida_destino = partida_original
    ) AS asignaciones_historicas_originales,
    COUNT(*) FILTER (
        WHERE partida_destino <> partida_original
    ) AS asignaciones_adicionales,
    COUNT(DISTINCT idcarton) AS cartones_derivables,
    COUNT(DISTINCT idbingo) AS bingos_involucrados
FROM asignaciones_simuladas;

-- 24. La simulación no debe producir pares cartón/partida duplicados.
WITH asignaciones_simuladas AS (
    SELECT
        c.idcarton,
        destino.idpartidabingo AS idpartida
    FROM carton AS c
    JOIN partidabingo AS origen
      ON origen.idpartidabingo = c.idpartida
    JOIN bingo AS b
      ON b.idbingo = origen.idbingo
    JOIN partidabingo AS destino
      ON destino.idbingo = origen.idbingo
)
SELECT
    a.idcarton,
    a.idpartida,
    COUNT(*) AS repeticiones
FROM asignaciones_simuladas AS a
GROUP BY a.idcarton, a.idpartida
HAVING COUNT(*) > 1
ORDER BY a.idcarton, a.idpartida;

-- 25. Posibles cartones maestros duplicados por Bingo, jugador y matriz.
-- No implica duplicación segura: requiere revisión de código y compra.
SELECT
    p.idbingo,
    c.idjugador,
    md5(c.matriznumeros) AS huella_matriz,
    COUNT(*) AS cantidad,
    array_agg(c.idcarton ORDER BY c.idcarton) AS ids_carton,
    array_agg(c.codigocarton ORDER BY c.idcarton) AS codigos
FROM carton AS c
JOIN partidabingo AS p
  ON p.idpartidabingo = c.idpartida
WHERE c.idjugador IS NOT NULL
  AND c.matriznumeros IS NOT NULL
  AND btrim(c.matriznumeros) <> ''
GROUP BY p.idbingo, c.idjugador, md5(c.matriznumeros)
HAVING COUNT(*) > 1
ORDER BY cantidad DESC, p.idbingo, c.idjugador;

-- 26. Ganadores finales que no poseen ningún cartón en la partida.
SELECT
    p.idpartidabingo,
    p.idbingo,
    p.nombreronda,
    p.estadopartida,
    p.idjugadorganador
FROM partidabingo AS p
WHERE p.idjugadorganador IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM carton AS c
      WHERE c.idpartida = p.idpartidabingo
        AND c.idjugador = p.idjugadorganador
  )
ORDER BY p.idpartidabingo;

-- 27. Fechas y resultados históricamente incoherentes.
SELECT
    p.idpartidabingo,
    p.idbingo,
    p.nombreronda,
    p.estadopartida,
    p.horainicio,
    p.horafin,
    p.idjugadorganador,
    p.haydesempate,
    p.bolamayordesempate,
    CASE
        WHEN p.horafin IS NOT NULL AND p.horafin < p.horainicio
            THEN 'Hora final anterior a hora inicial'
        WHEN p.estadopartida = 'Finalizada' AND p.horafin IS NULL
            THEN 'Partida finalizada sin hora final'
        WHEN p.estadopartida <> 'Finalizada' AND p.horafin IS NOT NULL
            THEN 'Partida no finalizada con hora final'
        WHEN p.idjugadorganador IS NOT NULL AND p.estadopartida <> 'Finalizada'
            THEN 'Ganador definido en partida no finalizada'
        WHEN p.haydesempate IS TRUE AND p.idbingadores IS NULL
            THEN 'Desempate sin candidatos registrados'
        ELSE 'Sin clasificar'
    END AS incoherencia
FROM partidabingo AS p
WHERE (p.horafin IS NOT NULL AND p.horafin < p.horainicio)
   OR (p.estadopartida = 'Finalizada' AND p.horafin IS NULL)
   OR (p.estadopartida <> 'Finalizada' AND p.horafin IS NOT NULL)
   OR (p.idjugadorganador IS NOT NULL AND p.estadopartida <> 'Finalizada')
   OR (p.haydesempate IS TRUE AND p.idbingadores IS NULL)
ORDER BY p.idpartidabingo;

-- 28. Cartones asociados a Bingos ya finalizados pero no cerrados.
-- Es una alerta para definir/confirmar la caducidad histórica, no una corrección.
SELECT
    b.idbingo,
    b.titulobingo,
    b.estadobingo,
    c.idcarton,
    c.codigocarton,
    c.estadocarton
FROM carton AS c
JOIN partidabingo AS p
  ON p.idpartidabingo = c.idpartida
JOIN bingo AS b
  ON b.idbingo = p.idbingo
WHERE lower(btrim(b.estadobingo)) IN ('finalizado', 'finalizada', 'cerrado', 'cerrada')
  AND lower(btrim(c.estadocarton)) NOT IN ('cerrado', 'cerrada', 'anulado', 'anulada')
ORDER BY b.idbingo, c.idcarton;

-- 29. Sesiones y posibles referencias huérfanas.
SELECT
    s.idsesion,
    s.idjugador,
    s.idpartida,
    s.estadosesion,
    CASE
        WHEN j.idjugador IS NULL THEN 'Jugador inexistente'
        WHEN p.idpartidabingo IS NULL THEN 'Partida inexistente'
        ELSE 'Sin clasificar'
    END AS incoherencia
FROM sesionjuego AS s
LEFT JOIN jugador AS j
  ON j.idjugador = s.idjugador
LEFT JOIN partidabingo AS p
  ON p.idpartidabingo = s.idpartida
WHERE j.idjugador IS NULL
   OR p.idpartidabingo IS NULL
ORDER BY s.idsesion;

-- 30. Resumen unificado de hallazgos para decidir si la migración es segura.
WITH hallazgos AS (
    SELECT 'CARTON_SIN_PARTIDA' AS tipo, COUNT(*) AS cantidad
    FROM carton
    WHERE idpartida IS NULL

    UNION ALL

    SELECT 'CARTON_SIN_BINGO_DERIVABLE', COUNT(*)
    FROM carton AS c
    LEFT JOIN partidabingo AS p
      ON p.idpartidabingo = c.idpartida
    LEFT JOIN bingo AS b
      ON b.idbingo = p.idbingo
    WHERE c.idpartida IS NULL
       OR p.idpartidabingo IS NULL
       OR b.idbingo IS NULL

    UNION ALL

    SELECT 'CARTON_SIN_JUGADOR', COUNT(*)
    FROM carton
    WHERE idjugador IS NULL

    UNION ALL

    SELECT 'CARTON_SIN_MATRIZ', COUNT(*)
    FROM carton
    WHERE matriznumeros IS NULL OR btrim(matriznumeros) = ''

    UNION ALL

    SELECT 'CODIGO_DUPLICADO_EXACTO', COALESCE(SUM(cantidad - 1), 0)
    FROM (
        SELECT COUNT(*) AS cantidad
        FROM carton
        GROUP BY codigocarton
        HAVING COUNT(*) > 1
    ) AS duplicados

    UNION ALL

    SELECT 'CODIGO_DUPLICADO_NORMALIZADO', COALESCE(SUM(cantidad - 1), 0)
    FROM (
        SELECT COUNT(*) AS cantidad
        FROM carton
        GROUP BY upper(btrim(codigocarton))
        HAVING COUNT(*) > 1
    ) AS duplicados

    UNION ALL

    SELECT 'ESTADO_CARTON_NO_ESPERADO', COUNT(*)
    FROM carton
    WHERE estadocarton IS NULL
       OR btrim(estadocarton) = ''
       OR estadocarton NOT IN ('Disponible', 'Vendido', 'Cerrado')

    UNION ALL

    SELECT 'PRECIO_NEGATIVO', COUNT(*)
    FROM carton
    WHERE preciopagado < 0

    UNION ALL

    SELECT 'VENDIDO_SIN_PRECIO_POSITIVO', COUNT(*)
    FROM carton
    WHERE lower(btrim(estadocarton)) = 'vendido'
      AND (preciopagado IS NULL OR preciopagado <= 0)

    UNION ALL

    SELECT 'INDICE_VICTORIA_NEGATIVO', COUNT(*)
    FROM carton
    WHERE indicevictoria < 0

    UNION ALL

    SELECT 'PARTIDA_SIN_BINGO', COUNT(*)
    FROM partidabingo AS p
    LEFT JOIN bingo AS b
      ON b.idbingo = p.idbingo
    WHERE b.idbingo IS NULL

    UNION ALL

    SELECT 'GANADOR_SIN_CARTON_EN_PARTIDA', COUNT(*)
    FROM partidabingo AS p
    WHERE p.idjugadorganador IS NOT NULL
      AND NOT EXISTS (
          SELECT 1
          FROM carton AS c
          WHERE c.idpartida = p.idpartidabingo
            AND c.idjugador = p.idjugadorganador
      )
)
SELECT tipo, cantidad
FROM hallazgos
ORDER BY tipo;
