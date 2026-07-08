from contextlib import nullcontext
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import models as django_models
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.configuracion.models import Metodopago
from apps.socios.models import Socio

from . import services as finanzas_services
from . import views as finanzas_views
from .forms import PagoPrestamoForm, PrestamoConGarantesForm
from .models import Pago, PagoPrestamo, Prestamo, PrestamoGarante
from .services import (
    PrestamoGarantiaError,
    PrestamoPagoError,
    calcular_capacidad_garante,
    construir_datos_garantes,
    crear_prestamo_con_garantes,
    registrar_pago_prestamo,
    validar_garantes_prestamo,
)


class FakeSocioQuerySet:
    model = Socio

    def __init__(self, socios):
        self.socios = list(socios)

    def all(self):
        return self

    def order_by(self, *fields):
        return self

    def get(self, **kwargs):
        valor = next(iter(kwargs.values()))
        for socio in self.socios:
            if str(socio.idsocio) == str(valor):
                return socio
        raise Socio.DoesNotExist


def socio_stub(idsocio, nombre=None):
    return Socio(
        idsocio=idsocio,
        primernombresocio=nombre or f"Socio {idsocio}",
        segundonombresocio="",
        primerapellidosocio="Prueba",
        segundoapellidosocio="",
        cisocio=str(idsocio).zfill(10),
        estadosocio="Activo",
    )


class PrestamoGaranteModelMetadataTests(SimpleTestCase):
    def test_prestamo_primary_key_es_autofield(self):
        pk = Prestamo._meta.pk

        self.assertIsInstance(pk, django_models.AutoField)
        self.assertEqual(pk.name, "idprestamo")
        self.assertEqual(pk.column, "idprestamo")
        self.assertTrue(pk.primary_key)

    def test_modelo_existe_y_no_es_gestionado(self):
        self.assertEqual(PrestamoGarante.__name__, "PrestamoGarante")
        self.assertFalse(PrestamoGarante._meta.managed)

    def test_tabla_fisica_correcta(self):
        self.assertEqual(PrestamoGarante._meta.db_table, "prestamo_garante")

    def test_primary_key_correcta(self):
        pk = PrestamoGarante._meta.pk

        self.assertIsInstance(pk, django_models.AutoField)
        self.assertEqual(pk.name, "idprestamogarante")
        self.assertEqual(pk.column, "idprestamogarante")
        self.assertTrue(pk.primary_key)

    def test_columnas_fisicas_correctas(self):
        columnas = {
            field.name: field.column
            for field in PrestamoGarante._meta.fields
        }

        self.assertEqual(
            columnas,
            {
                "idprestamogarante": "idprestamogarante",
                "idprestamo": "idprestamo",
                "idgarante": "idgarante",
                "capacidadcalculada": "capacidadcalculada",
                "fecharegistro": "fecharegistro",
                "estado": "estado",
            },
        )

    def test_foreign_key_a_prestamo_usa_idprestamo(self):
        field = PrestamoGarante._meta.get_field("idprestamo")

        self.assertIs(field.remote_field.model, Prestamo)
        self.assertEqual(field.column, "idprestamo")

    def test_foreign_key_a_socio_usa_idgarante(self):
        field = PrestamoGarante._meta.get_field("idgarante")

        self.assertIs(field.remote_field.model, Socio)
        self.assertEqual(field.column, "idgarante")

    def test_estado_tiene_choices_activo_inactivo(self):
        field = PrestamoGarante._meta.get_field("estado")

        self.assertEqual(
            tuple(field.choices),
            (
                ("Activo", "Activo"),
                ("Inactivo", "Inactivo"),
            ),
        )
        self.assertEqual(field.default, "Activo")

    def test_capacidadcalculada_precision_decimal(self):
        field = PrestamoGarante._meta.get_field("capacidadcalculada")

        self.assertEqual(field.max_digits, 12)
        self.assertEqual(field.decimal_places, 2)


class PagoPrestamoModelMetadataTests(SimpleTestCase):
    def test_modelo_existe_y_no_es_gestionado(self):
        self.assertEqual(PagoPrestamo.__name__, "PagoPrestamo")
        self.assertFalse(PagoPrestamo._meta.managed)

    def test_tabla_fisica_correcta(self):
        self.assertEqual(PagoPrestamo._meta.db_table, "pago_prestamo")

    def test_primary_key_es_autofield(self):
        pk = PagoPrestamo._meta.pk

        self.assertIsInstance(pk, django_models.AutoField)
        self.assertEqual(pk.name, "idpagoprestamo")
        self.assertEqual(pk.column, "idpagoprestamo")
        self.assertTrue(pk.primary_key)

    def test_foreign_key_a_prestamo_usa_idprestamo(self):
        field = PagoPrestamo._meta.get_field("idprestamo")

        self.assertIs(field.remote_field.model, Prestamo)
        self.assertEqual(field.column, "idprestamo")

    def test_foreign_key_a_metodopago_usa_idmetodopago(self):
        field = PagoPrestamo._meta.get_field("idmetodopago")

        self.assertIs(field.remote_field.model, Metodopago)
        self.assertEqual(field.column, "idmetodopago")
        self.assertTrue(field.null)
        self.assertTrue(field.blank)

    def test_montopagado_precision_decimal(self):
        field = PagoPrestamo._meta.get_field("montopagado")

        self.assertEqual(field.max_digits, 12)
        self.assertEqual(field.decimal_places, 2)

    def test_estado_tiene_choices_registrado_anulado(self):
        field = PagoPrestamo._meta.get_field("estado")

        self.assertEqual(
            tuple(field.choices),
            (
                ("Registrado", "Registrado"),
                ("Anulado", "Anulado"),
            ),
        )
        self.assertEqual(field.default, "Registrado")

    def test_prestamo_garante_conserva_metadata_actual(self):
        self.assertEqual(PrestamoGarante._meta.db_table, "prestamo_garante")
        self.assertEqual(PrestamoGarante._meta.pk.name, "idprestamogarante")
        self.assertEqual(PrestamoGarante._meta.pk.column, "idprestamogarante")

    def test_pago_actual_conserva_tabla_y_columnas(self):
        columnas = {
            field.name: field.column
            for field in Pago._meta.fields
        }

        self.assertEqual(Pago._meta.db_table, "pago")
        self.assertEqual(Pago._meta.pk.name, "idpago")
        self.assertEqual(
            columnas,
            {
                "idpago": "idpago",
                "idprestamo": "idprestamo",
                "idmetodopago": "idmetodopago",
                "montopagado": "montopagado",
                "numeroreferencia": "numeroreferencia",
                "fechapago": "fechapago",
                "fechaconfirmacionadmin": "fechaconfirmacionadmin",
                "comprobantepago": "comprobantepago",
                "estadopago": "estadopago",
            },
        )


