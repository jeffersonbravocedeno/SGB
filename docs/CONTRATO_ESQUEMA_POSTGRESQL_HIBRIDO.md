# Contrato de esquema PostgreSQL para cartones híbridos de SIAB

Fecha: 2026-07-05  
Fase: 0.6 — confirmación física de PostgreSQL  
Estado: **BLOQUEADA POR CONFIGURACIÓN ACTIVA NO SEGURA PARA ESTA FASE**  
Fuentes: `docs/AUDITORIA_TECNICA_SIAB.md` y
`docs/PLAN_CORRECCION_HIBRIDA_SIAB.md`

## Alcance y principio de evidencia

El objetivo de esta fase era inspeccionar exclusivamente una base de ensayo
autorizada. Antes de abrir cualquier conexión se revisaron localmente
`config/settings.py` y solo la variable `DB_NAME` de la configuración activa,
sin mostrar el contenido de `.env`, usuario, contraseña, host completo ni
cadena de conexión.

La configuración activa resultó apuntar a `bingo`, identificada por el Prompt
Maestro como la base principal real. La regla de seguridad ordena detenerse en
ese punto. En consecuencia:

- no se abrió una conexión PostgreSQL;
- no se ejecutó `psql` ni un cursor Django;
- no se consultaron `information_schema`, `pg_catalog`, `pg_indexes` ni
  `pg_constraint`;
- no se ejecutaron conteos ni verificaciones de relaciones;
- no se sustituyó `DB_NAME` temporalmente;
- no se cambió `.env`, `settings.py` ni otra configuración;
- no se creó ni verificó la existencia de una base de ensayo;
- no se ejecutó ningún script SQL.

Este documento separa estrictamente las expectativas del código de los hechos
físicos. Todo campo marcado como “no confirmado” requiere una inspección futura
segura; no es un resultado negativo ni positivo sobre PostgreSQL.

## 1. Resultado de seguridad de conexión

### 1.1 Resultado

| Control | Resultado |
|---|---|
| Motor configurado | `django.db.backends.postgresql` |
| Nombre de base en la configuración activa | `bingo` |
| ¿Es la base de ensayo autorizada? | No |
| ¿Es la base principal real prohibida en esta fase? | Sí |
| ¿Se abrió conexión? | No |
| ¿Se ejecutaron consultas SQL? | No |
| Resultado de la fase física | Bloqueada antes de conectar |

La base inspeccionada es **ninguna**. El nombre `bingo` solo se obtuvo leyendo
la clave local de configuración; no se consultó la base con ese nombre.

### 1.2 Método de validación de seguridad

1. Se confirmó estáticamente en `config/settings.py` que Django usa el backend
   PostgreSQL y obtiene el nombre desde `DB_NAME`.
2. Se leyó exclusivamente el valor de la clave `DB_NAME` mediante un filtro
   local que no imprime ninguna otra variable.
3. Al obtener `DB_NAME=bingo`, se aplicó la condición de bloqueo del encargo.
4. No se intentó descubrir bases mediante `pg_database`, porque eso requeriría
   conectarse al destino prohibido o a otra base no confirmada.

No fue posible validar `current_database()` ni
`transaction_read_only`, porque ambas comprobaciones requieren una conexión y
la configuración no identifica una base segura.

### 1.3 Dato exacto necesario para continuar

El usuario debe preparar, fuera de este cambio documental, un perfil o sesión
de entorno cuya configuración activa resuelva inequívocamente a una base de
ensayo existente. Para continuar se necesita:

1. el nombre exacto de la base autorizada, esperado por ejemplo como
   `bingo_ensayo_hibridos`;
2. confirmación de que el perfil activo de Django ya muestra ese nombre en
   `DB_NAME` antes de conectar, sin que el agente edite `.env`;
3. confirmación de que la base existe y es una copia de ensayo, no un alias ni
   redirección hacia `bingo`;
4. un rol PostgreSQL preconfigurado con permisos de solo lectura sobre
   catálogos y tablas necesarias, sin permisos DDL/DML;
