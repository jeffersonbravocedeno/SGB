# Diagnostico Etapa 7: login real de jugadores, roles y panel personal

## Alcance

Este diagnostico revisa si SIAB / CoopBingo ya tiene una relacion fisica y
segura entre una cuenta autenticada de Django y un jugador del dominio. No
implementa login nuevo, panel "Mis cartones", migraciones, tablas, columnas,
pagos ni reclamos de Bingo.

Revision realizada sobre codigo, modelos `managed=False`, `models_inspectdb.py`,
rutas, vistas, formularios, plantillas de autenticacion y documentacion
existente.

## Respuestas directas

1. **Modelo o tabla de usuarios autenticados:** el proyecto usa el `User`
   estandar de Django (`django.contrib.auth.models.User`), respaldado por la
   tabla `auth_user`. No hay `AUTH_USER_MODEL` personalizado en
   `config/settings.py`.
2. **Roles o tipos de usuario:** existen los mecanismos estandar de Django
   `auth_group`, `auth_permission`, `is_staff` e `is_superuser`. En el dominio
   existe `Tiposocio.roltiposocio`, pero representa rol/tipo de socio, no rol de
   autenticacion. No se encontro tabla propia `tipousuario`, `rolusuario` o
   equivalente.
3. **Modelo o tabla de jugador:** `apps.jugadores.models.Jugador`, tabla
   fisica `jugador`.
4. **Relacion entre `User` y `Jugador`:** no existe FK, OneToOne ni tabla puente
   detectada entre `auth_user` y `jugador`. La unica relacion de `Jugador` es
   opcional hacia `Socio` mediante `Jugador.idsocio`.
5. **Login actual de administrador:** `/login/` usa `django.contrib.auth.views.LoginView`
   con `SIABAuthenticationForm`. Autentica contra el backend estandar de Django.
   El dashboard `/` requiere `login_required`.
6. **"Mis cartones" sin modificar PostgreSQL:** no de forma segura ni correcta.
   Se podria hacer una aproximacion por convencion usando `User.email`,
   `User.username`, `Jugador.correojugador` o `Jugador.aliasjugador`, pero no
   seria una relacion fisica ni auditable.
7. **Permisos reales actuales:** `admin_required` permite `is_staff` o
   `is_superuser` en rutas operativas de Bingo. Varias apps administrativas
   (`jugadores`, `socios`, `finanzas`, `configuracion` y `home`) usan solo
   `login_required`, por lo que cualquier `User` autenticado podria entrar si
   existe la cuenta.
8. **Datos necesarios para separar administrador, operador/cajero y jugador:**
   una identidad Django por persona/cuenta, un rol formal en `auth_group` o una
   tabla de perfil, una relacion fisica `User`-`Jugador` para jugadores, reglas
   de permisos por vista, estados de cuenta y datos de auditoria.
9. **Riesgo de usar alias, correo o codigo de carton como autenticacion:** alto.
   Son datos visibles o compartibles, pueden cambiar, pueden filtrarse en
   pantallas publicas o tickets, y no prueban propiedad de la cuenta.
10. **Cambio minimo de base recomendado si no existe relacion:** aprobar una
    relacion fisica 1:1 entre `auth_user` y `jugador`, preferiblemente con una
    tabla puente nueva `jugador_usuario` que no altere la tabla legacy
    `jugador`.

## Modelos y tablas encontrados

### Autenticacion Django

El proyecto incluye `django.contrib.auth` en `INSTALLED_APPS` y no define
`AUTH_USER_MODEL`. Por tanto, el usuario autenticado es el modelo estandar:

- Modelo: `django.contrib.auth.models.User`.
- Tabla: `auth_user`.
- Campos de control relevantes: `username`, `password`, `email`, `is_active`,
  `is_staff`, `is_superuser`.
- Roles/permisos Django disponibles: `auth_group`, `auth_permission`,
  relaciones many-to-many internas de Django para grupos y permisos.

El codigo actual no usa `has_perm`, `permission_required` ni grupos para
autorizar vistas de negocio.

### Seguridad

`apps/seguridad/models.py` no define modelos. La app contiene formularios:

- `SIABAuthenticationForm`, basado en `AuthenticationForm`.
- `SIABPasswordChangeForm`, basado en `PasswordChangeForm`.

`apps/seguridad/urls.py` no registra rutas propias. Las rutas reales de login,
logout y cambio de contrasena estan en `config/urls.py`.

### Jugador

`apps/jugadores/models.py` define:

- Modelo: `Jugador`.
- Tabla: `jugador`.
- `managed = False`.
- PK: `idjugador`.
- Relacion opcional: `idsocio -> Socio`.
- Identificadores de negocio: `aliasjugador` unico y nullable,
  `correojugador` unico y nullable.