class PrestamoConGarantesFormTests(SimpleTestCase):
    def setUp(self):
        self.socios = [
            socio_stub(1, "Deudor"),
            socio_stub(2, "Garante Uno"),
            socio_stub(3, "Garante Dos"),
        ]
        self.socio_queryset = FakeSocioQuerySet(self.socios)

    def _datos_formulario(self, **overrides):
        datos = {
            "idsocio": "1",
            "montoprestamosolicitado": "1000.00",
            "tasainteres": "5.00",
            "montototalpagar": "1050.00",
            "saldopendiente": "1050.00",
            "numerocuotas": "10",
            "fechasolicitud": "2026-07-08",
            "fechavencimiento": "2026-12-08",
            "estadoprestamo": "Solicitado",
            "garante_1": "",
            "garante_2": "",
        }
        datos.update(overrides)
        return datos

    def _form(self, **overrides):
        return PrestamoConGarantesForm(
            data=self._datos_formulario(**overrides),
            socio_queryset=self.socio_queryset,
        )

    def _is_valid(self, form):
        with patch.object(Prestamo, "full_clean"):
            return form.is_valid()

    def test_formulario_permite_garantes_vacios(self):
        form = self._form()

        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertEqual(form.garantes_seleccionados(), [])

    def test_formulario_permite_solo_garante_1(self):
        form = self._form(garante_1="2", garante_2="")

        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertEqual(
            [socio.idsocio for socio in form.garantes_seleccionados()],
            [2],
        )

    def test_formulario_permite_solo_garante_2(self):
        form = self._form(garante_1="", garante_2="2")

        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertEqual(
            [socio.idsocio for socio in form.garantes_seleccionados()],
            [2],
        )

    def test_formulario_permite_dos_garantes(self):
        form = self._form(garante_1="2", garante_2="3")

        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertEqual(
            [socio.idsocio for socio in form.garantes_seleccionados()],
            [2, 3],
        )

    def test_formulario_rechaza_garante_igual_a_socio_deudor(self):
        form = self._form(garante_1="1", garante_2="2")

        self.assertFalse(self._is_valid(form))
        self.assertIn("garante_1", form.errors)
        self.assertIn(
            "El garante no puede ser el mismo socio deudor.",
            form.errors["garante_1"],
        )

    def test_formulario_rechaza_garante_repetido(self):
        form = self._form(garante_1="2", garante_2="2")

        self.assertFalse(self._is_valid(form))
        self.assertIn("garante_2", form.errors)
        self.assertIn("No puede repetir el mismo garante.", form.errors["garante_2"])


class PagoPrestamoFormTests(SimpleTestCase):
    def _form(self, **overrides):
        datos = {
            "idmetodopago": "",
            "montopagado": "10.00",
            "numeroreferencia": "",
            "observacion": "",
        }
        datos.update(overrides)
        return PagoPrestamoForm(
            data=datos,
            metodo_pago_queryset=Metodopago.objects.none(),
        )

    def test_formulario_rechaza_monto_cero(self):
        form = self._form(montopagado="0")

        self.assertFalse(form.is_valid())
        self.assertIn("montopagado", form.errors)
        self.assertIn(
            "El monto del pago debe ser mayor que cero.",
            form.errors["montopagado"],
        )

    def test_formulario_rechaza_monto_negativo(self):
        form = self._form(montopagado="-1.00")

        self.assertFalse(form.is_valid())
        self.assertIn("montopagado", form.errors)

    def test_formulario_limpia_referencia_y_observacion(self):
        form = self._form(
            numeroreferencia=" REF-001 ",
            observacion=" Pago de cuota ",
        )

        self.assertTrue(form.is_valid(), form.errors.as_data())
        self.assertEqual(form.cleaned_data["numeroreferencia"], "REF-001")
        self.assertEqual(form.cleaned_data["observacion"], "Pago de cuota")


class PrestamoConGarantesViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.usuario = User(username="admin", is_staff=True)

    def _request_post(self):
        request = self.factory.post("/finanzas/prestamos/nuevo/", data={"x": "1"})
        request.user = self.usuario
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _request_pago_post(self):
        request = self.factory.post(
            "/finanzas/prestamos/10/pagos/nuevo/",
            data={
                "idmetodopago": "",
                "montopagado": "100.00",
                "numeroreferencia": " REF-01 ",
                "observacion": " Pago inicial ",
            },
        )
        request.user = self.usuario
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _request_get(self):
        request = self.factory.get("/finanzas/prestamos/10/")
        request.user = self.usuario
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_prestamo_nuevo_llama_servicio_con_formulario_valido(self):
        request = self._request_post()
        datos_prestamo = {
            "idsocio": socio_stub(1, "Deudor"),
            "montoprestamosolicitado": Decimal("1000.00"),
            "tasainteres": Decimal("5.00"),
            "montototalpagar": Decimal("1050.00"),
            "saldopendiente": Decimal("1050.00"),
            "numerocuotas": 10,
            "fechasolicitud": date(2026, 7, 8),
            "fechavencimiento": date(2026, 12, 8),
            "estadoprestamo": "Solicitado",
        }
        garantes = [socio_stub(2, "Garante Uno"), socio_stub(3, "Garante Dos")]
        prestamo = Prestamo(idprestamo=99)
        form = MagicMock()
        form.is_valid.return_value = True
        form.datos_prestamo.return_value = datos_prestamo
        form.garantes_seleccionados.return_value = garantes

        with (
            patch(
                "apps.finanzas.views.PrestamoConGarantesForm",
                return_value=form,
            ) as form_class,
            patch(
                "apps.finanzas.views.crear_prestamo_con_garantes",
                return_value=prestamo,
            ) as crear,
            patch("apps.finanzas.views.save_new_model_form") as save_directo,
        ):
            response = finanzas_views.prestamo_nuevo(request)

        form_class.assert_called_once_with(request.POST)
        crear.assert_called_once_with(
            datos_prestamo=datos_prestamo,
            garantes=garantes,
            usuario=request.user,
        )
        save_directo.assert_not_called()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/finanzas/prestamos/99/", response["Location"])

    def test_prestamo_nuevo_muestra_error_si_servicio_rechaza(self):
        request = self._request_post()
        form = MagicMock()
        form.is_valid.return_value = True
        form.datos_prestamo.return_value = {"idsocio": socio_stub(1, "Deudor")}
        form.garantes_seleccionados.return_value = [socio_stub(2, "Garante")]
        errores_no_asociados = []

        def add_error(field, error):
            if field is None:
                errores_no_asociados.append(error)

        form.add_error.side_effect = add_error

        def render_spy(_request, _template, context):
            contenido = "\n".join(errores_no_asociados)
            self.assertIs(context["form"], form)
            return HttpResponse(contenido)

        with (
            patch(
                "apps.finanzas.views.PrestamoConGarantesForm",
                return_value=form,
            ),
            patch(
                "apps.finanzas.views.crear_prestamo_con_garantes",
                side_effect=PrestamoGarantiaError(
                    "La capacidad total de los garantes debe cubrir al menos el 50% del monto solicitado."
                ),
            ) as crear,
            patch("apps.finanzas.views.render", side_effect=render_spy),
        ):
            response = finanzas_views.prestamo_nuevo(request)

        crear.assert_called_once()
        form.add_error.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "La capacidad total de los garantes",
            response.content.decode(),
        )

    def test_pago_nuevo_usa_servicio_y_no_guardado_directo(self):
        request = self._request_pago_post()
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            saldopendiente=Decimal("300.00"),
        )

        with (
            patch("apps.finanzas.views.get_object_or_404", return_value=prestamo),
            patch(
                "apps.finanzas.views.registrar_pago_prestamo",
                return_value=PagoPrestamo(idpagoprestamo=5),
            ) as registrar_pago,
            patch("apps.finanzas.views.save_new_model_form") as save_directo,
        ):
            response = finanzas_views.pago_nuevo(request, 10)

        registrar_pago.assert_called_once()
        llamada = registrar_pago.call_args.kwargs
        self.assertIs(registrar_pago.call_args.args[0], prestamo)
        self.assertEqual(llamada["monto_pagado"], Decimal("100.00"))
        self.assertIsNone(llamada["metodo_pago"])
        self.assertEqual(llamada["numero_referencia"], "REF-01")
        self.assertEqual(llamada["observacion"], "Pago inicial")
        save_directo.assert_not_called()
        self.assertNotIn("Pago", finanzas_views.__dict__)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/finanzas/prestamos/10/", response["Location"])

    def test_pago_nuevo_muestra_error_si_servicio_rechaza(self):
        request = self._request_pago_post()
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            saldopendiente=Decimal("300.00"),
        )
        errores_no_asociados = []

        def render_spy(_request, _template, context):
            errores_no_asociados.extend(context["form"].non_field_errors())
            return HttpResponse("\n".join(errores_no_asociados))

        with (
            patch("apps.finanzas.views.get_object_or_404", return_value=prestamo),
            patch(
                "apps.finanzas.views.registrar_pago_prestamo",
                side_effect=PrestamoPagoError(
                    "El monto del pago no puede superar el saldo pendiente."
                ),
            ) as registrar_pago,
            patch("apps.finanzas.views.render", side_effect=render_spy),
        ):
            response = finanzas_views.pago_nuevo(request, 10)

        registrar_pago.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "El monto del pago no puede superar el saldo pendiente.",
            response.content.decode(),
        )

    def test_pagos_lista_usa_pago_prestamo(self):
        request = self.factory.get("/finanzas/pagos/")
        request.user = self.usuario
        pagos_qs = MagicMock()
        pagos_ordenados = MagicMock()
        pagos_qs.order_by.return_value = pagos_ordenados
        pagos_ordenados.count.return_value = 2
        contexto = {}

        def render_spy(_request, _template, context):
            contexto.update(context)
            return HttpResponse("ok")

        with (
            patch(
                "apps.finanzas.views.PagoPrestamo.objects.select_related",
                return_value=pagos_qs,
            ) as select_related,
            patch("apps.finanzas.views.paginate", return_value=["page"]) as paginate,
            patch("apps.finanzas.views.render", side_effect=render_spy),
        ):
            response = finanzas_views.pagos_lista(request)

        self.assertEqual(response.status_code, 200)
        select_related.assert_called_once_with(
            "idprestamo",
            "idprestamo__idsocio",
            "idmetodopago",
        )
        paginate.assert_called_once_with(request, pagos_ordenados)
        self.assertEqual(contexto["page_obj"], ["page"])
        self.assertEqual(contexto["total"], 2)
        self.assertNotIn("Pago", finanzas_views.__dict__)

    def test_prestamo_detalle_carga_pagos_y_total_pagado_registrado(self):
        request = self._request_get()
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            saldopendiente=Decimal("300.00"),
            estadoprestamo="Aprobado",
        )
        garantes = [
            PrestamoGarante(
                idprestamo=prestamo,
                idgarante=socio_stub(2, "Garante"),
                capacidadcalculada=Decimal("500.00"),
                estado=PrestamoGarante.ESTADO_ACTIVO,
            )
        ]
        pagos = [
            PagoPrestamo(
                idpagoprestamo=5,
                idprestamo=prestamo,
                fechapago=datetime(2026, 7, 8, 10, 30),
                montopagado=Decimal("125.00"),
                estado=PagoPrestamo.ESTADO_REGISTRADO,
            )
        ]
        garantes_qs = MagicMock()
        garantes_qs.select_related.return_value.order_by.return_value = garantes
        pagos_qs = MagicMock()
        pagos_qs.select_related.return_value.order_by.return_value = pagos
        total_qs = MagicMock()
        total_qs.aggregate.return_value = {"total": Decimal("125.00")}
        contexto = {}

        def render_spy(_request, _template, context):
            contexto.update(context)
            return HttpResponse("ok")

        with (
            patch("apps.finanzas.views.get_object_or_404", return_value=prestamo),
            patch(
                "apps.finanzas.views.PrestamoGarante.objects.filter",
                return_value=garantes_qs,
            ) as garantes_filter,
            patch(
                "apps.finanzas.views.PagoPrestamo.objects.filter",
                side_effect=[pagos_qs, total_qs],
            ) as pagos_filter,
            patch("apps.finanzas.views.render", side_effect=render_spy),
        ):
            response = finanzas_views.prestamo_detalle(request, 10)

        self.assertEqual(response.status_code, 200)
        garantes_filter.assert_called_once_with(
            idprestamo=prestamo,
            estado=PrestamoGarante.ESTADO_ACTIVO,
        )
        self.assertEqual(contexto["garantes"], garantes)
        self.assertEqual(contexto["pagos"], pagos)
        self.assertEqual(contexto["total_pagado"], Decimal("125.00"))
        self.assertTrue(contexto["puede_registrar_pago"])
        self.assertEqual(pagos_filter.call_count, 2)
        pagos_filter.assert_any_call(idprestamo=prestamo)
        pagos_filter.assert_any_call(
            idprestamo=prestamo,
            estado=PagoPrestamo.ESTADO_REGISTRADO,
        )

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }
    )
    def test_template_detalle_muestra_historial_y_boton_de_pago(self):
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            montoprestamosolicitado=Decimal("1000.00"),
            montototalpagar=Decimal("1050.00"),
            saldopendiente=Decimal("925.00"),
            numerocuotas=10,
            fechasolicitud=date(2026, 7, 8),
            fechavencimiento=date(2026, 12, 8),
            estadoprestamo="Aprobado",
        )
        garantes = [
            PrestamoGarante(
                idprestamo=prestamo,
                idgarante=socio_stub(2, "Garante"),
                capacidadcalculada=Decimal("500.00"),
                estado=PrestamoGarante.ESTADO_ACTIVO,
            )
        ]
        pagos = [
            PagoPrestamo(
                idpagoprestamo=1,
                idprestamo=prestamo,
                idmetodopago=Metodopago(nombremetodopago="Transferencia"),
                fechapago=datetime(2026, 7, 8, 10, 30),
                montopagado=Decimal("125.00"),
                numeroreferencia="REF-001",
                estado=PagoPrestamo.ESTADO_REGISTRADO,
            )
        ]

        html = render_to_string(
            "finanzas/prestamo_detalle.html",
            {
                "prestamo": prestamo,
                "garantes": garantes,
                "pagos": pagos,
                "total_pagado": Decimal("125.00"),
                "puede_registrar_pago": True,
            },
        )

        self.assertIn("Garantes activos", html)
        self.assertIn("Garante", html)
        self.assertIn("Historial de pagos", html)
        self.assertIn("Registrar pago", html)
        self.assertIn("REF-001", html)
        self.assertIn("$125,00", html)
        self.assertNotIn("Los pagos de préstamos se normalizarán", html)

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }
    )
    def test_template_detalle_oculta_boton_si_prestamo_liquidado(self):
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            montoprestamosolicitado=Decimal("1000.00"),
            montototalpagar=Decimal("1050.00"),
            saldopendiente=Decimal("0.00"),
            fechasolicitud=date(2026, 7, 8),
            fechavencimiento=date(2026, 12, 8),
            estadoprestamo="Liquidado",
        )

        html = render_to_string(
            "finanzas/prestamo_detalle.html",
            {
                "prestamo": prestamo,
                "garantes": [],
                "pagos": [],
                "total_pagado": Decimal("1050.00"),
                "puede_registrar_pago": False,
            },
        )

        self.assertNotIn("Registrar pago", html)
        self.assertIn("Aún no hay pagos registrados para este préstamo.", html)


