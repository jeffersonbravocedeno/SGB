# Auditoría técnica real de SIAB / CoopBingo

Fecha de auditoría: 2026-07-05  
Fase: 0 — diagnóstico previo a cambios funcionales o visuales  
Repositorio auditado: `/home/jeffersonbravo/Escritorio/bingo`  
Rama y revisión inicial: `feat/mejoras-ux-siab`, commit `2b0cab3`

## Alcance y método

Esta auditoría se realizó exclusivamente sobre el repositorio actual de SIAB.
No se consultaron ni copiaron proyectos externos. Se revisaron de forma
estática la configuración, las aplicaciones Django, modelos, formularios,
vistas, servicios, rutas, plantillas, permisos, pruebas y scripts SQL.

No se ejecutaron migraciones, DDL, DML, `flush`, `makemigrations`,
`showmigrations` ni consultas contra la base real `bingo`. Por esa razón, las
conclusiones sobre el estado físico actual de PostgreSQL distinguen entre:

- lo que exige el código actual;
- lo que los scripts proponen;
- lo que documentos anteriores registran como comprobado;
- lo que todavía no puede confirmarse sin una verificación explícitamente
  autorizada sobre PostgreSQL.

## Resumen ejecutivo

SIAB es una aplicación Django 5.2.15 organizada en siete aplicaciones propias:
`common`, `configuracion`, `socios`, `jugadores`, `finanzas`, `bingos` y
`seguridad`. Usa PostgreSQL, plantillas Django con Bootstrap 5, Channels con
Redis para tiempo real, ReportLab para PDF y OpenPyXL para Excel.

La configuración local efectiva declara `DB_NAME=bingo`; no existe una
configuración SQLite. Todos los 16 modelos de negocio propios tienen
`managed=False`, y las carpetas de migraciones de las aplicaciones solo
contienen `__init__.py`. El esquema de negocio se administra fuera de las
migraciones Django mediante SQL manual y modelos que mapean tablas existentes.

El código ya contiene una implementación híbrida relevante:

- `Carton.idbingo` vincula el cartón maestro con un Bingo;
- `Carton.idpartida` permanece como relación histórica opcional;
- `CartonPartidaBingo` representa una participación independiente por ronda;
- el flujo nuevo crea un maestro con un solo precio y una participación por
  cada ronda existente;
- ganador, índice y fecha de validación pueden guardarse por participación;
- los reportes de resumen general calculan cartones y recaudación sobre
  maestros únicos.

Sin embargo, la transición no está cerrada. Siguen activas rutas que crean un
cartón para una sola partida, formularios genéricos que permiten editar matriz,
precio, partida e índice, vistas que solo muestran cartones históricos y un
desempate de interfaz que todavía utiliza el servicio legado agrupado por
jugador. Además, crear una ronda nueva no crea participaciones para los
cartones maestros ya vendidos.

La evidencia documental del repositorio indica que el 2026-06-30 la base real
`bingo` todavía no tenía `carton.idbingo` ni `carton_partida_bingo`. Documentos
posteriores registran que el esquema híbrido sí fue aplicado y probado en
`bingo_ensayo_hibridos`. El script de expansión continúa marcado como
“PROPUESTA / NO EJECUTAR”. Sin consultar PostgreSQL no es correcto afirmar que
la base real actual soporte el modelo que exige el código.

Los riesgos de mayor prioridad son:

1. posible incompatibilidad entre el código híbrido y el esquema de `bingo`;
2. venta heredada por partida aún accesible, incompatible con el maestro por
   Bingo y con riesgo de cobrar el mismo concepto varias veces;
3. participaciones faltantes cuando se agregan rondas después de una venta;
4. desempate híbrido implementado en servicios pero no conectado a las rutas;
5. validación incompleta del estado del jugador, precio autorizado y pago;
6. recaudación repetida en columnas por ronda de los archivos Excel;
7. permisos administrativos demasiado amplios y sin rol de operador separado;
8. pantallas que exponen lenguaje de migración y datos internos.

## Arquitectura actual

### Capas y flujo

| Capa | Implementación actual | Observación |
|---|---|---|
| Configuración | `config/settings.py`, `config/urls.py`, `config/asgi.py`, `config/wsgi.py` | Configuración única por variables de entorno; PostgreSQL y Redis |
| Presentación | `templates/`, `static/css/styles.css`, `static/js/realtime_bingo.js` | Renderizado del servidor; Bootstrap por CDN; JavaScript para actualización pública |
| Vistas HTTP | `apps/*/views.py` | Vistas basadas principalmente en funciones; CRUD y orquestación en la misma capa |
| Formularios | `apps/*/forms.py`, `apps/common/forms.py` | Validación visual y de datos; mensajes en español |
| Servicios | `apps/bingos/services.py`, `apps/jugadores/services.py` | Bingo concentra reglas complejas; jugadores concentra autenticación y vinculación |
| Persistencia | Modelos Django `managed=False` | Mapean tablas físicas PostgreSQL; las PK antiguas se calculan manualmente |
| Tiempo real | Django Channels, Daphne, Redis, un consumer público | Un grupo WebSocket por partida/ronda |
| Reportes | `apps/bingos/reportes.py` | PDF de ronda y Excel de ronda/Bingo |
| Pruebas | `apps/bingos/tests.py`, `apps/seguridad/tests.py` | 284 pruebas `SimpleTestCase`; las demás apps solo tienen archivos vacíos |

### Aplicaciones instaladas

Además de las aplicaciones Django estándar, están instaladas:

- `daphne`;
- `crispy_forms` y `crispy_bootstrap5`;
- las siete aplicaciones propias de SIAB.

`channels` y `channels-redis` están en dependencias y se usan desde ASGI, aunque
`channels` no aparece como una entrada independiente en `INSTALLED_APPS`.

