from contextlib import nullcontext
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from apps.configuracion.models import Tiposocio
from apps.jugadores.models import Jugador

from . import views as socios_views
from . import services as socios_services
from .forms import RechazarSolicitudSocioForm, SolicitudSocioForm
from .models import Socio, SolicitudSocio


def socio_stub(idsocio=1):
    return Socio(
        idsocio=idsocio,
        idtiposocio=tipo_socio_stub(),
        primernombresocio="Socio",
        segundonombresocio="",
        primerapellidosocio="Prueba",
        segundoapellidosocio="",
        cisocio=str(idsocio).zfill(10),
        fechanacimientosocio=date(1990, 1, 1),
        direcciondomiciliosocio="Direccion",
        estadosocio="Activo",
    )


def tipo_socio_stub(idtiposocio=1):
    return Tiposocio(
        idtiposocio=idtiposocio,
        nombretiposocio=f"Tipo {idtiposocio}",
        roltiposocio=f"tipo_{idtiposocio}",
    )


def jugador_stub(idjugador=1, socio=None):
    return Jugador(
        idjugador=idjugador,
        idsocio=socio,
        aliasjugador=f"jugador{idjugador}",
        correojugador=f"jugador{idjugador}@example.com",
        fecharegistrojugador=datetime(2026, 7, 10, 10, 0),
        saldocreditojugador=Decimal("0.00"),
        estadocuentajugador="Activo",
    )


def solicitud_socio_stub(
    idsolicitud=1,
    jugador=None,
    tipo_socio=None,
    estado=SolicitudSocio.ESTADO_PENDIENTE,
):
    return SolicitudSocio(
        idsolicitud=idsolicitud,
        idjugador=jugador or jugador_stub(),
        idtiposocio=tipo_socio or tipo_socio_stub(),
        primernombresocio="Maria",
        segundonombresocio="",
        primerapellidosocio="Perez",
        segundoapellidosocio="Lopez",
        cisocio="0912345678",
        fechanacimientosocio=date(1995, 5, 20),
        telefonopersonalsocio="0999999999",
        telefonotrabajosocio="",
        direcciondomiciliosocio="Av. Principal",
        direcciontrabajosocio="",
        sexosocio="M",
        estado=estado,
        fechasolicitud=datetime(2026, 7, 10, 10, 0),
    )


class FakeQuerySet(list):
    def all(self):
        return self

    def order_by(self, *fields):
        return self

    def select_related(self, *fields):
        return self

    def filter(self, *args, **kwargs):
        return self

    def exists(self):
        return bool(self)

    def first(self):
        return self[0] if self else None

    def get(self, **kwargs):
        for obj in self:
            if _coincide_objeto(obj, kwargs):
                return obj
        if self:
            return self[0]
        raise LookupError("Objeto no encontrado en FakeQuerySet")


class FakeModelChoiceQuerySet(FakeQuerySet):
    def __init__(self, model, objects):
        self.model = model
        super().__init__(objects)


def _coincide_objeto(obj, filtros):
    for field_name, expected in filtros.items():
        if field_name == "pk":
            value = getattr(obj, "pk", None)
        else:
            value = getattr(obj, field_name, None)
        if str(value) != str(expected):
            return False
    return True


def ahorro_stub(monto, estado="Activo", tipo="Obligatorio"):
    return SimpleNamespace(
        tipoahorro=tipo,
        idbingo="Bingo prueba",
        montoahorro=Decimal(monto),
        fechaahorro=datetime(2026, 7, 8, 10, 30),
        estado=estado,
    )


class RegaloStub(SimpleNamespace):
    def __str__(self):
        return self.nombreregalo


def aporte_stub(valor=Decimal("12.50")):
    return SimpleNamespace(
        numerosemana=3,
        idregalo=RegaloStub(nombreregalo="Regalo semanal", valorregalo=valor),
        fechaplanificadada=datetime(2026, 7, 8, 10, 30),
        fechaentregareal=None,
        estadoaporte="Al Dia",
    )


class SocioDetalleAhorrosTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.usuario = User(username="admin", is_staff=True)
        self.socio = socio_stub()

    def _queryset_ahorros(self, ahorros):
        queryset = MagicMock()
        queryset.select_related.return_value.order_by.return_value = list(ahorros)
        return queryset

    def _queryset_aportes(self):
        queryset = MagicMock()
        queryset.select_related.return_value.order_by.return_value = []
        return queryset

    def _queryset_prestamos(self):
        queryset = MagicMock()
        queryset.order_by.return_value = []
        return queryset

    def _render_detalle(self, *, total_agregado, ahorros=None):
        request = self.factory.get("/socios/1/")
        request.user = self.usuario
        contexto = {}
        ahorros = list(ahorros or [])
        ahorros_qs = self._queryset_ahorros(ahorros)
        total_qs = MagicMock()
        total_qs.aggregate.return_value = {"total": total_agregado}

        def render_spy(_request, _template, context):
            contexto.update(context)
            return HttpResponse("ok")

        with (
            patch("apps.socios.views.get_object_or_404", return_value=self.socio),
            patch(
                "apps.socios.views.Cuentabancaria.objects.filter",
                return_value=MagicMock(order_by=MagicMock(return_value=[])),
            ),
            patch(
                "apps.socios.views.Ahorro.objects.filter",
                side_effect=[ahorros_qs, total_qs],
            ) as ahorros_filter,
            patch(
                "apps.socios.views.Aportesemanal.objects.filter",
                return_value=self._queryset_aportes(),
            ),
            patch(
                "apps.socios.views.Prestamo.objects.filter",
                return_value=self._queryset_prestamos(),
            ),
            patch("apps.socios.views.render", side_effect=render_spy),
        ):
            response = socios_views.detalle(request, self.socio.idsocio)

        return response, contexto, ahorros_filter

    def test_detalle_incluye_total_ahorro_activo_en_contexto(self):
        response, contexto, ahorros_filter = self._render_detalle(
            total_agregado=Decimal("120.00"),
            ahorros=[ahorro_stub("120.00")],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(contexto["total_ahorro_activo"], Decimal("120.00"))
        ahorros_filter.assert_any_call(
            idsocio=self.socio,
            estado__iexact="Activo",
        )

    def test_ahorros_inactivos_no_suman_en_total_activo(self):
        _response, contexto, ahorros_filter = self._render_detalle(
            total_agregado=Decimal("120.00"),
            ahorros=[
                ahorro_stub("120.00", estado="Activo"),
                ahorro_stub("999.00", estado="Inactivo"),
            ],
        )

        self.assertEqual(contexto["total_ahorro_activo"], Decimal("120.00"))
        ahorros_filter.assert_any_call(
            idsocio=self.socio,
            estado__iexact="Activo",
        )

    def test_socio_sin_ahorros_activos_muestra_total_cero(self):
        _response, contexto, _ahorros_filter = self._render_detalle(
            total_agregado=None,
            ahorros=[],
        )

        self.assertEqual(contexto["total_ahorro_activo"], Decimal("0"))

    def test_template_ahorros_muestra_total_activo(self):
        html = render_to_string(
            "socios/includes/tabla_ahorros.html",
            {
                "ahorros": [ahorro_stub("120.00")],
                "total_ahorro_activo": Decimal("120.00"),
            },
        )

        self.assertIn("Total de ahorro activo:", html)
        self.assertIn("$120,00", html)

    def test_template_ahorros_mantiene_tabla_existente(self):
        html = render_to_string(
            "socios/includes/tabla_ahorros.html",
            {
                "ahorros": [ahorro_stub("25.00", tipo="Voluntario")],
                "total_ahorro_activo": Decimal("25.00"),
            },
        )

        self.assertIn("<th>Tipo</th>", html)
        self.assertIn("<th>Bingo</th>", html)
        self.assertIn("<th>Monto</th>", html)
        self.assertIn("Voluntario", html)
        self.assertIn("$25,00", html)

    def test_template_aportes_muestra_valor_regalo_asociado(self):
        html = render_to_string(
            "socios/includes/tabla_aportes.html",
            {"aportes": [aporte_stub(Decimal("12.50"))]},
        )

        self.assertIn("Valor del regalo asociado", html)
        self.assertIn("Regalo semanal", html)
        self.assertIn("$12,50", html)
        self.assertIn("<th>Semana</th>", html)
        self.assertIn("<th>Regalo</th>", html)


class SolicitudSocioModelMetadataTests(SimpleTestCase):
    def test_modelo_solicitud_socio_no_es_gestionado(self):
        self.assertFalse(SolicitudSocio._meta.managed)
        self.assertEqual(SolicitudSocio._meta.db_table, "solicitud_socio")

    def test_primary_key_es_autofield(self):
        pk = SolicitudSocio._meta.pk

        self.assertEqual(pk.name, "idsolicitud")
        self.assertEqual(pk.column, "idsolicitud")
        self.assertTrue(pk.primary_key)

    def test_estados_aprobados(self):
        self.assertEqual(
            tuple(SolicitudSocio._meta.get_field("estado").choices),
            (
                ("Pendiente", "Pendiente"),
                ("Aprobada", "Aprobada"),
                ("Rechazada", "Rechazada"),
            ),
        )


class SolicitudSocioFormTests(SimpleTestCase):
    def _tipo_queryset(self):
        return FakeModelChoiceQuerySet(Tiposocio, [tipo_socio_stub()])

    def test_formulario_rechaza_campos_obligatorios_vacios(self):
        form = SolicitudSocioForm(data={}, tipo_socio_queryset=self._tipo_queryset())

        self.assertFalse(form.is_valid())
        for field_name in (
            "primernombresocio",
            "primerapellidosocio",
            "segundoapellidosocio",
            "cisocio",
            "fechanacimientosocio",
            "direcciondomiciliosocio",
        ):
            self.assertIn(field_name, form.errors)

    def test_formulario_limpia_textos_importantes(self):
        form = SolicitudSocioForm(
            data={
                "idtiposocio": "",
                "primernombresocio": "  Maria ",
                "segundonombresocio": "",
                "primerapellidosocio": " Perez ",
                "segundoapellidosocio": " Lopez ",
                "cisocio": " 0912345678 ",
                "fechanacimientosocio": "1995-05-20",
                "direcciondomiciliosocio": " Av. Principal ",
                "sexosocio": "",
                "observacion": "  revisar datos ",
            },
            tipo_socio_queryset=self._tipo_queryset(),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["primernombresocio"], "Maria")
        self.assertEqual(form.cleaned_data["cisocio"], "0912345678")
        self.assertEqual(form.cleaned_data["observacion"], "revisar datos")

    def test_formulario_rechazo_exige_motivo(self):
        form = RechazarSolicitudSocioForm(data={"motivorechazo": "  "})

        self.assertFalse(form.is_valid())
        self.assertIn("motivorechazo", form.errors)


class SolicitudSocioServicesTests(SimpleTestCase):
    def _datos_solicitud(self, **overrides):
        datos = {
            "idtiposocio": tipo_socio_stub(),
            "primernombresocio": " Maria ",
            "segundonombresocio": "",
            "primerapellidosocio": "Perez",
            "segundoapellidosocio": "Lopez",
            "cisocio": "0912345678",
            "fechanacimientosocio": date(1995, 5, 20),
            "telefonopersonalsocio": "0999999999",
            "telefonotrabajosocio": "",
            "direcciondomiciliosocio": "Av. Principal",
            "direcciontrabajosocio": "",
            "sexosocio": "M",
            "observacion": "",
        }
        datos.update(overrides)
        return datos

    def test_jugador_no_socio_puede_crear_solicitud(self):
        jugador = jugador_stub()
        solicitud = solicitud_socio_stub(jugador=jugador)

        with patch("apps.socios.services.transaction.atomic", return_value=nullcontext()), patch(
            "apps.socios.services.Jugador.objects.select_for_update",
            return_value=FakeQuerySet([jugador]),
        ), patch(
            "apps.socios.services.SolicitudSocio.objects.filter",
            return_value=FakeQuerySet(),
        ), patch(
            "apps.socios.services.SolicitudSocio.objects.create",
            return_value=solicitud,
        ) as create_mock:
            resultado = socios_services.crear_solicitud_socio(
                jugador,
                self._datos_solicitud(),
            )

        self.assertIs(resultado, solicitud)
        self.assertEqual(create_mock.call_args.kwargs["estado"], "Pendiente")
        self.assertIs(create_mock.call_args.kwargs["idjugador"], jugador)
        self.assertEqual(create_mock.call_args.kwargs["cisocio"], "0912345678")

    def test_jugador_socio_no_puede_crear_solicitud(self):
        jugador = jugador_stub(socio=socio_stub())

        with patch("apps.socios.services.transaction.atomic", return_value=nullcontext()), patch(
            "apps.socios.services.Jugador.objects.select_for_update",
            return_value=FakeQuerySet([jugador]),
        ), patch("apps.socios.services.SolicitudSocio.objects.create") as create_mock:
            with self.assertRaises(ValidationError) as context:
                socios_services.crear_solicitud_socio(
                    jugador,
                    self._datos_solicitud(),
                )

        self.assertIn("El jugador ya está vinculado a un socio.", str(context.exception))
        create_mock.assert_not_called()

    def test_no_permite_duplicar_solicitud_pendiente(self):
        jugador = jugador_stub()
        pendiente = solicitud_socio_stub(jugador=jugador)

        with patch("apps.socios.services.transaction.atomic", return_value=nullcontext()), patch(
            "apps.socios.services.Jugador.objects.select_for_update",
            return_value=FakeQuerySet([jugador]),
        ), patch(
            "apps.socios.services.SolicitudSocio.objects.filter",
            return_value=FakeQuerySet([pendiente]),
        ), patch("apps.socios.services.SolicitudSocio.objects.create") as create_mock:
            with self.assertRaises(ValidationError) as context:
                socios_services.crear_solicitud_socio(
                    jugador,
                    self._datos_solicitud(),
                )

        self.assertIn("Ya existe una solicitud pendiente", str(context.exception))
        create_mock.assert_not_called()

    def test_admin_aprueba_y_crea_socio_si_cedula_no_existe(self):
        admin = User(username="admin", is_staff=True)
        jugador = jugador_stub()
        solicitud = solicitud_socio_stub(jugador=jugador)

        with self._patch_aprobacion(solicitud, jugador, socios=[]) as mocks:
            resultado, socio = socios_services.aprobar_solicitud_socio(
                solicitud.idsolicitud,
                admin,
            )

        self.assertIs(resultado, solicitud)
        self.assertEqual(socio.idsocio, 99)
        self.assertIs(jugador.idsocio, socio)
        self.assertEqual(solicitud.estado, "Aprobada")
        self.assertIs(solicitud.idusuarioadminrespuesta, admin)
        self.assertIs(solicitud.idsocioresultado, socio)
        mocks["assign_pk"].assert_called_once_with(socio)
        mocks["socio_save"].assert_called_once()
        mocks["jugador_save"].assert_called_once()
        mocks["solicitud_save"].assert_called_once()

    def test_admin_aprueba_y_vincula_socio_existente(self):
        admin = User(username="admin", is_staff=True)
        jugador = jugador_stub()
        solicitud = solicitud_socio_stub(jugador=jugador)
        socio_existente = socio_stub(idsocio=50)
        socio_existente.cisocio = solicitud.cisocio

        with self._patch_aprobacion(solicitud, jugador, socios=[socio_existente]) as mocks:
            _resultado, socio = socios_services.aprobar_solicitud_socio(
                solicitud.idsolicitud,
                admin,
            )

        self.assertIs(socio, socio_existente)
        self.assertIs(jugador.idsocio, socio_existente)
        self.assertEqual(solicitud.estado, "Aprobada")
        mocks["assign_pk"].assert_not_called()
        mocks["socio_save"].assert_not_called()
        mocks["jugador_save"].assert_called_once()

    def test_no_se_puede_aprobar_solicitud_ya_aprobada(self):
        admin = User(username="admin", is_staff=True)
        jugador = jugador_stub()
        solicitud = solicitud_socio_stub(
            jugador=jugador,
            estado=SolicitudSocio.ESTADO_APROBADA,
        )

        with self._patch_aprobacion(solicitud, jugador, socios=[]) as mocks:
            with self.assertRaises(ValidationError) as context:
                socios_services.aprobar_solicitud_socio(
                    solicitud.idsolicitud,
                    admin,
                )

        self.assertIn("La solicitud ya fue resuelta.", str(context.exception))
        mocks["socio_filter"].assert_not_called()
        mocks["jugador_save"].assert_not_called()

    def test_no_se_puede_aprobar_si_jugador_ya_fue_vinculado(self):
        admin = User(username="admin", is_staff=True)
        jugador_solicitud = jugador_stub()
        jugador_bloqueado = jugador_stub(socio=socio_stub())
        solicitud = solicitud_socio_stub(jugador=jugador_solicitud)

        with self._patch_aprobacion(solicitud, jugador_bloqueado, socios=[]) as mocks:
            with self.assertRaises(ValidationError) as context:
                socios_services.aprobar_solicitud_socio(
                    solicitud.idsolicitud,
                    admin,
                )

        self.assertIn("jugador ya fue vinculado", str(context.exception))
        mocks["socio_filter"].assert_not_called()
        mocks["jugador_save"].assert_not_called()

    def test_rechazar_deja_solicitud_rechazada_sin_modificar_jugador(self):
        admin = User(username="admin", is_staff=True)
        jugador = jugador_stub()
        solicitud = solicitud_socio_stub(jugador=jugador)

        with patch("apps.socios.services.transaction.atomic", return_value=nullcontext()), patch(
            "apps.socios.services.SolicitudSocio.objects.select_for_update",
            return_value=FakeQuerySet([solicitud]),
        ), patch.object(SolicitudSocio, "save", autospec=True) as solicitud_save, patch.object(
            Jugador,
            "save",
            autospec=True,
        ) as jugador_save, patch.object(Socio, "save", autospec=True) as socio_save:
            resultado = socios_services.rechazar_solicitud_socio(
                solicitud.idsolicitud,
                admin,
                "No cumple requisitos",
            )

        self.assertIs(resultado, solicitud)
        self.assertEqual(solicitud.estado, "Rechazada")
        self.assertEqual(solicitud.motivorechazo, "No cumple requisitos")
        self.assertIs(solicitud.idusuarioadminrespuesta, admin)
        self.assertIsNone(jugador.idsocio_id)
        solicitud_save.assert_called_once()
        jugador_save.assert_not_called()
        socio_save.assert_not_called()

    def test_no_se_puede_rechazar_solicitud_ya_aprobada(self):
        admin = User(username="admin", is_staff=True)
        solicitud = solicitud_socio_stub(estado=SolicitudSocio.ESTADO_APROBADA)

        with patch("apps.socios.services.transaction.atomic", return_value=nullcontext()), patch(
            "apps.socios.services.SolicitudSocio.objects.select_for_update",
            return_value=FakeQuerySet([solicitud]),
        ), patch.object(SolicitudSocio, "save", autospec=True) as solicitud_save:
            with self.assertRaises(ValidationError) as context:
                socios_services.rechazar_solicitud_socio(
                    solicitud.idsolicitud,
                    admin,
                    "No cumple requisitos",
                )

        self.assertIn("La solicitud ya fue resuelta.", str(context.exception))
        solicitud_save.assert_not_called()

    def test_rechazar_exige_motivo(self):
        admin = User(username="admin", is_staff=True)

        with self.assertRaises(ValidationError) as context:
            socios_services.rechazar_solicitud_socio(1, admin, "  ")

        self.assertIn("Debe ingresar un motivo de rechazo.", str(context.exception))

    def _patch_aprobacion(self, solicitud, jugador_bloqueado, socios):
        patches = [
            patch("apps.socios.services.transaction.atomic", return_value=nullcontext()),
            patch(
                "apps.socios.services.SolicitudSocio.objects.select_for_update",
                return_value=FakeQuerySet([solicitud]),
            ),
            patch(
                "apps.socios.services.Jugador.objects.select_for_update",
                return_value=FakeQuerySet([jugador_bloqueado]),
            ),
            patch(
                "apps.socios.services.Socio.objects.filter",
                return_value=FakeQuerySet(socios),
            ),
            patch(
                "apps.socios.services.assign_next_integer_pk",
                side_effect=lambda socio: setattr(socio, "idsocio", 99) or socio,
            ),
            patch.object(Socio, "save", autospec=True),
            patch.object(Jugador, "save", autospec=True),
            patch.object(SolicitudSocio, "save", autospec=True),
        ]
        return _PatchGroup(
            patches,
            (
                "atomic",
                "solicitud_select",
                "jugador_select",
                "socio_filter",
                "assign_pk",
                "socio_save",
                "jugador_save",
                "solicitud_save",
            ),
        )


class _PatchGroup:
    def __init__(self, patches, names):
        self.patches = patches
        self.names = names
        self.mocks = {}

    def __enter__(self):
        for name, patcher in zip(self.names, self.patches):
            self.mocks[name] = patcher.__enter__()
        return self.mocks

    def __exit__(self, exc_type, exc_value, traceback):
        for patcher in reversed(self.patches):
            patcher.__exit__(exc_type, exc_value, traceback)
