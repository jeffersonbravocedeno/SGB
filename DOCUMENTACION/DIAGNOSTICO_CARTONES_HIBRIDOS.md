# Diagnostico tecnico: cartones hibridos por Bingo

Este documento es solo de analisis y propuesta. No implementa cambios en codigo,
modelos, migraciones, PostgreSQL, datos, vistas, templates, WebSockets ni tests.

## 1. Estado actual

### Modelo actual de Carton

El modelo actual esta en `apps/bingos/models.py` y representa la tabla fisica
`carton` con `managed = False`.

Campos relevantes:

- `idcarton`: PK entera.
- `idjugador`: FK nullable a `jugador`.
- `idpartida`: FK nullable a `partidabingo`.
- `codigocarton`: codigo unico global.
- `matriznumeros`: matriz B-I-N-G-O serializada.
- `indicevictoria`: entero opcional.
- `preciopagado`: valor monetario opcional.
- `fechacompra`: fecha de compra opcional.
- `estadocarton`: estado general del carton.

La relacion fisica actual es:

```text
Carton -> Partidabingo
```

Esto significa que un carton pertenece a una sola partida o ronda.

### Como se crean hoy los cartones

La creacion principal esta en `apps/bingos/services.py`:

- `generar_codigo_carton()` recibe `idpartida` y genera codigos con prefijo
  `P<idpartida>-C-`.
- `crear_y_asignar_carton()` valida la partida, genera matriz, asigna
  `Carton.idpartida = partida_bloqueada`, asigna `idjugador`, `preciopagado`,
  `fechacompra`, `estadocarton = "Vendido"` y guarda el carton.

La vista administrativa `partida_carton_nuevo()` en `apps/bingos/views.py`
recibe `idpartidabingo` y llama a `crear_y_asignar_carton(partida=partida, ...)`.

### Como se valida hoy un ganador

La validacion esta acoplada a partida:

- `_carton_pertenece_a_partida(carton, partida)` valida
  `carton.idpartida_id == partida.pk`.
- `evaluar_carton_en_partida()` rechaza el carton si no pertenece a la partida.
- `buscar_cartones_ganadores()` consulta `Carton.objects.filter(idpartida=partida)`.
- `validar_carton_ganador()` bloquea todos los cartones de esa partida con
  `Carton.objects.select_for_update(...).filter(idpartida=partida_bloqueada)`.

El ganador y el desempate se guardan en `partidabingo`:

- `idjugadorganador`;
- `estadopartida`;
- `haydesempate`;
- `idbingadores`;
- `bolamayordesempate`.

El JSON de `idbingadores` contiene candidatos y codigos de cartones para el
desempate, pero no existe una tabla de participacion por ronda.

### Como funcionan hoy Mis cartones

`mis_cartones()` en `apps/bingos/views.py` filtra:

```python
Carton.objects.filter(idjugador=jugador).select_related(
    "idpartida",
    "idpartida__idbingo",
)
```

Cada carton mostrado tiene una sola partida asociada. El detalle privado
`mi_carton_detalle()` tambien obtiene el carton por `codigocarton` e
`idjugador`, luego usa `carton.idpartida` para calcular progreso, ultima bola y
estado de visualizacion.

### Como se generan los reportes actuales

`apps/bingos/reportes.py` trabaja con cartones por partida:

- PDF de partida: recibe la partida y los cartones filtrados por
  `Carton.idpartida`.
- Excel de cartones de partida: lista los cartones de una partida y usa
  `preciopagado`, `indicevictoria` y datos de la ronda.
- Excel resumen de Bingo: agrupa cartones por `carton.idpartida_id`.

Las vistas de descarga en `apps/bingos/views.py` consultan:

- `Carton.objects.filter(idpartida=partida)`;
- `Carton.objects.filter(idpartida__in=partidas)`.

### Partes acopladas directamente a Carton.idpartida