class RegistrarPagoPrestamoTests(SimpleTestCase):
    def _prestamo_bloqueado(
        self,
        *,
        saldo=Decimal("300.00"),
        estado="Aprobado",
    ):
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            montoprestamosolicitado=Decimal("1000.00"),
            tasainteres=Decimal("5.00"),
            montototalpagar=Decimal("1050.00"),
            saldopendiente=saldo,
            numerocuotas=10,
            fechasolicitud=date(2026, 7, 8),
            fechavencimiento=date(2026, 12, 8),
            estadoprestamo=estado,
        )
        prestamo.save = MagicMock()
        return prestamo

    def _patch_prestamo_bloqueado(self, prestamo):
        prestamos_bloqueados = MagicMock()
        prestamos_bloqueados.get.return_value = prestamo
        return (
            patch(
                "apps.finanzas.services.Prestamo.objects.select_for_update",
                return_value=prestamos_bloqueados,
            ),
            prestamos_bloqueados,
        )

    def test_rechaza_montos_invalidos(self):
        prestamo = Prestamo(idprestamo=10)
        montos_invalidos = (
            None,
            True,
            Decimal("0"),
            Decimal("-1.00"),
            "valor invalido",
            Decimal("NaN"),
            Decimal("Infinity"),
        )

        for monto in montos_invalidos:
            with self.subTest(monto=monto):
                with self.assertRaisesMessage(
                    PrestamoPagoError,
                    "El monto del pago debe ser mayor que cero.",
                ):
                    registrar_pago_prestamo(prestamo, monto_pagado=monto)

    def test_rechaza_prestamo_con_saldo_cero(self):
        prestamo = self._prestamo_bloqueado(saldo=Decimal("0.00"))
        bloqueo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.PagoPrestamo.objects.create"
            ) as pago_create,
        ):
            with self.assertRaisesMessage(
                PrestamoPagoError,
                "El préstamo no tiene saldo pendiente.",
            ):
                registrar_pago_prestamo(prestamo, monto_pagado=Decimal("10.00"))

        pago_create.assert_not_called()
        prestamo.save.assert_not_called()

    def test_rechaza_prestamo_en_estado_liquidado(self):
        prestamo = self._prestamo_bloqueado(
            saldo=Decimal("100.00"),
            estado="Liquidado",
        )
        bloqueo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.PagoPrestamo.objects.create"
            ) as pago_create,
        ):
            with self.assertRaisesMessage(
                PrestamoPagoError,
                "No se pueden registrar pagos para un préstamo cerrado o liquidado.",
            ):
                registrar_pago_prestamo(prestamo, monto_pagado=Decimal("10.00"))

        pago_create.assert_not_called()
        prestamo.save.assert_not_called()

    def test_rechaza_sobrepago(self):
        prestamo = self._prestamo_bloqueado(saldo=Decimal("100.00"))
        bloqueo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.PagoPrestamo.objects.create"
            ) as pago_create,
        ):
            with self.assertRaisesMessage(
                PrestamoPagoError,
                "El monto del pago no puede superar el saldo pendiente.",
            ):
                registrar_pago_prestamo(prestamo, monto_pagado=Decimal("150.00"))

        pago_create.assert_not_called()
        prestamo.save.assert_not_called()

    def test_pago_parcial_valido_bloquea_crea_pago_y_descuenta_saldo(self):
        prestamo_recibido = Prestamo(idprestamo=10)
        prestamo = self._prestamo_bloqueado(saldo=Decimal("300.00"))
        metodo_pago = Metodopago(idmetodopago=2)
        fecha_pago = datetime(2026, 7, 8, 10, 30)
        pago_creado = PagoPrestamo(idpagoprestamo=1)
        bloqueo_patch, prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        monto_original = prestamo.montoprestamosolicitado
        total_original = prestamo.montototalpagar
        socio_original = prestamo.idsocio

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic,
            bloqueo_patch as select_for_update,
            patch(
                "apps.finanzas.services.PagoPrestamo.objects.create",
                return_value=pago_creado,
            ) as pago_prestamo_create,
            patch.object(Pago.objects, "create") as pago_create,
            patch.object(Pago.objects, "filter") as pago_filter,
        ):
            pago = registrar_pago_prestamo(
                prestamo_recibido,
                monto_pagado="125.50",
                metodo_pago=metodo_pago,
                numero_referencia=" REF-123 ",
                observacion=" Pago parcial ",
                fecha_pago=fecha_pago,
            )

        self.assertIs(pago, pago_creado)
        atomic.assert_called_once()
        select_for_update.assert_called_once_with()
        prestamos_bloqueados.get.assert_called_once_with(idprestamo=10)
        pago_prestamo_create.assert_called_once_with(
            idprestamo=prestamo,
            idmetodopago=metodo_pago,
            fechapago=fecha_pago,
            montopagado=Decimal("125.50"),
            numeroreferencia="REF-123",
            observacion="Pago parcial",
            estado="Registrado",
        )
        self.assertEqual(prestamo.saldopendiente, Decimal("174.50"))
        self.assertEqual(prestamo.estadoprestamo, "Aprobado")
        self.assertEqual(prestamo.montoprestamosolicitado, monto_original)
        self.assertEqual(prestamo.montototalpagar, total_original)
        self.assertIs(prestamo.idsocio, socio_original)
        prestamo.save.assert_called_once_with(update_fields=["saldopendiente"])
        pago_create.assert_not_called()
        pago_filter.assert_not_called()
        self.assertNotIn("Pago", finanzas_services.__dict__)

    def test_pago_exacto_liquida_prestamo_y_crea_pago_registrado(self):
        prestamo = self._prestamo_bloqueado(saldo=Decimal("250.00"))
        fecha_pago = datetime(2026, 7, 8, 11, 45)
        pago_creado = PagoPrestamo(idpagoprestamo=2)
        bloqueo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.PagoPrestamo.objects.create",
                return_value=pago_creado,
            ) as pago_prestamo_create,
        ):
            pago = registrar_pago_prestamo(
                prestamo,
                monto_pagado=Decimal("250.00"),
                fecha_pago=fecha_pago,
            )

        self.assertIs(pago, pago_creado)
        self.assertEqual(prestamo.saldopendiente, Decimal("0"))
        self.assertEqual(prestamo.estadoprestamo, "Liquidado")
        pago_prestamo_create.assert_called_once_with(
            idprestamo=prestamo,
            idmetodopago=None,
            fechapago=fecha_pago,
            montopagado=Decimal("250.00"),
            numeroreferencia="",
            observacion="",
            estado="Registrado",
        )
        prestamo.save.assert_called_once_with(
            update_fields=["saldopendiente", "estadoprestamo"]
        )