### Plantillas

La plantilla base es `templates/base.html`. La navegación común está en
`templates/includes/navbar.html` y `templates/includes/sidebar.html`. Los
componentes reutilizables incluyen mensajes, paginación, campos y errores de
formularios.

Las plantillas funcionales se agrupan así:

- `templates/socios/`: listado, detalle con pestañas, formularios y tablas
  parciales de ahorros, aportes y préstamos;
- `templates/jugadores/`: listado, alta/edición y detalle con acceso, cartones y
  sesiones;
- `templates/finanzas/`: panel, préstamos, pagos, ahorros y aportes;
- `templates/configuracion/`: panel y pantallas genéricas de catálogo;
- `templates/bingos/`: 18 pantallas para Bingos, rondas, cartones, jugador,
  público, operador, desempate y sesiones;
- `templates/registration/` y `templates/seguridad/`: autenticación, registro,
  cambio de contraseña y cuenta sin acceso.

### Formularios y validación

`FriendlyModelForm` centraliza estilos Bootstrap, campos de fecha, estados,
mensajes amigables, valores no negativos y traducción parcial de
`IntegrityError`. Los formularios de socios, jugadores, finanzas y
configuración agregan validaciones de unicidad y opciones de negocio.

En Bingo existen dos familias en paralelo:

- formularios de maestro híbrido: `GenerarCartonBingoForm`;
- formularios heredados o genéricos: `GenerarAsignarCartonForm`, `CartonForm`
  y `CartonPartidaForm`.

`PartidaBingoForm` y `CartonForm` exponen campos internos que no deberían ser
editados directamente por una persona administradora: bolas serializadas,
bingadores, matriz, índice de victoria y relaciones históricas.

### Servicios

`apps/bingos/services.py` concentra generación de matrices y códigos, estados
de ronda, extracción de bolas, validación de cartones, venta híbrida,
participaciones, ganador y desempate. Tiene tanto servicios legados basados en
`Carton.idpartida` como servicios híbridos basados en
`CartonPartidaBingo`.

`apps/jugadores/services.py` gestiona el grupo `Jugador`, creación de usuarios,
registro público, vinculación por alias y el decorador `jugador_required`.

`apps/common/ids.py` asigna PK enteras mediante `LOCK TABLE` y `MAX(pk) + 1`.
Esto preserva tablas históricas sin secuencias y evita carreras dentro de las
operaciones que lo llaman en una transacción, pero introduce bloqueo exclusivo
y limita la concurrencia.

Socios, finanzas y configuración no tienen capa de servicios propia: la lógica
de escritura está principalmente en sus vistas y formularios.

### Decoradores y middleware de acceso

- `admin_required`: permite únicamente usuarios autenticados con `is_staff` o
  `is_superuser`;
- `jugador_required`: exige pertenencia al grupo `Jugador`, un alias que
  coincida exactamente con `Jugador.aliasjugador` y estado `Activo`;
- `login_required`: se usa en la pantalla de cuenta sin acceso;
- decoradores HTTP limitan GET/POST en rutas públicas y acciones críticas.

No existen permisos propios por módulo, objeto o tarea. Tampoco existe un grupo
o decorador específico de operador de Bingo.

### Reportes PDF y Excel

| Reporte | Ruta | Implementación |
|---|---|---|
| PDF de ronda | `/partidas/<id>/reporte/pdf/` | ReportLab; datos, bolas, cartones y resultado |
| Excel de cartones de ronda | `/partidas/<id>/cartones/excel/` | OpenPyXL; históricos y participaciones híbridas |
| Excel resumen de Bingo | `/bingos/<id>/resumen/excel/` | Hoja por rondas y hoja de maestros únicos |

Los reportes son solo de lectura. Validan que maestro, participación, ronda y
Bingo coincidan antes de mezclar datos. Los archivos todavía muestran IDs
internos y distinciones técnicas entre registros históricos e híbridos.

### WebSockets

ASGI publica un único patrón:

`/ws/juego/partidas/<idpartidabingo>/`

`PartidaPublicaConsumer` comprueba que la partida exista, se une al grupo
`partida_<id>`, ignora comandos del cliente y solo emite datos públicos. Las
publicaciones se programan con `transaction.on_commit`, evitando informar un
cambio que luego se revierta. El payload no transmite el nombre del ganador;
solo indica `Confirmado`.

El WebSocket no usa `AuthMiddlewareStack`, por lo que es deliberadamente
público. La separación por partida está bien implementada. Cada conexión sí
realiza una consulta de existencia a PostgreSQL.

### Pruebas existentes

| Archivo | Clases reales | Pruebas | Cobertura predominante |
|---|---:|---:|---|
| `apps/bingos/tests.py` | 32 | 254 | Formularios, matrices, ventas, bolas, ganadores, híbridos, desempate, público, permisos, WebSocket y reportes |
| `apps/seguridad/tests.py` | 5 | 30 | Permisos, registro, acceso, privacidad y redirección |
| `apps/socios/tests.py` | 0 | 0 | Archivo inicial sin pruebas |
| `apps/jugadores/tests.py` | 0 | 0 | Archivo inicial sin pruebas |
| `apps/finanzas/tests.py` | 0 | 0 | Archivo inicial sin pruebas |
| `apps/configuracion/tests.py` | 0 | 0 | Archivo inicial sin pruebas |

Las 284 pruebas reales heredan de `SimpleTestCase` y están construidas con
objetos no persistidos y mocks. Esto permite ejecutarlas sin preparar una base
de datos. Hay una brecha clara de cobertura en socios, finanzas, configuración
y CRUD administrativo de jugadores.

## Mapa de apps

