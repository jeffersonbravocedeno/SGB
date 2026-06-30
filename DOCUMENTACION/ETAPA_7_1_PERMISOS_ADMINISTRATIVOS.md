# Etapa 7.1 - Permisos administrativos

## Objetivo

Endurecer el acceso a las pantallas internas antes de crear cuentas de
jugadores. Desde esta etapa, las vistas administrativas requieren un usuario
de Django con `is_staff=True` o `is_superuser=True`.

No se implemento login nuevo de jugadores, panel privado, pagos, reclamo de
Bingo por jugador ni cambios de base de datos.

## Problema de seguridad encontrado

Varias vistas internas estaban protegidas solo con `login_required`. Eso
impedia el acceso anonimo, pero permitia que cualquier usuario autenticado sin
rol administrativo entrara si conocia la URL.

Como todavia no existe una relacion fisica entre `auth_user` y `jugador`, no es
seguro asumir que un usuario autenticado normal representa a un jugador valido.

## `login_required` vs `admin_required`

`login_required` solo comprueba que el visitante haya iniciado sesion.

`admin_required` comprueba:

- si el usuario no esta autenticado, redirige a `/login/`;
- si el usuario tiene `is_staff=True` o `is_superuser=True`, permite entrar;
- si el usuario esta autenticado pero no es staff ni superusuario, responde con
  `PermissionDenied` y Django devuelve 403.

## Rutas publicas conservadas

Estas rutas siguen sin requerir staff:

- `/juego/`: sala publica de juego.
- `/juego/partidas/<idpartidabingo>/tablero/`: tablero publico.
- `/juego/cartones/acceder/`: consulta publica de carton por codigo.
- `/juego/cartones/<codigocarton>/`: visualizacion publica de carton.
- WebSocket publico de partida.
- `/login/`: inicio de sesion.
- `/logout/`: cierre de sesion.
- `/password-change/`: cambio de contrasena para usuarios autenticados.
- `/password-change/done/`: confirmacion de cambio de contrasena.
- `/health/`: verificacion simple de servicio.

## Rutas administrativas protegidas

Quedaron protegidas con `admin_required`:

- `/`: dashboard interno.
- `/socios/`, altas, detalle, edicion y cuentas bancarias de socios.
- `/jugadores/`, alta, detalle y edicion de jugadores.
- `/finanzas/`, prestamos, pagos, ahorros y aportes.
- `/configuracion/`, tipos de socio, metodos de pago, plataformas y regalos.
- `/bingos/`, alta, detalle y edicion de bingos.
- `/partidas/`, alta, detalle, edicion y consola de operador.
- Extraccion de bolas.
- Generacion, asignacion, edicion y validacion de cartones internos.
- Gestion de ganador.
- Gestion y confirmacion de desempate.
- `/cartones/` y gestion interna de cartones.
- `/sesiones-juego/`.

## Comportamiento por tipo de usuario

Visitante anonimo:

- no puede entrar a vistas administrativas;
- es redirigido a `/login/` con parametro `next`;
- puede abrir las rutas publicas de Bingo y consulta de carton.

Usuario autenticado normal sin staff:

- no puede entrar al dashboard interno ni a Socios, Jugadores, Finanzas,
  Configuracion o gestion operativa de Bingo;
- recibe 403 en vistas administrativas;
- puede usar cambio de contrasena;
- puede abrir las rutas publicas.

Usuario staff o superusuario:

- puede entrar al dashboard interno;
- puede entrar a Socios, Jugadores, Finanzas y Configuracion;
- puede usar las vistas administrativas y operativas de Bingo existentes.

## Por que era necesario antes del login de jugadores

La etapa de cuentas de jugadores creara usuarios autenticados no
administrativos. Si las vistas internas siguieran usando solo
`login_required`, esos usuarios podrian alcanzar modulos de administracion por
URL directa.

Esta etapa deja una separacion basica:

- usuario autenticado normal: cuenta personal, sin acceso administrativo;
- usuario staff/superusuario: gestion interna;
- visitante anonimo: solo rutas publicas.

## Validacion con pruebas

Se agregaron pruebas automaticas en `apps/seguridad/tests.py`.

Las pruebas verifican:

- anonimos redirigidos desde vistas administrativas;
- usuario autenticado normal bloqueado con `PermissionDenied`;
- usuario autenticado normal con acceso a cambio de contrasena;
- anonimos y usuarios normales con acceso a rutas publicas de Bingo;
- staff con acceso a dashboard, Socios, Jugadores, Finanzas, Configuracion y
  gestion de Bingos.

Las pruebas usan objetos en memoria y mocks para evitar dependencia de datos
reales de PostgreSQL.

## Pendiente para login real de jugadores

Todavia falta aprobar un cambio minimo de base de datos que vincule de forma
segura una cuenta `auth_user` con un registro `jugador`.

Despues de aprobar ese cambio, la siguiente etapa deberia implementar:

- relacion real entre usuario Django y jugador;
- permisos diferenciados para administrador, operador/cajero y jugador;
- login de jugador sin usar alias, correo o codigo de carton como contrasena;
- panel privado "Mis cartones";
- pruebas de acceso por rol y propiedad de datos.