class ServiciosGarantesPrestamoTests(SimpleTestCase):
    def _patch_agregados_capacidad(self, total_ahorros, total_pendiente):
        ahorros_qs = MagicMock()
        ahorros_qs.aggregate.return_value = {"total": total_ahorros}

        prestamos_filtrados_qs = MagicMock()
        prestamos_filtrados_qs.aggregate.return_value = {"total": total_pendiente}
        prestamos_qs = MagicMock()
        prestamos_qs.exclude.return_value = prestamos_filtrados_qs

        return (
            patch(
                "apps.finanzas.services.Ahorro.objects.filter",
                return_value=ahorros_qs,
            ),
            patch(
                "apps.finanzas.services.Prestamo.objects.filter",
                return_value=prestamos_qs,
            ),
            prestamos_qs,
        )

    def _datos_prestamo(self, socio=None, monto=Decimal("1000.00")):
        return {
            "idsocio": socio or Socio(idsocio=1),
            "montoprestamosolicitado": monto,
            "tasainteres": Decimal("5.00"),
            "montototalpagar": Decimal("1050.00"),
            "saldopendiente": Decimal("1050.00"),
            "numerocuotas": 10,
            "fechasolicitud": date(2026, 7, 8),
            "fechavencimiento": date(2026, 12, 8),
            "estadoprestamo": "Solicitado",
        }

    def _patch_bloqueo_socios(self, ids):
        socios_qs = MagicMock()
        socios_qs.filter.return_value = [
            Socio(idsocio=idsocio)
            for idsocio in dict.fromkeys(ids)
        ]
        return (
            patch(
                "apps.finanzas.services.Socio.objects.select_for_update",
                return_value=socios_qs,
            ),
            socios_qs,
        )

    def test_calcular_capacidad_garante_resta_prestamos_activos(self):
        (
            ahorros_filter_patch,
            prestamos_filter_patch,
            prestamos_qs,
        ) = self._patch_agregados_capacidad(
            Decimal("700.00"),
            Decimal("200.00"),
        )

        with ahorros_filter_patch as ahorros_filter, prestamos_filter_patch as prestamos_filter:
            capacidad = calcular_capacidad_garante(2)

        self.assertEqual(capacidad, Decimal("500.00"))
        ahorros_filter.assert_called_once_with(idsocio_id=2, estado__iexact="Activo")
        prestamos_filter.assert_called_once_with(idsocio_id=2)
        prestamos_qs.exclude.assert_called_once()

    def test_calcular_capacidad_garante_devuelve_cero_si_deudas_superan_ahorros(self):
        (
            ahorros_filter_patch,
            prestamos_filter_patch,
            _prestamos_qs,
        ) = self._patch_agregados_capacidad(
            Decimal("100.00"),
            Decimal("250.00"),
        )

        with ahorros_filter_patch, prestamos_filter_patch:
            capacidad = calcular_capacidad_garante(Socio(idsocio=2))

        self.assertEqual(capacidad, Decimal("0"))

    def test_construir_datos_garantes_calcula_capacidad_de_dos_socios(self):
        socios = [SimpleNamespace(idsocio=2), " 3 ", "", None]

        with patch(
            "apps.finanzas.services.calcular_capacidad_garante",
            side_effect=[Decimal("300.00"), Decimal("250.00")],
        ) as calcular:
            resultado = construir_datos_garantes(socios)

        self.assertEqual(
            resultado,
            [
                {"idsocio": 2, "capacidad": Decimal("300.00")},
                {"idsocio": 3, "capacidad": Decimal("250.00")},
            ],
        )
        self.assertEqual(calcular.call_count, 2)

    def test_crear_prestamo_con_garantes_crea_prestamo_y_dos_garantes(self):
        socios = [Socio(idsocio=2), Socio(idsocio=3)]
        bloqueo_patch, socios_qs = self._patch_bloqueo_socios([2, 3])
        eventos = []
        prestamos_creados = []
        garantes_creados = []
        validar_original = finanzas_services.validar_garantes_prestamo

        def validar_spy(**kwargs):
            eventos.append("validar")
            return validar_original(**kwargs)

        def crear_prestamo(**kwargs):
            eventos.append("prestamo")
            prestamos_creados.append(kwargs)
            return Prestamo(idprestamo=101, **kwargs)

        def crear_garante(**kwargs):
            eventos.append("garante")
            garantes_creados.append(kwargs)
            return PrestamoGarante(**kwargs)

        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.calcular_capacidad_garante",
                side_effect=[Decimal("300.00"), Decimal("250.00")],
            ),
            patch(
                "apps.finanzas.services.validar_garantes_prestamo",
                side_effect=validar_spy,
            ),
            patch.object(
                Prestamo.objects,
                "create",
                side_effect=crear_prestamo,
            ) as prestamo_create,
            patch.object(
                PrestamoGarante.objects,
                "create",
                side_effect=crear_garante,
            ) as garante_create,
        ):
            prestamo = crear_prestamo_con_garantes(
                datos_prestamo=self._datos_prestamo(),
                garantes=socios,
            )

        atomic_mock.assert_called_once()
        socios_qs.filter.assert_called_once_with(idsocio__in=[2, 3])
        self.assertEqual(eventos, ["validar", "prestamo", "garante", "garante"])
        self.assertIsInstance(prestamo, Prestamo)
        self.assertEqual(prestamo.idprestamo, 101)
        prestamo_create.assert_called_once()
        self.assertNotIn("idprestamo", prestamos_creados[0])
        self.assertEqual(prestamos_creados[0]["idsocio"].idsocio, 1)
        self.assertEqual(
            prestamos_creados[0]["montoprestamosolicitado"],
            Decimal("1000.00"),
        )
        self.assertEqual(prestamos_creados[0]["tasainteres"], Decimal("5.00"))
        self.assertEqual(prestamos_creados[0]["montototalpagar"], Decimal("1050.00"))
        self.assertEqual(prestamos_creados[0]["saldopendiente"], Decimal("1050.00"))
        self.assertEqual(prestamos_creados[0]["numerocuotas"], 10)
        self.assertEqual(prestamos_creados[0]["fechasolicitud"], date(2026, 7, 8))
        self.assertEqual(
            prestamos_creados[0]["fechavencimiento"],
            date(2026, 12, 8),
        )
        self.assertEqual(prestamos_creados[0]["estadoprestamo"], "Solicitado")
        self.assertEqual(garante_create.call_count, 2)
        self.assertNotIn("idprestamogarante", garantes_creados[0])
        self.assertNotIn("idprestamogarante", garantes_creados[1])
        self.assertEqual(
            [garante["idgarante"].idsocio for garante in garantes_creados],
            [2, 3],
        )
        self.assertEqual(
            [garante["capacidadcalculada"] for garante in garantes_creados],
            [Decimal("300.00"), Decimal("250.00")],
        )
        self.assertEqual(
            [garante["estado"] for garante in garantes_creados],
            ["Activo", "Activo"],
        )
        self.assertTrue(
            all(garante["idprestamo"] is prestamo for garante in garantes_creados)
        )

    def test_crear_prestamo_con_garantes_crea_prestamo_sin_garantes(self):
        prestamo_creado = Prestamo(idprestamo=101, **self._datos_prestamo())
        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            patch(
                "apps.finanzas.services.calcular_capacidad_garante"
            ) as calcular_capacidad,
            patch.object(
                Prestamo.objects,
                "create",
                return_value=prestamo_creado,
            ) as prestamo_create,
            patch.object(PrestamoGarante.objects, "create") as garante_create,
        ):
            prestamo = crear_prestamo_con_garantes(
                datos_prestamo=self._datos_prestamo(),
                garantes=[],
            )

        atomic_mock.assert_called_once()
        self.assertIs(prestamo, prestamo_creado)
        prestamo_create.assert_called_once()
        garante_create.assert_not_called()
        calcular_capacidad.assert_not_called()

    def test_crear_prestamo_con_garantes_crea_prestamo_con_un_garante(self):
        bloqueo_patch, _socios_qs = self._patch_bloqueo_socios([2])
        prestamo_creado = Prestamo(idprestamo=101, **self._datos_prestamo())
        garantes_creados = []
        atomic_mock = MagicMock(return_value=nullcontext())

        def crear_garante(**kwargs):
            garantes_creados.append(kwargs)
            return PrestamoGarante(**kwargs)

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.calcular_capacidad_garante",
                return_value=Decimal("500.00"),
            ),
            patch.object(
                Prestamo.objects,
                "create",
                return_value=prestamo_creado,
            ) as prestamo_create,
            patch.object(
                PrestamoGarante.objects,
                "create",
                side_effect=crear_garante,
            ) as garante_create,
        ):
            prestamo = crear_prestamo_con_garantes(
                datos_prestamo=self._datos_prestamo(),
                garantes=[Socio(idsocio=2)],
            )

        atomic_mock.assert_called_once()
        self.assertIs(prestamo, prestamo_creado)
        prestamo_create.assert_called_once()
        garante_create.assert_called_once()
        self.assertNotIn("idprestamogarante", garantes_creados[0])
        self.assertEqual(garantes_creados[0]["idgarante"].idsocio, 2)
        self.assertEqual(garantes_creados[0]["capacidadcalculada"], Decimal("500.00"))
        self.assertIs(garantes_creados[0]["idprestamo"], prestamo_creado)

    def test_crear_prestamo_con_garantes_no_crea_si_capacidad_insuficiente(self):
        bloqueo_patch, _socios_qs = self._patch_bloqueo_socios([2, 3])
        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.calcular_capacidad_garante",
                side_effect=[Decimal("250.00"), Decimal("249.99")],
            ),
            patch.object(Prestamo.objects, "create") as prestamo_create,
            patch.object(PrestamoGarante.objects, "create") as garante_create,
        ):
            with self.assertRaisesMessage(
                PrestamoGarantiaError,
                "La capacidad total de los garantes debe cubrir al menos el 50% "
                "del monto solicitado.",
            ):
                crear_prestamo_con_garantes(
                    datos_prestamo=self._datos_prestamo(),
                    garantes=[Socio(idsocio=2), Socio(idsocio=3)],
                )

        atomic_mock.assert_called_once()
        prestamo_create.assert_not_called()
        garante_create.assert_not_called()

    def test_crear_prestamo_con_garantes_no_crea_si_garante_repetido(self):
        bloqueo_patch, _socios_qs = self._patch_bloqueo_socios([2])
        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.calcular_capacidad_garante",
                side_effect=[Decimal("300.00"), Decimal("300.00")],
            ),
            patch.object(Prestamo.objects, "create") as prestamo_create,
            patch.object(PrestamoGarante.objects, "create") as garante_create,
        ):
            with self.assertRaisesMessage(
                PrestamoGarantiaError,
                "No puede repetir el mismo garante.",
            ):
                crear_prestamo_con_garantes(
                    datos_prestamo=self._datos_prestamo(),
                    garantes=[Socio(idsocio=2), Socio(idsocio=2)],
                )

        atomic_mock.assert_called_once()
        prestamo_create.assert_not_called()
        garante_create.assert_not_called()

    def test_crear_prestamo_con_garantes_no_crea_si_garante_es_deudor(self):
        bloqueo_patch, _socios_qs = self._patch_bloqueo_socios([1, 2])
        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.calcular_capacidad_garante",
                side_effect=[Decimal("500.00"), Decimal("500.00")],
            ),
            patch.object(Prestamo.objects, "create") as prestamo_create,
            patch.object(PrestamoGarante.objects, "create") as garante_create,
        ):
            with self.assertRaisesMessage(
                PrestamoGarantiaError,
                "El garante no puede ser el mismo socio deudor.",
            ):
                crear_prestamo_con_garantes(
                    datos_prestamo=self._datos_prestamo(),
                    garantes=[Socio(idsocio=1), Socio(idsocio=2)],
                )

        atomic_mock.assert_called_once()
        prestamo_create.assert_not_called()
        garante_create.assert_not_called()

    def test_crear_prestamo_con_garantes_rechaza_mas_de_dos_garantes(self):
        bloqueo_patch, _socios_qs = self._patch_bloqueo_socios([2, 3, 4])
        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.calcular_capacidad_garante",
                side_effect=[
                    Decimal("200.00"),
                    Decimal("200.00"),
                    Decimal("200.00"),
                ],
            ),
            patch.object(Prestamo.objects, "create") as prestamo_create,
            patch.object(PrestamoGarante.objects, "create") as garante_create,
        ):
            with self.assertRaisesMessage(
                PrestamoGarantiaError,
                "Un préstamo no puede tener más de dos garantes.",
            ):
                crear_prestamo_con_garantes(
                    datos_prestamo=self._datos_prestamo(),
                    garantes=[
                        Socio(idsocio=2),
                        Socio(idsocio=3),
                        Socio(idsocio=4),
                    ],
                )

        atomic_mock.assert_called_once()
        prestamo_create.assert_not_called()
        garante_create.assert_not_called()


