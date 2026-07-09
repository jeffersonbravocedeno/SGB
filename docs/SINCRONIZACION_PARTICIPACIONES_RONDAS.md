# Sincronización de participaciones al crear rondas

## 1. Problema corregido

El flujo administrativo `partida_nueva` guardaba una ronda mediante el
formulario, pero no generaba participaciones para los cartones maestros que ya
habían sido vendidos en el Bingo. Por esa razón, un cartón comprado para todo
el Bingo podía quedar fuera de una ronda creada posteriormente.

La estructura PostgreSQL ya soporta el caso correcto: `carton` identifica al
maestro, `carton_partida_bingo` representa su participación independiente y la
restricción física única sobre cartón+ronda impide registrar dos veces la misma
participación. Esta fase corrige el flujo de aplicación sin modificar ese
esquema ni realizar un backfill de datos históricos.

## 2. Flujo implementado

El servicio `crear_ronda_con_participaciones` de
`apps/bingos/services.py` ejecuta esta secuencia:

1. valida que el Bingo exista y que la ronda todavía no esté registrada;
2. abre `transaction.atomic()`;
3. recupera y bloquea el Bingo con `select_for_update()`;
4. asigna la clave primaria compatible con el esquema físico actual y guarda
   la ronda;
5. recupera y bloquea, en orden estable, los cartones maestros del mismo
   Bingo;
6. selecciona los maestros válidos según las reglas actuales de SIAB;
7. consulta las participaciones que ya existan para la ronda;
8. crea únicamente las participaciones faltantes con estado `Pendiente`;
9. confirma conjuntamente la ronda y sus participaciones.

No se usa `ignore_conflicts`. Una infracción de integridad se propaga fuera del
servicio para que Django revierta toda la transacción y la vista la convierta
en un error claro del formulario.

El servicio existente `crear_carton_maestro_para_bingo` conserva su flujo y
usa el mismo ayudante interno de creación de participaciones. Continúa
bloqueando primero el Bingo y generando una participación por cada ronda
vigente.

## 3. Cartones incluidos y excluidos

Una participación automática se crea solamente para un cartón que cumpla al
mismo tiempo estas condiciones existentes en SIAB:

- pertenece al Bingo bloqueado;
- `idpartida` es nulo, por lo que es un cartón maestro;
- tiene jugador asignado;
- su estado actual es `Vendido`, comparado sin distinguir mayúsculas ni
  espacios externos.

Quedan excluidos:

- cartones de otros Bingos;
- cartones históricos ligados directamente a una partida;
- cartones `Disponible` o `Cerrado`;
- cartones sin jugador asignado;
- cualquier otro estado no reconocido por la regla actual.

No se inventaron estados ni se amplió el comportamiento de registros
históricos. Tampoco se modificaron precios, pagos, premios, ventas o datos de
recaudación.

## 4. Rutas y servicios actualizados

| Elemento | Ubicación | Cambio |
|---|---|---|
| Servicio atómico | `apps/bingos/services.py` — `crear_ronda_con_participaciones` | Crea ronda y participaciones faltantes como una sola operación |
| Creación de maestro | `apps/bingos/services.py` — `crear_carton_maestro_para_bingo` | Reutiliza el ayudante de participación y mantiene el bloqueo inicial del Bingo |
| Vista administrativa | `apps/bingos/views.py` — `partida_nueva` | Delega la escritura al servicio y maneja errores de negocio, integridad y base de datos |
| Ruta existente | `apps/bingos/urls.py` — `bingos/<idbingo>/partidas/nueva/` | No cambió; ahora su vista usa el servicio atómico |
| Formulario | `apps/bingos/forms.py` — `PartidaBingoForm` | No requirió cambios |

No se encontró otra ruta que cree una `Partidabingo`. La edición de una ronda
existente no crea rondas nuevas y permanece fuera del alcance de esta fase.

