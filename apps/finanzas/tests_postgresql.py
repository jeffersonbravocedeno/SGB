from django.conf import settings


if settings.SETTINGS_MODULE == "config.settings_finance_test":
    from datetime import date
    from decimal import Decimal

    from django.contrib.auth.models import User
    from django.core.exceptions import ImproperlyConfigured
    from django.db import IntegrityError, connection, transaction
    from django.test import TransactionTestCase
    from django.utils import timezone

    from apps.configuracion.models import Metodopago, Tiposocio
    from apps.jugadores.models import Jugador
    from apps.socios.models import Socio

    from .models import PagoPrestamo, Prestamo, SolicitudPagoPrestamo
    from .services import (
        SolicitudPagoPrestamoError,
        aprobar_solicitud_pago_prestamo,
        crear_solicitud_pago_prestamo,
        rechazar_solicitud_pago_prestamo,
    )


    class PostgreSQLTemporalTestCase(TransactionTestCase):
        databases = {"default"}
        reset_sequences = True

        @classmethod
        def setUpClass(cls):
            super().setUpClass()
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                cls.database_name = str(cursor.fetchone()[0]).strip()
            if not cls.database_name.startswith("test_"):
                raise ImproperlyConfigured(
                    "Pruebas PostgreSQL rechazadas: la base actual no comienza "
                    f"con 'test_': {cls.database_name!r}."
                )

        def _fixture_teardown(self):
            SolicitudPagoPrestamo.objects.all().delete()
            PagoPrestamo.objects.all().delete()
            Prestamo.objects.all().delete()
            Jugador.objects.all().delete()
            Socio.objects.all().delete()
            Metodopago.objects.all().delete()
            Tiposocio.objects.all().delete()
            User.objects.all().delete()


    class SolicitudPagoPrestamoPostgreSQLTests(PostgreSQLTemporalTestCase):
        def setUp(self):
            self.tipo = Tiposocio.objects.create(
                idtiposocio=1,
                nombretiposocio="Socio crédito",
                roltiposocio="socio_credito",
            )
            self.socio = self._crear_socio(1, "0910000001")
            self.otro_socio = self._crear_socio(2, "0910000002")
            self.jugador = Jugador.objects.create(
                idjugador=1,
                idsocio=self.socio,
                aliasjugador="jugador_pago_pg",
                correojugador="jugador_pago_pg@example.com",
                fecharegistrojugador=timezone.now(),
                saldocreditojugador=Decimal("0.00"),
                estadocuentajugador="Activo",
            )
            self.metodo = Metodopago.objects.create(
                idmetodopago=1,
                nombremetodopago="Transferencia PostgreSQL",
                estadometodopago=True,
                urlmetodopago="https://example.com/pago",
            )
            self.prestamo = self._crear_prestamo()
            self.admin = User.objects.create_user(
                username="admin_solicitudes_pago_pg",
                password="test",
                is_staff=True,
            )

        def _crear_socio(self, identificador, cedula):
            return Socio.objects.create(
                idsocio=identificador,
                idtiposocio=self.tipo,
                primernombresocio=f"Socio {identificador}",
                primerapellidosocio="Prueba",
                segundoapellidosocio="PostgreSQL",
                cisocio=cedula,
                fechanacimientosocio=date(1985, 1, 1),
                direcciondomiciliosocio="Dirección de prueba",
                estadosocio="Activo",
            )

        def _crear_prestamo(self, saldo=Decimal("300.00"), estado="Aprobado"):
            return Prestamo.objects.create(
                idsocio=self.socio,
                montoprestamosolicitado=Decimal("300.00"),
                tasainteres=Decimal("0.00"),
                montototalpagar=Decimal("300.00"),
                saldopendiente=saldo,
                numerocuotas=3,
                fechasolicitud=date(2026, 7, 1),
                fechavencimiento=date(2026, 10, 1),
                estadoprestamo=estado,
            )

        def _datos(self, monto=Decimal("100.00"), referencia="REF-PG-001"):
            return {
                "monto": monto,
                "idmetodopago": self.metodo,
                "referencia": referencia,
                "rutacomprobante": "COMP-PG-001",
                "observacionsocio": "Pago desde integración PostgreSQL",
            }

        def _crear_solicitud(self, **kwargs):
            return crear_solicitud_pago_prestamo(
                self.jugador,
                self.prestamo.pk,
                self._datos(**kwargs),
            )

        def test_crear_solicitud_no_modifica_saldo(self):
            solicitud = self._crear_solicitud()

            self.prestamo.refresh_from_db()
            self.assertEqual(solicitud.estado, SolicitudPagoPrestamo.ESTADO_PENDIENTE)
            self.assertEqual(self.prestamo.saldopendiente, Decimal("300.00"))
            self.assertTrue(self.database_name.startswith("test_"))

        def test_indice_parcial_rechaza_dos_pendientes_para_el_mismo_prestamo(self):
            self._crear_solicitud()

            with self.assertRaises(IntegrityError), transaction.atomic():
                SolicitudPagoPrestamo.objects.create(
                    idprestamo=self.prestamo,
                    idsocio=self.socio,
                    idjugador=self.jugador,
                    idmetodopago=self.metodo,
                    monto=Decimal("50.00"),
                    referencia="REF-PG-002",
                    estado=SolicitudPagoPrestamo.ESTADO_PENDIENTE,
                    fechasolicitud=timezone.now(),
                )

            self.assertEqual(
                SolicitudPagoPrestamo.objects.filter(
                    idprestamo=self.prestamo,
                    estado=SolicitudPagoPrestamo.ESTADO_PENDIENTE,
                ).count(),
                1,
            )

        def test_claves_foraneas_de_solicitud_pago_son_fisicas(self):
            with self.assertRaises(IntegrityError), transaction.atomic():
                SolicitudPagoPrestamo.objects.create(
                    idprestamo_id=999999,
                    idsocio=self.socio,
                    idjugador=self.jugador,
                    monto=Decimal("10.00"),
                    referencia="REF-FK-PG",
                    estado=SolicitudPagoPrestamo.ESTADO_PENDIENTE,
                    fechasolicitud=timezone.now(),
                )

        def test_aprobar_crea_pago_disminuye_saldo_y_no_falla_por_join_nullable(self):
            solicitud = self._crear_solicitud(monto=Decimal("125.00"))

            resuelta, pago = aprobar_solicitud_pago_prestamo(
                solicitud.pk,
                self.admin,
                {"observacionadmin": "Validado en PostgreSQL"},
            )

            self.prestamo.refresh_from_db()
            resuelta.refresh_from_db()
            self.assertTrue(PagoPrestamo.objects.filter(pk=pago.pk).exists())
            self.assertEqual(self.prestamo.saldopendiente, Decimal("175.00"))
            self.assertEqual(resuelta.estado, SolicitudPagoPrestamo.ESTADO_APROBADA)
            self.assertEqual(resuelta.idpagoprestamoresultado_id, pago.pk)

        def test_pago_exacto_deja_prestamo_liquidado(self):
            solicitud = self._crear_solicitud(monto=Decimal("300.00"))

            aprobar_solicitud_pago_prestamo(solicitud.pk, self.admin)

            self.prestamo.refresh_from_db()
            self.assertEqual(self.prestamo.saldopendiente, Decimal("0.00"))
            self.assertEqual(self.prestamo.estadoprestamo, "Liquidado")

        def test_rechazar_no_crea_pago_ni_modifica_saldo(self):
            solicitud = self._crear_solicitud()

            rechazar_solicitud_pago_prestamo(
                solicitud.pk,
                self.admin,
                "Referencia no comprobada",
            )

            self.prestamo.refresh_from_db()
            solicitud.refresh_from_db()
            self.assertEqual(PagoPrestamo.objects.count(), 0)
            self.assertEqual(self.prestamo.saldopendiente, Decimal("300.00"))
            self.assertEqual(solicitud.estado, SolicitudPagoPrestamo.ESTADO_RECHAZADA)

        def test_prestamo_finalizado_no_admite_solicitud(self):
            self.prestamo.estadoprestamo = "Finalizado"
            self.prestamo.save(update_fields=["estadoprestamo"])

            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "El préstamo no admite nuevos pagos.",
            ):
                self._crear_solicitud()

            self.assertEqual(SolicitudPagoPrestamo.objects.count(), 0)
            self.assertEqual(PagoPrestamo.objects.count(), 0)

        def test_solicitud_no_se_aprueba_si_prestamo_fue_finalizado_despues(self):
            solicitud = self._crear_solicitud()
            self.prestamo.estadoprestamo = "Finalizado"
            self.prestamo.save(update_fields=["estadoprestamo"])

            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "El préstamo no admite nuevos pagos.",
            ):
                aprobar_solicitud_pago_prestamo(solicitud.pk, self.admin)

            self.prestamo.refresh_from_db()
            solicitud.refresh_from_db()
            self.assertEqual(self.prestamo.saldopendiente, Decimal("300.00"))
            self.assertEqual(solicitud.estado, SolicitudPagoPrestamo.ESTADO_PENDIENTE)
            self.assertEqual(PagoPrestamo.objects.count(), 0)

        def test_incoherencia_jugador_socio_prestamo_es_error_controlado(self):
            solicitud = self._crear_solicitud()
            self.jugador.idsocio = self.otro_socio
            self.jugador.save(update_fields=["idsocio"])

            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "La solicitud no conserva una relación válida entre jugador, socio y préstamo.",
            ):
                aprobar_solicitud_pago_prestamo(solicitud.pk, self.admin)

            self.prestamo.refresh_from_db()
            solicitud.refresh_from_db()
            self.assertEqual(self.prestamo.saldopendiente, Decimal("300.00"))
            self.assertEqual(solicitud.estado, SolicitudPagoPrestamo.ESTADO_PENDIENTE)
            self.assertEqual(PagoPrestamo.objects.count(), 0)
