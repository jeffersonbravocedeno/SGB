# Diagnostico actual SIAB / CoopBingo

Fecha de revision: 2026-06-27.

## 1. Funcionalidades existentes

El proyecto ya es una aplicacion Django existente. No se debe crear un proyecto nuevo.

Existe una estructura central `config` y apps propias dentro de `apps`:

- `apps.common`: helpers compartidos para paginacion, conteos seguros, formularios amigables y asignacion manual de claves primarias enteras.
- `apps.configuracion`: tipos de socio, metodos de pago, plataformas de juego y regalos.
- `apps.socios`: socios y cuentas bancarias.
- `apps.jugadores`: jugadores vinculables a socios.
- `apps.finanzas`: prestamos, pagos, ahorros y aportes semanales.
- `apps.bingos`: bingos, partidas, cartones y sesiones de juego.
- `apps.seguridad`: formularios de login y cambio de clave.

La configuracion usa PostgreSQL:

- `ENGINE = django.db.backends.postgresql`.
- Las credenciales se leen desde `.env` mediante `python-decouple`.
- No se inspecciono ni modifico `.env`.
- No se usa SQLite.

La interfaz principal ya existe con templates HTML propios basados en Bootstrap 5:

- `templates/base.html`.
- `templates/home.html`.
- parciales en `templates/includes/`.
- templates por modulo en `templates/bingos/`, `templates/jugadores/`, `templates/socios/`, `templates/finanzas/` y `templates/configuracion/`.

El dashboard principal esta en `config.views.home` y muestra accesos rapidos y metricas con `safe_count`.

## 2. Modelos y rutas existentes

### Modelos relacionados con bingo

En `apps/bingos/models.py` existen modelos no administrados por migraciones de Django:

- `Bingo`, tabla `bingo`.
- `Partidabingo`, tabla `partidabingo`.
- `Carton`, tabla `carton`.
- `Sesionjuego`, tabla `sesionjuego`.

En `apps/jugadores/models.py` existe:

- `Jugador`, tabla `jugador`.

En `apps/configuracion/models.py` existe:

- `Plataformajuego`, tabla `plataformajuego`.

No existe un modelo ni tabla detectada para `CartonPartidaBingo`. La relacion actual entre carton y partida se maneja con `Carton.idpartida`.

Todos estos modelos relevantes tienen `managed = False`, por lo que Django no debe crear ni alterar sus tablas.

### Rutas existentes de bingos

En `apps/bingos/urls.py` ya existian estas rutas:

- `bingos/`: lista de bingos.
- `bingos/nuevo/`: crear bingo.
- `bingos/<idbingo>/`: detalle de bingo.
- `bingos/<idbingo>/editar/`: editar bingo.
- `bingos/<idbingo>/partidas/nueva/`: crear partida dentro de un bingo.
- `partidas/<idpartidabingo>/`: detalle de partida.
- `partidas/<idpartidabingo>/editar/`: editar partida.
- `cartones/`: lista global de cartones.
- `cartones/nuevo/`: crear carton.
- `cartones/<idcarton>/editar/`: editar carton.
- `sesiones-juego/`: lista de sesiones de juego.

### Migraciones

Las apps propias solo contienen `migrations/__init__.py`; no hay migraciones de dominio creadas.

Se ejecuto `python manage.py showmigrations --plan`, pero no fue posible consultar el estado aplicado porque PostgreSQL no acepto conexion en este entorno y Django devolvio `OperationalError`. No se modifico `.env` ni se cambio la base.

Se ejecuto `python manage.py check` antes de implementar la etapa 1 y no reporto errores.

## 3. Funcionalidades faltantes para un bingo funcional

Para operar un bingo completo aun faltaban estas piezas:

- Lista propia de partidas.
- Estados de partida centralizados y coherentes.
- Consola del operador para cambiar estados.
- Vista enfocada en crear o asignar cartones dentro de una partida.
- Control de permisos para impedir que usuarios jugadores entren a pantallas administrativas.
- Manejo visual de bolas cantadas en detalle/consola.
- Logica futura para extraer bolas.
- Validacion futura de ganador y patrones de bingo.
- Flujo futuro de desempate automatico.
- Tiempo real con WebSockets.
- Canales, Redis/Daphne y actualizacion en vivo.

Queda fuera de esta etapa:

- Redis.
- Celery.
- Daphne.
- Django Channels.
- WebSockets.
- PDF.
- Excel.
- chat.
- sorteos automaticos.
- desempate automatico.

## 4. Archivos que se deben modificar en la etapa 1

Para implementar el nucleo sin tocar la estructura fisica de la base:

- `apps/bingos/forms.py`: centralizar choices de estados y crear formulario de carton por partida.
- `apps/bingos/views.py`: agregar lista de partidas, consola de operador y creacion/asignacion de cartones por partida.
- `apps/bingos/urls.py`: agregar rutas nuevas.
- `apps/bingos/tests.py`: pruebas basicas de estados y permisos.
- `apps/common/decorators.py`: helper de permisos administrativos.
- `apps/common/templatetags/siab_tags.py`: clases visuales para nuevos estados.
- `templates/bingos/*.html`: nuevas pantallas y enlaces desde pantallas existentes.
- `DOCUMENTACION/ETAPA_1_PARTIDAS.md`: documentacion final de la etapa.

No se requiere modificar modelos ni migraciones para esta etapa.

## 5. Campos actuales que se usaran para manejar una partida

En `Partidabingo` se usaran:

- `idpartidabingo`: identificador de la partida.
- `idbingo`: bingo al que pertenece.
- `idjugadorganador`: ganador, opcional mientras la partida no termine.
- `nombreronda`: nombre visible de la ronda o partida.
- `valorefectivo`: premio en efectivo.
- `premiomaterial`: premio material.
- `estadopartida`: estado funcional centralizado.
- `bolascantadas`: texto con las bolas ya extraidas, por ahora solo lectura/manual.
- `ultimabola`: ultima bola registrada, por ahora sin extraccion automatica.
- `haydesempate`: indicador manual de desempate.
- `idbingadores`: texto con posibles ganadores/bingadores.
- `bolamayordesempate`: dato manual para desempate.
- `horainicio`: fecha/hora de inicio programada o registrada.
- `horafin`: fecha/hora de cierre cuando se finaliza.

En `Carton` se usaran:

- `idcarton`: identificador de carton.
- `idjugador`: jugador asignado.
- `idpartida`: partida asociada.
- `codigocarton`: codigo unico.
- `matriznumeros`: matriz del carton.
- `indicevictoria`: valor auxiliar existente.
- `preciopagado`: precio pagado.
- `fechacompra`: fecha de compra/asignacion.
- `estadocarton`: estado del carton.

## 6. Riesgos o inconsistencias detectadas

- Los modelos son `managed = False`; cualquier cambio de esquema requiere autorizacion y debe hacerse fuera de migraciones automaticas.
- Las claves primarias son `IntegerField` sin secuencia gestionada por Django. El proyecto ya usa `apps.common.ids.assign_next_integer_pk` con bloqueo de tabla y `MAX(pk) + 1`.
- No existe tabla separada `CartonPartidaBingo`; si en el futuro un mismo carton debe reutilizarse en varias partidas, la estructura actual no lo soporta sin cambio fisico.
- Los estados existentes en formulario eran `En Juego`, `Verificando`, `Desempate` y `Finalizada`, pero el requerimiento pide `Programada`, `En espera`, `En curso`, `Pausada`, `Desempate`, `Finalizada` y `Cancelada`.
- `horainicio` es obligatorio y no hay un campo separado para fecha programada de partida; se reutilizara como hora planificada/inicio disponible.
- La app `seguridad` no define modelo propio de roles. La autenticacion usa `django.contrib.auth`; por tanto, para esta etapa se usara `is_staff`/`is_superuser` como criterio administrativo.
- Las rutas existentes solo tenian `login_required`; un usuario autenticado no administrativo podia entrar a pantallas operativas.
- `bolascantadas` es `TextField`; no hay restriccion de formato. En esta etapa se interpretara como lista JSON o texto separado por comas solo para visualizacion.
- `showmigrations --plan` no pudo consultar la base aplicada por falta de conexion PostgreSQL en el entorno actual.

## 7. Plan de implementacion por etapas

### Etapa 1: nucleo de partidas y cartones sin tiempo real

- Centralizar estados de partida en codigo.
- Ajustar formularios para usar los estados aprobados.
- Crear lista de partidas.
- Crear consola basica de operador.
- Permitir iniciar, pausar, reanudar y finalizar partida.
- Mostrar bolas ya extraidas sin generar nuevas bolas.
- Crear/asignar cartones a jugadores dentro de una partida.
- Proteger pantallas administrativas con permisos de staff/superusuario.
- Agregar pruebas basicas de estados y permisos.

### Etapa 2: extraccion manual/controlada de bolas

- Agregar accion para registrar bolas extraidas.
- Validar rango y repeticion de bolas.
- Actualizar `bolascantadas` y `ultimabola`.
- Mostrar tablero de bolas.

### Etapa 3: validacion de bingo y cierre operativo

- Validar cartones contra bolas cantadas.
- Registrar ganador manual/confirmado.
- Manejar estado `Desempate` de forma guiada.
- Bloquear cambios cuando la partida este finalizada o cancelada.

### Etapa 4: tiempo real

- Incorporar Django Channels, Daphne y Redis.
- Emitir eventos de estado y bolas.
- Crear pantalla de jugador en vivo.

### Etapa 5: reportes y exportaciones

- PDF de cartones/resultados.
- Excel de ventas/asistencia.
- Reportes financieros integrados.
