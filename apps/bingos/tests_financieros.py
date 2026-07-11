from django.conf import settings


if settings.SETTINGS_MODULE == "config.settings_finance_test":
    from datetime import timedelta
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
        CierreFinancieroError,
        ESTADO_PARTIDA_CANCELADA,
        ESTADO_PARTIDA_DESEMPATE,
        ESTADO_PARTIDA_EN_CURSO,
        ESTADO_PARTIDA_EN_ESPERA,
        ESTADO_PARTIDA_FINALIZADA,
        ESTADO_PARTIDA_PAUSADA,
        ESTADO_PARTIDA_PROGRAMADA,
        anular_costo_premio_material_bingo,
        anular_gasto_operativo_bingo,
        cerrar_financieramente_bingo,
        construir_resumen_financiero_real_bingo,
        crear_carton_maestro_para_bingo,
        registrar_costo_premio_material_bingo,
        registrar_gasto_operativo_bingo,
    )
    from apps.jugadores.models import Jugador


    class FinanceBootstrapSchemaTests(TestCase):
        databases = {"default"}

        BOOTSTRAP_TABLES = (
            "tiposocio",
            "socio",
            "metodopago",
            "bingo",
            "jugador",
            "prestamo",
            "pago_prestamo",
            "solicitud_socio",
            "solicitud_pago_prestamo",
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

        def _crear_cierre_abierto(self):
            return BingoCierreFinanciero.objects.create(
                idbingo=self.bingo,
                estado=BingoCierreFinanciero.ESTADO_ABIERTO,
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
                fechacierre=None,
                idusuariocierre=None,
                observacioncierre="Precalculo",
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

        def test_registrar_gasto_operativo_correcto(self):
            fecha_gasto = self.ahora - timedelta(days=1)

            gasto = registrar_gasto_operativo_bingo(
                self.bingo,
                self.usuario,
                "  Impresion de cartones  ",
                "12.50",
                fechagasto=fecha_gasto,
                observacion="  urgente  ",
            )

            self.assertEqual(gasto.estado, BingoGastoOperativo.ESTADO_REGISTRADO)
            self.assertEqual(gasto.idusuarioregistro, self.usuario)
            self.assertEqual(gasto.concepto, "Impresion de cartones")
            self.assertEqual(gasto.monto, Decimal("12.50"))
            self.assertEqual(gasto.fechagasto, fecha_gasto)
            self.assertEqual(gasto.observacion, "urgente")
            self.assertIsNotNone(gasto.fechacreacion)

        def test_registrar_gasto_usa_fecha_actual_si_no_recibe_fecha(self):
            antes = timezone.now()

            gasto = registrar_gasto_operativo_bingo(
                self.bingo,
                self.usuario,
                "Transporte",
                Decimal("3.00"),
            )

            despues = timezone.now()
            self.assertGreaterEqual(gasto.fechagasto, antes)
            self.assertLessEqual(gasto.fechagasto, despues)

        def test_registrar_gasto_rechaza_concepto_vacio(self):
            for concepto in ("", "   "):
                with self.subTest(concepto=repr(concepto)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "El concepto del gasto es obligatorio.",
                    ):
                        registrar_gasto_operativo_bingo(
                            self.bingo,
                            self.usuario,
                            concepto,
                            Decimal("1.00"),
                        )

            self.assertEqual(BingoGastoOperativo.objects.count(), 0)

        def test_registrar_gasto_rechaza_montos_no_positivos_y_booleanos(self):
            for monto in (Decimal("0.00"), Decimal("-1.00"), True, False):
                with self.subTest(monto=repr(monto)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "El monto del gasto debe ser mayor que cero.",
                    ):
                        registrar_gasto_operativo_bingo(
                            self.bingo,
                            self.usuario,
                            "Gasto invalido",
                            monto,
                        )

            self.assertEqual(BingoGastoOperativo.objects.count(), 0)

        def test_registrar_gasto_rechaza_montos_invalidos(self):
            for monto in (
                Decimal("NaN"),
                Decimal("Infinity"),
                Decimal("-Infinity"),
                "texto-invalido",
                "",
                None,
            ):
                with self.subTest(monto=repr(monto)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "El monto del gasto debe ser mayor que cero.",
                    ):
                        registrar_gasto_operativo_bingo(
                            self.bingo,
                            self.usuario,
                            "Gasto invalido",
                            monto,
                        )

                    self.assertEqual(BingoGastoOperativo.objects.count(), 0)

        def test_anular_gasto_operativo_conserva_registro_y_guarda_auditoria(self):
            gasto = registrar_gasto_operativo_bingo(
                self.bingo,
                self.usuario,
                "Sonido",
                Decimal("15.00"),
            )
            usuario_anulacion = User.objects.create_user(
                username="admin_anulacion",
                password="test",
            )
            antes = timezone.now()

            gasto_anulado = anular_gasto_operativo_bingo(
                gasto,
                usuario_anulacion,
                "  Factura duplicada  ",
            )

            despues = timezone.now()
            self.assertEqual(BingoGastoOperativo.objects.count(), 1)
            self.assertEqual(gasto_anulado.pk, gasto.pk)
            self.assertEqual(gasto_anulado.estado, BingoGastoOperativo.ESTADO_ANULADO)
            self.assertEqual(gasto_anulado.idusuarioanulacion, usuario_anulacion)
            self.assertGreaterEqual(gasto_anulado.fechaanulacion, antes)
            self.assertLessEqual(gasto_anulado.fechaanulacion, despues)
            self.assertEqual(gasto_anulado.motivoanulacion, "Factura duplicada")

        def test_anular_gasto_rechaza_motivo_vacio(self):
            gasto = registrar_gasto_operativo_bingo(
                self.bingo,
                self.usuario,
                "Sonido",
                Decimal("15.00"),
            )

            for motivo in ("", "   "):
                with self.subTest(motivo=repr(motivo)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "Debe indicar el motivo de anulación.",
                    ):
                        anular_gasto_operativo_bingo(gasto, self.usuario, motivo)

            gasto.refresh_from_db()
            self.assertEqual(gasto.estado, BingoGastoOperativo.ESTADO_REGISTRADO)

        def test_anular_gasto_rechaza_gasto_ya_anulado(self):
            gasto = registrar_gasto_operativo_bingo(
                self.bingo,
                self.usuario,
                "Sonido",
                Decimal("15.00"),
            )
            anular_gasto_operativo_bingo(gasto, self.usuario, "Error")

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "El gasto ya se encuentra anulado.",
            ):
                anular_gasto_operativo_bingo(gasto, self.usuario, "Otro error")

        def test_resumen_cuenta_gasto_registrado_por_servicio(self):
            registrar_gasto_operativo_bingo(
                self.bingo,
                self.usuario,
                "Sonido",
                Decimal("15.00"),
            )

            resumen = self._resumen()

            self.assertEqual(resumen["gastos_operativos"], Decimal("15.00"))

        def test_resumen_deja_de_contar_gasto_anulado_por_servicio(self):
            gasto = registrar_gasto_operativo_bingo(
                self.bingo,
                self.usuario,
                "Sonido",
                Decimal("15.00"),
            )
            anular_gasto_operativo_bingo(gasto, self.usuario, "Error")

            resumen = self._resumen()

            self.assertEqual(resumen["gastos_operativos"], Decimal("0.00"))

        def test_registrar_gasto_bloquea_bingo_con_cierre_cerrado(self):
            self._crear_cierre_cerrado()

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "No se pueden registrar gastos porque el cierre financiero está cerrado.",
            ):
                registrar_gasto_operativo_bingo(
                    self.bingo,
                    self.usuario,
                    "Sonido",
                    Decimal("15.00"),
                )

            self.assertEqual(BingoGastoOperativo.objects.count(), 0)

        def test_anular_gasto_bloquea_bingo_con_cierre_cerrado(self):
            gasto = self._crear_gasto(Decimal("15.00"))
            self._crear_cierre_cerrado()

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "No se pueden anular gastos porque el cierre financiero está cerrado.",
            ):
                anular_gasto_operativo_bingo(gasto, self.usuario, "Error")

            gasto.refresh_from_db()
            self.assertEqual(gasto.estado, BingoGastoOperativo.ESTADO_REGISTRADO)

        def test_registrar_costo_material_correcto(self):
            partida = self._crear_partida(premio_material="Canasta familiar")

            costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "  Canasta familiar  ",
                "18.50",
                observacion="  compra local  ",
            )

            self.assertEqual(costo.estado, BingoPremioMaterialCosto.ESTADO_REGISTRADO)
            self.assertEqual(costo.idbingo, self.bingo)
            self.assertEqual(costo.idpartidabingo, partida.pk)
            self.assertEqual(costo.idusuarioregistro, self.usuario)
            self.assertEqual(costo.descripcionpremio, "Canasta familiar")
            self.assertEqual(costo.monto, Decimal("18.50"))
            self.assertEqual(costo.observacion, "compra local")
            partida.refresh_from_db()
            self.assertEqual(partida.premiomaterial, "Canasta familiar")

        def test_registrar_costo_material_rechaza_partida_de_otro_bingo(self):
            otro_bingo = Bingo.objects.create(
                idbingo=101,
                titulobingo="Otro bingo",
                fechaprogramadabingo=self.ahora,
                tipobingo="Virtual",
                preciocarton=Decimal("5.00"),
                premiomayor=Decimal("50.00"),
                descripcionpremiomayor="Premio mayor",
                estadobingo="Programado",
            )
            partida = Partidabingo.objects.create(
                idpartidabingo=9001,
                idbingo=otro_bingo,
                nombreronda="Ronda otro bingo",
                valorefectivo=Decimal("0.00"),
                premiomaterial="Canasta",
                estadopartida=ESTADO_PARTIDA_FINALIZADA,
                patronganador="carton_lleno",
                bolascantadas="[]",
                ultimabola=0,
                haydesempate=False,
                horainicio=self.ahora,
                horafin=self.ahora,
            )

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "La partida no pertenece al Bingo indicado.",
            ):
                registrar_costo_premio_material_bingo(
                    self.bingo,
                    partida,
                    self.usuario,
                    "Canasta",
                    Decimal("10.00"),
                )

            self.assertEqual(BingoPremioMaterialCosto.objects.count(), 0)

        def test_registrar_costo_material_rechaza_descripcion_vacia(self):
            partida = self._crear_partida(premio_material="Canasta")

            for descripcion in ("", "   "):
                with self.subTest(descripcion=repr(descripcion)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "La descripción del premio es obligatoria.",
                    ):
                        registrar_costo_premio_material_bingo(
                            self.bingo,
                            partida,
                            self.usuario,
                            descripcion,
                            Decimal("10.00"),
                        )

            self.assertEqual(BingoPremioMaterialCosto.objects.count(), 0)

        def test_registrar_costo_material_rechaza_partida_sin_premio_material(self):
            for premio_material in ("", "   "):
                partida = self._crear_partida(premio_material=premio_material)
                with self.subTest(premio_material=repr(premio_material)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "La partida no tiene un premio material configurado.",
                    ):
                        registrar_costo_premio_material_bingo(
                            self.bingo,
                            partida,
                            self.usuario,
                            "Canasta",
                            Decimal("10.00"),
                        )

            self.assertEqual(BingoPremioMaterialCosto.objects.count(), 0)

        def test_registrar_costo_material_rechaza_montos_invalidos(self):
            partida = self._crear_partida(premio_material="Canasta")

            for monto in (
                Decimal("-1.00"),
                True,
                False,
                Decimal("NaN"),
                Decimal("Infinity"),
                Decimal("-Infinity"),
                "texto-invalido",
            ):
                with self.subTest(monto=repr(monto)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "El monto del costo no puede ser negativo.",
                    ):
                        registrar_costo_premio_material_bingo(
                            self.bingo,
                            partida,
                            self.usuario,
                            "Canasta",
                            monto,
                        )

                    self.assertEqual(BingoPremioMaterialCosto.objects.count(), 0)

        def test_registrar_costo_material_rechaza_cero_sin_observacion(self):
            partida = self._crear_partida(premio_material="Canasta")

            for observacion in ("", "   "):
                with self.subTest(observacion=repr(observacion)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "Un costo de cero debe incluir una observación que indique la donación.",
                    ):
                        registrar_costo_premio_material_bingo(
                            self.bingo,
                            partida,
                            self.usuario,
                            "Canasta",
                            Decimal("0.00"),
                            observacion=observacion,
                        )

            self.assertEqual(BingoPremioMaterialCosto.objects.count(), 0)

        def test_registrar_costo_material_permite_cero_con_observacion(self):
            partida = self._crear_partida(premio_material="Canasta")

            costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("0.00"),
                observacion="Donación del proveedor",
            )

            self.assertEqual(costo.monto, Decimal("0.00"))
            self.assertEqual(costo.observacion, "Donación del proveedor")
            self.assertEqual(costo.estado, BingoPremioMaterialCosto.ESTADO_REGISTRADO)

        def test_registrar_costo_material_rechaza_segundo_registrado(self):
            partida = self._crear_partida(premio_material="Canasta")
            registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("10.00"),
            )

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "Ya existe un costo de premio material registrado para esta partida.",
            ):
                registrar_costo_premio_material_bingo(
                    self.bingo,
                    partida,
                    self.usuario,
                    "Canasta nueva",
                    Decimal("12.00"),
                )

            self.assertEqual(
                BingoPremioMaterialCosto.objects.filter(
                    estado=BingoPremioMaterialCosto.ESTADO_REGISTRADO
                ).count(),
                1,
            )

        def test_anular_costo_material_conserva_registro_y_guarda_auditoria(self):
            partida = self._crear_partida(premio_material="Canasta")
            costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("10.00"),
            )
            usuario_anulacion = User.objects.create_user(
                username="admin_anula_costo",
                password="test",
            )
            antes = timezone.now()

            costo_anulado = anular_costo_premio_material_bingo(
                costo,
                usuario_anulacion,
                "  Valor duplicado  ",
            )

            despues = timezone.now()
            self.assertEqual(BingoPremioMaterialCosto.objects.count(), 1)
            self.assertEqual(costo_anulado.pk, costo.pk)
            self.assertEqual(
                costo_anulado.estado,
                BingoPremioMaterialCosto.ESTADO_ANULADO,
            )
            self.assertEqual(costo_anulado.idusuarioanulacion, usuario_anulacion)
            self.assertGreaterEqual(costo_anulado.fechaanulacion, antes)
            self.assertLessEqual(costo_anulado.fechaanulacion, despues)
            self.assertEqual(costo_anulado.motivoanulacion, "Valor duplicado")

        def test_anular_costo_material_rechaza_motivo_vacio(self):
            partida = self._crear_partida(premio_material="Canasta")
            costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("10.00"),
            )

            for motivo in ("", "   "):
                with self.subTest(motivo=repr(motivo)):
                    with self.assertRaisesMessage(
                        CierreFinancieroError,
                        "Debe indicar el motivo de anulación.",
                    ):
                        anular_costo_premio_material_bingo(
                            costo,
                            self.usuario,
                            motivo,
                        )

            costo.refresh_from_db()
            self.assertEqual(costo.estado, BingoPremioMaterialCosto.ESTADO_REGISTRADO)

        def test_anular_costo_material_rechaza_costo_ya_anulado(self):
            partida = self._crear_partida(premio_material="Canasta")
            costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("10.00"),
            )
            anular_costo_premio_material_bingo(costo, self.usuario, "Error")

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "El costo de premio material ya se encuentra anulado.",
            ):
                anular_costo_premio_material_bingo(costo, self.usuario, "Otro error")

        def test_resumen_cuenta_costo_material_registrado_por_servicio(self):
            partida = self._crear_partida(premio_material="Canasta")
            registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("10.00"),
            )

            resumen = self._resumen()

            self.assertEqual(resumen["costos_premios_materiales"], Decimal("10.00"))

        def test_resumen_deja_de_contar_costo_material_anulado_por_servicio(self):
            partida = self._crear_partida(premio_material="Canasta")
            costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("10.00"),
            )
            anular_costo_premio_material_bingo(costo, self.usuario, "Error")

            resumen = self._resumen()

            self.assertEqual(resumen["costos_premios_materiales"], Decimal("0.00"))

        def test_registrar_costo_material_permite_nuevo_despues_de_anular(self):
            partida = self._crear_partida(premio_material="Canasta")
            costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("10.00"),
            )
            anular_costo_premio_material_bingo(costo, self.usuario, "Error")

            nuevo_costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta corregida",
                Decimal("12.00"),
            )

            self.assertNotEqual(nuevo_costo.pk, costo.pk)
            self.assertEqual(nuevo_costo.estado, BingoPremioMaterialCosto.ESTADO_REGISTRADO)
            self.assertEqual(nuevo_costo.monto, Decimal("12.00"))
            self.assertEqual(
                BingoPremioMaterialCosto.objects.filter(
                    idpartidabingo=partida.pk,
                    estado=BingoPremioMaterialCosto.ESTADO_REGISTRADO,
                ).count(),
                1,
            )

        def test_registrar_costo_material_bloquea_bingo_con_cierre_cerrado(self):
            partida = self._crear_partida(premio_material="Canasta")
            self._crear_cierre_cerrado()

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "No se pueden registrar costos porque el cierre financiero está cerrado.",
            ):
                registrar_costo_premio_material_bingo(
                    self.bingo,
                    partida,
                    self.usuario,
                    "Canasta",
                    Decimal("10.00"),
                )

            self.assertEqual(BingoPremioMaterialCosto.objects.count(), 0)

        def test_anular_costo_material_bloquea_bingo_con_cierre_cerrado(self):
            partida = self._crear_partida(premio_material="Canasta")
            costo = registrar_costo_premio_material_bingo(
                self.bingo,
                partida,
                self.usuario,
                "Canasta",
                Decimal("10.00"),
            )
            self._crear_cierre_cerrado()

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "No se pueden anular costos porque el cierre financiero está cerrado.",
            ):
                anular_costo_premio_material_bingo(costo, self.usuario, "Error")

            costo.refresh_from_db()
            self.assertEqual(costo.estado, BingoPremioMaterialCosto.ESTADO_REGISTRADO)

        def test_cerrar_financieramente_crea_cierre_con_snapshot_correcto(self):
            partida_finalizada = self._crear_partida(
                valor=Decimal("4.00"),
                premio_material="Canasta",
            )
            partida_cancelada = self._crear_partida(
                estado=ESTADO_PARTIDA_CANCELADA,
                valor=Decimal("99.00"),
            )
            costo = self._crear_costo(partida_finalizada, Decimal("3.00"))
            gasto = self._crear_gasto(Decimal("2.00"))
            cartones = [self._crear_carton(Decimal("5.00")) for _indice in range(3)]
            participaciones = []
            for carton in cartones:
                participaciones.append(
                    self._crear_participacion(carton, partida_finalizada)
                )
                participaciones.append(
                    self._crear_participacion(carton, partida_cancelada)
                )
            estado_operativo_original = self.bingo.estadobingo
            antes = timezone.now()

            cierre = cerrar_financieramente_bingo(
                self.bingo,
                self.usuario,
                observacion_cierre="  cierre validado  ",
            )

            despues = timezone.now()
            self.assertEqual(BingoCierreFinanciero.objects.count(), 1)
            self.assertEqual(cierre.estado, BingoCierreFinanciero.ESTADO_CERRADO)
            self.assertEqual(cierre.idbingo, self.bingo)
            self.assertEqual(cierre.cartonesvendidosunicos, 3)
            self.assertEqual(cierre.recaudacionregistrada, Decimal("15.00"))
            self.assertNotEqual(cierre.recaudacionregistrada, Decimal("30.00"))
            self.assertEqual(cierre.premiosefectivofinalizados, Decimal("4.00"))
            self.assertEqual(cierre.costospremiosmateriales, Decimal("3.00"))
            self.assertEqual(cierre.gastosoperativos, Decimal("2.00"))
            self.assertEqual(cierre.resultadoprovisional, Decimal("11.00"))
            self.assertEqual(cierre.utilidadbruta, Decimal("8.00"))
            self.assertEqual(cierre.utilidadneta, Decimal("6.00"))
            self.assertEqual(cierre.totalrondas, 2)
            self.assertEqual(cierre.rondasfinalizadas, 1)
            self.assertEqual(cierre.rondascanceladas, 1)
            self.assertEqual(cierre.rondaspendientes, 0)
            self.assertGreaterEqual(cierre.fechacalculo, antes)
            self.assertLessEqual(cierre.fechacalculo, despues)
            self.assertGreaterEqual(cierre.fechacierre, antes)
            self.assertLessEqual(cierre.fechacierre, despues)
            self.assertEqual(cierre.idusuariocierre, self.usuario)
            self.assertEqual(cierre.observacioncierre, "cierre validado")

            self.bingo.refresh_from_db()
            self.assertEqual(self.bingo.estadobingo, estado_operativo_original)
            partida_finalizada.refresh_from_db()
            partida_cancelada.refresh_from_db()
            self.assertEqual(partida_finalizada.estadopartida, ESTADO_PARTIDA_FINALIZADA)
            self.assertEqual(partida_finalizada.premiomaterial, "Canasta")
            self.assertEqual(partida_cancelada.estadopartida, ESTADO_PARTIDA_CANCELADA)
            for carton in cartones:
                carton.refresh_from_db()
                self.assertEqual(carton.estadocarton, "Vendido")
            for participacion in participaciones:
                participacion.refresh_from_db()
                self.assertEqual(
                    participacion.estado_participacion,
                    CartonPartidaBingo.ESTADO_PENDIENTE,
                )
            gasto.refresh_from_db()
            costo.refresh_from_db()
            self.assertEqual(gasto.estado, BingoGastoOperativo.ESTADO_REGISTRADO)
            self.assertEqual(costo.estado, BingoPremioMaterialCosto.ESTADO_REGISTRADO)

        def test_cerrar_financieramente_rechaza_cada_estado_pendiente(self):
            for indice, estado in enumerate(
                (
                    ESTADO_PARTIDA_PROGRAMADA,
                    ESTADO_PARTIDA_EN_ESPERA,
                    ESTADO_PARTIDA_EN_CURSO,
                    ESTADO_PARTIDA_PAUSADA,
                    ESTADO_PARTIDA_DESEMPATE,
                ),
                start=1,
            ):
                with self.subTest(estado=estado):
                    bingo = Bingo.objects.create(
                        idbingo=300 + indice,
                        titulobingo=f"Bingo pendiente {indice}",
                        fechaprogramadabingo=self.ahora,
                        tipobingo="Virtual",
                        preciocarton=Decimal("5.00"),
                        premiomayor=Decimal("50.00"),
                        descripcionpremiomayor="Premio mayor",
                        estadobingo="Programado",
                    )
                    Partidabingo.objects.create(
                        idpartidabingo=9300 + indice,
                        idbingo=bingo,
                        nombreronda=f"Ronda pendiente {indice}",
                        valorefectivo=Decimal("0.00"),
                        premiomaterial="",
                        estadopartida=estado,
                        patronganador="carton_lleno",
                        bolascantadas="[]",
                        ultimabola=0,
                        haydesempate=False,
                        horainicio=self.ahora,
                        horafin=None,
                    )

                    with self.assertRaises(CierreFinancieroError) as contexto:
                        cerrar_financieramente_bingo(bingo, self.usuario)

                    mensaje = str(contexto.exception)
                    self.assertTrue(
                        mensaje.startswith(
                            "No se puede cerrar financieramente el Bingo:"
                        )
                    )
                    self.assertIn("rondas pendientes", mensaje)
                    self.assertFalse(
                        BingoCierreFinanciero.objects.filter(idbingo=bingo).exists()
                    )

        def test_cerrar_financieramente_rechaza_premio_material_sin_costo(self):
            self._crear_partida(premio_material="Canasta")

            with self.assertRaises(CierreFinancieroError) as contexto:
                cerrar_financieramente_bingo(self.bingo, self.usuario)

            mensaje = str(contexto.exception)
            self.assertTrue(
                mensaje.startswith("No se puede cerrar financieramente el Bingo:")
            )
            self.assertIn("premios materiales", mensaje)
            self.assertEqual(BingoCierreFinanciero.objects.count(), 0)

        def test_cerrar_financieramente_costo_anulado_no_resuelve_bloqueo(self):
            partida = self._crear_partida(premio_material="Canasta")
            self._crear_costo(
                partida,
                Decimal("10.00"),
                estado=BingoPremioMaterialCosto.ESTADO_ANULADO,
            )

            with self.assertRaises(CierreFinancieroError) as contexto:
                cerrar_financieramente_bingo(self.bingo, self.usuario)

            self.assertIn("premios materiales", str(contexto.exception))
            self.assertEqual(BingoCierreFinanciero.objects.count(), 0)

        def test_cerrar_financieramente_costo_registrado_resuelve_bloqueo(self):
            partida = self._crear_partida(premio_material="Canasta")
            self._crear_costo(partida, Decimal("10.00"))

            cierre = cerrar_financieramente_bingo(self.bingo, self.usuario)

            self.assertEqual(cierre.estado, BingoCierreFinanciero.ESTADO_CERRADO)
            self.assertEqual(cierre.costospremiosmateriales, Decimal("10.00"))
            self.assertEqual(cierre.rondaspendientes, 0)

        def test_cerrar_financieramente_cancelada_con_material_no_exige_costo(self):
            self._crear_partida(
                estado=ESTADO_PARTIDA_CANCELADA,
                premio_material="Canasta",
            )

            cierre = cerrar_financieramente_bingo(self.bingo, self.usuario)

            self.assertEqual(cierre.estado, BingoCierreFinanciero.ESTADO_CERRADO)
            self.assertEqual(cierre.rondascanceladas, 1)
            self.assertEqual(cierre.costospremiosmateriales, Decimal("0.00"))

        def test_cerrar_financieramente_segundo_cierre_preserva_snapshot(self):
            self._crear_carton(Decimal("5.00"))
            self._crear_partida(valor=Decimal("2.00"))
            cierre = cerrar_financieramente_bingo(
                self.bingo,
                self.usuario,
                observacion_cierre="Original",
            )
            cierre.refresh_from_db()
            campos_snapshot = (
                "cartonesvendidosunicos",
                "recaudacionregistrada",
                "premiosefectivofinalizados",
                "costospremiosmateriales",
                "gastosoperativos",
                "resultadoprovisional",
                "utilidadbruta",
                "utilidadneta",
                "totalrondas",
                "rondasfinalizadas",
                "rondascanceladas",
                "rondaspendientes",
                "fechacalculo",
                "fechacierre",
                "observacioncierre",
            )
            snapshot_original = {
                campo: getattr(cierre, campo) for campo in campos_snapshot
            }

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "El cierre financiero ya está cerrado.",
            ):
                cerrar_financieramente_bingo(
                    self.bingo,
                    self.usuario,
                    observacion_cierre="Intento posterior",
                )

            cierre.refresh_from_db()
            self.assertEqual(BingoCierreFinanciero.objects.count(), 1)
            for campo, valor in snapshot_original.items():
                self.assertEqual(getattr(cierre, campo), valor)

        def test_cerrar_financieramente_reutiliza_cierre_abierto(self):
            self._crear_carton(Decimal("7.00"))
            self._crear_partida(valor=Decimal("2.00"))
            cierre_abierto = self._crear_cierre_abierto()
            cierre_abierto.refresh_from_db()
            fechacreacion_original = cierre_abierto.fechacreacion

            cierre = cerrar_financieramente_bingo(
                self.bingo,
                self.usuario,
                observacion_cierre="  cierre definitivo  ",
            )

            self.assertEqual(cierre.pk, cierre_abierto.pk)
            self.assertEqual(BingoCierreFinanciero.objects.count(), 1)
            self.assertEqual(cierre.estado, BingoCierreFinanciero.ESTADO_CERRADO)
            self.assertEqual(cierre.recaudacionregistrada, Decimal("7.00"))
            self.assertEqual(cierre.resultadoprovisional, Decimal("5.00"))
            self.assertEqual(cierre.observacioncierre, "cierre definitivo")
            self.assertEqual(cierre.fechacreacion, fechacreacion_original)

        def test_cerrar_financieramente_snapshot_omite_anulados(self):
            partida = self._crear_partida(premio_material="Canasta")
            self._crear_costo(partida, Decimal("8.00"))
            self._crear_costo(
                partida,
                Decimal("20.00"),
                estado=BingoPremioMaterialCosto.ESTADO_ANULADO,
            )
            self._crear_gasto(Decimal("5.00"))
            self._crear_gasto(
                Decimal("7.00"),
                estado=BingoGastoOperativo.ESTADO_ANULADO,
            )

            cierre = cerrar_financieramente_bingo(self.bingo, self.usuario)

            self.assertEqual(cierre.costospremiosmateriales, Decimal("8.00"))
            self.assertEqual(cierre.gastosoperativos, Decimal("5.00"))
            self.assertEqual(cierre.utilidadneta, Decimal("-13.00"))

        def test_servicios_financieros_rechazan_despues_de_cerrar(self):
            partida = self._crear_partida(premio_material="Canasta")
            self._crear_costo(partida, Decimal("10.00"))
            cerrar_financieramente_bingo(self.bingo, self.usuario)

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "No se pueden registrar gastos porque el cierre financiero está cerrado.",
            ):
                registrar_gasto_operativo_bingo(
                    self.bingo,
                    self.usuario,
                    "Sonido",
                    Decimal("15.00"),
                )

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "No se pueden registrar costos porque el cierre financiero está cerrado.",
            ):
                registrar_costo_premio_material_bingo(
                    self.bingo,
                    partida,
                    self.usuario,
                    "Canasta",
                    Decimal("12.00"),
                )

        def test_crear_carton_maestro_permite_venta_antes_del_cierre(self):
            partida = self._crear_partida(estado=ESTADO_PARTIDA_PROGRAMADA)

            carton = crear_carton_maestro_para_bingo(
                self.bingo,
                self.jugador,
                Decimal("5.00"),
            )

            self.assertEqual(Carton.objects.count(), 1)
            self.assertEqual(carton.idbingo, self.bingo)
            self.assertIsNone(carton.idpartida_id)
            self.assertEqual(carton.estadocarton, "Vendido")
            self.assertEqual(carton.preciopagado, Decimal("5.00"))
            self.assertEqual(
                CartonPartidaBingo.objects.filter(
                    idcarton=carton,
                    idpartida=partida,
                    idbingo=self.bingo,
                ).count(),
                1,
            )

        def test_crear_carton_maestro_bloquea_venta_despues_del_cierre(self):
            self._crear_carton(Decimal("5.00"))
            self._crear_partida(valor=Decimal("2.00"))
            cierre = cerrar_financieramente_bingo(self.bingo, self.usuario)
            cierre.refresh_from_db()
            snapshot_original = {
                "estado": cierre.estado,
                "recaudacionregistrada": cierre.recaudacionregistrada,
                "resultadoprovisional": cierre.resultadoprovisional,
                "utilidadbruta": cierre.utilidadbruta,
                "utilidadneta": cierre.utilidadneta,
                "cartonesvendidosunicos": cierre.cartonesvendidosunicos,
            }
            total_cartones = Carton.objects.count()
            total_participaciones = CartonPartidaBingo.objects.count()

            with self.assertRaisesMessage(
                CierreFinancieroError,
                "No se pueden vender cartones porque el cierre financiero está cerrado.",
            ):
                crear_carton_maestro_para_bingo(
                    self.bingo,
                    self.jugador,
                    Decimal("5.00"),
                )

            self.assertEqual(Carton.objects.count(), total_cartones)
            self.assertEqual(
                CartonPartidaBingo.objects.count(),
                total_participaciones,
            )
            cierre.refresh_from_db()
            for campo, valor in snapshot_original.items():
                self.assertEqual(getattr(cierre, campo), valor)
