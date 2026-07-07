from django.conf import settings


if settings.SETTINGS_MODULE == "config.settings_finance_test":
    from decimal import Decimal

    from django.contrib.auth.models import User
    from django.db import connection
    from django.test import TestCase
    from django.utils import timezone

    from .models import (
        Bingo,
        BingoCierreFinanciero,
        BingoGastoOperativo,
        BingoPremioMaterialCosto,
        Carton,
        CartonPartidaBingo,
        Partidabingo,
    )
    from .services import (
        ESTADO_PARTIDA_CANCELADA,
        ESTADO_PARTIDA_DESEMPATE,
        ESTADO_PARTIDA_EN_CURSO,
        ESTADO_PARTIDA_EN_ESPERA,
        ESTADO_PARTIDA_FINALIZADA,
        ESTADO_PARTIDA_PAUSADA,
        ESTADO_PARTIDA_PROGRAMADA,
        construir_resumen_financiero_real_bingo,
    )
    from apps.jugadores.models import Jugador


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


    class ResumenFinancieroRealBingoTests(TestCase):
        databases = {"default"}

        def setUp(self):
            self.ahora = timezone.now()
            self.usuario = User.objects.create_user(
                username="admin_finanzas",
                password="test",
            )
            self.bingo = Bingo.objects.create(
                idbingo=100,
                titulobingo="Bingo financiero",
                fechaprogramadabingo=self.ahora,
                tipobingo="Virtual",
                preciocarton=Decimal("5.00"),
                premiomayor=Decimal("50.00"),
                descripcionpremiomayor="Premio mayor",
                estadobingo="Programado",
            )
            self.jugador = Jugador.objects.create(
                idjugador=200,
                aliasjugador="jugador_finanzas",
                correojugador="jugador_finanzas@example.com",
                fecharegistrojugador=self.ahora,
                saldocreditojugador=Decimal("0.00"),
                estadocuentajugador="Activo",
            )
            self._partida_id = 1000
            self._carton_id = 2000

        def _crear_partida(
            self,
            estado=ESTADO_PARTIDA_FINALIZADA,
            valor=Decimal("0.00"),
            premio_material="",
        ):
            self._partida_id += 1
            return Partidabingo.objects.create(
                idpartidabingo=self._partida_id,
                idbingo=self.bingo,
                nombreronda=f"Ronda {self._partida_id}",
                valorefectivo=valor,
                premiomaterial=premio_material,
                estadopartida=estado,
                patronganador="carton_lleno",
                bolascantadas="[]",
                ultimabola=0,
                haydesempate=False,
                horainicio=self.ahora,
                horafin=self.ahora if estado == ESTADO_PARTIDA_FINALIZADA else None,
            )

        def _crear_carton(self, precio=Decimal("5.00")):
            self._carton_id += 1
            return Carton.objects.create(
                idcarton=self._carton_id,
                idjugador=self.jugador,
                idbingo=self.bingo,
                idpartida=None,
                codigocarton=f"B100-C-{self._carton_id}",
                matriznumeros="[]",
                indicevictoria=None,
                preciopagado=precio,
                fechacompra=self.ahora,
                estadocarton="Vendido",
            )

        def _crear_participacion(self, carton, partida):
            return CartonPartidaBingo.objects.create(
                idcarton=carton,
                idpartida=partida,
                idbingo=self.bingo,
                estado_participacion=CartonPartidaBingo.ESTADO_PENDIENTE,
                indicevictoria=None,
                es_asignacion_original=False,
                origen_asignacion=CartonPartidaBingo.ORIGEN_APLICACION,
                fechacreacion=self.ahora,
                fechavalidacion=None,
            )

        def _crear_gasto(self, monto, estado=BingoGastoOperativo.ESTADO_REGISTRADO):
            datos = {
                "idbingo": self.bingo,
                "concepto": f"Gasto {monto}",
                "monto": monto,
                "fechagasto": self.ahora,
                "estado": estado,
                "idusuarioregistro": self.usuario,
                "fechacreacion": self.ahora,
            }
            if estado == BingoGastoOperativo.ESTADO_ANULADO:
                datos.update(
                    {
                        "idusuarioanulacion": self.usuario,
                        "fechaanulacion": self.ahora,
                        "motivoanulacion": "Anulado en prueba",
                    }
                )
            return BingoGastoOperativo.objects.create(**datos)

        def _crear_costo(
            self,
            partida,
            monto,
            estado=BingoPremioMaterialCosto.ESTADO_REGISTRADO,
        ):
            datos = {
                "idbingo": self.bingo,
                "idpartidabingo": partida.pk,
                "descripcionpremio": f"Premio {partida.pk}",
                "monto": monto,
                "estado": estado,
                "idusuarioregistro": self.usuario,
                "fechacreacion": self.ahora,
            }
            if estado == BingoPremioMaterialCosto.ESTADO_ANULADO:
                datos.update(
                    {
                        "idusuarioanulacion": self.usuario,
                        "fechaanulacion": self.ahora,
                        "motivoanulacion": "Anulado en prueba",
                    }
                )
            return BingoPremioMaterialCosto.objects.create(**datos)

        def _crear_cierre_cerrado(self):
            return BingoCierreFinanciero.objects.create(
                idbingo=self.bingo,
                estado=BingoCierreFinanciero.ESTADO_CERRADO,
                cartonesvendidosunicos=0,
                recaudacionregistrada=Decimal("0.00"),
                premiosefectivofinalizados=Decimal("0.00"),
                costospremiosmateriales=Decimal("0.00"),
                gastosoperativos=Decimal("0.00"),
                resultadoprovisional=Decimal("0.00"),
                utilidadbruta=Decimal("0.00"),
                utilidadneta=Decimal("0.00"),
                totalrondas=0,
                rondasfinalizadas=0,
                rondascanceladas=0,
                rondaspendientes=0,
                fechacalculo=self.ahora,
                fechacierre=self.ahora,
                idusuariocierre=self.usuario,
                fechacreacion=self.ahora,
            )

        def _resumen(self):
            return construir_resumen_financiero_real_bingo(self.bingo)

        def test_recaudacion_cuenta_cartones_unicos_no_participaciones(self):
            partidas = [self._crear_partida() for _indice in range(3)]
            cartones = [self._crear_carton(Decimal("5.00")) for _indice in range(3)]
            for carton in cartones:
                for partida in partidas:
                    self._crear_participacion(carton, partida)

            resumen = self._resumen()

            self.assertEqual(resumen["cartones_vendidos_unicos"], 3)
            self.assertEqual(resumen["recaudacion_registrada"], Decimal("15.00"))
            self.assertNotEqual(resumen["recaudacion_registrada"], Decimal("45.00"))

        def test_premio_efectivo_suma_solo_rondas_finalizadas(self):
            self._crear_partida(
                estado=ESTADO_PARTIDA_FINALIZADA,
                valor=Decimal("25.00"),
            )
            self._crear_partida(
                estado=ESTADO_PARTIDA_PROGRAMADA,
                valor=Decimal("99.00"),
            )
            self._crear_partida(
                estado=ESTADO_PARTIDA_CANCELADA,
                valor=Decimal("70.00"),
            )

            resumen = self._resumen()

            self.assertEqual(
                resumen["premios_efectivo_finalizados"],
                Decimal("25.00"),
            )

        def test_gasto_registrado_cuenta_y_anulado_no_cuenta(self):
            self._crear_gasto(Decimal("10.00"))
            self._crear_gasto(
                Decimal("7.00"),
                estado=BingoGastoOperativo.ESTADO_ANULADO,
            )

            resumen = self._resumen()

            self.assertEqual(resumen["gastos_operativos"], Decimal("10.00"))

        def test_costo_registrado_cuenta_y_anulado_no_cuenta(self):
            partida = self._crear_partida(premio_material="Canasta")
            self._crear_costo(partida, Decimal("12.00"))
            self._crear_costo(
                partida,
                Decimal("9.00"),
                estado=BingoPremioMaterialCosto.ESTADO_ANULADO,
            )

            resumen = self._resumen()

            self.assertEqual(
                resumen["costos_premios_materiales"],
                Decimal("12.00"),
            )

        def test_resultado_provisional_resta_premios_efectivo(self):
            self._crear_carton(Decimal("15.00"))
            self._crear_partida(valor=Decimal("4.00"))

            resumen = self._resumen()

            self.assertEqual(
                resumen["resultado_provisional"],
                Decimal("11.00"),
            )

        def test_utilidad_bruta_resta_costos_materiales(self):
            self._crear_carton(Decimal("20.00"))
            partida = self._crear_partida(
                valor=Decimal("5.00"),
                premio_material="Canasta",
            )
            self._crear_costo(partida, Decimal("3.00"))

            resumen = self._resumen()

            self.assertEqual(resumen["utilidad_bruta"], Decimal("12.00"))

        def test_utilidad_neta_resta_gastos_operativos(self):
            self._crear_carton(Decimal("20.00"))
            partida = self._crear_partida(
                valor=Decimal("5.00"),
                premio_material="Canasta",
            )
            self._crear_costo(partida, Decimal("3.00"))
            self._crear_gasto(Decimal("2.00"))

            resumen = self._resumen()

            self.assertEqual(resumen["utilidad_neta"], Decimal("10.00"))

        def test_utilidad_negativa_es_valida(self):
            self._crear_carton(Decimal("5.00"))
            partida = self._crear_partida(
                valor=Decimal("10.00"),
                premio_material="Canasta",
            )
            self._crear_costo(partida, Decimal("3.00"))
            self._crear_gasto(Decimal("2.00"))

            resumen = self._resumen()

            self.assertEqual(resumen["resultado_provisional"], Decimal("-5.00"))
            self.assertEqual(resumen["utilidad_bruta"], Decimal("-8.00"))
            self.assertEqual(resumen["utilidad_neta"], Decimal("-10.00"))

        def test_detecta_rondas_pendientes(self):
            for estado in (
                ESTADO_PARTIDA_PROGRAMADA,
                ESTADO_PARTIDA_EN_ESPERA,
                ESTADO_PARTIDA_EN_CURSO,
                ESTADO_PARTIDA_PAUSADA,
                ESTADO_PARTIDA_DESEMPATE,
            ):
                self._crear_partida(estado=estado)

            resumen = self._resumen()

            self.assertEqual(resumen["rondas_pendientes"], 5)
            self.assertTrue(
                any(
                    "rondas pendientes" in bloqueo
                    for bloqueo in resumen["bloqueos_de_cierre"]
                )
            )

        def test_detecta_premio_material_finalizado_sin_costo(self):
            partida = self._crear_partida(premio_material="Canasta")

            resumen = self._resumen()

            self.assertEqual(
                resumen["premios_materiales_pendientes_de_costo"],
                [
                    {
                        "partida": partida,
                        "idpartidabingo": partida.pk,
                        "ronda": partida.nombreronda,
                        "descripcion": "Canasta",
                    }
                ],
            )
            self.assertTrue(
                any(
                    "premios materiales" in bloqueo
                    for bloqueo in resumen["bloqueos_de_cierre"]
                )
            )

        def test_no_bloquea_premio_material_con_costo_registrado(self):
            partida = self._crear_partida(premio_material="Canasta")
            self._crear_costo(partida, Decimal("8.00"))

            resumen = self._resumen()

            self.assertEqual(resumen["premios_materiales_pendientes_de_costo"], [])
            self.assertFalse(
                any(
                    "premios materiales" in bloqueo
                    for bloqueo in resumen["bloqueos_de_cierre"]
                )
            )

        def test_detecta_cierre_ya_cerrado(self):
            cierre = self._crear_cierre_cerrado()

            resumen = self._resumen()

            self.assertEqual(resumen["cierre_existente"], cierre)
            self.assertTrue(resumen["cierre_esta_cerrado"])
            self.assertTrue(
                any(
                    "cierre Cerrado" in bloqueo
                    for bloqueo in resumen["bloqueos_de_cierre"]
                )
            )