| App | Propósito real | Modelos o componentes principales |
|---|---|---|
| `common` | Infraestructura transversal | Formularios amigables, decorador administrativo, PK manual, paginación, contadores y filtros de plantillas |
| `configuracion` | Catálogos operativos | `Tiposocio`, `Metodopago`, `Plataformajuego`, `Regalo` |
| `socios` | Datos de cooperados y cuentas bancarias | `Socio`, `Cuentabancaria`; detalle integra préstamos, ahorros y aportes |
| `jugadores` | Perfil de juego y vínculo con autenticación | `Jugador`; creación de acceso Django, alias, estado y saldo |
| `finanzas` | Operación financiera del socio | `Prestamo`, `Pago`, `Ahorro`, `Aportesemanal` |
| `bingos` | Núcleo del Bingo | `Bingo`, `Partidabingo`, `Carton`, `CartonPartidaBingo`, `Sesionjuego`; juego, venta, ganador, desempate, reportes y tiempo real |
| `seguridad` | Entrada y clasificación de usuarios | Login, registro público, cambio de contraseña y cuenta sin acceso; no tiene modelo propio |

### Ubicación de los módulos solicitados

| Concepto | Implementación real |
|---|---|
| Socios | `apps/socios/models.py`: `Socio`; vistas y plantillas `socios/` |
| Jugadores | `apps/jugadores/models.py`: `Jugador`; servicios de autenticación por alias |
| Préstamos | `apps/finanzas/models.py`: `Prestamo` |
| Pagos | `apps/finanzas/models.py`: `Pago`, obligatoriamente vinculado a `Prestamo` |
| Ahorros | `apps/finanzas/models.py`: `Ahorro`, vinculado a socio y Bingo |
| Aportes | `apps/finanzas/models.py`: `Aportesemanal`, opcionalmente vinculado a una partida |
| Bingo | `apps/bingos/models.py`: `Bingo` |
| Rondas | `Partidabingo`; la interfaz aún alterna “Partida” y “Ronda” |
| Cartones | `Carton`; maestro híbrido o registro histórico según `idpartida` |
| Participación por ronda | `CartonPartidaBingo` |
| Ganadores | `Partidabingo.idjugadorganador`, `idbingadores` y estado/índice de `CartonPartidaBingo`; no hay modelo `Ganador` separado |
| Desempates | Campos de `Partidabingo` más servicios legados e híbridos; no hay tabla separada |
| Sesiones de juego | `Sesionjuego` |
| Plataformas | `Plataformajuego` en `configuracion` |
| Configuración | Tipos de socio, métodos de pago, plataformas y regalos |
| RNG | No hay modelo ni pantalla. La generación usa `random.SystemRandom` en el servidor |
| Core | No existe app, modelo o pantalla con ese nombre |
| Unidad monetaria | No existe modelo; los importes se muestran con `$` fijo |

## Mapa de rutas

El proyecto declara 78 rutas HTTP propias o de primer nivel, más las rutas
internas que aporta Django Admin y un WebSocket. La clasificación funcional no
siempre coincide con la autorización real: “operador” sigue usando
`admin_required`.

### Visitante público

| Ruta | Función |
|---|---|
| `/login/` | Inicio de sesión |
| `/registro/` | Registro de jugador y creación de usuario |
| `/health/` | Respuesta técnica `SIAB OK` |
| `/juego/` | Sala pública de rondas |
| `/juego/partidas/<id>/tablero/` | Tablero público de una ronda |
| `/juego/cartones/acceder/` | Consulta por código de cartón |
| `/juego/cartones/<codigo>/` | Vista pública del cartón y selección de ronda |
| `/ws/juego/partidas/<id>/` | Actualizaciones públicas de una ronda |

### Jugador autenticado

| Ruta | Función | Control real |
|---|---|---|
| `/mis-cartones/` | Listado privado | Grupo `Jugador`, alias coincidente y estado activo |
| `/mis-cartones/<codigo>/` | Detalle privado | Mismo control y propiedad del cartón |
| `/password-change/` | Cambio de contraseña | Usuario autenticado por la vista Django |
| `/password-change/done/` | Confirmación del cambio | Usuario autenticado |
| `/logout/` | Cierre de sesión | Sesión Django |
| `/seguridad/cuenta-sin-acceso/` | Explicación para usuario sin rol válido | Cualquier usuario autenticado |

### Administración general

Todas estas rutas usan `admin_required`; no hay permisos diferenciados.

| Prefijo | Rutas y tareas |
|---|---|
| `/` | Panel principal con contadores y accesos rápidos |
| `/socios/` | Listar, crear, ver y editar socio; crear y editar cuentas bancarias |
| `/jugadores/` | Listar, crear, ver y editar jugador; crear cuenta de acceso |
| `/finanzas/` | Panel; préstamos, pagos de préstamo, ahorros y aportes |
| `/configuracion/` | Panel y CRUD sin borrado de tipos de socio, métodos de pago, plataformas y regalos |
| `/bingos/` | Listar y crear Bingos |
| `/bingos/<id>/` | Detalle de Bingo |
| `/bingos/<id>/editar/` | Editar Bingo |
| `/bingos/<id>/partidas/nueva/` | Crear ronda |
| `/bingos/<id>/cartones/nuevo/` | Vender cartón maestro para el Bingo |
| `/bingos/<id>/resumen/excel/` | Exportar resumen |
| `/partidas/` | Listar rondas |
| `/partidas/<id>/` | Detalle de ronda |
| `/partidas/<id>/editar/` | Editar todos los campos de la ronda |
| `/partidas/<id>/reporte/pdf/` | Reporte PDF |
| `/partidas/<id>/cartones/excel/` | Excel de cartones/participaciones |
| `/cartones/` | Listado general de cartones |
| `/cartones/nuevo/` | Alta manual genérica de cartón |
| `/cartones/<id>/editar/` | Edición manual genérica |
| `/sesiones-juego/` | Listado de sesiones históricas |