| Archivo | Clase, funcion o vista | Uso actual | Impacto |
|---|---|---|---|
| `apps/bingos/models.py` | `Carton.idpartida` | FK directa a `Partidabingo` | Alto |
| `apps/bingos/forms.py` | `CartonForm` | expone `idpartida` en el formulario general | Medio |
| `apps/bingos/services.py` | `generar_codigo_carton` | codigo prefijado por partida | Alto |
| `apps/bingos/services.py` | `crear_y_asignar_carton` | crea un carton para una sola partida | Alto |
| `apps/bingos/services.py` | `_carton_pertenece_a_partida` | valida contra `carton.idpartida_id` | Alto |
| `apps/bingos/services.py` | `buscar_cartones_ganadores` | filtra cartones por partida | Alto |
| `apps/bingos/services.py` | `preparar_datos_carton_jugador` | obtiene la partida desde `carton.idpartida` | Alto |
| `apps/bingos/services.py` | `validar_carton_ganador` | bloquea y valida cartones de una partida | Alto |
| `apps/bingos/views.py` | `carton_publico` | muestra un carton asociado a una partida | Alto |
| `apps/bingos/views.py` | `mis_cartones` | lista cartones del jugador con una partida | Alto |
| `apps/bingos/views.py` | `mi_carton_detalle` | detalle privado de un carton y su partida | Alto |
| `apps/bingos/views.py` | `bingo_detalle` | lista cartones usando `idpartida__idbingo` | Medio |
| `apps/bingos/views.py` | `bingo_resumen_excel` | obtiene cartones por partidas del Bingo | Medio |
| `apps/bingos/views.py` | `partida_detalle` | lista cartones por `idpartida=partida` | Alto |
| `apps/bingos/views.py` | `partida_reporte_pdf` | reporte por `idpartida=partida` | Medio |
| `apps/bingos/views.py` | `partida_cartones_excel` | exporta cartones de una partida | Medio |
| `apps/bingos/views.py` | `partida_carton_nuevo` | genera carton desde una partida | Alto |
| `apps/bingos/views.py` | `partida_carton_editar` | edita carton perteneciente a partida | Alto |
| `apps/bingos/views.py` | `consola_operador` | muestra validacion de cartones por partida | Alto |
| `apps/bingos/views.py` | `validar_carton` | obtiene carton por `idcarton` e `idpartida` | Alto |
| `apps/bingos/views.py` | `cartones_lista` | selecciona `idpartida` e `idpartida__idbingo` | Medio |
| `apps/bingos/reportes.py` | `generar_excel_resumen_bingo` | agrupa por `idpartida_id` | Medio |
| `apps/jugadores/views.py` | `_detalle_context` | muestra ultimos cartones del jugador con partida | Medio |
| `templates/bingos/*.html` | varias plantillas | muestran partida, ronda y enlaces por partida | Medio |
| `apps/bingos/tests.py` | pruebas de servicios/vistas/reportes | fixtures y mocks con `Carton.idpartida` | Alto |

## 2. Diferencia entre estado actual y logica esperada

Estado actual:

```text
Bingo -> muchas PartidaBingo
Carton -> una PartidaBingo
```

Estado esperado:

```text
Bingo -> muchas PartidaBingo
Carton maestro -> un Bingo
CartonPartidaBingo -> Carton maestro + PartidaBingo
```

La regla de negocio definitiva indica que el jugador compra o recibe un carton
una sola vez para el Bingo semanal. Ese carton conserva el mismo codigo y la
misma matriz para todas las rondas del mismo Bingo. La relacion actual impide
esto porque el carton queda atado a una sola ronda desde el campo `idpartida`.

Consecuencias de mantener el diseno actual:

- Para que el mismo jugador participe en tres rondas, habria que crear tres
  cartones distintos o duplicar el mismo carton en tres filas.
- Si se duplican filas, el codigo unico global impide conservar exactamente el
  mismo `codigocarton` sin cambiar restricciones.
- Si se genera un codigo nuevo por ronda, el carton impreso y el carton virtual
  dejan de ser el mismo objeto de negocio.
- La validacion de ganador solo ve los cartones asignados a una partida, no los
  cartones maestros del Bingo.
- `Mis cartones` muestra una relacion carton-ronda, no carton-Bingo.
- Los reportes de Bingo cuentan cartones por partida, lo que puede duplicar
  ventas y recaudacion si el carton se replica.

## 3. Inventario de impacto