class ValidarGarantesPrestamoTests(SimpleTestCase):
    def test_cero_garantes_es_valido(self):
        resultado = validar_garantes_prestamo(
            socio_deudor_id=1,
            monto_solicitado=Decimal("1000"),
            garantes=[],
        )

        self.assertEqual(resultado["capacidad_total"], Decimal("0.00"))
        self.assertEqual(resultado["capacidad_requerida"], Decimal("500.00"))
        self.assertEqual(resultado["porcentaje_requerido"], Decimal("0.50"))
        self.assertEqual(resultado["garantes_normalizados"], [])

    def test_un_garante_suficiente_es_valido(self):
        resultado = validar_garantes_prestamo(
            socio_deudor_id=1,
            monto_solicitado=Decimal("1000"),
            garantes=[{"idsocio": 2, "capacidad": Decimal("500")}],
        )

        self.assertEqual(resultado["capacidad_total"], Decimal("500"))
        self.assertEqual(resultado["capacidad_requerida"], Decimal("500.00"))
        self.assertEqual(
            resultado["garantes_normalizados"],
            [{"idsocio": 2, "capacidad": Decimal("500")}],
        )

    def test_un_garante_insuficiente_rechaza_prestamo(self):
        with self.assertRaisesMessage(
            PrestamoGarantiaError,
            "La capacidad total de los garantes debe cubrir al menos el 50% "
            "del monto solicitado.",
        ):
            validar_garantes_prestamo(
                socio_deudor_id=1,
                monto_solicitado=Decimal("1000"),
                garantes=[{"idsocio": 2, "capacidad": Decimal("499.99")}],
            )

    def test_dos_garantes_suman_capacidad(self):
        resultado = validar_garantes_prestamo(
            socio_deudor_id=1,
            monto_solicitado=Decimal("1000"),
            garantes=[
                {"idsocio": 2, "capacidad": Decimal("300")},
                {"idsocio": 3, "capacidad": Decimal("250")},
            ],
        )

        self.assertEqual(resultado["capacidad_total"], Decimal("550"))

    def test_capacidad_insuficiente_rechaza_prestamo(self):
        with self.assertRaisesMessage(
            PrestamoGarantiaError,
            "La capacidad total de los garantes debe cubrir al menos el 50% "
            "del monto solicitado.",
        ):
            validar_garantes_prestamo(
                socio_deudor_id=1,
                monto_solicitado=Decimal("1000"),
                garantes=[
                    {"idsocio": 2, "capacidad": Decimal("250.00")},
                    {"idsocio": 3, "capacidad": Decimal("249.99")},
                ],
            )

    def test_mas_de_dos_garantes_rechaza_prestamo(self):
        with self.assertRaisesMessage(
            PrestamoGarantiaError,
            "Un préstamo no puede tener más de dos garantes.",
        ):
            validar_garantes_prestamo(
                socio_deudor_id=1,
                monto_solicitado=Decimal("1000"),
                garantes=[
                    {"idsocio": 2, "capacidad": Decimal("200")},
                    {"idsocio": 3, "capacidad": Decimal("200")},
                    {"idsocio": 4, "capacidad": Decimal("200")},
                ],
            )

    def test_garante_igual_al_socio_deudor_rechaza_prestamo(self):
        with self.assertRaisesMessage(
            PrestamoGarantiaError,
            "El garante no puede ser el mismo socio deudor.",
        ):
            validar_garantes_prestamo(
                socio_deudor_id=1,
                monto_solicitado=Decimal("1000"),
                garantes=[
                    {"idsocio": 1, "capacidad": Decimal("500")},
                    {"idsocio": 2, "capacidad": Decimal("500")},
                ],
            )

    def test_garante_repetido_rechaza_prestamo(self):
        with self.assertRaisesMessage(
            PrestamoGarantiaError,
            "No puede repetir el mismo garante.",
        ):
            validar_garantes_prestamo(
                socio_deudor_id=1,
                monto_solicitado=Decimal("1000"),
                garantes=[
                    {"idsocio": 2, "capacidad": Decimal("300")},
                    {"idsocio": 2, "capacidad": Decimal("300")},
                ],
            )

    def test_idsocio_faltante_rechaza_prestamo(self):
        with self.assertRaisesMessage(
            PrestamoGarantiaError,
            "Debe seleccionar un garante válido.",
        ):
            validar_garantes_prestamo(
                socio_deudor_id=1,
                monto_solicitado=Decimal("1000"),
                garantes=[
                    {"capacidad": Decimal("500")},
                    {"idsocio": 3, "capacidad": Decimal("500")},
                ],
            )

    def test_monto_solicitado_invalido_rechaza_prestamo(self):
        valores_invalidos = [
            None,
            True,
            Decimal("0"),
            Decimal("-1"),
            "texto inválido",
            Decimal("NaN"),
            Decimal("Infinity"),
        ]

        for valor in valores_invalidos:
            with self.subTest(valor=valor):
                with self.assertRaisesMessage(
                    PrestamoGarantiaError,
                    "El monto solicitado del préstamo debe ser mayor que cero.",
                ):
                    validar_garantes_prestamo(
                        socio_deudor_id=1,
                        monto_solicitado=valor,
                        garantes=[
                            {"idsocio": 2, "capacidad": Decimal("250")},
                            {"idsocio": 3, "capacidad": Decimal("250")},
                        ],
                    )

    def test_capacidad_invalida_rechaza_prestamo(self):
        valores_invalidos = [
            None,
            True,
            "texto inválido",
            Decimal("NaN"),
            Decimal("Infinity"),
        ]

        for valor in valores_invalidos:
            with self.subTest(valor=valor):
                with self.assertRaisesMessage(
                    PrestamoGarantiaError,
                    "La capacidad del garante debe ser un valor numérico válido.",
                ):
                    validar_garantes_prestamo(
                        socio_deudor_id=1,
                        monto_solicitado=Decimal("1000"),
                        garantes=[
                            {"idsocio": 2, "capacidad": valor},
                            {"idsocio": 3, "capacidad": Decimal("500")},
                        ],
                    )

    def test_capacidad_negativa_se_normaliza_a_cero(self):
        resultado = validar_garantes_prestamo(
            socio_deudor_id=1,
            monto_solicitado=Decimal("1000"),
            garantes=[
                {"idsocio": 2, "capacidad": Decimal("-100")},
                {"idsocio": 3, "capacidad": Decimal("500")},
            ],
        )

        self.assertEqual(resultado["capacidad_total"], Decimal("500"))
        self.assertEqual(
            resultado["garantes_normalizados"][0]["capacidad"],
            Decimal("0"),
        )

    def test_verifica_valores_devueltos(self):
        resultado = validar_garantes_prestamo(
            socio_deudor_id="1",
            monto_solicitado="1000.00",
            garantes=[
                SimpleNamespace(idsocio="2", capacidad="300.00"),
                SimpleNamespace(idsocio="3", capacidad=Decimal("250.00")),
            ],
        )

        self.assertEqual(resultado["monto_solicitado"], Decimal("1000.00"))
        self.assertEqual(resultado["porcentaje_requerido"], Decimal("0.50"))
        self.assertEqual(resultado["capacidad_requerida"], Decimal("500.0000"))
        self.assertEqual(resultado["capacidad_total"], Decimal("550.00"))
        self.assertEqual(
            resultado["garantes_normalizados"],
            [
                {"idsocio": 2, "capacidad": Decimal("300.00")},
                {"idsocio": 3, "capacidad": Decimal("250.00")},
            ],
        )
