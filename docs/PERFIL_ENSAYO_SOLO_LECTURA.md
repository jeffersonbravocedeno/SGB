# Perfil de ensayo PostgreSQL en modo solo lectura

Fecha: 2026-07-05  
Fase: 0.6A — preparación sin conexión a PostgreSQL

## Resultado

El perfil separado fue creado como:

```text
config.settings_ensayo_lectura
```

Su archivo es `config/settings_ensayo_lectura.py`. Importa
`config.settings`, copia la configuración del alias principal y construye un
nuevo `DATABASES` exclusivo para la auditoría. No modifica
`config/settings.py` ni la configuración normal del proyecto.

Esta fase no carga ni conecta el perfil nuevo. Su validación se limita a la
sintaxis porque todavía no están activadas las variables ni el acceso local de
solo lectura.

## Configuración existente identificada

El proyecto usa:

- paquete Django: `config`;
- settings normal: `config.settings`;
- backend: `django.db.backends.postgresql`;
- alias de base: `default`;
- comando principal: `manage.py`, que usa `config.settings` si no se indica
  otro módulo.

El settings normal obtiene del entorno estos nombres de variables, sin que
esta fase lea o documente sus valores:

- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`;
- `REDIS_URL`;
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`,
  `DB_CONN_MAX_AGE`;