La ruta heredada `partidas/<idpartidabingo>/cartones/nuevo/` continúa usando
`crear_y_asignar_carton`. Se conserva exclusivamente por compatibilidad
histórica y no es el flujo recomendado para nuevos cartones maestros.

Después de una creación correcta, la vista informa:

> La ronda fue creada correctamente y se registraron las participaciones de
> los cartones activos del Bingo.

## 5. Protección contra concurrencia

La creación de una ronda y la creación de un cartón maestro bloquean el mismo
registro principal de `Bingo` antes de crear sus registros dependientes.

Esto serializa las dos operaciones para un mismo Bingo:

- si la ronda obtiene primero el bloqueo, el nuevo cartón espera y, después,
  encuentra esa ronda entre las rondas vigentes;
- si el cartón obtiene primero el bloqueo, la nueva ronda espera y, después,
  encuentra el cartón entre los maestros válidos.

Los cartones maestros se bloquean con `select_for_update()` y se ordenan por
`idcarton`. También se bloquea cualquier participación ya localizada para el
par ronda+cartón. La restricción única física sigue siendo la última defensa
ante una duplicación.

Los Bingos diferentes usan registros de bloqueo diferentes y sus cartones no
entran en la consulta del servicio.

## 6. Manejo de errores y rollback

La ronda, sus claves y todas las participaciones se guardan dentro del mismo
`transaction.atomic()`. Si falla cualquier participación:

- la excepción sale del bloque atómico;
- PostgreSQL revierte la ronda y las participaciones creadas en esa operación;
- no se usa `ignore_conflicts` ni se oculta el error;
- `partida_nueva` maneja `IntegrityError` con el mecanismo de errores del
  formulario;
- otros errores de base de datos muestran que no se guardaron cambios
  parciales.

Las validaciones previas de Bingo, tipo de instancia y ronda ya registrada
ocurren antes de abrir la transacción.

## 7. Pruebas implementadas

Las pruebas están en `apps/bingos/tests.py` y usan `SimpleTestCase` con el ORM
y las transacciones simulados. El ejecutor informó `Skipping setup of unused
database(s): default`, por lo que no creó ni consultó una base de pruebas.

Casos cubiertos:

1. tres maestros válidos generan exactamente tres participaciones;
2. cartones de otro Bingo y cartones históricos o no válidos quedan fuera;
3. una participación existente no se duplica;
4. un `IntegrityError` al crear una participación sale del bloque atómico y se
   propaga para rollback;
5. crear una ronda no guarda cartones ni cambia su precio o el premio de la
   ronda;
6. una ronda ya registrada se rechaza antes de abrir una transacción;
7. la ruta administrativa llama al servicio y muestra el mensaje esperado;
8. el servicio de cartón maestro sigue creando una participación por cada
   ronda vigente;
9. el flujo heredado por partida continúa resolviendo con su servicio legado.

Resultados:

- ejecución relacionada: **21 pruebas aprobadas**;
- suite completa segura: **291 pruebas aprobadas**.

La suite completa usa pruebas sin acceso a base de datos. Los mensajes de log
por fallos simulados de base de datos y reportes forman parte de casos de error
ya existentes y no representan fallos de la ejecución.

## 8. Límites de esta fase

Esta fase no resuelve ni modifica:

- reportes ni el riesgo de duplicar recaudación al sumar filas de
  participación;
- liquidación, ventas, pagos, premios o gastos;
- backfill de participaciones históricas;
- conversión de cartones históricos por partida en maestros;
- eliminación o redirección definitiva de rutas heredadas;
- integración del desempate híbrido;
- mejoras visuales generales, navegación, menús o roles;
- modelos, migraciones, tablas, columnas, restricciones o índices de
  PostgreSQL.

No se ejecutó SQL ni se realizó ningún cambio de estructura o datos en
PostgreSQL. La base real `bingo` no forma parte de las pruebas de esta fase.