| Area | Archivo | Clase, funcion o vista | Uso actual de `Carton.idpartida` | Impacto | Adaptacion necesaria |
|---|---|---|---|---|---|
| Generacion de cartones | `apps/bingos/services.py` | `generar_codigo_carton` | Prefijo `P<idpartida>-C-` | Alto | Cambiar a prefijo por Bingo o codigo maestro independiente de ronda |
| Generacion de cartones | `apps/bingos/services.py` | `crear_y_asignar_carton` | Crea una fila `Carton` ligada a una partida | Alto | Crear carton maestro por Bingo y filas `CartonPartidaBingo` para sus partidas |
| Generacion de cartones | `apps/bingos/views.py` | `partida_carton_nuevo` | Ruta parte de una partida | Alto | Redefinir flujo: generar desde Bingo o desde partida pero creando para todo el Bingo |
| Formularios | `apps/bingos/forms.py` | `CartonForm` | Expone `idpartida` | Medio | Reemplazar por `idbingo` en maestro y gestionar participaciones aparte |
| Consola del operador | `apps/bingos/views.py` | `consola_operador` | Lista `Carton.objects.filter(idpartida=partida)` | Alto | Listar participaciones de la partida con join a carton maestro |
| Extraccion de bolas | `apps/bingos/services.py` | `sacar_bola_partida` y payloades | No depende de carton, pero los cartones visuales usan partida | Bajo | Mantener por partida; actualizar visualizacion contra asignacion de partida |
| Validacion de ganador | `apps/bingos/services.py` | `_carton_pertenece_a_partida` | Compara `carton.idpartida_id` | Alto | Validar existencia de `CartonPartidaBingo(carton, partida)` |
| Validacion de ganador | `apps/bingos/services.py` | `buscar_cartones_ganadores` | Filtra cartones por partida | Alto | Filtrar asignaciones de partida y evaluar matriz del carton maestro |
| Validacion de ganador | `apps/bingos/services.py` | `validar_carton_ganador` | Bloquea cartones de la partida | Alto | Bloquear participaciones de partida y la partida; guardar indice por asignacion |
| Desempate | `apps/bingos/services.py` | serializacion de candidatos | Usa `idcarton` y `codigocarton` de cartones de una partida | Alto | Serializar candidatos desde asignaciones; evitar tiros privados en reportes publicos |
| Tablero publico | `apps/bingos/views.py` | `tablero_publico` | No lista cartones; depende de partida | Bajo | Mantener por partida; no requiere cambio fuerte |
| Consulta publica | `apps/bingos/views.py` | `carton_publico` | Un codigo lleva a una sola partida por `carton.idpartida` | Alto | Necesita seleccionar contexto: Bingo actual, partida activa o resumen de rondas |
| Carton publico | `templates/bingos/carton_publico.html` | WebSocket por `partida.idpartidabingo` | Escucha una sola partida | Alto | Determinar que partida del Bingo se muestra o permitir tabs por ronda |
| Mis cartones | `apps/bingos/views.py` | `mis_cartones` | Lista cartones del jugador con una sola partida | Alto | Listar cartones maestros por Bingo y estado global; incluir rondas asociadas |
| Detalle privado | `apps/bingos/views.py` | `mi_carton_detalle` | Calcula progreso contra `carton.idpartida` | Alto | Calcular progreso por partida activa o por ronda seleccionada |
| Reporte PDF | `apps/bingos/views.py` y `reportes.py` | `partida_reporte_pdf` | Cartones filtrados por partida | Medio | Usar participaciones de la partida; mantener resultado por ronda |
| Excel de cartones | `apps/bingos/views.py` y `reportes.py` | `partida_cartones_excel` | Lista cartones de una partida | Medio | Exportar participaciones con datos del carton maestro |
| Excel resumen Bingo | `apps/bingos/reportes.py` | `generar_excel_resumen_bingo` | Agrupa por `carton.idpartida_id` | Alto | Agrupar por `CartonPartidaBingo.idpartida`; recaudar por carton maestro sin duplicar |
| WebSockets | `apps/bingos/consumers.py` y `routing.py` | Canal por partida | No usa `Carton.idpartida` directamente | Medio | Mantener canal por partida; cliente de carton debe suscribirse a ronda activa |
| Estado de carton | `apps/bingos/models.py` | `Carton.estadocarton` | Estado unico en fila ligada a partida | Alto | Separar estado general del carton y estado de participacion por ronda |
| Precio pagado | `apps/bingos/models.py` | `Carton.preciopagado` | Precio por fila de partida | Medio | Mantener en carton maestro si la compra es por Bingo completo |
| Indice de victoria | `apps/bingos/models.py` | `Carton.indicevictoria` | Campo en carton | Alto | Mover a asignacion por partida |
| Jugador | `apps/bingos/models.py` | `Carton.idjugador` | Propietario del carton | Bajo | Mantener en carton maestro |
| Pruebas | `apps/bingos/tests.py` | fixtures y mocks | Crean `Carton(idpartida=partida)` | Alto | Actualizar pruebas a carton maestro + asignacion por partida |

## 4. Modelo fisico propuesto

### Carton maestro

Tabla recomendada: `carton`.

Campos recomendados:

- `idcarton`: PK.
- `idbingo`: FK obligatoria a `bingo`.
- `idjugador`: FK nullable a `jugador`.
- `codigocarton`: codigo unico del carton maestro.
- `matriznumeros`: matriz B-I-N-G-O unica para todo el Bingo.
- `fechacreacion` o reutilizar `fechacompra`: fecha de emision/compra.
- `preciopagado`: precio pagado por el carton para el Bingo completo.
- `estadocarton`: estado general: `Activo`, `Anulado`, `Cerrado`, `Expirado`.

Campos que deberian salir del maestro o quedar obsoletos:

- `idpartida`: no debe ser la relacion principal.
- `indicevictoria`: debe ser por partida, no global.

Justificacion:

- `idjugador` debe permanecer en `Carton` porque la propiedad del carton es
  unica para todo el Bingo. El mismo carton impreso y virtual pertenece al mismo
  jugador.
- `preciopagado` debe vivir en `Carton` si la compra es una sola para todo el
  Bingo semanal. Guardarlo en la tabla intermedia duplicaria recaudacion por
  ronda.
- `estadocarton` debe ser general para indicar si el carton maestro esta activo,
  anulado, cerrado o expirado.

### CartonPartidaBingo

Tabla recomendada: `carton_partida_bingo`.

Campos minimos:

- `idcartonpartidabingo`: PK.
- `idcarton`: FK a `carton`.
- `idpartida`: FK a `partidabingo`.
- `estado_participacion`: estado por ronda: `Pendiente`, `En juego`,
  `Perdedor`, `Ganador`, `Anulado`, `Cerrado`.
- `indicevictoria`: calculo o posicion por partida.
- `fechacreacion`: fecha de generacion de la asignacion.
- `fechavalidacion`: fecha opcional cuando se valida.

Campos opcionales segun aprobacion:

- `es_ganador`: booleano por partida.
- `motivo_estado`: texto corto para anulaciones o cierres.
- `preciopagado_partida`: solo si el negocio decide cobrar por ronda, no
  recomendado para la regla actual.

Justificacion:

- `indicevictoria` debe estar en `CartonPartidaBingo` porque una misma matriz
  puede tener progreso o resultado diferente en cada ronda.
- `estado_participacion` debe ser por partida porque una ronda puede estar
  ganada, anulada o cerrada sin cambiar el estado del carton maestro en otras
  rondas.
- El carton puede participar en todas las partidas del Bingo sin duplicar codigo
  ni matriz.

### Puede un carton ganar mas de una ronda

Tecnicamente el modelo propuesto lo permite porque la condicion de ganador vive
por partida. La decision de negocio debe aprobar si:

- un mismo carton puede ganar varias rondas del mismo Bingo; o
- al ganar una ronda se bloquea para las siguientes; o
- puede ganar solo ciertos tipos de premio.

Recomendacion tecnica inicial: permitirlo a nivel de estructura y controlar la
regla en servicios segun la decision aprobada. Bloquearlo en base sin una
decision clara puede impedir reglas futuras.

### Como impedir cartones de otro Bingo en una partida

La tabla intermedia debe garantizar que:

```text
Carton.idbingo == Partidabingo.idbingo
```

Esto no se puede expresar con una FK simple usando solo `idcarton` e
`idpartida`. Opciones:

1. Validacion en aplicacion: facil, pero insuficiente si hay scripts o cargas
   directas.
2. Trigger en PostgreSQL: valida al insertar o actualizar la intermedia.
3. Diseno con `idbingo` tambien en `carton_partida_bingo` y FKs compuestas:
   `(idcarton, idbingo)` contra `carton` y `(idpartida, idbingo)` contra
   `partidabingo`.

Recomendacion: usar trigger o FKs compuestas. Si se puede ajustar el diseno
fisico con mas rigor, preferir `idbingo` en la tabla intermedia con FKs
compuestas e indices unicos auxiliares.

## 5. Reglas y restricciones SQL recomendadas

Propuesta, no ejecutar en esta etapa.

### Claves y FKs

- `carton.idcarton` como PK.
- `carton.idbingo` FK a `bingo(idbingo)`.
- `carton.idjugador` FK nullable a `jugador(idjugador)`.
- `carton_partida_bingo.idcartonpartidabingo` como PK.
- `carton_partida_bingo.idcarton` FK a `carton(idcarton)`.
- `carton_partida_bingo.idpartida` FK a `partidabingo(idpartidabingo)`.

### UNIQUE

- `carton.codigocarton` unico global para trazabilidad.
- Alternativa: `UNIQUE(idbingo, codigocarton)` si se permite reutilizar codigo
  en distintos Bingos. No recomendado porque un codigo impreso antiguo podria
  confundirse.
- `carton_partida_bingo(idcarton, idpartida)` unico.

### CHECK

- `carton.estadocarton IN ('Activo', 'Anulado', 'Cerrado', 'Expirado')`.
- `carton_partida_bingo.estado_participacion IN ('Pendiente', 'En juego',
  'Perdedor', 'Ganador', 'Anulado', 'Cerrado')`.
- `carton.preciopagado >= 0`.
- `carton_partida_bingo.indicevictoria >= 0` cuando no sea null.

### Indices

