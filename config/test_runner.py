from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.test.runner import DiscoverRunner


class FinanceSchemaDiscoverRunner(DiscoverRunner):
    """Loads unmanaged finance-test tables into Django's test database."""

    expected_test_database_name = "test_siab_finanzas"
    bootstrap_sql = "sql/test_schema_bingos_financiero.sql"
    protected_database_names = {"bingo", "bingo_ensayo_hibridos"}
    required_database_prefix = "test_"

    def setup_databases(self, **kwargs):
        self._validate_configured_test_database_name()
        old_config = super().setup_databases(**kwargs)
        try:
            self._bootstrap_finance_schema_once()
        except Exception:
            self.teardown_databases(old_config)
            raise
        return old_config

    def _bootstrap_finance_schema_once(self):
        if getattr(self, "_finance_schema_bootstrapped", False):
            return

        connection = connections[DEFAULT_DB_ALIAS]
        database_name = self._current_database_name(connection)
        self._validate_database_name(database_name)

        sql_path = Path(settings.BASE_DIR) / self.bootstrap_sql
        if not sql_path.exists():
            raise ImproperlyConfigured(
                f"No existe el bootstrap SQL financiero: {sql_path}"
            )

        sql = sql_path.read_text(encoding="utf-8")
        statements = connection.ops.prepare_sql_script(sql)

        if self.verbosity >= 1:
            self.log(
                f"Cargando esquema financiero de pruebas en {database_name}."
            )

        with transaction.atomic(using=DEFAULT_DB_ALIAS):
            with connection.cursor() as cursor:
                for statement in statements:
                    if statement.strip():
                        cursor.execute(statement)

        self._finance_schema_bootstrapped = True

    def _current_database_name(self, connection):
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            row = cursor.fetchone()
        return str(row[0]).strip() if row else ""

    def _validate_configured_test_database_name(self):
        database_settings = settings.DATABASES.get(DEFAULT_DB_ALIAS, {})
        test_settings = database_settings.get("TEST") or {}
        test_database_name = str(test_settings.get("NAME") or "").strip()

        if not test_database_name:
            raise ImproperlyConfigured(
                "Bootstrap financiero rechazado: DATABASES['default']"
                "['TEST']['NAME'] es obligatorio y no puede usar fallback."
            )
        if test_database_name != self.expected_test_database_name:
            raise ImproperlyConfigured(
                "Bootstrap financiero rechazado: DATABASES['default']"
                "['TEST']['NAME'] debe ser exactamente "
                f"{self.expected_test_database_name!r}; valor actual "
                f"{test_database_name!r}."
            )
        self._validate_database_name(
            test_database_name,
            context="la base de pruebas configurada",
        )

    def _validate_database_name(self, database_name, *, context="la base actual"):
        if database_name in self.protected_database_names:
            raise ImproperlyConfigured(
                "Bootstrap financiero rechazado: "
                f"{context} "
                f"{database_name!r} esta protegida."
            )
        if not database_name.startswith(self.required_database_prefix):
            raise ImproperlyConfigured(
                "Bootstrap financiero rechazado: "
                f"{context} "
                f"{database_name!r} no comienza con "
                f"{self.required_database_prefix!r}."
            )
