-- =============================================================================
-- PROPUESTA / NO EJECUTAR
-- ETAPA 9.5A - ROLLBACK DE LA FASE EXPANSIVA DE CARTONES HIBRIDOS
-- =============================================================================
-- Este archivo NO fue ejecutado. Solo es aplicable antes de aceptar escrituras
-- de la aplicación con el modelo híbrido y después de verificar un respaldo.
-- No reemplaza una restauración completa.
--
-- Bloqueo intencional para psql. Una etapa futura autorizada deberá copiar y
-- versionar el archivo, ensayarlo y retirar explícitamente estas dos líneas.
\echo 'PROPUESTA / NO EJECUTAR: rollback bloqueado intencionalmente.'
\quit

-- A partir de aquí todo es una propuesta técnica no ejecutada.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '15min';

LOCK TABLE bingo, partidabingo, carton, carton_partida_bingo
    IN ACCESS EXCLUSIVE MODE;

-- Este rollback conserva carton.idpartida e indicevictoria, que la migración
-- expansiva no elimina. Se bloquea si ya existen filas creadas por la nueva
-- aplicación o si la referencia histórica dejó de ser suficiente.
DO $precondiciones_rollback$
BEGIN
    IF to_regclass('public.carton_partida_bingo') IS NULL THEN
        RAISE EXCEPTION
            'carton_partida_bingo no existe; no aplicar este rollback';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'carton'
          AND column_name = 'idbingo'
    ) THEN
        RAISE EXCEPTION 'carton.idbingo no existe; estado no reconocido';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton_partida_bingo
        WHERE origen_asignacion = 'Aplicacion'
    ) THEN
        RAISE EXCEPTION
            'Existen asignaciones nuevas de la aplicacion; preservar antes de revertir';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton AS c
        LEFT JOIN partidabingo AS p
          ON p.idpartidabingo = c.idpartida
        WHERE c.idpartida IS NULL
           OR p.idpartidabingo IS NULL
           OR p.idbingo <> c.idbingo
    ) THEN
        RAISE EXCEPTION
            'carton.idpartida ya no permite reconstruir el estado anterior';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton AS c
        LEFT JOIN carton_partida_bingo AS cpb
          ON cpb.idcarton = c.idcarton
         AND cpb.idpartida = c.idpartida
         AND cpb.es_asignacion_original
        WHERE cpb.idcartonpartidabingo IS NULL
    ) THEN
        RAISE EXCEPTION 'Falta una asignacion original para uno o mas cartones';
    END IF;
END
$precondiciones_rollback$;

-- La tabla intermedia se elimina primero para retirar sus FKs compuestas.
DROP TABLE carton_partida_bingo;

DROP INDEX idx_carton_idbingo;
DROP INDEX idx_carton_idjugador;
DROP INDEX idx_partidabingo_idbingo;

ALTER TABLE carton
    DROP CONSTRAINT fk_carton_bingo,
    DROP CONSTRAINT uq_carton_idcarton_idbingo,
    DROP COLUMN idbingo;

ALTER TABLE partidabingo
    DROP CONSTRAINT uq_partidabingo_idpartida_idbingo;

-- Verificación de catálogo dentro de la misma transacción.
DO $validacion_rollback$
BEGIN
    IF to_regclass('public.carton_partida_bingo') IS NOT NULL THEN
        RAISE EXCEPTION 'No se elimino carton_partida_bingo';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'carton'
          AND column_name = 'idbingo'
    ) THEN
        RAISE EXCEPTION 'No se elimino carton.idbingo';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'carton'
          AND column_name IN ('idpartida', 'indicevictoria')
        GROUP BY table_schema, table_name
        HAVING COUNT(*) = 2
    ) THEN
        RAISE EXCEPTION 'No se conservaron las columnas historicas requeridas';
    END IF;
END
$validacion_rollback$;

COMMIT;

-- Después de un rollback futuro autorizado se debe repetir
-- 00_PREFLIGHT_CARTONES_HIBRIDOS.sql en modo solo lectura y comparar contra el
-- corte previo. Si hubo escrituras híbridas, detenerse y usar el plan de
-- reversión específico o restaurar el respaldo; no forzar este archivo.