### Operador de Bingo

Funcionalmente son rutas de operador, pero técnicamente cualquier `staff` o
superusuario puede usarlas y no existe un rol independiente.

| Ruta | Acción |
|---|---|
| `/partidas/<id>/consola/` | Iniciar, pausar, reanudar o finalizar; sacar bolas y validar |
| `/partidas/<id>/sacar-bola/` | Extraer la siguiente bola, solo POST |
| `/partidas/<id>/cartones/<carton>/validar/` | Validar ganador, solo POST |
| `/partidas/<id>/desempate/` | Pantalla de desempate |
| `/partidas/<id>/desempate/<jugador>/sortear/` | Sorteo legado por jugador, solo POST |
| `/partidas/<id>/desempate/confirmar/` | Confirmación legada, solo POST |
| `/partidas/<id>/cartones/nuevo/` | Flujo heredado de venta por una sola ronda |
| `/partidas/<id>/cartones/<carton>/editar/` | Edición de cartón histórico de ronda |

### Técnico o superusuario

| Ruta | Estado |
|---|---|
| `/admin/` | Django Admin; accesible a `staff` con permisos y a superusuarios |
| `/health/` | Endpoint técnico, actualmente público |

Django Admin registra directamente 15 modelos de negocio. No registra
`CartonPartidaBingo`, pero sí permite al superusuario crear, editar y eliminar
filas de otros modelos `managed=False`, incluidos pagos, cartones, sesiones y
partidas. Esto evita las reglas de los formularios SIAB y permite borrado
físico con la confirmación estándar de Django.

## Mapa de permisos

| Perfil | Regla real | Capacidades | Brecha |
|---|---|---|---|
| Visitante | Sin autenticación | Sala, tablero, consulta por código, registro y login | No hay rate limiting para probar códigos de cartón |
| Jugador | Grupo `Jugador` + alias exacto + estado `Activo` | Solo sus cartones privados y pantallas públicas | No hay permisos por objeto más allá de propiedad del cartón |
| Administrador | `is_staff` o `is_superuser` | Todos los módulos administrativos y de operador | Un solo indicador habilita finanzas, configuración y operación de Bingo |
| Operador | No existe como perfil técnico | Usa las mismas rutas de administrador | No se puede conceder operación sin conceder toda la administración SIAB |
| Técnico | `is_staff` y permisos de Django Admin | `/admin/` | Puede evadir servicios de negocio; el superusuario puede borrar historial |
| Usuario autenticado sin rol | Sesión válida | Pantalla “cuenta sin acceso” y cambio de contraseña | No tiene módulo funcional |

No se encontraron usos de `permission_required`, permisos personalizados,
grupos administrativos, permisos por Bingo ni restricciones por sede. El
grupo `Jugador` se crea dinámicamente con `get_or_create` durante la creación
de accesos.

## Estado de PostgreSQL

### Configuración

| Elemento | Estado |
|---|---|
| Motor | `django.db.backends.postgresql` |
| Base local efectiva | `.env`: `bingo` |
| Base del ejemplo | `.env.example`: `siab_db` |
| Host/puerto/usuario/clave | Variables `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` |
| Persistencia de conexión | `DB_CONN_MAX_AGE`, valor por defecto 60 segundos |
| SQLite | No configurado ni usado |

La diferencia entre `bingo` y `siab_db` en el ejemplo y en los documentos
iniciales puede inducir a ejecutar comandos en una base equivocada. Debe
corregirse documentalmente en una fase autorizada, sin cambiar la base
efectiva por accidente.

### Modelos `managed=False`

| App | Tablas mapeadas |
|---|---|
| `configuracion` | `tiposocio`, `metodopago`, `plataformajuego`, `regalo` |
| `socios` | `socio`, `cuentabancaria` |
| `jugadores` | `jugador` |
| `finanzas` | `prestamo`, `pago`, `ahorro`, `aportesemanal` |
| `bingos` | `bingo`, `partidabingo`, `carton`, `carton_partida_bingo`, `sesionjuego` |

Los 16 modelos de negocio son no administrados. Las tablas estándar de
autenticación, sesiones, permisos y administración siguen perteneciendo a
Django y tienen sus migraciones dentro de los paquetes instalados.

### Estrategia de migraciones

- las seis apps con modelos tienen carpeta `migrations/`, pero solo
  `__init__.py`;
- no hay archivos `0001_*.py` propios;
- no se debe usar `makemigrations` para intentar construir el esquema
  aprobado;
- las PK históricas son `IntegerField` sin secuencia según la documentación y
  se generan en aplicación con bloqueo de tabla;
- la nueva PK de `carton_partida_bingo` está mapeada como `AutoField` y exige
  una secuencia/IDENTITY física.

### SQL existente

| Archivo | Tipo | Estado documental |
|---|---|---|
| `DATABASE/00_PREFLIGHT_CARTONES_HIBRIDOS.sql` | Diagnóstico de esquema y datos | Solo lectura; usado históricamente |
| `DATABASE/02_MIGRACION_CARTONES_HIBRIDOS_PROPUESTA.sql` | Expansión, backfill, constraints e índices | Bloqueado con `\quit`; “NO EJECUTAR” |
| `DATABASE/03_VALIDACION_CARTONES_HIBRIDOS.sql` | Validación posterior | Solo lectura |
| `DATABASE/04_ROLLBACK_CARTONES_HIBRIDOS_PROPUESTA.sql` | Reversión destructiva | Propuesta; no ejecutar automáticamente |
| `DATABASE/actualizar_estados_partidabingo.sql` | Cambio de CHECK y valores de estado | DDL/DML manual con bloque de reversión |
| `DATABASE/01_RESPALDO_CARTONES_HIBRIDOS.md` | Procedimiento de respaldo | Documentación, no script ejecutable |

