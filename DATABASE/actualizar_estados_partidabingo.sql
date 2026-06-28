/*
Correccion de estados reales para public.partidabingo.estadopartida.

IMPORTANTE:
- Revisar antes de ejecutar.
- Ejecutar manualmente por el administrador de base de datos.
- Este script no crea tablas, no elimina registros y no modifica columnas.
- Cambia la restriccion CHECK de valores permitidos y actualiza valores legacy.
*/

/* -------------------------------------------------------------------------
1. Consultas previas de respaldo / validacion

Ejecutar y guardar el resultado antes de continuar.
Si se usa psql, se recomienda tambien exportar:

\copy (
    SELECT idpartidabingo, estadopartida
    FROM partidabingo
    ORDER BY idpartidabingo
) TO 'backup_partidabingo_estadopartida_antes.csv' CSV HEADER;
------------------------------------------------------------------------- */

SELECT conname, pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'partidabingo'::regclass
  AND conname = 'chk_partidabingo_estadopartida';

SELECT estadopartida, COUNT(*) AS cantidad
FROM partidabingo
GROUP BY estadopartida
ORDER BY estadopartida;

SELECT idpartidabingo, estadopartida
FROM partidabingo
WHERE estadopartida NOT IN ('En Juego', 'Verificando', 'Desempate', 'Finalizada')
   OR estadopartida IS NULL
ORDER BY idpartidabingo;

/* -------------------------------------------------------------------------
2. Cambio transaccional

Si cualquier comprobacion no es satisfactoria, ejecutar ROLLBACK en lugar de
COMMIT.
------------------------------------------------------------------------- */

BEGIN;

LOCK TABLE partidabingo IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE partidabingo
    DROP CONSTRAINT chk_partidabingo_estadopartida;

UPDATE partidabingo
SET estadopartida = CASE estadopartida
    WHEN 'En Juego' THEN 'En curso'
    WHEN 'Verificando' THEN 'En espera'
    ELSE estadopartida
END
WHERE estadopartida IN ('En Juego', 'Verificando');

ALTER TABLE partidabingo
    ADD CONSTRAINT chk_partidabingo_estadopartida
    CHECK (
        estadopartida IN (
            'Programada',
            'En espera',
            'En curso',
            'Pausada',
            'Desempate',
            'Finalizada',
            'Cancelada'
        )
    );

/* -------------------------------------------------------------------------
3. Comprobaciones finales dentro de la transaccion
------------------------------------------------------------------------- */

SELECT conname, pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'partidabingo'::regclass
  AND conname = 'chk_partidabingo_estadopartida';

SELECT estadopartida, COUNT(*) AS cantidad
FROM partidabingo
GROUP BY estadopartida
ORDER BY estadopartida;

SELECT idpartidabingo, estadopartida
FROM partidabingo
WHERE estadopartida NOT IN (
    'Programada',
    'En espera',
    'En curso',
    'Pausada',
    'Desempate',
    'Finalizada',
    'Cancelada'
)
ORDER BY idpartidabingo;

COMMIT;

/* -------------------------------------------------------------------------
4. Reversion documentada

Antes del COMMIT:
    ROLLBACK;

Despues del COMMIT, la reversion al vocabulario antiguo pierde informacion.
Solo usar si se acepta esa perdida y despues de respaldar los datos actuales.

BEGIN;

LOCK TABLE partidabingo IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE partidabingo
    DROP CONSTRAINT chk_partidabingo_estadopartida;

UPDATE partidabingo
SET estadopartida = CASE estadopartida
    WHEN 'En curso' THEN 'En Juego'
    WHEN 'En espera' THEN 'Verificando'
    WHEN 'Programada' THEN 'Verificando'
    WHEN 'Pausada' THEN 'En Juego'
    WHEN 'Cancelada' THEN 'Finalizada'
    ELSE estadopartida
END
WHERE estadopartida IN ('En curso', 'En espera', 'Programada', 'Pausada', 'Cancelada');

ALTER TABLE partidabingo
    ADD CONSTRAINT chk_partidabingo_estadopartida
    CHECK (
        estadopartida IN ('En Juego', 'Verificando', 'Desempate', 'Finalizada')
    );

COMMIT;
------------------------------------------------------------------------- */