- `carton(idbingo)`.
- `carton(idjugador)`.
- `carton(codigocarton)`.
- `carton_partida_bingo(idpartida)`.
- `carton_partida_bingo(idcarton)`.
- `carton_partida_bingo(idpartida, estado_participacion)`.

### Validacion de mismo Bingo

Opcion con trigger:

```sql
-- PROPUESTO, NO EJECUTAR EN ESTA ETAPA
CREATE OR REPLACE FUNCTION validar_carton_partida_mismo_bingo()
RETURNS trigger AS $$
DECLARE
    v_bingo_carton integer;
    v_bingo_partida integer;
BEGIN
    SELECT idbingo INTO v_bingo_carton
    FROM carton
    WHERE idcarton = NEW.idcarton;

    SELECT idbingo INTO v_bingo_partida
    FROM partidabingo
    WHERE idpartidabingo = NEW.idpartida;

    IF v_bingo_carton IS NULL OR v_bingo_partida IS NULL THEN
        RAISE EXCEPTION 'Carton o partida inexistente.';
    END IF;

    IF v_bingo_carton <> v_bingo_partida THEN
        RAISE EXCEPTION 'El carton y la partida pertenecen a Bingos distintos.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_carton_partida_mismo_bingo
BEFORE INSERT OR UPDATE OF idcarton, idpartida
ON carton_partida_bingo
FOR EACH ROW
EXECUTE FUNCTION validar_carton_partida_mismo_bingo();
```

## 6. Estrategia para migrar datos existentes

Objetivo: transformar los cartones actuales sin perder historial.

Pasos recomendados:

1. Hacer respaldo completo antes de tocar estructura.
2. Identificar el Bingo de cada carton actual usando:

   ```text
   carton.idpartida -> partidabingo.idbingo
   ```

3. Agregar `carton.idbingo` y poblarlo desde la partida actual.
4. Crear `carton_partida_bingo`.
5. Crear una asignacion para la partida original de cada carton, preservando
   `indicevictoria` y estado equivalente.
6. Para cada carton, crear asignaciones faltantes contra las demas partidas del
   mismo Bingo.
7. Para Bingos o partidas historicas finalizadas, no recalcular ganadores ni
   reabrir estados. Las asignaciones nuevas deben quedar en estado historico o
   cerrado, segun decision aprobada.
8. Verificar inconsistencias: cartones sin partida, partidas sin Bingo,
   cartones sin matriz, codigos duplicados, partidas de prueba.
9. Adaptar codigo despues de validar la migracion en una copia.
10. Mantener `carton.idpartida` temporalmente durante una fase de compatibilidad
    o eliminarlo solo cuando todo el codigo use la tabla intermedia.

### 6.1 Respaldo propuesto

```sql
-- PROPUESTO, NO EJECUTAR EN ESTA ETAPA
BEGIN;

CREATE TABLE backup_carton_pre_hibrido AS
SELECT * FROM carton;

CREATE TABLE backup_partidabingo_pre_hibrido AS
SELECT * FROM partidabingo;

CREATE TABLE backup_bingo_pre_hibrido AS
SELECT * FROM bingo;

COMMIT;
```

### 6.2 Creacion de estructura propuesta

```sql
-- PROPUESTO, NO EJECUTAR EN ESTA ETAPA
BEGIN;

ALTER TABLE carton
ADD COLUMN idbingo integer;

ALTER TABLE carton
ADD CONSTRAINT fk_carton_bingo
FOREIGN KEY (idbingo)
REFERENCES bingo(idbingo);

CREATE TABLE carton_partida_bingo (
    idcartonpartidabingo integer PRIMARY KEY,
    idcarton integer NOT NULL,
    idpartida integer NOT NULL,
    estado_participacion varchar(20) NOT NULL DEFAULT 'Pendiente',
    indicevictoria integer,
    fechacreacion timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    fechavalidacion timestamp without time zone,
    CONSTRAINT fk_cpb_carton
        FOREIGN KEY (idcarton) REFERENCES carton(idcarton),
    CONSTRAINT fk_cpb_partida
        FOREIGN KEY (idpartida) REFERENCES partidabingo(idpartidabingo),
    CONSTRAINT uq_cpb_carton_partida
        UNIQUE (idcarton, idpartida),
    CONSTRAINT chk_cpb_estado
        CHECK (estado_participacion IN (
            'Pendiente', 'En juego', 'Perdedor', 'Ganador', 'Anulado', 'Cerrado'
        )),
    CONSTRAINT chk_cpb_indice
        CHECK (indicevictoria IS NULL OR indicevictoria >= 0)
);

CREATE INDEX idx_carton_idbingo ON carton(idbingo);
CREATE INDEX idx_carton_idjugador ON carton(idjugador);
CREATE INDEX idx_cpb_idpartida ON carton_partida_bingo(idpartida);
CREATE INDEX idx_cpb_idcarton ON carton_partida_bingo(idcarton);
CREATE INDEX idx_cpb_partida_estado
    ON carton_partida_bingo(idpartida, estado_participacion);

COMMIT;
```