- Estado: `estadocuentajugador`.
- No contiene FK hacia `auth_user`.

`models_inspectdb.py` confirma la misma estructura para `Jugador` y no muestra
una relacion hacia una tabla de usuarios.

### Socio y tipo de socio

`apps/socios/models.py` define:

- `Socio`, tabla `socio`, `managed = False`.
- `Socio.idtiposocio -> Tiposocio`.

`apps/configuracion/models.py` define:

- `Tiposocio`, tabla `tiposocio`, `managed = False`.
- Campo `roltiposocio`.

`roltiposocio` puede servir como clasificacion de socio, pero actualmente no
esta conectado a `auth_user`, `auth_group`, permisos Django ni al login.

### Bingo, cartones y sesiones

`apps/bingos/models.py` define:

- `Carton.idjugador -> Jugador`.
- `Partidabingo.idjugadorganador -> Jugador`.
- `Sesionjuego.idjugador -> Jugador`.

Estas relaciones permiten saber que cartones y sesiones pertenecen a un
jugador, pero no permiten saber que `request.user` es ese jugador.

## Relaciones reales encontradas

Relaciones fisicas relevantes:

- `Jugador.idsocio -> Socio`.
- `Socio.idtiposocio -> Tiposocio`.
- `Carton.idjugador -> Jugador`.
- `Partidabingo.idjugadorganador -> Jugador`.
- `Sesionjuego.idjugador -> Jugador`.

Relacion no encontrada:

- `User -> Jugador`.
- `Jugador -> User`.
- Tabla puente `User`/`Jugador`.
- Perfil propio que una `auth_user` con `Jugador`.

Conclusion: hoy no existe forma fisica de responder "estos son los cartones del
jugador autenticado" sin introducir una convencion externa o una relacion nueva.

## Flujo actual de login

Rutas en `config/urls.py`:

- `GET/POST /login/`: `LoginView` con `SIABAuthenticationForm`.
- `POST /logout/`: `LogoutView`.
- `GET/POST /password-change/`: `PasswordChangeView` con
  `SIABPasswordChangeForm`.
- `GET /password-change/done/`: confirmacion de cambio.

Configuracion:

- `LOGIN_URL = "/login/"`.
- `LOGIN_REDIRECT_URL = "/"`.
- `LOGOUT_REDIRECT_URL = "/login/"`.

El template `templates/registration/login.html` indica que el acceso es para
"gestion operativa del sistema". No existe una pantalla separada de login para
jugadores ni un redirect por rol.

## Roles existentes

Roles efectivos en codigo:

- `is_superuser`: acceso administrativo total donde se usa `admin_required`.
- `is_staff`: acceso administrativo donde se usa `admin_required`.
- usuario autenticado no staff: puede pasar vistas con `login_required`.
- visitante anonimo: puede usar rutas publicas de sala, tablero y consulta de
  carton por codigo.

Roles de negocio disponibles pero no conectados a login:

- `Tiposocio.roltiposocio`.
- `Jugador.estadocuentajugador` (`Activo`, `Suspendido`, `Moroso` en formulario).

Roles requeridos por el sistema pero no modelados aun:

- Administrador.
- Operador.
- Cajero.
- Jugador.

## Limitaciones actuales

- No hay relacion fisica `auth_user`-`jugador`.
- No hay separacion formal entre administrador, operador y cajero.
- Las rutas de Bingo operativas estan protegidas con `admin_required`, pero
  otras secciones administrativas aun usan solo `login_required`.
- Crear un `User` no crea ni vincula un `Jugador`.
- Crear un `Jugador` no crea ni vincula un `User`.
- `aliasjugador` y `correojugador` son datos de identificacion de dominio, no
  credenciales ni prueba de propiedad.
- La vista publica de carton por codigo no autentica al jugador; solo conoce un
  codigo de carton.
- `models_inspectdb.py` no muestra tablas de usuario/rol propias del dominio.

## Alternativa A: usar solo la base actual

Posible alcance sin modificar PostgreSQL:

- Mantener login Django solo para personal administrativo existente.
- Conservar consulta publica por codigo de carton.
- Crear una pantalla "Mis cartones" no autenticada por jugador, basada en codigo
  de carton o busqueda publica limitada.
- Usar `request.user.email == Jugador.correojugador` o
  `request.user.username == Jugador.aliasjugador` como convencion temporal.

Problemas:

- No es una relacion fisica.
- No hay garantia de unicidad cruzada entre `auth_user` y `jugador`.
- Si cambia el correo o alias, se rompe el acceso.
- No hay trazabilidad fuerte de quien reclama o consulta.
- Un usuario autenticado no staff podria entrar a vistas con `login_required`
  que hoy son administrativas en otras apps.