No existe todavía `sql/migraciones/`. Cualquier cambio físico nuevo debe
crearse allí conforme al Prompt Maestro; no corresponde mover ni ejecutar los
scripts existentes durante esta auditoría.

### Soporte físico inferido

| Componente | Código actual | Evidencia sobre `bingo` | Evidencia sobre ensayo |
|---|---|---|---|
| Tablas históricas | Requeridas por todos los modelos | Confirmadas en el preflight del 2026-06-30 | Confirmadas documentalmente |
| `carton.idbingo` | Obligatorio | El último preflight documentado indicó que no existía; no hay confirmación posterior autorizada | Documentado como existente y no nulo |
| `carton_partida_bingo` | Obligatoria para flujo híbrido | El último preflight indicó que no existía; la propuesta sigue bloqueada | Documentada con 12 filas históricas |
| PK IDENTITY de participaciones | Requerida por `AutoField` | No confirmada | Documentada y probada |
| Constraints de mismo Bingo y unicidad | Esperadas por los servicios | No confirmadas | Documentadas y validadas |
| Nuevos estados de ronda | El código usa siete estados | La consola comprueba la CHECK en tiempo de ejecución; estado actual no confirmado | Pruebas anteriores reportan compatibilidad |

Conclusión: el código híbrido parece desarrollado y validado contra
`bingo_ensayo_hibridos`, pero el estado físico de `bingo` no debe asumirse. Una
verificación futura necesitará autorización explícita y deberá ser de solo
lectura antes de proponer cualquier aplicación de SQL.

## Estado de cartones híbridos

### Confirmaciones del código

1. `Carton` sí tiene `idbingo`, obligatorio en el modelo.
2. `Carton` sí conserva `idpartida`, opcional y marcado como histórico.
3. Sí existe el modelo `CartonPartidaBingo`, tabla
   `carton_partida_bingo`, con unicidad ORM `(idcarton, idpartida)`.
4. El precio pagado está únicamente en `Carton.preciopagado`; la participación
   no tiene importe.
5. El índice de victoria nuevo está en cada participación; el índice de
   `Carton` queda como compatibilidad histórica.

### Creación actual

El flujo nuevo es:

`bingo_carton_nuevo` → `GenerarCartonBingoForm` →
`crear_carton_maestro_para_bingo`.

Dentro de `transaction.atomic()` el servicio:

- valida que Bingo y jugador tengan PK;
- valida que el precio sea numérico, finito y positivo;
- bloquea el Bingo y sus rondas con `select_for_update()`;
- exige al menos una ronda y que todas estén `Programada` o `En espera`;
- genera matriz y código en el servidor;
- crea un solo cartón con `idbingo`, precio, jugador, matriz y compra;
- deja `idpartida` e `indicevictoria` en `NULL`;
- crea una participación `Pendiente` por cada ronda actual;
- revierte toda la operación si falla una participación.

`IntegrityError`, `ValidationError` y errores de base se convierten en mensajes
controlados desde la vista. El bloqueo exclusivo usado para la PK manual del
maestro también evita dos `MAX(id)+1` concurrentes, aunque con alto costo de
concurrencia.

### Generación de participaciones por ronda

Las participaciones se crean solamente durante la venta y para las rondas que
ya existen. `partida_nueva` no recorre los maestros existentes ni crea la
participación de la nueva ronda. Tampoco se encontró un signal, tarea o comando
que lo haga después. Esto incumpliría la regla “el cartón participa en cada
ronda del Bingo” si se permite agregar rondas después de vender cartones.

### Rutas heredadas activas

Persisten tres caminos peligrosos:

1. `/partidas/<id>/cartones/nuevo/` llama a
   `crear_y_asignar_carton` y crea un cartón ligado a una sola ronda;
2. `/cartones/nuevo/` guarda manualmente `CartonForm`;
3. las dos rutas de edición permiten modificar matriz, jugador, precio,
   compra, estado, partida e índice.

El servicio legado no asigna `Carton.idbingo`. Por tanto, es incompatible con
el modelo actual y con el esquema híbrido propuesto, donde `idbingo` es
obligatorio. Además, usarlo una vez por ronda crea maestros y precios separados,
lo que puede duplicar recaudación para un único derecho de participación.

### Ganadores y desempate

La validación híbrida comprueba en el servidor participación, cartón, ronda,
Bingo, estado, matriz, bolas e índice. Usa transacción y bloquea ronda,
participaciones y maestros en orden. Un mismo maestro puede quedar `Ganador`
en varias rondas diferentes.

Hay servicios híbridos correctos para sortear y confirmar desempate por
participación. Sin embargo, las vistas y URLs de desempate llaman todavía a
`sortear_balota_desempate` y `confirmar_y_finalizar_desempate`, que agrupan por
jugador. Al recibir candidatos híbridos, ese normalizador descarta el
identificador de participación al volver a serializar. La confirmación legada
actualiza `Partidabingo`, pero no marca las participaciones ganadora/perdedoras.
La integración de desempate híbrido está, por tanto, incompleta.

### Precio, pago y recaudación

El diseño de almacenamiento no duplica el precio: un maestro tiene un precio y
sus participaciones no. El Excel general de Bingo calcula el total sobre
maestros únicos.

Persisten dos brechas:

- el servicio acepta cualquier precio positivo enviado por el formulario; no
  exige el precio de `Bingo.preciocarton`, no valida descuento autorizado y no
  registra estado, método o confirmación del pago;
