-- =============================================================================
-- PROPUESTA / NO EJECUTAR
-- ETAPA 9.5B - MIGRACION HISTORICA DE CARTONES HIBRIDOS
-- =============================================================================
-- Este archivo NO fue ejecutado. Contiene DDL y DML y solo puede habilitarse
-- en una etapa posterior, con respaldo restaurado, ventana y autorizacion.
--
-- Bloqueo intencional para psql. La ejecucion futura exige copiar y versionar
-- el archivo, ensayarlo y retirar explicitamente estas dos lineas.
\echo 'PROPUESTA / NO EJECUTAR: migracion bloqueada intencionalmente.'
\quit

-- A partir de aqui todo es una propuesta tecnica no ejecutada.
-- Parte del esquema fisico confirmado en PostgreSQL 16.14 el 2026-06-30.
--
-- Regla historica: cada carton existente conserva exclusivamente la partida
-- registrada en carton.idpartida. No se inventan participaciones para otras
-- rondas del Bingo. La aplicacion Django adaptada sera responsable de crear
-- una asignacion por cada ronda solo para cartones nuevos.

BEGIN;

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '15min';

-- La ventana futura debe impedir escrituras concurrentes. Los bloqueos se
-- solicitan antes de validar para mantener estable el conjunto diagnosticado.
LOCK TABLE bingo, partidabingo, carton, jugador, sesionjuego
    IN SHARE ROW EXCLUSIVE MODE;

-- Bloqueos reales. Las advertencias historicas de precio de lista, datos de
-- prueba, indice default 0 y fechas incoherentes no forman parte de este bloque.
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
    ) THEN
        RAISE EXCEPTION 'Existen cartones con precio negativo';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton
        WHERE lower(btrim(estadocarton)) = 'vendido'
          AND idjugador IS NULL
    ) THEN
        RAISE EXCEPTION 'Existen cartones vendidos sin jugador';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton
        WHERE lower(btrim(estadocarton)) = 'vendido'
          AND (preciopagado IS NULL OR preciopagado <= 0)
    ) THEN
        RAISE EXCEPTION 'Existen cartones vendidos sin precio positivo';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton AS c
        LEFT JOIN jugador AS j ON j.idjugador = c.idjugador
        WHERE c.idjugador IS NOT NULL AND j.idjugador IS NULL
    ) THEN
        RAISE EXCEPTION 'Existen referencias huerfanas de carton a jugador';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM partidabingo AS p
        LEFT JOIN bingo AS b ON b.idbingo = p.idbingo
        WHERE b.idbingo IS NULL
    ) THEN
        RAISE EXCEPTION 'Existen referencias huerfanas de partida a Bingo';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM sesionjuego AS s
        LEFT JOIN jugador AS j ON j.idjugador = s.idjugador
        LEFT JOIN partidabingo AS p ON p.idpartidabingo = s.idpartida
        WHERE j.idjugador IS NULL OR p.idpartidabingo IS NULL
    ) THEN
        RAISE EXCEPTION 'Existen referencias huerfanas en sesionjuego';
    END IF;
END
$precondiciones$;

-- Fase expansiva. Solo se agrega y puebla carton.idbingo; no se modifican
-- precios, codigos, matrices, propietarios, estados, idpartida ni
-- indicevictoria de los 12 cartones historicos.
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

-- La clave auxiliar permite la FK compuesta de la tabla intermedia. Junto con
-- idbingo evita relacionar un carton con una partida de otro Bingo.
ALTER TABLE partidabingo
    ADD CONSTRAINT uq_partidabingo_idpartida_idbingo
        UNIQUE (idpartidabingo, idbingo);

CREATE INDEX idx_carton_idbingo
    ON carton (idbingo);

CREATE INDEX idx_carton_idjugador
    ON carton (idjugador);

CREATE INDEX idx_partidabingo_idbingo
    ON partidabingo (idbingo);

-- Las tablas antiguas conservan sus PK integer manuales. La tabla nueva puede
-- usar IDENTITY sin alterar esas PK, evita calcular MAX(id)+1 y exige que el
-- futuro modelo Django managed=False mapee esta PK como autogenerada.
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
            'Pendiente', 'En juego', 'Cerrado', 'Ganador', 'Anulado'
        )),
    CONSTRAINT chk_cpb_indice
        CHECK (indicevictoria IS NULL OR indicevictoria > 0),
    CONSTRAINT chk_cpb_origen
        CHECK (origen_asignacion IN ('Historica original', 'Aplicacion')),
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

-- Una y solo una asignacion por carton historico: su partida original.
-- No se usa idjugadorganador, no se consultan fechas para deducir participacion
-- y el default historico indicevictoria=0 se convierte en NULL en la nueva tabla.
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
    CASE
        WHEN c.indicevictoria > 0 THEN c.indicevictoria
        ELSE NULL
    END,
    true,
    'Historica original',
    'Relacion original conservada desde carton.idpartida',
    COALESCE(c.fechacompra, CURRENT_TIMESTAMP),
    NULL
FROM carton AS c
JOIN partidabingo AS p
  ON p.idpartidabingo = c.idpartida
 AND p.idbingo = c.idbingo;

-- Validaciones dentro de la transaccion. Con el corte confirmado deben resultar
-- 12 cartones, 12 asignaciones originales y 0 asignaciones no originales.
DO $validacion$
DECLARE
    v_cartones bigint;
    v_originales bigint;
    v_no_originales bigint;
    v_asignaciones bigint;
BEGIN
    SELECT count(*) INTO v_cartones FROM carton;

    SELECT
        count(*),
        count(*) FILTER (WHERE es_asignacion_original),
        count(*) FILTER (WHERE NOT es_asignacion_original)
    INTO v_asignaciones, v_originales, v_no_originales
    FROM carton_partida_bingo;

    IF v_asignaciones <> v_cartones
       OR v_originales <> v_cartones
       OR v_no_originales <> 0 THEN
        RAISE EXCEPTION
            'Conteo historico invalido: cartones %, filas %, originales %, no originales %',
            v_cartones, v_asignaciones, v_originales, v_no_originales;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton_partida_bingo AS cpb
        JOIN carton AS c ON c.idcarton = cpb.idcarton
        WHERE cpb.idpartida <> c.idpartida
           OR NOT cpb.es_asignacion_original
           OR cpb.origen_asignacion <> 'Historica original'
    ) THEN
        RAISE EXCEPTION
            'Una asignacion historica no coincide con carton.idpartida';
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
        FROM carton_partida_bingo AS cpb
        JOIN carton AS c ON c.idcarton = cpb.idcarton
        WHERE cpb.indicevictoria IS DISTINCT FROM
              CASE
                  WHEN c.indicevictoria > 0 THEN c.indicevictoria
                  ELSE NULL
              END
    ) THEN
        RAISE EXCEPTION 'No se aplico correctamente el filtro de indicevictoria';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM carton_partida_bingo
        WHERE estado_participacion = 'Ganador'
    ) THEN
        RAISE EXCEPTION 'La migracion historica infirio un ganador';
    END IF;
END
$validacion$;

-- No retirar carton.idpartida ni carton.indicevictoria en esta fase.
-- No crear aqui filas para otras partidas. Las asignaciones de cartones nuevos
-- pertenecen a la futura aplicacion Django adaptada.
COMMIT;
