-- =============================================================================
-- PROPUESTA / NO EJECUTAR
-- ETAPA 9.5A - MIGRACION DE CARTONES HIBRIDOS
-- =============================================================================
-- Este archivo NO fue ejecutado. Contiene DDL y DML destructivos si se usa sin
-- el procedimiento, respaldo, ventana y aprobaciones documentadas.
--
-- Bloqueo intencional para psql. Para una etapa futura autorizada se deberá
-- copiar y versionar el archivo, resolver todos los bloqueos, ensayarlo sobre
-- una restauración aislada y retirar explícitamente estas dos líneas.
\echo 'PROPUESTA / NO EJECUTAR: migracion bloqueada intencionalmente.'
\quit

-- A partir de aquí todo es una propuesta técnica no ejecutada.
-- Requiere PostgreSQL 16 y parte del esquema físico confirmado el 2026-06-30.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '15min';

-- La ventana futura debe impedir escrituras concurrentes. Los bloqueos se
-- solicitan antes de validar para que el conjunto diagnosticado sea estable.
LOCK TABLE bingo, partidabingo, carton, jugador IN SHARE ROW EXCLUSIVE MODE;

-- Precondiciones estructurales y de integridad. Cualquier excepción revierte
-- la transacción completa.
DO $precondiciones$
BEGIN
    IF current_database() <> 'bingo' THEN
        RAISE EXCEPTION 'Base incorrecta: se esperaba bingo y se obtuvo %',
            current_database();
    END IF;

    IF to_regclass('public.carton_partida_bingo') IS NOT NULL THEN
        RAISE EXCEPTION
            'carton_partida_bingo ya existe; detener y rediagnosticar';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton AS c
        LEFT JOIN partidabingo AS p
          ON p.idpartidabingo = c.idpartida
        LEFT JOIN bingo AS b
          ON b.idbingo = p.idbingo
        WHERE c.idpartida IS NULL
           OR p.idpartidabingo IS NULL
           OR b.idbingo IS NULL
    ) THEN
        RAISE EXCEPTION 'Existen cartones sin Bingo derivable';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton
        WHERE matriznumeros IS NULL OR btrim(matriznumeros) = ''
    ) THEN
        RAISE EXCEPTION 'Existen cartones sin matriz';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton
        GROUP BY upper(btrim(codigocarton))
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Existen codigos de carton duplicados al normalizar';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton
        WHERE preciopagado < 0
           OR (
               lower(btrim(estadocarton)) = 'vendido'
               AND (idjugador IS NULL OR preciopagado IS NULL OR preciopagado <= 0)
           )
    ) THEN
        RAISE EXCEPTION 'Existen cartones vendidos incompletos o precios invalidos';
    END IF;

    -- Bloqueos reales encontrados el 2026-06-30. No retirar estas validaciones
    -- sin una decisión documentada para cada fila afectada.
    IF EXISTS (
        SELECT 1
        FROM carton AS c
        JOIN partidabingo AS p
          ON p.idpartidabingo = c.idpartida
        JOIN bingo AS b
          ON b.idbingo = p.idbingo
        WHERE c.preciopagado IS NOT NULL
          AND c.preciopagado <> b.preciocarton
    ) THEN
        RAISE EXCEPTION
            'Hay precios pagados distintos al precio de lista; aprobar su tratamiento';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton
        WHERE indicevictoria IS NOT NULL
          AND lower(btrim(estadocarton)) <> 'vendido'
    ) THEN
        RAISE EXCEPTION
            'Hay indices de victoria en cartones no vendidos; aprobar su semantica';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM partidabingo
        WHERE horafin IS NOT NULL AND horafin < horainicio
    ) THEN
        RAISE EXCEPTION 'Hay partidas con hora final anterior a hora inicial';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton AS c
        JOIN partidabingo AS p
          ON p.idpartidabingo = c.idpartida
        JOIN bingo AS b
          ON b.idbingo = p.idbingo
        WHERE concat_ws(' ', b.titulobingo, b.tipobingo, p.nombreronda)
              ~* '(prueba|test|demo|ensayo|simulaci[oó]n)'
    ) THEN
        RAISE EXCEPTION
            'Hay cartones ligados a datos de prueba; aprobar inclusion o depuracion';
    END IF;
END
$precondiciones$;