- en la hoja `Resumen de partidas` y en el Excel de una ronda se copia y suma
  `Carton.preciopagado` por participación. Un mismo pago reaparece en cada
  ronda. Aunque el resumen final del Bingo es correcto, esas columnas pueden
  interpretarse o sumarse como recaudación real duplicada.

`Pago` no se reutiliza para cartones, lo cual es correcto: su FK obligatoria
apunta a `Prestamo`. No existe todavía una entidad de venta/pago de cartón.

### Validación obligatoria en servidor

| Regla | Estado actual |
|---|---|
| Bingo y ronda coherentes | Implementada en servicios híbridos y reforzada por constraints propuestos |
| Matriz | Generada y validada en servidor en el flujo nuevo |
| Ganador e índice | Validados en servidor por participación |
| Precio positivo | Implementado |
| Precio autorizado | No implementado; el POST decide cualquier valor positivo |
| Jugador existente | Parcial: se exige PK, pero el formulario lista también suspendidos o morosos |
| Estado de pago | No existe en el flujo de cartones |
| Doble venta/asignación | La creación nueva es atómica; la unicidad cartón-ronda evita duplicar una participación |
| Edición concurrente | Las ediciones genéricas usan `atomic()` pero no `select_for_update()` |
| Datos críticos desde JavaScript | El JavaScript público solo presenta datos; las acciones críticas se recalculan en servidor |

## Riesgos encontrados

| Prioridad | Riesgo | Evidencia e impacto |
|---|---|---|
| Crítica | Esquema real no confirmado | `.env` apunta a `bingo`, pero la última evidencia de esa base no contiene las estructuras que el ORM consulta |
| Crítica | Flujo heredado por ronda activo | Botones en detalle y consola llevan a una venta incompatible con `idbingo` obligatorio y susceptible de cobro repetido |
| Alta | Alta/edición manual de cartones | Permite introducir matriz, partida, índice, precio y estado sin el servicio híbrido ni bloqueo de fila |
| Alta | Rondas añadidas después de la venta | Los maestros existentes no reciben una participación automática |
| Alta | Desempate híbrido no integrado | Las rutas usan servicios por jugador y no actualizan el resultado individual de las participaciones |
| Alta | Pago y precio insuficientemente validados | No hay confirmación de pago ni precio autorizado; un usuario staff decide el valor enviado |
| Alta | Recaudación por ronda ambigua | El mismo precio se suma en cada ronda del resumen, aunque el total general sí deduplica maestros |
| Alta | Permisos demasiado amplios | Cualquier `staff` accede a socios, finanzas, configuración y operación de Bingo |
| Alta | Django Admin evita reglas SIAB | Superusuarios pueden editar o borrar directamente tablas históricas no administradas |
| Media | Pantallas incompletas para híbridos | Detalle de Bingo y detalle de ronda consultan solo `Carton.idpartida`; omiten maestros/participaciones nuevas |
| Media | Listado de cartones engañoso | Un híbrido muestra partida vacía y se ofrece edición genérica |
| Media | Consulta pública por código | No hay limitación de intentos; códigos históricos cortos pueden ser enumerables, aunque no se muestra el nombre del jugador |
| Media | PK manual con bloqueo de tabla | Es consistente bajo transacción, pero serializa altas y puede afectar rendimiento |
| Media | Estados físicos inciertos | La consola consulta una CHECK de PostgreSQL y muestra instrucciones técnicas si no coincide |
| Media | Cobertura desigual | No hay pruebas reales para socios, finanzas, configuración ni CRUD de jugadores |
| Baja | Documentación de base divergente | `.env.example`, `README.md` y `docs/02_base_datos.md` usan `siab_db`, no `bingo` |

No se encontraron rutas SIAB de borrado en los módulos propios. El borrado
sigue disponible a través de Django Admin según permisos.

## Pantallas existentes del jugador

| Pantalla | Ruta | Estado funcional |
|---|---|---|
| Registro | `/registro/` | Crea `Jugador`, `User` y grupo en una transacción |
| Login | `/login/` | Redirige jugadores a “Mis cartones” |
| Mis cartones | `/mis-cartones/` | Muestra maestros propios, tipo, ronda elegida, última bola y progreso |
| Detalle privado | `/mis-cartones/<codigo>/` | Matriz, rondas, estado, progreso y tiempo real |
| Sala pública | `/juego/` | Lista todas las rondas y estados |
| Tablero público | `/juego/partidas/<id>/tablero/` | Bolas, resultado y WebSocket |
| Consulta por código | `/juego/cartones/acceder/` | Acceso sin autenticación al cartón identificado por código |
| Cartón público | `/juego/cartones/<codigo>/` | Matriz y rondas; no muestra el dueño |
| Cambio de contraseña | `/password-change/` | Formulario estándar adaptado al español |

Problemas de experiencia del jugador:

- “Cartón de Bingo” frente a “Histórico por partida” revela una distinción de
  migración que no ayuda a jugar;
- “Índice de victoria” y “Validación” son datos internos en el detalle privado;
- “Mis cartones” tiene nueve columnas y mezcla estado del cartón, estado de
  ronda y estado de participación;
- no existe una vista simple de compra/pago porque la venta es administrativa;
- la sala lista todas las rondas sin agrupación visible por Bingo.

## Pantallas existentes del administrador

| Área | Pantallas actuales |
|---|---|
| Inicio | Contadores generales y cinco accesos por módulo |
| Socios | Lista, formulario, detalle con pestañas y cuentas bancarias |
| Jugadores | Lista, formulario, detalle, creación de acceso, cartones y sesiones |
| Finanzas | Panel y pantallas separadas de préstamos, pagos, ahorros y aportes |
| Configuración | Panel y CRUD genérico de tipos, métodos, plataformas y regalos |
| Bingos | Lista, alta/edición, detalle, venta híbrida y Excel |
| Rondas | Lista, alta/edición, detalle, PDF, Excel, consola y desempate |
| Cartones | Lista, alta/edición genérica, generación heredada y generación híbrida |
| Sesiones | Listado histórico por jugador, plataforma y ronda |
| Técnico | Django Admin en `/admin/` |