5. autorización para ejecutar los SELECT de diagnóstico de esta fase mediante
   ese perfil.

No deben enviarse contraseñas ni cadenas de conexión en el chat. Es suficiente
activar el perfil seguro en el entorno y comunicar su nombre/base efectiva.
La inspección futura deberá comenzar verificando
`current_database() = 'bingo_ensayo_hibridos'` y
`transaction_read_only = 'on'`; si alguna condición falla, volverá a detenerse.

## 2. Tablas reales encontradas

### 2.1 Resultado físico

No se confirmó ninguna tabla física en esta fase, porque no hubo conexión a
PostgreSQL. No es correcto afirmar que una tabla existe o no existe basándose
solo en los modelos Django o en documentos de fases anteriores.

### 2.2 Mapeo esperado desde Django, no confirmado físicamente

Esta tabla sirve únicamente como lista de búsqueda para una próxima inspección.
Los nombres `db_table` son expectativas del código, no “tablas encontradas”.

| Concepto solicitado | Modelo Django | `db_table` esperado por el código | Esquema real | Estado físico |
|---|---|---|---|---|
| Bingo | `Bingo` | `bingo` | No confirmado | No inspeccionado |
| Ronda/partida | `Partidabingo` | `partidabingo` | No confirmado | No inspeccionado |
| Cartón | `Carton` | `carton` | No confirmado | No inspeccionado |
| Participación por ronda | `CartonPartidaBingo` | `carton_partida_bingo` | No confirmado | No inspeccionado |
| Jugador | `Jugador` | `jugador` | No confirmado | No inspeccionado |
| Socio | `Socio` | `socio` | No confirmado | No inspeccionado |
| Pago de préstamo | `Pago` | `pago` | No confirmado | No inspeccionado |
| Préstamo | `Prestamo` | `prestamo` | No confirmado | No inspeccionado |
| Ahorro | `Ahorro` | `ahorro` | No confirmado | No inspeccionado |
| Aporte semanal | `Aportesemanal` | `aportesemanal` | No confirmado | No inspeccionado |

La solicitud menciona nombres como `partida_bingo` y `aporte_semanal`, pero el
código espera `partidabingo` y `aportesemanal`. Solo PostgreSQL puede confirmar
el nombre real y el esquema —por ejemplo `public`—. No se asumió ninguna de
estas variantes.

## 3. Contrato físico actual de cartones híbridos

### 3.1 Respuestas obligatorias

| Pregunta | Respuesta física de esta fase | Expectativa del código |
|---|---|---|
| ¿Existe `carton.idbingo`? | No confirmado | Sí, FK obligatoria en `Carton` |
| ¿Existe `carton.idpartida`? | No confirmado | Sí, FK histórica opcional |
| ¿`carton.idpartida` acepta `NULL`? | No confirmado | El modelo lo permite para maestros nuevos |
| ¿Existe `carton_partida_bingo` o equivalente? | No confirmado | El ORM espera exactamente `carton_partida_bingo` |
| ¿La participación referencia cartón? | No confirmado | `idcarton` hacia `Carton` |
| ¿La participación referencia ronda? | No confirmado | `idpartida` hacia `Partidabingo` |
| ¿Existe `UNIQUE(idcarton,idpartida)`? | No confirmado | Declarado como `unique_together` y esperado físicamente |
| ¿Hay índice para cartones por Bingo? | No confirmado | Recomendado `carton(idbingo)` |
| ¿Hay índice para participaciones por ronda? | No confirmado | Recomendado `carton_partida_bingo(idpartida)` |
| ¿Hay índice para participaciones por cartón? | No confirmado | Puede cubrirlo el UNIQUE con prefijo `idcarton` |

### 3.2 Claves primarias esperadas, no confirmadas