### 6.3 Migracion de datos propuesta

```sql
-- PROPUESTO, NO EJECUTAR EN ESTA ETAPA
BEGIN;

UPDATE carton c
SET idbingo = p.idbingo
FROM partidabingo p
WHERE c.idpartida = p.idpartidabingo
  AND c.idbingo IS NULL;

INSERT INTO carton_partida_bingo (
    idcartonpartidabingo,
    idcarton,
    idpartida,
    estado_participacion,
    indicevictoria,
    fechacreacion
)
SELECT
    ROW_NUMBER() OVER (ORDER BY c.idcarton) AS idcartonpartidabingo,
    c.idcarton,
    c.idpartida,
    CASE
        WHEN lower(coalesce(c.estadocarton, '')) = 'cerrado' THEN 'Cerrado'
        WHEN lower(coalesce(c.estadocarton, '')) = 'anulado' THEN 'Anulado'
        ELSE 'Pendiente'
    END AS estado_participacion,
    c.indicevictoria,
    coalesce(c.fechacompra, CURRENT_TIMESTAMP)
FROM carton c
WHERE c.idpartida IS NOT NULL;

-- Asignaciones faltantes para las demas rondas del mismo Bingo.
-- Requiere definir antes si las partidas historicas quedan Cerradas o Pendientes.
INSERT INTO carton_partida_bingo (
    idcartonpartidabingo,
    idcarton,
    idpartida,
    estado_participacion,
    indicevictoria,
    fechacreacion
)
SELECT
    (SELECT coalesce(max(idcartonpartidabingo), 0) FROM carton_partida_bingo)
    + ROW_NUMBER() OVER (ORDER BY c.idcarton, p.idpartidabingo),
    c.idcarton,
    p.idpartidabingo,
    CASE
        WHEN lower(coalesce(p.estadopartida, '')) IN ('finalizada', 'cerrada')
            THEN 'Cerrado'
        ELSE 'Pendiente'
    END,
    NULL,
    coalesce(c.fechacompra, CURRENT_TIMESTAMP)
FROM carton c
JOIN partidabingo p
  ON p.idbingo = c.idbingo
LEFT JOIN carton_partida_bingo cpb
  ON cpb.idcarton = c.idcarton
 AND cpb.idpartida = p.idpartidabingo
WHERE c.idbingo IS NOT NULL
  AND cpb.idcartonpartidabingo IS NULL;

COMMIT;
```

### 6.4 Validacion propuesta

```sql
-- PROPUESTO, NO EJECUTAR EN ESTA ETAPA
SELECT c.idcarton, c.codigocarton, c.idpartida
FROM carton c
WHERE c.idbingo IS NULL;

SELECT cpb.idcarton, cpb.idpartida, count(*)
FROM carton_partida_bingo cpb
GROUP BY cpb.idcarton, cpb.idpartida
HAVING count(*) > 1;

SELECT c.idcarton, c.idbingo AS bingo_carton,
       p.idpartidabingo, p.idbingo AS bingo_partida
FROM carton_partida_bingo cpb
JOIN carton c ON c.idcarton = cpb.idcarton
JOIN partidabingo p ON p.idpartidabingo = cpb.idpartida
WHERE c.idbingo <> p.idbingo;

SELECT c.idbingo, count(*) AS cartones_maestros
FROM carton c
GROUP BY c.idbingo
ORDER BY c.idbingo;

SELECT p.idbingo, p.idpartidabingo, count(cpb.idcarton) AS participaciones
FROM partidabingo p
LEFT JOIN carton_partida_bingo cpb
  ON cpb.idpartida = p.idpartidabingo
GROUP BY p.idbingo, p.idpartidabingo
ORDER BY p.idbingo, p.idpartidabingo;
```

### 6.5 Rollback propuesto

```sql
-- PROPUESTO, NO EJECUTAR EN ESTA ETAPA
BEGIN;

DROP TRIGGER IF EXISTS trg_carton_partida_mismo_bingo
ON carton_partida_bingo;

DROP FUNCTION IF EXISTS validar_carton_partida_mismo_bingo();

DROP TABLE IF EXISTS carton_partida_bingo;

ALTER TABLE carton
DROP CONSTRAINT IF EXISTS fk_carton_bingo;

ALTER TABLE carton
DROP COLUMN IF EXISTS idbingo;

-- Si hubo transformaciones destructivas posteriores, restaurar desde respaldo:
-- TRUNCATE TABLE carton;
-- INSERT INTO carton SELECT * FROM backup_carton_pre_hibrido;

COMMIT;
```

