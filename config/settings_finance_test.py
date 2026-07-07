"""Settings for isolated PostgreSQL finance service tests."""

from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


_FINANCE_TEST_DATABASE_NAME = "test_siab_finanzas"
_POSTGRESQL_ENGINE_PREFIX = "django.db.backends.postgresql"


_finance_database = deepcopy(DATABASES["default"])  # noqa: F405
_finance_engine = str(_finance_database.get("ENGINE", "")).strip()

if not _finance_engine.startswith(_POSTGRESQL_ENGINE_PREFIX):
    raise ImproperlyConfigured(
        "Las pruebas financieras aisladas solo pueden usar PostgreSQL."
    )

_finance_database.update(
    {
        "NAME": _FINANCE_TEST_DATABASE_NAME,
        "CONN_MAX_AGE": 0,
        "TEST": {
            "NAME": _FINANCE_TEST_DATABASE_NAME,
        },
    }
)

DATABASES = {"default": _finance_database}
TEST_RUNNER = "config.test_runner.FinanceSchemaDiscoverRunner"