- `LANGUAGE_CODE`, `TIME_ZONE`;
- `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.

El perfil de ensayo no cambia ninguna de esas variables. Para seleccionar la
base auditada usa un conjunto separado.

## Protecciones implementadas

El módulo nuevo aborta durante la carga de settings, antes de que un comando
pueda conectarse, si ocurre cualquiera de estas condiciones:

- `SIAB_ENSAYO_DB_NAME` está vacía;
- el nombre es `bingo`;
- el nombre no es exactamente `bingo_ensayo_hibridos`;
- el backend heredado no es PostgreSQL;
- usuario, host o puerto de ensayo están vacíos;
- el puerto no es numérico o está fuera del rango TCP válido.

Además:

- reemplaza nombre, usuario, host y puerto con variables `SIAB_ENSAYO_*`;
- elimina `PASSWORD` del alias final;
- permite que libpq use el archivo señalado por `PGPASSFILE`;
- agrega `-c default_transaction_read_only=on` a las opciones de sesión;
- usa `CONN_MAX_AGE=0` para no conservar conexiones de auditoría;
- preserva otras opciones existentes del backend, como SSL, codificación o
  timeouts;
- expone únicamente el alias `default` de ensayo;
- etiqueta las conexiones futuras con
  `application_name=siab_auditoria_ensayo`.

La protección de settings complementa, pero no reemplaza, un rol PostgreSQL
con permisos reales de solo lectura.

## Archivo de ejemplo sin secretos

Se creó `.env.ensayo.example` únicamente con valores no sensibles:

```dotenv
SIAB_ENSAYO_DB_NAME=bingo_ensayo_hibridos
SIAB_ENSAYO_DB_USER=siab_auditor
SIAB_ENSAYO_DB_HOST=127.0.0.1
SIAB_ENSAYO_DB_PORT=5432
```

No contiene contraseña. El perfil tampoco carga automáticamente un archivo
`.env.ensayo`; las variables deben activarse en la sesión del proceso.

`.gitignore` ya protegía `.env.ensayo` mediante la regla general `.env.*`. Se
agregó únicamente una excepción para permitir versionar el ejemplo seguro:

```gitignore
!.env.ensayo.example
```

Un archivo real `.env.ensayo` permanece ignorado y no debe contenerse en el
repositorio.

## Activación mediante variables de entorno

En una terminal dedicada, activar exclusivamente valores no secretos:

```bash
export DJANGO_SETTINGS_MODULE=config.settings_ensayo_lectura
export SIAB_ENSAYO_DB_NAME=bingo_ensayo_hibridos
export SIAB_ENSAYO_DB_USER=siab_auditor
export SIAB_ENSAYO_DB_HOST=127.0.0.1
export SIAB_ENSAYO_DB_PORT=5432
export PGPASSFILE="$HOME/.config/siab/pgpass_ensayo"
```

El nombre de usuario, host y ruta de `PGPASSFILE` deben ajustarse a los valores
preparados por el administrador local. No se debe guardar una contraseña en
las variables `SIAB_ENSAYO_*` ni pegarla en comandos, documentación o chat.

## Uso seguro de PGPASSFILE

`PGPASSFILE` debe apuntar a un archivo local creado fuera del repositorio y
administrado por la persona responsable de PostgreSQL. Para usarlo sin exponer
la contraseña:

1. guardar el archivo en un directorio privado del usuario;
2. limitar sus permisos en sistemas compatibles:

   ```bash
   chmod 600 "$PGPASSFILE"
   ```

3. no ejecutar `cat`, `sed`, `grep` ni comandos que impriman el archivo;
4. no copiarlo dentro del proyecto;
5. no añadir su contenido a `.env.ensayo.example`;
6. comprobar con el administrador que esa entrada corresponde solamente al
   rol de auditoría y a `bingo_ensayo_hibridos`.

Al no existir `PASSWORD` en el alias Django de ensayo, el controlador
PostgreSQL puede solicitar a libpq la credencial desde `PGPASSFILE` sin que la
aplicación la incluya en settings.

## Check futuro con el perfil de ensayo

No ejecutar este comando hasta que las variables y el acceso de solo lectura
estén preparados:

```bash
python manage.py check --settings=config.settings_ensayo_lectura
```

El check valida la carga del perfil, pero no sustituye el preflight de base
efectiva y modo de transacción.

## Comando para iniciar la futura Fase 0.6

Después de activar las variables, el primer comando de la Fase 0.6 debe ser el
preflight mínimo que confirma el destino real y el modo de sesión:

```bash
python manage.py shell --settings=config.settings_ensayo_lectura -c "from django.db import connection; cursor = connection.cursor(); cursor.execute(\"SELECT current_database(), current_setting('transaction_read_only')\"); print(cursor.fetchone()); cursor.close()"
```

El resultado autorizado debe ser exactamente equivalente a:

```text
('bingo_ensayo_hibridos', 'on')
```

Si el nombre o el modo no coinciden, no debe ejecutarse ninguna otra consulta.
Este preflight es un SELECT y se documenta para la fase futura; no fue
ejecutado en la Fase 0.6A.

Después del preflight aprobado, la Fase 0.6 continuará solo con consultas de
catálogo y conteos descritas en
`docs/CONTRATO_ESQUEMA_POSTGRESQL_HIBRIDO.md`.

## Restricciones de uso

Este perfil sirve exclusivamente para auditoría de solo lectura. No debe
usarse para:

- `migrate` o `makemigrations`;
- pruebas que creen, actualicen o eliminen datos;
- `flush` o `collectstatic`;
- desarrollo normal o ejecución del servidor;
- administración de usuarios;
- ventas, asignaciones, rondas o ganadores;
- scripts de migración, backfill o reversión;
- conexión a `bingo`.

Aunque PostgreSQL rechazará escrituras por defecto, no se deben intentar para
“probar” la protección.

## Volver al perfil normal

La forma más segura es cerrar la terminal dedicada. En la misma terminal se
pueden retirar las variables de ensayo:

```bash
unset DJANGO_SETTINGS_MODULE
unset SIAB_ENSAYO_DB_NAME
unset SIAB_ENSAYO_DB_USER
unset SIAB_ENSAYO_DB_HOST
unset SIAB_ENSAYO_DB_PORT
unset PGPASSFILE
```

Sin `DJANGO_SETTINGS_MODULE` explícito, `manage.py` vuelve a usar su valor
normal `config.settings`. No se debe editar `config/settings.py` para cambiar
entre perfiles.

## Verificaciones de la Fase 0.6A

| Verificación permitida | Resultado |
|---|---|
| `.venv/bin/python -m py_compile config/settings_ensayo_lectura.py` | Correcto, sin importar ni cargar el módulo |
| `bash -n .env.ensayo.example` | Correcto; cuatro asignaciones sin contraseña |
| `.venv/bin/python manage.py check` con el perfil normal | Correcto: `System check identified no issues (0 silenced)` |
| `git check-ignore -v --no-index .env.ensayo` | Ignorado por la regla `.env.*` |
| Comprobación de `.env.ensayo.example` | Versionable por la excepción segura |

No se ejecutó `check` con `config.settings_ensayo_lectura`, no se importó ese
módulo y no se intentó una conexión. Tampoco se ejecutaron pruebas, comandos
PostgreSQL, scripts SQL o comandos de despliegue.

No se leyó, mostró, copió ni modificó el contenido de `.env`, `PGPASSFILE`,
`.pgpass`, contraseñas, cadenas de conexión o secretos. El check normal cargó
la configuración de Django de la forma habitual, sin imprimir sus valores.

## Cambios de la Fase 0.6A

- Creados: `config/settings_ensayo_lectura.py`, `.env.ensayo.example` y
  `docs/PERFIL_ENSAYO_SOLO_LECTURA.md`.
- Modificado: `.gitignore`, únicamente para versionar el ejemplo seguro.
- Sin cambios: `config/settings.py`, `DATABASES` normal, `.env`, modelos,
  migraciones, rutas, servicios, plantillas y PostgreSQL.
- Conexiones o consultas PostgreSQL: ninguna.
