# Etapa 8A - Registro, login y panel de jugadores

## Objetivo

Implementar registro publico, login y panel privado de jugadores usando solo
tablas existentes. No se crearon tablas, columnas, migraciones ni relaciones
fisicas nuevas.

## Tablas existentes utilizadas

- `auth_user`: usuario, hash de contrasena, correo informativo y banderas de
  staff/superusuario.
- `auth_group`: grupo Django `Jugador`.
- `auth_user_groups`: pertenencia del usuario al grupo `Jugador`.
- `jugador`: alias, correo, fecha de registro, saldo y estado.
- `carton`: cartones asignados al registro de jugador.
- `partidabingo` y `bingo`: datos de la partida mostrados en lectura.

## Convencion de relacion

La relacion se controla en aplicacion:

```text
Jugador.aliasjugador == auth_user.username
```

Ejemplo:

```text
jugador.aliasjugador = maria456
auth_user.username = maria456
```

No existe una foreign key fisica. Si alguien cambia directamente datos en base
sin pasar por la aplicacion, puede romper la relacion.

## Alias y contrasena

El alias es solo el nombre de usuario. No es una contrasena.

Las contrasenas se guardan exclusivamente con Django Auth mediante
`User.objects.create_user(...)`, que almacena hash cifrado en `auth_user`.

No se usa correo, cedula de socio ni codigo de carton como contrasena ni como
relacion principal. El correo puede cambiar o repetirse conceptualmente entre
sistemas externos; la cedula depende de socio y no todos los jugadores son
socios; el codigo de carton identifica un carton concreto de una partida, no
una identidad permanente.

## Registro publico

Ruta:

```text
/registro/
```

El formulario pide solo:

- alias de jugador;
- correo electronico;
- contrasena;
- confirmacion de contrasena.

El visitante no puede enviar staff, superusuario, grupos, permisos, socio,
saldo, estado administrativo ni datos de cartones.

Validaciones:

- alias obligatorio y no vacio;
- alias unico en `jugador` con comparacion insensible a mayusculas;
- alias no ocupado en `auth_user` con comparacion insensible a mayusculas;
- correo valido;
- correo no usado por otro jugador;
- contrasenas coincidentes;
- validadores de contrasena de Django.

Al registrarse, se crea dentro de `transaction.atomic`:

- un `Jugador` activo con saldo `0.00` y fecha actual;
- un `User` activo, no staff, no superusuario;
- el grupo Django `Jugador` si todavia no existe;
- la pertenencia del usuario al grupo `Jugador`.

La experiencia elegida es iniciar sesion automaticamente y redirigir a
`/mis-cartones/`.

## Creacion de acceso por staff

En el detalle administrativo de un jugador se agrego la seccion:

```text
Cuenta de acceso
```

Solo staff o superusuario puede usarla. Para jugadores ya existentes sin cuenta,
el staff puede crear acceso si:

- el jugador tiene alias;
- el jugador esta `Activo`;
- no existe ningun `auth_user` con ese alias.

La pantalla pide contrasena inicial y confirmacion. No muestra contrasenas ni
hashes despues de crear la cuenta.

## Login y redireccion

El login usa una vista propia basada en `LoginView`.

- Staff o superusuario: redirige al dashboard administrativo. Respeta `next`
  solo si es local y no apunta al panel de jugador.
- Usuario del grupo `Jugador`: redirige a `/mis-cartones/`. Solo respeta `next`
  para rutas de jugador, rutas publicas de juego o cambio de contrasena.
- Usuario autenticado sin staff y sin grupo `Jugador`: redirige a una pagina
  segura de cuenta sin acceso asignado.
- Un `next` externo se descarta para evitar open redirect.

## Panel Mis cartones

Rutas nuevas:

```text
/mis-cartones/
/mis-cartones/<codigocarton>/
```

Ambas requieren usuario autenticado, pertenencia al grupo `Jugador` y un
registro `Jugador` activo cuyo alias coincida con `request.user.username`.

`/mis-cartones/` lista solo cartones donde:

```text
Carton.idjugador == jugador autenticado
```

Muestra codigo, bingo, ronda, estado del carton, estado de partida, ultima bola,
cantidad marcada y progreso. No muestra cartones ajenos, precios de otros
jugadores, `idbingadores`, tiros privados de desempate ni controles
administrativos.

`/mis-cartones/<codigocarton>/` vuelve a verificar propiedad. Si el codigo existe
pero pertenece a otro jugador, responde como no encontrado sin revelar datos.
Reutiliza los servicios existentes de lectura de matriz y progreso, incluida la
casilla LIBRE y las marcas por bolas extraidas.

## Manejo de alias al editar

Si staff edita un jugador sin cuenta vinculada, el alias se edita normalmente.

Si existe un `User` con el alias anterior y ese usuario pertenece al grupo
`Jugador`, el cambio de alias sincroniza `User.username` al nuevo alias dentro
de `transaction.atomic`.

Antes de guardar se valida:

- que el nuevo alias no este vacio;
- que no exista otro `auth_user` con ese alias;
- que no exista otro `Jugador` con ese alias.

Nunca se modifica la contrasena al cambiar alias. Nunca se sincroniza un `User`
que no pertenezca al grupo `Jugador`.

## Navegacion

Visitante anonimo:

- Sala de juego;
- Consultar carton;
- Iniciar sesion;
- Registrarse.

Jugador autenticado:

- Mis cartones;
- Sala de juego;
- Consultar carton;
- Cambiar contrasena;
- Cerrar sesion.

Staff o superusuario:

- mantiene la navegacion administrativa;
- conserva acceso a sala publica y consulta publica;
- no ve `Mis cartones` por defecto.

## Pruebas realizadas

Se agregaron pruebas en `apps/seguridad/tests.py` para:

- registro publico y validaciones;
- creacion coherente de `Jugador` y `User`;
- uso de hash de contrasena;
- grupo `Jugador`;
- rechazo de alias repetido;
- rechazo de alias ocupado por `auth_user`;
- rechazo de contrasenas diferentes;
- creacion de acceso por staff para jugador existente;
- bloqueo de acceso para anonimo o usuario no staff;
- panel `Mis cartones` y propiedad de cartones;
- bloqueo de cartones ajenos;
- bloqueo de administracion para usuarios no staff;
- sincronizacion de alias;
- conflicto de alias sin cambios parciales;
- redireccion por tipo de usuario;
- bloqueo de open redirect externo.

## Limitaciones de esta etapa

La relacion por alias funciona, pero no tiene integridad referencial fisica. La
mejora recomendada para una etapa posterior es aprobar una tabla puente, por
ejemplo:

```text
jugador_usuario(idjugador, user_id)
```

con foreign keys reales y restriccion de unicidad. Esa mejora reduciria el
riesgo de inconsistencias por cambios manuales directos en base de datos.