El rollback real debe ensayarse en una copia y debe ajustarse si en una fase
posterior se elimina `carton.idpartida` o se mueven campos fisicamente.

## 7. Plan de adaptacion de codigo

### Fase A: base fisica

- Archivos probables: scripts SQL en `DATABASE/` y documentacion.
- Cambios: agregar `carton.idbingo`, crear `carton_partida_bingo`, restricciones,
  indices y validacion de mismo Bingo.
- Riesgo: alto.
- Orden: respaldo, estructura, migracion, validacion, aprobacion.
- Pruebas: validaciones SQL, conteos por Bingo, participaciones por partida.

### Fase B: modelos inspectdb

- Archivos probables: `models_inspectdb.py`, `apps/bingos/models.py`.
- Cambios: regenerar referencia con inspectdb y actualizar modelos `managed=False`
  bajo aprobacion.
- Riesgo: medio.
- Orden: despues de aprobar base fisica.
- Pruebas: `python manage.py check`, imports de modelos, consultas basicas.

### Fase C: servicios de creacion y asignacion

- Archivos probables: `apps/bingos/services.py`, `apps/bingos/forms.py`,
  `apps/bingos/views.py`.
- Cambios: crear carton maestro por Bingo; crear participaciones para todas las
  partidas del Bingo; cambiar codigo a prefijo por Bingo.
- Riesgo: alto.
- Pruebas: crear un carton para Bingo con tres rondas y verificar tres
  asignaciones con el mismo codigo y matriz.

### Fase D: validacion de ganador y desempate

- Archivos probables: `apps/bingos/services.py`, `apps/bingos/views.py`,
  `apps/bingos/tests.py`.
- Cambios: validar por `CartonPartidaBingo`; mover `indicevictoria` a la
  participacion; serializar candidatos desde asignaciones.
- Riesgo: alto.
- Pruebas: ganador unico, multiples ganadores, desempate, bloqueo transaccional,
  cartones anulados, carton de otro Bingo.

### Fase E: vistas administrativas

- Archivos probables: `apps/bingos/views.py`, `apps/bingos/urls.py`,
  `templates/bingos/`.
- Cambios: detalle de Bingo muestra cartones maestros; detalle de partida muestra
  participaciones; editar carton maestro separado de participacion.
- Riesgo: medio.
- Pruebas: permisos `admin_required`, listados, creacion, edicion, validacion.

### Fase F: sala publica, tablero y WebSockets

- Archivos probables: `apps/bingos/views.py`, `apps/bingos/realtime.py`,
  `apps/bingos/consumers.py`, `templates/bingos/`, `static/js/realtime_bingo.js`.
- Cambios: mantener WebSocket por partida; definir como el carton publico elige
  ronda activa o muestra rondas del Bingo.
- Riesgo: medio.
- Pruebas: tablero actualiza por partida, carton visual actualiza contra la ronda
  activa sin recargar en bucle.

### Fase G: Mis cartones y detalle privado

- Archivos probables: `apps/bingos/views.py`, `templates/bingos/`,
  `apps/jugadores/services.py`.
- Cambios: listar cartones maestros del jugador por Bingo; detalle muestra matriz
  unica y progreso por ronda seleccionada o activa.
- Riesgo: alto.
- Pruebas: jugador ve solo sus cartones maestros; no ve cartones ajenos; detalle
  privado respeta propiedad y estado del Bingo.

### Fase H: reportes PDF/Excel

- Archivos probables: `apps/bingos/reportes.py`, `apps/bingos/views.py`,
  `apps/bingos/tests.py`.
- Cambios: PDF de partida usa participaciones; Excel de cartones de partida usa
  `CartonPartidaBingo`; Excel de Bingo no duplica recaudacion por ronda.
- Riesgo: medio.
- Pruebas: archivos descargables, hojas esperadas, totales correctos, datos
  privados excluidos.

### Fase I: impresion presencial de cartones

- Archivos probables: nuevo modulo de reportes/impresion, `apps/bingos/views.py`,
  `templates/bingos/`.
- Cambios: PDF individual y masivo de cartones maestros por Bingo.
- Riesgo: medio.
- Pruebas: mismo codigo y matriz en virtual e impreso; PDF no muestra datos
  privados innecesarios.

### Fase J: pruebas y documentacion

- Archivos probables: `apps/bingos/tests.py`, `apps/jugadores/tests.py`,
  `DOCUMENTACION/`.
- Cambios: actualizar pruebas de cartones, ganador, desempate, WebSockets,
  reportes, Mis cartones e impresion.
