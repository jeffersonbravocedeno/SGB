from django.conf import settings


if settings.SETTINGS_MODULE == "config.settings_finance_test":
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date
    from decimal import Decimal

    from django.contrib.auth.models import User
    from django.core.exceptions import ImproperlyConfigured, ValidationError
    from django.db import IntegrityError, close_old_connections, connection, transaction
    from django.test import TransactionTestCase
    from django.utils import timezone

    from apps.configuracion.models import Metodopago, Tiposocio
    from apps.finanzas.models import PagoPrestamo, Prestamo, SolicitudPagoPrestamo
    from apps.jugadores.models import Jugador

    from .models import Socio, SolicitudSocio
    from .services import (
        aprobar_solicitud_socio,
        crear_solicitud_socio,
        rechazar_solicitud_socio,
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
            SolicitudSocio.objects.all().delete()
            PagoPrestamo.objects.all().delete()
            Prestamo.objects.all().delete()
            Jugador.objects.all().delete()
            Socio.objects.all().delete()
            Metodopago.objects.all().delete()
            Tiposocio.objects.all().delete()
            User.objects.all().delete()


    class SolicitudSocioPostgreSQLTests(PostgreSQLTemporalTestCase):
        def setUp(self):
            self.tipo = Tiposocio.objects.create(
                idtiposocio=1,
                nombretiposocio="Socio general",
                roltiposocio="socio_general",
            )
            self.jugador = self._crear_jugador(1)
            self.otro_jugador = self._crear_jugador(2)
            self.admin = User.objects.create_user(
                username="admin_solicitudes_socio_pg",
                password="test",
                is_staff=True,
            )

        def _crear_jugador(self, identificador, socio=None):
            return Jugador.objects.create(
                idjugador=identificador,
                idsocio=socio,
                aliasjugador=f"jugador_socio_pg_{identificador}",
                correojugador=f"jugador_socio_pg_{identificador}@example.com",
                fecharegistrojugador=timezone.now(),
                saldocreditojugador=Decimal("0.00"),
                estadocuentajugador="Activo",
            )

        def _datos(self, cedula="0912345678", **overrides):
            datos = {
                "idtiposocio": self.tipo,
                "primernombresocio": "María",
                "segundonombresocio": "Elena",
                "primerapellidosocio": "Pérez",
                "segundoapellidosocio": "López",
                "cisocio": cedula,
                "fechanacimientosocio": date(1990, 5, 20),
                "telefonopersonalsocio": "0999999999",
                "telefonotrabajosocio": "",
                "direcciondomiciliosocio": "Av. Principal",
                "direcciontrabajosocio": "",
                "sexosocio": "M",
                "observacion": "Solicitud PostgreSQL",
            }
            datos.update(overrides)
            return datos

        def _crear_directa(self, jugador, cedula):
            return SolicitudSocio.objects.create(
                idjugador=jugador,
                idtiposocio=self.tipo,
                primernombresocio="María",
                segundonombresocio="Elena",
                primerapellidosocio="Pérez",
                segundoapellidosocio="López",
                cisocio=cedula,
                fechanacimientosocio=date(1990, 5, 20),
                direcciondomiciliosocio="Av. Principal",
                sexosocio="M",
                estado=SolicitudSocio.ESTADO_PENDIENTE,
                fechasolicitud=timezone.now(),
            )

        def test_crea_solicitud_pendiente_en_postgresql_temporal(self):
            solicitud = crear_solicitud_socio(self.jugador, self._datos())

            solicitud.refresh_from_db()
            self.assertEqual(solicitud.estado, SolicitudSocio.ESTADO_PENDIENTE)
            self.assertEqual(solicitud.cisocio, "0912345678")
            self.assertTrue(self.database_name.startswith("test_"))

        def test_indices_parciales_rechazan_jugador_y_cedula_pendientes(self):
            self._crear_directa(self.jugador, "0912345678")

            with self.assertRaises(IntegrityError), transaction.atomic():
                self._crear_directa(self.jugador, "0912345679")

            with self.assertRaises(IntegrityError), transaction.atomic():
                self._crear_directa(self.otro_jugador, "0912345678")

            self.assertEqual(
                SolicitudSocio.objects.filter(
                    estado=SolicitudSocio.ESTADO_PENDIENTE
                ).count(),
                1,
            )

        def test_servicio_devuelve_validation_error_ante_conflicto_real(self):
            def solicitar(jugador_id):
                close_old_connections()
                try:
                    jugador = Jugador(pk=jugador_id)
                    return crear_solicitud_socio(
                        jugador,
                        self._datos(cedula="0911111111"),
                    )
                except ValidationError as exc:
                    return exc
                finally:
                    close_old_connections()

            with ThreadPoolExecutor(max_workers=2) as executor:
                resultados = list(executor.map(solicitar, (1, 2)))

            errores = [r for r in resultados if isinstance(r, ValidationError)]
            self.assertEqual(len(errores), 1)
            self.assertIn("solicitud pendiente", str(errores[0]).lower())
            self.assertEqual(
                SolicitudSocio.objects.filter(
                    cisocio="0911111111",
                    estado=SolicitudSocio.ESTADO_PENDIENTE,
                ).count(),
                1,
            )

        def test_clave_foranea_de_jugador_es_fisica(self):
            with self.assertRaises(IntegrityError), transaction.atomic():
                SolicitudSocio.objects.create(
                    idjugador_id=999999,
                    idtiposocio=self.tipo,
                    primernombresocio="Sin",
                    primerapellidosocio="Jugador",
                    segundoapellidosocio="Válido",
                    cisocio="0922222222",
                    fechanacimientosocio=date(1990, 1, 1),
                    direcciondomiciliosocio="Dirección",
                    estado=SolicitudSocio.ESTADO_PENDIENTE,
                    fechasolicitud=timezone.now(),
                )

        def test_aprobar_crea_socio_actualiza_jugador_y_no_falla_por_join_nullable(self):
            solicitud = crear_solicitud_socio(self.jugador, self._datos())

            resuelta, socio = aprobar_solicitud_socio(
                solicitud.pk,
                self.admin,
                {"idtiposocio": self.tipo, "estadosocio": "Activo"},
            )

            self.jugador.refresh_from_db()
            resuelta.refresh_from_db()
            self.assertTrue(Socio.objects.filter(pk=socio.pk).exists())
            self.assertEqual(self.jugador.idsocio_id, socio.pk)
            self.assertEqual(resuelta.idsocioresultado_id, socio.pk)
            self.assertEqual(resuelta.estado, SolicitudSocio.ESTADO_APROBADA)

        def test_aprobar_vincula_socio_existente(self):
            socio = Socio.objects.create(
                idsocio=10,
                idtiposocio=self.tipo,
                primernombresocio="María",
                segundonombresocio="Elena",
                primerapellidosocio="Pérez",
                segundoapellidosocio="López",
                cisocio="0912345678",
                fechanacimientosocio=date(1990, 5, 20),
                direcciondomiciliosocio="Av. Principal",
                estadosocio="Activo",
            )
            solicitud = crear_solicitud_socio(self.jugador, self._datos())

            _resuelta, socio_resultado = aprobar_solicitud_socio(
                solicitud.pk,
                self.admin,
            )

            self.jugador.refresh_from_db()
            self.assertEqual(socio_resultado.pk, socio.pk)
            self.assertEqual(self.jugador.idsocio_id, socio.pk)
            self.assertEqual(Socio.objects.filter(cisocio="0912345678").count(), 1)

        def test_rechazar_no_crea_socio_y_no_se_puede_resolver_dos_veces(self):
            solicitud = crear_solicitud_socio(self.jugador, self._datos())
            socios_antes = Socio.objects.count()

            rechazar_solicitud_socio(
                solicitud.pk,
                self.admin,
                "No cumple requisitos",
            )

            self.assertEqual(Socio.objects.count(), socios_antes)
            with self.assertRaisesMessage(ValidationError, "La solicitud ya fue resuelta."):
                aprobar_solicitud_socio(solicitud.pk, self.admin)