| Tabla esperada | PK esperada por Django | Tipo físico esperado |
|---|---|---|
| `bingo` | `idbingo` | `integer` manual según documentación previa |
| `partidabingo` | `idpartidabingo` | `integer` manual según documentación previa |
| `carton` | `idcarton` | `integer` manual según documentación previa |
| `carton_partida_bingo` | `idcartonpartidabingo` | `integer` autogenerado compatible con `AutoField`/IDENTITY |

La palabra “esperada” es esencial: no se inspeccionó `pg_constraint`, defaults,
secuencias ni atributos IDENTITY.

### 3.3 FK, UNIQUE, CHECK e índices

No se confirmó el nombre, definición, validación ni existencia de ninguna PK,
FK, UNIQUE, CHECK o índice. La auditoría y el plan registran como contrato
deseado:

- FK `carton.idbingo → bingo.idbingo`;
- FK histórica `carton.idpartida → partidabingo.idpartidabingo`;
- FK de participación hacia cartón y ronda;
- FK compuestas que obliguen a compartir el mismo Bingo;
- UNIQUE de cartón y ronda;
- CHECK de estados, índice de victoria y origen;
- índices por Bingo, ronda y estado.

Estas son recomendaciones pendientes de contraste, no hallazgos físicos de la
Fase 0.6.

## 4. Diagnóstico de integridad

### 4.1 Consultas de datos

No se ejecutó ningún SELECT de conteo o relación. Por tanto, los siguientes
resultados permanecen no evaluados:

| Diagnóstico solicitado | Resultado |
|---|---|
| Cantidad de Bingos | No evaluado |
| Cantidad de rondas | No evaluado |
| Cantidad de cartones | No evaluado |
| Cantidad de participaciones | No evaluado |
| Cartones con `idbingo` nulo | No evaluado |
| Participaciones sin cartón válido | No evaluado |
| Participaciones sin ronda válida | No evaluado |
| Duplicados `(idcarton,idpartida)` | No evaluado |
| Cartones maestros sin participaciones | No evaluado |
| Rondas sin participaciones para maestros existentes | No evaluado |

### 4.2 Riesgos reales confirmados en esta fase

El único riesgo confirmado directamente es operativo: la configuración activa
apunta a la base real, por lo que ejecutar el diagnóstico previsto habría
violado el aislamiento exigido.

Permanecen como riesgos previamente documentados, pero no comprobados
físicamente ahora:

- posible ausencia de `carton.idbingo` o `carton_partida_bingo`;
- ausencia de UNIQUE y FK compuestas;
- maestros sin participación en rondas posteriores;
- duplicados o huérfanos;
- divergencia entre el esquema de ensayo documentado y la base activa.

No se inventan cantidades a partir de la documentación histórica. Los conteos
de otras fases no sustituyen una inspección actual autorizada.

## 5. Comparación con la regla de negocio SIAB

| Regla de negocio | Soporte en código | Soporte físico confirmado | Conclusión de esta fase |
|---|---|---|---|
| Un cartón maestro pertenece a un Bingo | `Carton.idbingo` y servicio de venta | No confirmado | Contrato ORM listo; PostgreSQL pendiente de inspección |
| Un cartón participa en varias rondas | `CartonPartidaBingo` | No confirmado | Diseño presente; capacidad física no demostrada |
| El mismo cartón gana varias rondas | Estado/índice por participación | No confirmado | Lógica disponible; constraints y datos no comprobados |
| No hay dos participaciones en la misma ronda | `unique_together` y validaciones | No confirmado | Falta demostrar UNIQUE físico |
| El valor se registra una vez por cartón y Bingo | `preciopagado` vive en `Carton` | No confirmado | Diseño lógico correcto; estados económicos aún requieren decisión |
| La liquidación no suma desde participaciones | Resumen general deduplica; reportes por ronda aún presentan subtotales riesgosos | No depende de una columna de participación | Pendiente de código en reportes |

El esquema por sí solo no garantiza la liquidación correcta. Aunque una
participación no tenga precio, una consulta puede repetir
`Carton.preciopagado` al unirla con varias rondas. La regla debe mantenerse en
servicios y reportes además de la integridad física.