Dictamen: esta alternativa no debe usarse para un panel privado real de jugador.
Solo podria aceptarse como prototipo interno, explicitamente marcado como no
seguro.

## Alternativa B: cambio minimo de base necesario

Recomendacion minima: crear una tabla puente fisica para vincular cuentas Django
con jugadores sin alterar la tabla legacy `jugador`.

Propuesta conceptual:

```text
jugador_usuario
- id
- user_id       UNIQUE NOT NULL REFERENCES auth_user(id)
- idjugador     UNIQUE NOT NULL REFERENCES jugador(idjugador)
- creado_en
- activo
```

Reglas:

- Un `User` jugador se vincula a un unico `Jugador`.
- Un `Jugador` se vincula a un unico `User`.
- Los roles operativos se manejan con `auth_group`: `Administrador`,
  `Operador`, `Cajero`, `Jugador`.
- Los permisos de vistas se expresan por grupo o permisos Django, no por texto
  libre.
- `Jugador.estadocuentajugador` complementa el acceso, pero no reemplaza
  `User.is_active`.

Ventajas:

- No modifica columnas de `jugador`.
- Permite auditoria y pruebas simples.
- Evita depender de alias/correo como clave de relacion.
- Permite implementar `Mis cartones` con:

```text
request.user -> jugador_usuario -> jugador -> carton
```

## Recomendacion tecnica clara

No implementar login privado de jugadores ni "Mis cartones" protegido hasta
aprobar una relacion fisica `User`-`Jugador`.

La opcion recomendada es la tabla puente `jugador_usuario` y el uso de grupos
Django para roles:

- `Administrador`: configuracion total y gestion de usuarios.
- `Operador`: consola, bolas, validacion y desempate.
- `Cajero`: ventas/asignacion de cartones y pagos autorizados.
- `Jugador`: panel personal de solo lectura y acciones futuras limitadas.

Antes de crear cuentas de jugadores se debe cerrar tambien la brecha actual de
permisos: reemplazar `login_required` por decoradores de rol/permisos en
secciones administrativas que no sean publicas.

## Riesgos de seguridad

- Usar `codigocarton` como autenticacion convierte un codigo compartible en
  credencial permanente.
- Usar `aliasjugador` como login o relacion puede exponer o permitir adivinar
  cuentas porque es visible publicamente.
- Usar `correojugador` como relacion implicita falla si el correo no esta
  verificado, esta desactualizado o no coincide con `auth_user.email`.
- Permitir que cualquier `User` autenticado acceda a vistas con
  `login_required` puede exponer datos de socios, jugadores, finanzas o
  configuracion a cuentas de jugador.
- Crear una relacion falsa en codigo dificulta auditoria, recuperacion de
  cuentas y control de reclamos futuros.

## Siguiente etapa recomendada

Etapa 8 propuesta: aprobacion e implementacion controlada de identidad y roles.

Alcance recomendado:

1. Aprobar SQL o migracion controlada para `jugador_usuario`.
2. Crear modelo Django para la tabla puente.
3. Crear helpers de rol/permisos.
4. Crear grupos Django iniciales.
5. Proteger todas las vistas administrativas por rol.
6. Implementar login con redireccion por rol.
7. Implementar panel "Mis cartones" para `Jugador` autenticado.
8. Mantener la consulta publica por codigo como modo invitado separado.

## Archivos a modificar despues

Cuando se apruebe el cambio de base, los archivos probables son:

- `apps/seguridad/models.py` o una nueva app/perfil para el vinculo
  `User`-`Jugador`.
- `apps/seguridad/forms.py` para formularios de vinculacion o alta de cuentas.
- `apps/seguridad/views.py` y `apps/seguridad/urls.py` para paneles de cuenta.
- `apps/common/decorators.py` para permisos por rol.
- `config/urls.py` para login/redirect por rol si se separan flujos.
- `apps/jugadores/views.py` y `apps/jugadores/forms.py` para administrar
  vinculos de cuenta.
- `apps/bingos/views.py` y `apps/bingos/urls.py` para "Mis cartones".
- `templates/registration/login.html` para texto y redireccion por tipo de
  usuario.
- `templates/includes/navbar.html` y `templates/includes/sidebar.html` para
  navegacion por rol.
- `templates/bingos/` para panel personal de jugador.
- Pruebas nuevas en `apps/seguridad/tests.py`, `apps/jugadores/tests.py` y
  `apps/bingos/tests.py`.

## Confirmacion del diagnostico

No se modifico PostgreSQL, migraciones, `.env`, tablas fisicas, datos existentes,
modelos `managed=False` ni `models_inspectdb.py`. Este documento solo deja
constancia de la decision tecnica necesaria antes de implementar login real de
jugadores.