### Pantallas confusas o sobrecargadas

1. **Consola del operador**: combina estado, acciones, ganador, desempate,
   extracción, historial, tablero de 75 bolas, dos validadores de cartones y
   dos inventarios. Muestra conceptos de migración y hasta instrucciones SQL.
2. **Formulario de ronda**: permite editar ganador, bolas serializadas, última
   bola, indicador de desempate, JSON de bingadores y bola mayor, además de los
   datos normales de planificación.
3. **Alta/edición genérica de cartón**: pide una matriz textual y un índice de
   victoria. Compite con la acción segura “Vender cartón para todo el Bingo”.
4. **Detalle de Bingo**: promueve venta híbrida, pero la tabla “Cartones
   relacionados” excluye precisamente los maestros híbridos por filtrar
   `idpartida__idbingo`.
5. **Detalle de ronda**: solo lista cartones históricos y conserva botones de
   generación heredada; las participaciones híbridas aparecen únicamente en
   la consola.
6. **Listado general de cartones**: una única columna “Partida” no representa
   un maestro con varias rondas y ofrece la misma edición para ambos tipos.
7. **Detalle de jugador**: mezcla perfil, cuenta técnica Django, cartones y
   sesiones. El texto “Crea una cuenta Django” no es lenguaje administrativo.
8. **Sesiones de juego**: es un historial técnico; no equivale a “Jugadores
   conectados” ni distingue conexiones activas de registros cerrados.
9. **Reportes**: muestran IDs internos y tipos de persistencia; la recaudación
   por ronda puede interpretarse como cobro real repetido.

El detalle de socio ya usa pestañas, lo que reduce la sobrecarga aunque integra
cinco temas en una sola ruta. Finanzas y configuración están mejor separadas
por tarea que el módulo de Bingo.

## Textos técnicos visibles

| Texto actual | Dónde aparece | Recomendación futura |
|---|---|---|
| “Partidas”, “Partidas de bingo” | Navegación interna, listas, formularios y reportes | “Rondas del Bingo” |
| “Venta híbrida” | Detalle de Bingo | “Venta válida para todas las rondas” |
| “Cartón maestro” / “Código maestro” | Venta, consola y reportes | “Cartón” / “Código del cartón” |
| “Participaciones híbridas” | Consola | “Participaciones por ronda” |
| “Histórico por partida” / “flujo heredado” | Jugador, administrador y consola | Ocultar la distinción o mostrar “Cartón anterior” solo si es imprescindible |
| `Carton.idpartida` | Consola | No mostrar nombres de campos ni tablas |
| “Índice de victoria” / “Índice” | Formularios, jugador y consola | Ocultarlo o traducirlo a un dato de resultado comprensible |
| “Bingadores” | Formulario de ronda | “Cartones candidatos”, en una pantalla controlada, no como JSON editable |
| “Matriz de números” como texto | Formulario genérico | “Vista previa del cartón” generada por el servidor |
| “La base de datos… CHECK… PostgreSQL” | Consola | “El sistema requiere una actualización técnica. Contacte al responsable.” |
| `DATABASE/actualizar_estados_partidabingo.sql` | Consola y errores de formulario | Registrar el detalle técnico en logs/documentación, no en la interfaz |
| “Crea una cuenta Django” | Detalle de jugador | “Crear acceso al sistema” |
| “Sesiones de juego” / “Plataforma” | Jugador y listado de sesiones | “Jugadores conectados” y “Canal de acceso”, según la decisión funcional |
| “ID de Bingo/partida/cartón” | PDF y Excel | Código o nombre de negocio; mantener ID solo en una hoja técnica autorizada |
| “Jugador #<id>” | Desempate | Alias o “Jugador sin alias”; no exponer ID interno |

No se encontraron los literales visibles `PartidaBingo`,
`CartonPartidaBingo`, `SesionJuego`, `PlataformaJuego`, `RNG`, `Core` o
`UnidadMonetaria` en las plantillas. Sí aparecen equivalentes técnicos y el
nombre literal `Carton.idpartida`.

## Archivos recomendados para modificar en cada fase futura

| Objetivo futuro | Archivos principales | Restricción |
|---|---|---|
| Navegación y lenguaje de negocio | `templates/includes/sidebar.html`, `templates/includes/navbar.html`, `config/views.py`, plantillas de cada módulo | No cambiar rutas ni permisos de forma implícita |
| Simplificar administración de Bingo | `templates/bingos/detalle.html`, `partida_detalle.html`, `consola_operador.html`, `partidas_lista.html`, `cartones_lista.html` | Separar tareas sin eliminar funciones heredadas hasta autorizar su retiro |
| Cerrar flujo híbrido | `apps/bingos/views.py`, `forms.py`, `services.py`, `urls.py`, `tests.py` | Mantener `atomic`, bloqueos y manejo de `IntegrityError` |
| Incorporar rondas nuevas a maestros | `apps/bingos/services.py`, `views.py`, `tests.py` | Requiere decidir política de backfill antes de escribir datos |
| Integrar desempate híbrido | `apps/bingos/views.py`, `urls.py`, `services.py`, `templates/bingos/desempate_operador.html`, `tests.py` | Operar por participación, no agrupar cartones por jugador |
| Venta, precio y pago de cartón | Nuevo servicio/formulario y posiblemente nuevo modelo/SQL | No reutilizar `Pago`; cualquier esquema nuevo requiere autorización |
| Reportes sin duplicar recaudación | `apps/bingos/reportes.py`, vistas y pruebas de reportes | Distinguir participación de transacción económica |
| Experiencia del jugador | `templates/bingos/mis_cartones.html`, `mi_carton_detalle.html`, `carton_publico.html`, vistas auxiliares | No exponer índices, IDs ni términos de migración |
| Permisos por tarea | `apps/common/decorators.py`, `apps/jugadores/services.py`, vistas, plantillas y pruebas de seguridad | Definir primero roles administrativos y de operador |
| Jugadores conectados | `apps/bingos/consumers.py`, `models.py`, `views.py`, `sesiones_lista.html` | Definir qué significa “conectado”; posible impacto de esquema |
| Protección de Django Admin | `apps/*/admin.py`, `config/urls.py`, configuración y permisos | No retirar la ruta sin autorización; impedir escrituras peligrosas |
| Cobertura de apps administrativas | `apps/socios/tests.py`, `jugadores/tests.py`, `finanzas/tests.py`, `configuracion/tests.py` | Usar pruebas aisladas o una base de ensayo explícita |
| Cambio físico PostgreSQL | Nuevo archivo en `sql/migraciones/` y documentación en `docs/` | Validaciones, reversión, ensayo primero y nunca ejecución automática en `bingo` |