- Riesgo: alto.
- Pruebas: `python manage.py check`, `python manage.py test`, pruebas de
  integridad de migracion en copia.

## 8. Impresion hibrida

Diseno propuesto, sin implementar todavia.

### Impresion PDF de un carton individual

Contenido minimo:

- Nombre del Bingo.
- Fecha programada del Bingo.
- Codigo del carton.
- Matriz B-I-N-G-O.
- Casilla LIBRE.
- Jugador opcional si el carton esta asignado.
- Estado general del carton.
- Fecha de emision o compra.
- Leyenda: valido solo para este Bingo.

### Impresion masiva de cartones de un Bingo

Opciones:

- Una hoja por carton: mas claro para presencial.
- Varios cartones por pagina: mas economico, requiere diseno cuidadoso.

El PDF masivo debe generarse desde cartones maestros filtrados por `idbingo`.
No debe crear cartones nuevos durante la impresion.

### Garantia de igualdad entre impreso y virtual

La fuente unica debe ser `Carton`:

```text
Carton.codigocarton
Carton.matriznumeros
Carton.idbingo
Carton.idjugador
```

El carton impreso y el virtual deben renderizar esos mismos datos. La tabla
`CartonPartidaBingo` solo indica participacion por ronda, no cambia codigo ni
matriz.

### Expiracion por Bingo

Un carton deja de ser valido cuando el Bingo asociado termina o se cierra.
Opciones:

- Cambiar `carton.estadocarton` a `Cerrado` o `Expirado` al cerrar el Bingo.
- Mantener estado del carton y derivar expiracion desde `bingo.estadobingo`.

Recomendacion: usar ambos conceptos. `bingo.estadobingo` define cierre general;
`carton.estadocarton` permite anulaciones o cierres puntuales. En pantalla e
impresion debe mostrarse claramente si el Bingo ya finalizo.

## 9. Decisiones que requieren aprobacion

Antes de implementar se deben aprobar:

1. Nombre definitivo de la tabla intermedia: `carton_partida_bingo` u otro.
2. Si `carton.idpartida` se mantiene temporalmente, se renombra a referencia
   historica o se elimina en una version posterior.
3. Si el codigo del carton sera unico global o unico por Bingo.
4. Formato nuevo del codigo: prefijo por Bingo, por fecha o secuencia interna.
5. Si `preciopagado` queda en `Carton` o se permite precio por ronda.
6. Estados oficiales de `Carton` y `CartonPartidaBingo`.
7. Si un carton puede ganar mas de una ronda del mismo Bingo.
8. Como se cierran o expiran cartones cuando finaliza el Bingo.
9. Como tratar Bingos historicos ya finalizados durante la migracion.
10. Si se exigira trigger o FK compuesta para impedir cartones de otro Bingo.
11. Si `Sesionjuego.idpartida` debe mantenerse por partida o ampliarse a carton
    maestro/participacion.
12. Como sera la consulta publica de un codigo cuando el Bingo tenga varias
    rondas: ronda activa, selector de ronda o resumen.
13. Si la base aprobada se versiona con un script formal nuevo.

## 10. Recomendacion final

El diseno recomendado es:

```text
Bingo
  -> Partidabingo

Carton maestro
  -> Bingo
  -> Jugador
  -> codigo unico
  -> matriz unica
  -> precio pagado por Bingo

CartonPartidaBingo
  -> Carton maestro
  -> Partidabingo
  -> estado e indice por ronda
```

Este diseno encaja con las diapositivas porque el carton nace para el Bingo
semanal completo y participa internamente en cada ronda. Tambien soporta el modo
presencial, virtual e hibrido porque el carton impreso y el carton virtual son
el mismo registro maestro: mismo codigo, misma matriz y mismo Bingo.

Es mas correcto que mantener `Carton.idpartida` porque separa dos conceptos que
hoy estan mezclados:

- el carton comprado o entregado para el Bingo;
- la participacion de ese carton en una ronda concreta.

Lo primero a implementar, cuando se apruebe la etapa, debe ser la base fisica en
una copia o ambiente de pruebas con respaldo, validacion y rollback ensayado.
Despues se deben adaptar los modelos `managed=False` y los servicios centrales
antes de tocar pantallas. No se debe iniciar por templates ni por WebSockets,
porque la fuente de verdad seguiria siendo incorrecta.

No se debe tocar aun:

- PostgreSQL productivo;
- migraciones;
- modelos `managed=False`;
- `models_inspectdb.py`;
- validacion de ganador;
- reportes;
- WebSockets;
- impresion de cartones.

Primero se requiere aprobacion del modelo fisico y de las decisiones de negocio
listadas en la seccion 9.
