"""Perfil Django exclusivo para auditorías de solo lectura en ensayo."""

import os
from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


_EXPECTED_DATABASE_NAME = "bingo_ensayo_hibridos"
_POSTGRESQL_ENGINE_PREFIX = "django.db.backends.postgresql"


def _required_environment_variable(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"La variable de entorno {name} es obligatoria para el perfil de ensayo."
        )
    return value


_base_database = deepcopy(DATABASES["default"])  # noqa: F405
_base_engine = str(_base_database.get("ENGINE", "")).strip()

if not _base_engine.startswith(_POSTGRESQL_ENGINE_PREFIX):
    raise ImproperlyConfigured(
        "El perfil de ensayo solo puede utilizar el motor PostgreSQL."
    )

_database_name = os.environ.get("SIAB_ENSAYO_DB_NAME", "")
if not _database_name:
    raise ImproperlyConfigured(
        "SIAB_ENSAYO_DB_NAME es obligatoria para el perfil de ensayo."
    )
if _database_name == "bingo":
    raise ImproperlyConfigured(
        "El perfil de ensayo rechaza explícitamente la base principal bingo."
    )
if _database_name != _EXPECTED_DATABASE_NAME:
    raise ImproperlyConfigured(
        "SIAB_ENSAYO_DB_NAME no coincide con la base de ensayo autorizada."
    )

_database_user = _required_environment_variable("SIAB_ENSAYO_DB_USER")
_database_host = _required_environment_variable("SIAB_ENSAYO_DB_HOST")
_database_port = _required_environment_variable("SIAB_ENSAYO_DB_PORT")
if not _database_port.isdigit() or not 1 <= int(_database_port) <= 65535:
    raise ImproperlyConfigured(
        "SIAB_ENSAYO_DB_PORT debe ser un puerto TCP válido."
    )

# Se preservan opciones de conexión del perfil principal, como SSL,
# codificación o timeouts. La opción de solo lectura se agrega al final para
# que sea el valor efectivo de la sesión PostgreSQL.
_database_options = deepcopy(_base_database.get("OPTIONS", {}))
_existing_server_options = str(_database_options.get("options", "")).strip()
_read_only_server_option = "-c default_transaction_read_only=on"
_database_options["options"] = " ".join(
    option
    for option in (_existing_server_options, _read_only_server_option)
    if option
)
_database_options.setdefault("application_name", "siab_auditoria_ensayo")

_base_database.update(
    {
        "ENGINE": _base_engine,
        "NAME": _database_name,
        "USER": _database_user,
        "HOST": _database_host,
        "PORT": _database_port,
        "CONN_MAX_AGE": 0,
        "OPTIONS": _database_options,
    }
)

# No se admite contraseña en código ni en variables SIAB_ENSAYO_*. Al no
# enviar PASSWORD, libpq puede resolver la autenticación mediante el archivo
# indicado externamente en PGPASSFILE.
_base_database.pop("PASSWORD", None)

# El perfil expone únicamente el alias de ensayo y no conserva otros aliases
# que pudieran agregarse al settings normal en el futuro.
DATABASES = {"default": _base_database}