-- Fase expansiva: la relación histórica carton.idpartida y el campo
-- carton.indicevictoria se conservan para compatibilidad y rollback.
ALTER TABLE carton
    ADD COLUMN idbingo integer;

UPDATE carton AS c
SET idbingo = p.idbingo
FROM partidabingo AS p
WHERE p.idpartidabingo = c.idpartida;

DO $poblacion_bingo$
BEGIN
    IF EXISTS (SELECT 1 FROM carton WHERE idbingo IS NULL) THEN
        RAISE EXCEPTION 'No se pudo poblar carton.idbingo para todas las filas';
    END IF;
END
$poblacion_bingo$;

ALTER TABLE carton
    ALTER COLUMN idbingo SET NOT NULL,
    ADD CONSTRAINT fk_carton_bingo
        FOREIGN KEY (idbingo) REFERENCES bingo(idbingo),
    ADD CONSTRAINT uq_carton_idcarton_idbingo
        UNIQUE (idcarton, idbingo);

-- Esta clave auxiliar permite una FK compuesta desde la tabla intermedia y
-- obliga a que cartón y partida pertenezcan al mismo Bingo sin usar triggers.
ALTER TABLE partidabingo
    ADD CONSTRAINT uq_partidabingo_idpartida_idbingo
        UNIQUE (idpartidabingo, idbingo);

CREATE INDEX idx_carton_idbingo
    ON carton (idbingo);

CREATE INDEX idx_carton_idjugador
    ON carton (idjugador);

CREATE INDEX idx_partidabingo_idbingo
    ON partidabingo (idbingo);

-- La PK nueva usa IDENTITY de forma deliberada. Las cinco tablas existentes
-- tienen PK integer sin secuencia; antes del despliegue la aplicación deberá
-- mapear este campo como autogenerado o aprobar otra estrategia.
CREATE TABLE carton_partida_bingo (
    idcartonpartidabingo integer GENERATED BY DEFAULT AS IDENTITY,
    idcarton integer NOT NULL,
    idpartida integer NOT NULL,
    idbingo integer NOT NULL,
    estado_participacion varchar(20) NOT NULL,
    indicevictoria integer,
    es_asignacion_original boolean NOT NULL DEFAULT false,
    origen_asignacion varchar(24) NOT NULL,
    motivoestado varchar(255),
    fechacreacion timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fechavalidacion timestamp without time zone,
    CONSTRAINT carton_partida_bingo_pkey
        PRIMARY KEY (idcartonpartidabingo),
    CONSTRAINT uq_cpb_carton_partida
        UNIQUE (idcarton, idpartida),
    CONSTRAINT fk_cpb_carton_bingo
        FOREIGN KEY (idcarton, idbingo)
        REFERENCES carton (idcarton, idbingo),
    CONSTRAINT fk_cpb_partida_bingo
        FOREIGN KEY (idpartida, idbingo)
        REFERENCES partidabingo (idpartidabingo, idbingo),
    CONSTRAINT chk_cpb_estado
        CHECK (estado_participacion IN (
            'Pendiente', 'En juego', 'Cerrado', 'Ganador', 'Anulado',
            'No participo'
        )),
    CONSTRAINT chk_cpb_indice
        CHECK (indicevictoria IS NULL OR indicevictoria >= 0),
    CONSTRAINT chk_cpb_origen
        CHECK (origen_asignacion IN (
            'Historica original', 'Historica inferida', 'Aplicacion'
        )),
    CONSTRAINT chk_cpb_origen_original
        CHECK (
            es_asignacion_original
            = (origen_asignacion = 'Historica original')
        )
);

CREATE INDEX idx_cpb_idpartida
    ON carton_partida_bingo (idpartida);

CREATE INDEX idx_cpb_idbingo
    ON carton_partida_bingo (idbingo);

CREATE INDEX idx_cpb_partida_estado
    ON carton_partida_bingo (idpartida, estado_participacion);

