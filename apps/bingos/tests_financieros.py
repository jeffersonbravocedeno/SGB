from django.conf import settings


if settings.SETTINGS_MODULE == "config.settings_finance_test":
    from django.db import connection
    from django.test import TestCase


    class FinanceBootstrapSchemaTests(TestCase):
        databases = {"default"}

        BOOTSTRAP_TABLES = (
            "bingo",
            "jugador",
            "partidabingo",
            "carton",
            "carton_partida_bingo",
            "bingo_gasto_operativo",
            "bingo_premio_material_costo",
            "bingo_cierre_financiero",
        )

        def test_base_financiera_es_temporal(self):
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                database_name = cursor.fetchone()[0]

            self.assertEqual(database_name, "test_siab_finanzas")
            self.assertTrue(database_name.startswith("test_"))
            self.assertNotIn(
                database_name,
                {"bingo", "bingo_ensayo_hibridos"},
            )

        def test_tablas_bootstrap_existen_y_son_consultables(self):
            with connection.cursor() as cursor:
                for table_name in self.BOOTSTRAP_TABLES:
                    with self.subTest(table=table_name):
                        cursor.execute(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM information_schema.tables
                                WHERE table_schema = %s
                                  AND table_name = %s
                            )
                            """,
                            ["public", table_name],
                        )
                        self.assertTrue(cursor.fetchone()[0])

                        quoted_table = connection.ops.quote_name(table_name)
                        cursor.execute(f"SELECT 1 FROM {quoted_table} LIMIT 0")