`apps/bingos/models.py` solo debe modificarse después de confirmar el esquema
físico objetivo. Los modelos actuales son contratos con PostgreSQL, no una
fuente autorizada para generar migraciones.

## Decisiones que requieren confirmación del usuario antes de tocar base de datos

1. Autorizar o no una inspección **solo lectura** de la base real `bingo` para
   confirmar `current_database()`, columnas, tabla híbrida, constraints,
   índices y CHECK de estados.
2. Confirmar si la migración híbrida ya fue aplicada fuera de lo que registra
   el repositorio. No debe deducirse por el estado del código.
3. Definir si `carton_partida_bingo` y `carton.idbingo` son el diseño físico
   definitivo antes de crear cualquier nuevo script.
4. Definir qué ocurre con los cartones vendidos cuando se agrega una ronda:
   participación automática, autorización manual o prohibición de agregarla.
5. Definir el tratamiento de los 12 cartones históricos: conservar solo su
   ronda original o ampliar participaciones mediante una decisión explícita.
6. Decidir si la venta de cartón necesita una entidad propia de venta/pago con
   método, referencia, confirmación, anulación y auditoría. `Pago` no sirve
   porque pertenece a préstamos.
7. Definir si el precio debe ser siempre `Bingo.preciocarton` o si se permiten
   descuentos con permiso y motivo.
8. Confirmar la política de estados físicos de `Partidabingo` antes de aplicar
   `actualizar_estados_partidabingo.sql` o una versión nueva en
   `sql/migraciones/`.
9. Autorizar cualquier backfill de `idbingo`, creación de participaciones,
   índices, FK, `CHECK`, `UNIQUE` o cambio de nulabilidad. La prueba debe ocurrir
   primero en `bingo_ensayo_hibridos`.
10. Confirmar si las columnas históricas `Carton.idpartida` e
    `indicevictoria` deben permanecer indefinidamente. No deben retirarse en una
    refactorización de interfaz.
11. Definir roles de administrador, operador, finanzas y técnico. Esto puede
    requerir datos de grupos/permisos, aunque no necesariamente cambios en las
    tablas de negocio.
12. Autorizar por separado cualquier ejecución en `bingo`. Crear un script no
    constituye autorización para ejecutarlo.

## Verificación de esta fase

Para el inventario se usaron únicamente comandos de lectura: `pwd`,
`git status --short`, `git log`, `rg --files`, `rg`, `sed`, `find`, `wc` y
pequeños análisis AST ejecutados con `python3`. Esos análisis solo leyeron
archivos Python; no importaron Django ni abrieron conexiones. El comando
`python` global no está instalado en el entorno, por lo que las comprobaciones
Django se ejecutaron con el intérprete versionado del proyecto,
`.venv/bin/python`.

Los comandos Django se ejecutaron con la variable temporal
`DB_NAME=bingo_ensayo_hibridos` y con
`PGOPTIONS='-c default_transaction_read_only=on'`. No se utilizó la base real
`bingo`. Todas las pruebas seleccionadas son `SimpleTestCase`; Django no creó
una base de pruebas.

| Comando | Resultado |
|---|---|
| `DB_NAME=bingo_ensayo_hibridos PGOPTIONS='-c default_transaction_read_only=on' .venv/bin/python manage.py check` | Correcto: `System check identified no issues (0 silenced)` |
| `DB_NAME=bingo_ensayo_hibridos PGOPTIONS='-c default_transaction_read_only=on' .venv/bin/python manage.py test apps.bingos.tests apps.seguridad.tests --verbosity 1` | Correcto: 284 pruebas, 0 fallos, 0 errores |
| `node --check static/js/realtime_bingo.js` | Correcto, sin salida |
| `git diff --check` | Correcto, sin errores de espacios |

Durante las pruebas aparecieron dos registros de error esperados por casos que
simulan un `DatabaseError` y una relación híbrida incoherente. No son fallos de
la suite. También apareció la advertencia de Django
`No directory at: .../staticfiles/`; `STATIC_ROOT` todavía no existe en el
workspace. Debe comprobarse `collectstatic` en una fase de despliegue, sin
mezclarlo con cambios de base de datos.

## Cambios realizados en la Fase 0

- Archivo creado: `docs/AUDITORIA_TECNICA_SIAB.md`.
- Modelos modificados: ninguno.
- Tablas, constraints, índices o datos modificados: ninguno.
- Migraciones creadas o ejecutadas: ninguna.
- Scripts SQL creados o ejecutados: ninguno.
- Base real `bingo`: no consultada y no modificada.