## 6. Brechas detectadas

| Área | Clasificación | Justificación |
|---|---|---|
| Motor PostgreSQL configurado | lista | Confirmado estáticamente, sin conexión |
| Conexión aislada a ensayo | requiere decisión del usuario | La configuración activa apunta a `bingo` |
| Nombres y esquemas físicos | requiere decisión del usuario | No pueden consultarse hasta activar un perfil seguro |
| `Carton.idbingo` en ORM | parcialmente lista | Existe en código; soporte físico no confirmado |
| `Carton.idpartida` nullable | parcialmente lista | El modelo lo permite; nulabilidad física no confirmada |
| Tabla de participaciones en ORM | parcialmente lista | Modelo presente; tabla física no confirmada |
| UNIQUE cartón-ronda | parcialmente lista | Contrato ORM presente; constraint físico no confirmado |
| FK de mismo Bingo | parcialmente lista | Validación de servicio y propuesta existentes; catálogo no inspeccionado |
| Índices híbridos | requiere decisión del usuario | Primero debe comprobarse si ya existen equivalentes |
| Venta única por Bingo | pendiente de código | Persisten rutas heredadas que escriben por ronda |
| Participaciones para rondas nuevas | pendiente de código | `partida_nueva()` no sincroniza maestros existentes |
| Desempate por participación | pendiente de código | Servicios existen, rutas todavía usan flujo legado |
| Recaudación única en reportes | pendiente de código | Los subtotales por ronda pueden repetir el precio |
| Cambios físicos concretos | requiere decisión del usuario | No se puede clasificar como pendiente de SQL sin inspección |
| SQL de expansión o reparación | pendiente de SQL PostgreSQL solo si el diagnóstico demuestra faltantes | No se crea ni ejecuta en esta fase |
| Tratamiento de cartones históricos | requiere decisión del usuario | No deben ampliarse ni transformarse automáticamente |

No se clasifica como “pendiente de SQL PostgreSQL” ninguna estructura
específica hasta comprobar que realmente falta. Hacerlo antes podría duplicar
constraints o alterar un esquema ya compatible.

## 7. Recomendaciones técnicas

### 7.1 Prioridad 0: desbloquear una conexión segura

1. Activar un perfil de Django que resuelva a
   `bingo_ensayo_hibridos` sin editar el repositorio durante la inspección.
2. Usar un rol de solo lectura.
3. Verificar como primeras consultas `current_database()` y
   `transaction_read_only`.
4. Abortar si el nombre no coincide exactamente o si la sesión admite
   escritura.
5. Registrar las consultas y resultados sin credenciales.

### 7.2 Inspección futura de solo lectura

Una vez desbloqueada, la inspección debe consultar en este orden:

1. `information_schema.tables` para descubrir nombres y esquemas reales;
2. `information_schema.columns` para tipos, nulabilidad y defaults;
3. `pg_constraint` y `pg_get_constraintdef()` para PK, FK, UNIQUE y CHECK;
4. `pg_indexes`/`pg_catalog` para índices e IDENTITY;
5. SELECT de conteos y relaciones usando solo nombres previamente descubiertos;
6. comparación con `apps/bingos/models.py` y el contrato del plan.

### 7.3 Restricciones condicionalmente recomendadas

Solo si se demuestra que faltan:

- `UNIQUE(idcarton,idpartida)` en la tabla real de participaciones;
- FK `carton.idbingo → bingo.idbingo`;
- FK compuesta `(idcarton,idbingo)` hacia el maestro;
- FK compuesta `(idpartida,idbingo)` hacia la ronda;
- CHECK de estado de participación;
- CHECK de índice positivo o nulo;
- CHECK de origen/asignación original.

Antes de validar cualquier constraint deben ejecutarse diagnósticos de
duplicados, nulos, huérfanos y relaciones entre Bingos distintos en ensayo.

### 7.4 Índices condicionalmente recomendados

Solo si no hay equivalentes efectivos:

- `carton(idbingo)`;
- participación `(idpartida)`;
- participación `(idbingo)`;
- participación `(idpartida, estado_participacion)`;
- búsqueda por cartón cubierta por
  `UNIQUE(idcarton,idpartida)` o un índice equivalente.

### 7.5 Posibles scripts y reversión

No se crea ningún script ahora. Si la inspección futura demuestra brechas, el
artefacto deberá ubicarse en `sql/migraciones/` y contener:

- guardas de `current_database()` y esquema;
- preflight sin escritura;
- comentarios de tablas, columnas y restricciones afectadas;
- bloqueo y timeout explícitos para una futura ventana autorizada;
- reparación/backfill separado de la creación de constraints;
- validaciones postcambio;
- reversión documentada y probada primero en ensayo.

La reversión preferida será volver al código anterior manteniendo estructuras
aditivas. Un DROP de tabla o columna no será un rollback rutinario, porque
podría eliminar participaciones y resultados. Cualquier reversión física
requerirá respaldo, prueba de reconstrucción y autorización independiente.

### 7.6 Prioridades

| Prioridad | Acción |
|---:|---|
| 0 | Activar y confirmar la base de ensayo con rol de solo lectura |
| 1 | Completar el inventario físico y diagnóstico de integridad |
| 2 | Decidir si realmente hace falta SQL |
| 3 | Agregar pruebas de contrato sin cambiar comportamiento |
| 4 | Normalizar creación de cartones y rutas heredadas |
| 5 | Sincronizar rondas, conectar desempate y corregir reportes |

## 8. Siguiente cambio de código recomendado

No debe realizarse ningún cambio funcional mientras el contrato físico siga
bloqueado. Después de confirmar satisfactoriamente el esquema de ensayo, el
primer cambio de repositorio recomendado es agregar pruebas de contrato en
`apps/bingos/tests.py` para:

- maestro con tres rondas;
- cuarta ronda posterior;
- unicidad cartón-ronda;
- misma tarjeta ganadora en rondas distintas;
- desempate por participación;
- recaudación deduplicada.

Estas pruebas fijan el comportamiento esperado sin modificar producción.

El primer cambio funcional posterior debe reforzar
`crear_carton_maestro_para_bingo()` en `apps/bingos/services.py` como única
fuente autorizada para cartones nuevos, con validación de jugador, precio,
Bingo y rondas en el servidor. Después se convertirán las rutas heredadas en
compatibilidad sin escritura y se implementará la creación atómica de ronda
con participaciones.

## 9. Consultas y comandos ejecutados

### 9.1 Consultas SQL

Ninguna. No se ejecutaron siquiera SELECT de catálogo o conteos, porque la
configuración activa no era segura para esta fase.

### 9.2 Comandos locales de solo lectura

- búsqueda de `ENGINE`, `DB_NAME`, host y puerto declarados en
  `config/settings.py` mediante `rg`;
- filtro local que imprimió únicamente `DB_NAME` desde la configuración activa;
- búsquedas en los dos documentos fuente con `rg`;
- `.venv/bin/python manage.py check`: correcto, con resultado
  `System check identified no issues (0 silenced)`; no se pasó `--database`,
  no se abrió cursor ni se ejecutó SQL;
- `git status --short`.

No se mostró ni almacenó contraseña, usuario, cadena de conexión o contenido
completo de `.env`.

No se ejecutaron pruebas, porque esta fase solo añadió documentación y la
configuración no permitió habilitar de forma segura pruebas contra PostgreSQL.

## 10. Cambios realizados en la Fase 0.6

- Archivo creado: `docs/CONTRATO_ESQUEMA_POSTGRESQL_HIBRIDO.md`.
- Código funcional modificado: ninguno.
- Modelos, migraciones, rutas, servicios y plantillas modificados: ninguno.
- Scripts SQL creados o ejecutados: ninguno.
- PostgreSQL consultado o modificado: no.
- Base real `bingo`: no conectada, no consultada y no alterada.