-- Asignación histórica original: conserva la única relación demostrable y el
-- indicevictoria existente. No infiere automáticamente el cartón ganador a
-- partir de idjugadorganador.
INSERT INTO carton_partida_bingo (
    idcarton,
    idpartida,
    idbingo,
    estado_participacion,
    indicevictoria,
    es_asignacion_original,
    origen_asignacion,
    motivoestado,
    fechacreacion,
    fechavalidacion
)
SELECT
    c.idcarton,
    c.idpartida,
    c.idbingo,
    CASE
        WHEN p.estadopartida = 'Finalizada' THEN 'Cerrado'
        WHEN p.estadopartida IN ('En curso', 'Desempate') THEN 'En juego'
        WHEN p.estadopartida = 'Cancelada' THEN 'Anulado'
        ELSE 'Pendiente'
    END,
    c.indicevictoria,
    true,
    'Historica original',
    'Relacion original conservada desde carton.idpartida',
    COALESCE(c.fechacompra, p.horainicio),
    CASE WHEN p.estadopartida = 'Finalizada' THEN p.horafin END
FROM carton AS c
JOIN partidabingo AS p
  ON p.idpartidabingo = c.idpartida
 AND p.idbingo = c.idbingo;

-- Asignaciones históricas inferidas para las demás rondas del mismo Bingo.
-- "No participo" evita afirmar participación cuando el cartón fue comprado
-- después de terminar la ronda destino. La regla y el vocabulario requieren
-- aprobación funcional antes de retirar el bloqueo inicial del archivo.
INSERT INTO carton_partida_bingo (
    idcarton,
    idpartida,
    idbingo,
    estado_participacion,
    indicevictoria,
    es_asignacion_original,
    origen_asignacion,
    motivoestado,
    fechacreacion,
    fechavalidacion
)
SELECT
    c.idcarton,
    p.idpartidabingo,
    c.idbingo,
    CASE
        WHEN p.estadopartida = 'Finalizada'
         AND c.fechacompra IS NOT NULL
         AND c.fechacompra > COALESCE(p.horafin, p.horainicio)
            THEN 'No participo'
        WHEN p.estadopartida = 'Finalizada' THEN 'Cerrado'
        WHEN p.estadopartida IN ('En curso', 'Desempate') THEN 'En juego'
        WHEN p.estadopartida = 'Cancelada' THEN 'Anulado'
        ELSE 'Pendiente'
    END,
    NULL,
    false,
    'Historica inferida',
    'Asignacion generada por pertenencia al mismo Bingo',
    COALESCE(c.fechacompra, p.horainicio),
    CASE WHEN p.estadopartida = 'Finalizada' THEN p.horafin END
FROM carton AS c
JOIN partidabingo AS p
  ON p.idbingo = c.idbingo
WHERE p.idpartidabingo <> c.idpartida;

-- Validaciones dentro de la transacción.
DO $validacion$
DECLARE
    v_cartones bigint;
    v_originales bigint;
    v_asignaciones bigint;
    v_esperadas bigint;
BEGIN
    SELECT count(*) INTO v_cartones FROM carton;

    SELECT count(*) FILTER (WHERE es_asignacion_original), count(*)
    INTO v_originales, v_asignaciones
    FROM carton_partida_bingo;

    SELECT COALESCE(sum(cartones * partidas), 0)
    INTO v_esperadas
    FROM (
        SELECT
            b.idbingo,
            count(DISTINCT c.idcarton) AS cartones,
            count(DISTINCT p.idpartidabingo) AS partidas
        FROM bingo AS b
        LEFT JOIN carton AS c ON c.idbingo = b.idbingo
        LEFT JOIN partidabingo AS p ON p.idbingo = b.idbingo
        GROUP BY b.idbingo
    ) AS por_bingo;

    IF v_originales <> v_cartones THEN
        RAISE EXCEPTION
            'Originales esperadas %, obtenidas %', v_cartones, v_originales;
    END IF;

    IF v_asignaciones <> v_esperadas THEN
        RAISE EXCEPTION
            'Asignaciones esperadas %, obtenidas %', v_esperadas, v_asignaciones;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton_partida_bingo AS cpb
        JOIN carton AS c ON c.idcarton = cpb.idcarton
        JOIN partidabingo AS p ON p.idpartidabingo = cpb.idpartida
        WHERE cpb.idbingo <> c.idbingo OR cpb.idbingo <> p.idbingo
    ) THEN
        RAISE EXCEPTION 'Se detectaron asignaciones entre Bingos distintos';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton_partida_bingo
        WHERE NOT es_asignacion_original AND indicevictoria IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Se replicaron indices a asignaciones inferidas';
    END IF;
END
$validacion$;

-- No retirar carton.idpartida ni carton.indicevictoria en esta fase.
COMMIT;
