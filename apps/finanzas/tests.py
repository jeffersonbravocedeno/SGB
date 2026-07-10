from contextlib import nullcontext
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import models as django_models
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.configuracion.models import Metodopago, Regalo
from apps.jugadores.models import Jugador
from apps.socios.models import Socio

from . import admin as finanzas_admin
from . import services as finanzas_services
from . import views as finanzas_views
from .forms import (
    AhorroForm,
    AprobarSolicitudPagoPrestamoForm,
    AporteSemanalForm,
    PagoPrestamoForm,
    PrestamoConGarantesForm,
    PrestamoEdicionForm,
    RechazarSolicitudPagoPrestamoForm,
    SolicitudPagoPrestamoForm,
)
from .models import (
    Ahorro,
    Aportesemanal,
    Pago,
    PagoPrestamo,
    Prestamo,
    PrestamoGarante,
    SolicitudPagoPrestamo,
)
from .services import (
    PrestamoGarantiaError,
    PrestamoPagoError,
    SolicitudPagoPrestamoError,
    aprobar_solicitud_pago_prestamo,
    calcular_capacidad_garante,
    construir_datos_garantes,
    crear_prestamo_con_garantes,
    crear_solicitud_pago_prestamo,
    registrar_pago_prestamo,
    rechazar_solicitud_pago_prestamo,
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


class FakeModelChoiceQuerySet:
    def __init__(self, model, objects):
        self.model = model
        self.objects = list(objects)

    def all(self):
        return self

    def get(self, **kwargs):
        field_name, value = next(iter(kwargs.items()))
        for obj in self.objects:
            candidates = {
                str(getattr(obj, "pk", "")),
                str(getattr(obj, field_name, "")),
            }
            if str(value) in candidates:
                return obj
        raise self.model.DoesNotExist


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


def jugador_stub(idjugador=1, socio=None):
    return Jugador(
        idjugador=idjugador,
        idsocio=socio,
        aliasjugador=f"jugador{idjugador}",
        correojugador=f"jugador{idjugador}@example.com",
        fecharegistrojugador=datetime(2026, 7, 10, 9, 0),
        saldocreditojugador=Decimal("0.00"),
        estadocuentajugador="Activo",
    )


def prestamo_solicitud_stub(
    idsocio,
    *,
    idprestamo=10,
    saldo=Decimal("300.00"),
    estado="Aprobado",
):
    prestamo = Prestamo(
        idprestamo=idprestamo,
        idsocio=idsocio,
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


def solicitud_pago_prestamo_stub(
    prestamo,
    jugador,
    *,
    idsolicitudpago=1,
    monto=Decimal("100.00"),
    estado=SolicitudPagoPrestamo.ESTADO_PENDIENTE,
    metodo_pago=None,
):
    solicitud = SolicitudPagoPrestamo(
        idsolicitudpago=idsolicitudpago,
        idprestamo=prestamo,
        idsocio=prestamo.idsocio,
        idjugador=jugador,
        idmetodopago=metodo_pago,
        monto=monto,
        referencia="REF-SOCIO-1",
        rutacomprobante="TRX-001",
        observacionsocio="Pago desde portal",
        estado=estado,
        fechasolicitud=datetime(2026, 7, 10, 9, 30),
    )
    solicitud.save = MagicMock()
    return solicitud


class LockedSolicitudPagoQuerySet:
    def __init__(self, solicitud):
        self.solicitud = solicitud

    def select_related(self, *args, **kwargs):
        raise AssertionError(
            "No se debe usar select_related despues de select_for_update en SolicitudPagoPrestamo."
        )

    def get(self, **kwargs):
        return self.solicitud


def bingo_stub(idbingo=1):
    bingo_model = Ahorro._meta.get_field("idbingo").remote_field.model
    return bingo_model(idbingo=idbingo, titulobingo=f"Bingo {idbingo}")


def regalo_stub(idregalo=1, valor=Decimal("12.50")):
    return Regalo(
        idregalo=idregalo,
        nombreregalo=f"Regalo {idregalo}",
        descripcionregalo="",
        valorregalo=valor,
        estadoregalo="Activo",
        fechaultimaactualizacion=datetime(2026, 7, 8, 10, 30),
        urlimagen="regalo.png",
    )


def aporte_stub(valor=Decimal("12.50")):
    return SimpleNamespace(
        idsocio=socio_stub(1, "Socio Aporte"),
        numerosemana=3,
        idregalo=regalo_stub(valor=valor),
        fechaplanificadada=datetime(2026, 7, 8, 10, 30),
        fechaentregareal=None,
        estadoaporte="Al Dia",
    )


class FakePage(list):
    number = 1
    paginator = SimpleNamespace(num_pages=1)

    def has_previous(self):
        return False

    def has_next(self):
        return False


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


class SolicitudPagoPrestamoModelMetadataTests(SimpleTestCase):
    def test_modelo_existe_y_no_es_gestionado(self):
        self.assertEqual(SolicitudPagoPrestamo.__name__, "SolicitudPagoPrestamo")
        self.assertFalse(SolicitudPagoPrestamo._meta.managed)

    def test_tabla_fisica_correcta(self):
        self.assertEqual(
            SolicitudPagoPrestamo._meta.db_table,
            "solicitud_pago_prestamo",
        )

    def test_primary_key_es_autofield(self):
        pk = SolicitudPagoPrestamo._meta.pk

        self.assertIsInstance(pk, django_models.AutoField)
        self.assertEqual(pk.name, "idsolicitudpago")
        self.assertEqual(pk.column, "idsolicitudpago")
        self.assertTrue(pk.primary_key)

    def test_columnas_fisicas_correctas(self):
        columnas = {
            field.name: field.column
            for field in SolicitudPagoPrestamo._meta.fields
        }

        self.assertEqual(
            columnas,
            {
                "idsolicitudpago": "idsolicitudpago",
                "idprestamo": "idprestamo",
                "idsocio": "idsocio",
                "idjugador": "idjugador",
                "idmetodopago": "idmetodopago",
                "monto": "monto",
                "referencia": "referencia",
                "rutacomprobante": "rutacomprobante",
                "observacionsocio": "observacionsocio",
                "estado": "estado",
                "fechasolicitud": "fechasolicitud",
                "fecharespuesta": "fecharespuesta",
                "idusuarioadminrespuesta": "idusuarioadminrespuesta",
                "motivorechazo": "motivorechazo",
                "observacionadmin": "observacionadmin",
                "idpagoprestamoresultado": "idpagoprestamoresultado",
            },
        )

    def test_foreign_keys_usan_modelos_correctos(self):
        self.assertIs(
            SolicitudPagoPrestamo._meta.get_field("idprestamo").remote_field.model,
            Prestamo,
        )
        self.assertIs(
            SolicitudPagoPrestamo._meta.get_field("idsocio").remote_field.model,
            Socio,
        )
        self.assertIs(
            SolicitudPagoPrestamo._meta.get_field("idjugador").remote_field.model,
            Jugador,
        )
        self.assertIs(
            SolicitudPagoPrestamo._meta.get_field("idmetodopago").remote_field.model,
            Metodopago,
        )
        self.assertIs(
            SolicitudPagoPrestamo._meta.get_field(
                "idpagoprestamoresultado"
            ).remote_field.model,
            PagoPrestamo,
        )

    def test_estado_tiene_choices_pendiente_aprobada_rechazada(self):
        field = SolicitudPagoPrestamo._meta.get_field("estado")

        self.assertEqual(
            tuple(field.choices),
            (
                ("Pendiente", "Pendiente"),
                ("Aprobada", "Aprobada"),
                ("Rechazada", "Rechazada"),
            ),
        )
        self.assertEqual(field.default, "Pendiente")

    def test_monto_precision_decimal(self):
        field = SolicitudPagoPrestamo._meta.get_field("monto")

        self.assertEqual(field.max_digits, 12)
        self.assertEqual(field.decimal_places, 2)


class PagoPrestamoAdminTests(SimpleTestCase):
    def setUp(self):
        self.admin = django_admin.site._registry[PagoPrestamo]
        self.request = RequestFactory().get("/admin/finanzas/pagoprestamo/")
        self.request.user = SimpleNamespace(has_perm=lambda permission: False)

    def test_pago_legacy_no_esta_registrado_en_admin(self):
        self.assertNotIn(Pago, django_admin.site._registry)

    def test_pago_prestamo_esta_registrado_en_admin(self):
        self.assertIn(PagoPrestamo, django_admin.site._registry)
        self.assertIsInstance(self.admin, finanzas_admin.PagoPrestamoAdmin)

    def test_pago_prestamo_admin_no_permite_add(self):
        self.assertFalse(self.admin.has_add_permission(self.request))

    def test_pago_prestamo_admin_no_permite_change(self):
        self.assertFalse(self.admin.has_change_permission(self.request))

    def test_pago_prestamo_admin_no_permite_delete(self):
        self.assertFalse(self.admin.has_delete_permission(self.request))

    def test_pago_prestamo_admin_todos_los_campos_son_readonly(self):
        campos_modelo = tuple(field.name for field in PagoPrestamo._meta.fields)

        self.assertEqual(tuple(self.admin.readonly_fields), campos_modelo)

    def test_pago_prestamo_admin_permiso_view_se_mantiene_disponible(self):
        self.request.user = SimpleNamespace(
            has_perm=lambda permission: permission == "finanzas.view_pagoprestamo"
        )

        self.assertTrue(self.admin.has_view_permission(self.request))

    def test_pago_prestamo_admin_configura_listas_busqueda_y_filtros(self):
        self.assertEqual(
            self.admin.list_display,
            (
                "idpagoprestamo",
                "idprestamo",
                "montopagado",
                "fechapago",
                "estado",
                "idmetodopago",
            ),
        )
        self.assertEqual(
            self.admin.search_fields,
            (
                "numeroreferencia",
                "observacion",
            ),
        )
        self.assertEqual(
            self.admin.list_filter,
            (
                "estado",
                "fechapago",
                "idmetodopago",
            ),
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

    def test_formulario_creacion_no_incluye_saldopendiente_editable(self):
        form = self._form(saldopendiente="9999.00")

        self.assertNotIn("saldopendiente", form.fields)
        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertNotIn("saldopendiente", form.cleaned_data)
        self.assertNotIn("saldopendiente", form.datos_prestamo())

    def test_formulario_rechaza_total_menor_que_monto_solicitado(self):
        form = self._form(
            montoprestamosolicitado="100.00",
            montototalpagar="99.99",
        )

        self.assertFalse(self._is_valid(form))
        self.assertIn("montototalpagar", form.errors)
        self.assertIn(
            "El total a pagar no puede ser menor que el monto solicitado.",
            form.errors["montototalpagar"],
        )

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

    def test_formulario_acepta_vencimiento_en_31_de_diciembre(self):
        form = self._form(fechavencimiento="2026-12-31")

        self.assertTrue(self._is_valid(form), form.errors.as_data())

    def test_formulario_acepta_vencimiento_dentro_del_mismo_anio(self):
        form = self._form(
            fechasolicitud="2026-01-08",
            fechavencimiento="2026-06-30",
        )

        self.assertTrue(self._is_valid(form), form.errors.as_data())

    def test_formulario_rechaza_vencimiento_anterior_a_solicitud(self):
        form = self._form(
            fechasolicitud="2026-07-08",
            fechavencimiento="2026-07-07",
        )

        self.assertFalse(self._is_valid(form))
        self.assertIn("fechavencimiento", form.errors)
        self.assertIn(
            "La fecha de vencimiento no puede ser anterior a la fecha de solicitud.",
            form.errors["fechavencimiento"],
        )

    def test_formulario_rechaza_vencimiento_en_anio_siguiente(self):
        form = self._form(
            fechasolicitud="2026-07-08",
            fechavencimiento="2027-01-08",
        )

        self.assertFalse(self._is_valid(form))
        self.assertIn("fechavencimiento", form.errors)
        self.assertIn(
            "El préstamo debe vencer dentro del mismo período anual, máximo hasta el 31 de diciembre.",
            form.errors["fechavencimiento"],
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


class PrestamoEdicionFormTests(SimpleTestCase):
    def _prestamo(self):
        return Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            montoprestamosolicitado=Decimal("1000.00"),
            tasainteres=Decimal("5.00"),
            montototalpagar=Decimal("1050.00"),
            saldopendiente=Decimal("1050.00"),
            numerocuotas=10,
            fechasolicitud=date(2026, 7, 8),
            fechavencimiento=date(2026, 12, 8),
            estadoprestamo="Aprobado",
        )

    def _datos_formulario(self, **overrides):
        datos = {
            "tasainteres": "5.00",
            "numerocuotas": "10",
            "fechasolicitud": "2026-07-08",
            "fechavencimiento": "2026-12-08",
            "estadoprestamo": "Aprobado",
        }
        datos.update(overrides)
        return datos

    def _form(self, **overrides):
        return PrestamoEdicionForm(
            data=self._datos_formulario(**overrides),
            instance=self._prestamo(),
        )

    def _is_valid(self, form):
        with patch.object(Prestamo, "full_clean"):
            return form.is_valid()

    def test_formulario_edicion_rechaza_vencimiento_fuera_periodo_anual(self):
        form = self._form(fechavencimiento="2027-01-08")

        self.assertFalse(self._is_valid(form))
        self.assertIn("fechavencimiento", form.errors)

    def test_formulario_edicion_no_incluye_saldopendiente(self):
        form = self._form()

        self.assertNotIn("saldopendiente", form.fields)

    def test_formulario_edicion_no_incluye_montos_base(self):
        form = self._form()

        self.assertNotIn("montoprestamosolicitado", form.fields)
        self.assertNotIn("montototalpagar", form.fields)

    def test_formulario_edicion_ignora_saldopendiente_enviado_manual(self):
        prestamo = self._prestamo()
        form = PrestamoEdicionForm(
            data=self._datos_formulario(saldopendiente="1.00"),
            instance=prestamo,
        )

        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertNotIn("saldopendiente", form.cleaned_data)
        instance = form.save(commit=False)
        self.assertEqual(instance.saldopendiente, Decimal("1050.00"))


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


class SolicitudPagoPrestamoFormTests(SimpleTestCase):
    def setUp(self):
        self.socio = socio_stub(1, "Socio Pago")
        self.prestamo = prestamo_solicitud_stub(
            self.socio,
            saldo=Decimal("300.00"),
        )

    def _form(self, **overrides):
        datos = {
            "monto": "100.00",
            "idmetodopago": "",
            "referencia": " REF-PORTAL ",
            "rutacomprobante": " TRX-123 ",
            "observacionsocio": " Pago desde portal ",
        }
        datos.update(overrides)
        return SolicitudPagoPrestamoForm(
            data=datos,
            prestamo=self.prestamo,
            metodo_pago_queryset=Metodopago.objects.none(),
        )

    def _is_valid(self, form):
        with patch.object(SolicitudPagoPrestamo, "full_clean"):
            return form.is_valid()

    def test_formulario_acepta_datos_validos_y_limpia_textos(self):
        form = self._form()

        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertEqual(form.cleaned_data["monto"], Decimal("100.00"))
        self.assertEqual(form.cleaned_data["referencia"], "REF-PORTAL")
        self.assertEqual(form.cleaned_data["rutacomprobante"], "TRX-123")
        self.assertEqual(form.cleaned_data["observacionsocio"], "Pago desde portal")

    def test_formulario_rechaza_monto_cero(self):
        form = self._form(monto="0")

        self.assertFalse(self._is_valid(form))
        self.assertIn("monto", form.errors)
        self.assertIn("El monto debe ser mayor que cero.", form.errors["monto"])

    def test_formulario_rechaza_monto_negativo(self):
        form = self._form(monto="-1.00")

        self.assertFalse(self._is_valid(form))
        self.assertIn("monto", form.errors)

    def test_formulario_rechaza_referencia_vacia(self):
        form = self._form(referencia="  ")

        self.assertFalse(self._is_valid(form))
        self.assertIn("referencia", form.errors)
        self.assertIn("Debe ingresar una referencia.", form.errors["referencia"])

    def test_formulario_rechaza_sobrepago_si_recibe_prestamo(self):
        form = self._form(monto="301.00")

        self.assertFalse(self._is_valid(form))
        self.assertIn("monto", form.errors)
        self.assertIn(
            "El monto no puede superar el saldo pendiente.",
            form.errors["monto"],
        )

    def test_formulario_rechaza_prestamo_sin_saldo(self):
        self.prestamo.saldopendiente = Decimal("0.00")
        form = self._form(monto="1.00")

        self.assertFalse(self._is_valid(form))
        self.assertIn("El préstamo no tiene saldo pendiente.", form.errors["monto"])


class SolicitudPagoPrestamoDecisionFormTests(SimpleTestCase):
    def test_aprobar_limpia_observacion_admin(self):
        form = AprobarSolicitudPagoPrestamoForm(
            data={"observacionadmin": " Validado en finanzas "}
        )

        self.assertTrue(form.is_valid(), form.errors.as_data())
        self.assertEqual(form.cleaned_data["observacionadmin"], "Validado en finanzas")

    def test_rechazar_exige_motivo(self):
        form = RechazarSolicitudPagoPrestamoForm(data={"motivorechazo": "  "})

        self.assertFalse(form.is_valid())
        self.assertIn("motivorechazo", form.errors)
        self.assertIn(
            "Debe ingresar un motivo de rechazo.",
            form.errors["motivorechazo"],
        )


class AhorroFormTests(SimpleTestCase):
    def setUp(self):
        self.socio = socio_stub(1, "Socio Ahorro")
        self.bingo = bingo_stub(10)

    def _datos_formulario(self, **overrides):
        datos = {
            "idsocio": "1",
            "idbingo": "10",
            "tipoahorro": "Obligatorio",
            "montoahorro": "25.00",
            "fechaahorro": "2026-07-08T10:30",
            "comentarioahorro": "",
            "estado": "Activo",
        }
        datos.update(overrides)
        return datos

    def _form(self, **overrides):
        form = AhorroForm(data=self._datos_formulario(**overrides))
        form.fields["idsocio"].queryset = FakeModelChoiceQuerySet(
            Socio,
            [self.socio],
        )
        form.fields["idbingo"].queryset = FakeModelChoiceQuerySet(
            self.bingo.__class__,
            [self.bingo],
        )
        return form

    def _is_valid(self, form):
        with patch.object(Ahorro, "full_clean"):
            return form.is_valid()

    def test_formulario_acepta_monto_positivo(self):
        form = self._form(montoahorro="25.00")

        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertEqual(form.cleaned_data["montoahorro"], Decimal("25.00"))

    def test_formulario_rechaza_monto_cero(self):
        form = self._form(montoahorro="0")

        self.assertFalse(self._is_valid(form))
        self.assertIn("montoahorro", form.errors)
        self.assertIn(
            "El monto del ahorro debe ser mayor que cero.",
            form.errors["montoahorro"],
        )

    def test_formulario_rechaza_monto_negativo(self):
        form = self._form(montoahorro="-1.00")

        self.assertFalse(self._is_valid(form))
        self.assertIn("montoahorro", form.errors)
        self.assertIn(
            "El monto del ahorro debe ser mayor que cero.",
            form.errors["montoahorro"],
        )

    def test_formulario_exige_socio(self):
        form = self._form(idsocio="")

        self.assertFalse(self._is_valid(form))
        self.assertIn("idsocio", form.errors)
        self.assertIn("Este campo es obligatorio.", form.errors["idsocio"])

    def test_formulario_exige_fecha(self):
        form = self._form(fechaahorro="")

        self.assertFalse(self._is_valid(form))
        self.assertIn("fechaahorro", form.errors)
        self.assertIn("Este campo es obligatorio.", form.errors["fechaahorro"])

    def test_formulario_rechaza_estado_invalido(self):
        form = self._form(estado="Pendiente")

        self.assertFalse(self._is_valid(form))
        self.assertIn("estado", form.errors)
        self.assertIn("Seleccione un estado válido.", form.errors["estado"])

    def test_formulario_mantiene_campos_esperados(self):
        form = self._form()

        self.assertEqual(
            list(form.fields),
            [
                "idsocio",
                "idbingo",
                "tipoahorro",
                "montoahorro",
                "fechaahorro",
                "comentarioahorro",
                "estado",
            ],
        )


class AporteSemanalFormTests(SimpleTestCase):
    def setUp(self):
        self.socio = socio_stub(1, "Socio Aporte")
        self.regalo = regalo_stub(1, Decimal("12.50"))

    def _datos_formulario(self, **overrides):
        datos = {
            "idsocio": "1",
            "idregalo": "1",
            "idpartida": "",
            "numerosemana": "3",
            "fechaplanificadada": "2026-07-08T10:30",
            "fechaentregareal": "",
            "metodoingreso": "Efectivo",
            "referenciaingreso": "",
            "estadoaporte": "Al Dia",
        }
        datos.update(overrides)
        return datos

    def _form(self, *, regalo=None, **overrides):
        form = AporteSemanalForm(data=self._datos_formulario(**overrides))
        form.fields["idsocio"].queryset = FakeModelChoiceQuerySet(
            Socio,
            [self.socio],
        )
        form.fields["idregalo"].queryset = FakeModelChoiceQuerySet(
            Regalo,
            [regalo or self.regalo],
        )
        return form

    def _is_valid(self, form):
        with patch.object(Aportesemanal, "full_clean"):
            return form.is_valid()

    def test_formulario_acepta_aporte_valido(self):
        form = self._form()

        self.assertTrue(self._is_valid(form), form.errors.as_data())
        self.assertEqual(form.cleaned_data["numerosemana"], 3)
        self.assertEqual(form.cleaned_data["idregalo"].valorregalo, Decimal("12.50"))

    def test_formulario_rechaza_numero_semana_cero(self):
        form = self._form(numerosemana="0")

        self.assertFalse(self._is_valid(form))
        self.assertIn("numerosemana", form.errors)
        self.assertIn(
            "El número de semana debe ser mayor que cero.",
            form.errors["numerosemana"],
        )

    def test_formulario_rechaza_numero_semana_negativo(self):
        form = self._form(numerosemana="-1")

        self.assertFalse(self._is_valid(form))
        self.assertIn("numerosemana", form.errors)
        self.assertIn(
            "El número de semana debe ser mayor que cero.",
            form.errors["numerosemana"],
        )

    def test_formulario_exige_socio(self):
        form = self._form(idsocio="")

        self.assertFalse(self._is_valid(form))
        self.assertIn("idsocio", form.errors)
        self.assertIn("Este campo es obligatorio.", form.errors["idsocio"])

    def test_formulario_exige_regalo(self):
        form = self._form(idregalo="")

        self.assertFalse(self._is_valid(form))
        self.assertIn("idregalo", form.errors)
        self.assertIn("Este campo es obligatorio.", form.errors["idregalo"])

    def test_formulario_exige_fecha_planificada(self):
        form = self._form(fechaplanificadada="")

        self.assertFalse(self._is_valid(form))
        self.assertIn("fechaplanificadada", form.errors)
        self.assertIn("Este campo es obligatorio.", form.errors["fechaplanificadada"])

    def test_formulario_exige_estado(self):
        form = self._form(estadoaporte="")

        self.assertFalse(self._is_valid(form))
        self.assertIn("estadoaporte", form.errors)
        self.assertIn("Este campo es obligatorio.", form.errors["estadoaporte"])

    def test_formulario_rechaza_regalo_con_valor_cero(self):
        form = self._form(regalo=regalo_stub(1, Decimal("0.00")))

        self.assertFalse(self._is_valid(form))
        self.assertIn("idregalo", form.errors)
        self.assertIn(
            "El regalo asociado al aporte debe tener un valor mayor que cero.",
            form.errors["idregalo"],
        )

    def test_formulario_rechaza_regalo_con_valor_negativo(self):
        form = self._form(regalo=regalo_stub(1, Decimal("-1.00")))

        self.assertFalse(self._is_valid(form))
        self.assertIn("idregalo", form.errors)
        self.assertIn(
            "El regalo asociado al aporte debe tener un valor mayor que cero.",
            form.errors["idregalo"],
        )


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

    def _request_ahorro_post(self, **overrides):
        datos = {
            "idsocio": "1",
            "idbingo": "10",
            "tipoahorro": "Obligatorio",
            "montoahorro": "25.00",
            "fechaahorro": "2026-07-08T10:30",
            "comentarioahorro": "",
            "estado": "Activo",
        }
        datos.update(overrides)
        request = self.factory.post("/finanzas/ahorros/nuevo/", data=datos)
        request.user = self.usuario
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _request_aporte_post(self, **overrides):
        datos = {
            "idsocio": "1",
            "idregalo": "1",
            "idpartida": "",
            "numerosemana": "3",
            "fechaplanificadada": "2026-07-08T10:30",
            "fechaentregareal": "",
            "metodoingreso": "Efectivo",
            "referenciaingreso": "",
            "estadoaporte": "Al Dia",
        }
        datos.update(overrides)
        request = self.factory.post("/finanzas/aportes/nuevo/", data=datos)
        request.user = self.usuario
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _datos_edicion(self, **overrides):
        datos = {
            "tasainteres": "5.00",
            "numerocuotas": "10",
            "fechasolicitud": "2026-07-08",
            "fechavencimiento": "2026-12-08",
            "estadoprestamo": "Aprobado",
        }
        datos.update(overrides)
        return datos

    def _request_editar_post(self, **overrides):
        request = self.factory.post(
            "/finanzas/prestamos/10/editar/",
            data=self._datos_edicion(**overrides),
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

    def test_ahorro_nuevo_no_guarda_si_formulario_invalido(self):
        request = self._request_ahorro_post(montoahorro="0")
        form = MagicMock()
        form.is_valid.return_value = False
        contexto = {}

        def render_spy(_request, _template, context):
            contexto.update(context)
            return HttpResponse("form invalido")

        with (
            patch("apps.finanzas.views.AhorroForm", return_value=form) as form_class,
            patch("apps.finanzas.views.save_new_model_form") as save_directo,
            patch("apps.finanzas.views.render", side_effect=render_spy),
        ):
            response = finanzas_views.ahorro_nuevo(request)

        form_class.assert_called_once_with(request.POST)
        form.is_valid.assert_called_once()
        save_directo.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIs(contexto["form"], form)
        self.assertEqual(contexto["titulo"], "Nuevo ahorro")

    def test_aporte_nuevo_no_guarda_si_formulario_invalido(self):
        request = self._request_aporte_post(numerosemana="0")
        form = MagicMock()
        form.is_valid.return_value = False
        contexto = {}

        def render_spy(_request, _template, context):
            contexto.update(context)
            return HttpResponse("form invalido")

        with (
            patch(
                "apps.finanzas.views.AporteSemanalForm",
                return_value=form,
            ) as form_class,
            patch("apps.finanzas.views.save_new_model_form") as save_directo,
            patch("apps.finanzas.views.render", side_effect=render_spy),
        ):
            response = finanzas_views.aporte_nuevo(request)

        form_class.assert_called_once_with(request.POST)
        form.is_valid.assert_called_once()
        save_directo.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIs(contexto["form"], form)
        self.assertEqual(contexto["titulo"], "Nuevo aporte semanal")

    def test_prestamo_nuevo_llama_servicio_con_formulario_valido(self):
        request = self._request_post()
        datos_prestamo = {
            "idsocio": socio_stub(1, "Deudor"),
            "montoprestamosolicitado": Decimal("1000.00"),
            "tasainteres": Decimal("5.00"),
            "montototalpagar": Decimal("1050.00"),
            "saldopendiente": Decimal("9999.00"),
            "numerocuotas": 10,
            "fechasolicitud": date(2026, 7, 8),
            "fechavencimiento": date(2026, 12, 8),
            "estadoprestamo": "Solicitado",
        }
        datos_esperados = {
            **datos_prestamo,
            "saldopendiente": Decimal("1050.00"),
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
            datos_prestamo=datos_esperados,
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
        form.datos_prestamo.return_value = {
            "idsocio": socio_stub(1, "Deudor"),
            "montototalpagar": Decimal("1050.00"),
        }
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

    def test_prestamo_editar_bloquea_estado_liquidado(self):
        request = self._request_editar_post()
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            estadoprestamo="Liquidado",
        )

        with (
            patch("apps.finanzas.views.get_object_or_404", return_value=prestamo),
            patch("apps.finanzas.views.messages.error") as mensaje_error,
        ):
            response = finanzas_views.prestamo_editar(request, 10)

        mensaje_error.assert_called_once_with(
            request,
            "No se puede editar un préstamo cerrado o liquidado.",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/finanzas/prestamos/10/", response["Location"])

    def test_prestamo_editar_bloquea_estados_cerrado_cancelado_anulado(self):
        for estado in ("Cerrado", "Cancelado", "Anulado"):
            with self.subTest(estado=estado):
                request = self._request_editar_post()
                prestamo = Prestamo(
                    idprestamo=10,
                    idsocio=socio_stub(1, "Deudor"),
                    estadoprestamo=estado,
                )

                with (
                    patch(
                        "apps.finanzas.views.get_object_or_404",
                        return_value=prestamo,
                    ),
                    patch("apps.finanzas.views.messages.error") as mensaje_error,
                ):
                    response = finanzas_views.prestamo_editar(request, 10)

                mensaje_error.assert_called_once_with(
                    request,
                    "No se puede editar un préstamo cerrado o liquidado.",
                )
                self.assertEqual(response.status_code, 302)

    def test_prestamo_editar_no_permite_modificar_saldo_manual(self):
        request = self._request_editar_post(saldopendiente="1.00")
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            saldopendiente=Decimal("1050.00"),
            estadoprestamo="Aprobado",
        )
        pagos_qs = MagicMock()
        pagos_qs.exists.return_value = False
        contexto = {}

        def render_spy(_request, _template, context):
            contexto.update(context)
            return HttpResponse("\n".join(context["form"].non_field_errors()))

        with (
            patch("apps.finanzas.views.get_object_or_404", return_value=prestamo),
            patch(
                "apps.finanzas.views.PagoPrestamo.objects.filter",
                return_value=pagos_qs,
            ),
            patch.object(Prestamo, "full_clean"),
            patch(
                "apps.finanzas.forms.PrestamoEdicionForm.save",
                return_value=prestamo,
            ) as form_save,
            patch("apps.finanzas.views.render", side_effect=render_spy),
        ):
            response = finanzas_views.prestamo_editar(request, 10)

        self.assertEqual(response.status_code, 200)
        self.assertIn("No se permite modificar saldo pendiente", response.content.decode())
        form_save.assert_not_called()
        self.assertEqual(prestamo.saldopendiente, Decimal("1050.00"))
        self.assertIn("form", contexto)

    def test_prestamo_editar_bloquea_monto_solicitado_si_hay_pagos(self):
        request = self._request_editar_post(montoprestamosolicitado="1.00")
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            montoprestamosolicitado=Decimal("1000.00"),
            montototalpagar=Decimal("1050.00"),
            saldopendiente=Decimal("925.00"),
            estadoprestamo="Aprobado",
        )
        pagos_qs = MagicMock()
        pagos_qs.exists.return_value = True

        with (
            patch("apps.finanzas.views.get_object_or_404", return_value=prestamo),
            patch(
                "apps.finanzas.views.PagoPrestamo.objects.filter",
                return_value=pagos_qs,
            ),
            patch.object(Prestamo, "full_clean"),
            patch(
                "apps.finanzas.forms.PrestamoEdicionForm.save",
                return_value=prestamo,
            ) as form_save,
            patch("apps.finanzas.views.render", return_value=HttpResponse("ok")),
        ):
            response = finanzas_views.prestamo_editar(request, 10)

        self.assertEqual(response.status_code, 200)
        form_save.assert_not_called()
        self.assertEqual(prestamo.montoprestamosolicitado, Decimal("1000.00"))

    def test_prestamo_editar_bloquea_monto_total_si_hay_pagos(self):
        request = self._request_editar_post(montototalpagar="1.00")
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            montoprestamosolicitado=Decimal("1000.00"),
            montototalpagar=Decimal("1050.00"),
            saldopendiente=Decimal("925.00"),
            estadoprestamo="Aprobado",
        )
        pagos_qs = MagicMock()
        pagos_qs.exists.return_value = True

        with (
            patch("apps.finanzas.views.get_object_or_404", return_value=prestamo),
            patch(
                "apps.finanzas.views.PagoPrestamo.objects.filter",
                return_value=pagos_qs,
            ),
            patch.object(Prestamo, "full_clean"),
            patch(
                "apps.finanzas.forms.PrestamoEdicionForm.save",
                return_value=prestamo,
            ) as form_save,
            patch("apps.finanzas.views.render", return_value=HttpResponse("ok")),
        ):
            response = finanzas_views.prestamo_editar(request, 10)

        self.assertEqual(response.status_code, 200)
        form_save.assert_not_called()
        self.assertEqual(prestamo.montototalpagar, Decimal("1050.00"))

    def test_prestamo_editar_guarda_cambios_seguros_sin_pagos(self):
        request = self._request_editar_post(tasainteres="6.00")
        prestamo = Prestamo(
            idprestamo=10,
            idsocio=socio_stub(1, "Deudor"),
            montoprestamosolicitado=Decimal("1000.00"),
            montototalpagar=Decimal("1050.00"),
            saldopendiente=Decimal("1050.00"),
            estadoprestamo="Aprobado",
        )
        pagos_qs = MagicMock()
        pagos_qs.exists.return_value = False

        with (
            patch("apps.finanzas.views.get_object_or_404", return_value=prestamo),
            patch(
                "apps.finanzas.views.PagoPrestamo.objects.filter",
                return_value=pagos_qs,
            ),
            patch.object(Prestamo, "full_clean"),
            patch(
                "apps.finanzas.forms.PrestamoEdicionForm.save",
                return_value=prestamo,
            ) as form_save,
            patch(
                "apps.finanzas.views.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic,
        ):
            response = finanzas_views.prestamo_editar(request, 10)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/finanzas/prestamos/10/", response["Location"])
        form_save.assert_called_once()
        atomic.assert_called_once()

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
    def test_template_aportes_lista_muestra_valor_regalo_asociado(self):
        html = render_to_string(
            "finanzas/aportes_lista.html",
            {
                "page_obj": FakePage([aporte_stub(Decimal("12.50"))]),
                "total": 1,
            },
        )

        self.assertIn("Valor del regalo asociado", html)
        self.assertIn("Regalo 1", html)
        self.assertIn("$12,50", html)

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

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }
    )
    def test_template_nuevo_prestamo_no_muestra_saldopendiente_editable(self):
        form = PrestamoConGarantesForm(socio_queryset=Socio.objects.none())

        html = render_to_string(
            "finanzas/prestamo_formulario.html",
            {
                "form": form,
                "titulo": "Nuevo préstamo",
            },
        )

        self.assertIn(
            "El saldo pendiente inicial se genera automáticamente con el total a pagar.",
            html,
        )
        self.assertNotIn('name="saldopendiente"', html)


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


class SolicitudPagoPrestamoServicesTests(SimpleTestCase):
    def setUp(self):
        self.socio = socio_stub(1, "Socio Deudor")
        self.otro_socio = socio_stub(2, "Otro Socio")
        self.jugador = jugador_stub(1, self.socio)
        self.admin = User(username="admin", is_staff=True)
        self.metodo_pago = Metodopago(idmetodopago=3, nombremetodopago="Transferencia")

    def _datos_solicitud(self, **overrides):
        datos = {
            "monto": Decimal("100.00"),
            "idmetodopago": self.metodo_pago,
            "referencia": " REF-PORTAL ",
            "rutacomprobante": " TRX-001 ",
            "observacionsocio": " Pago desde portal ",
        }
        datos.update(overrides)
        return datos

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

    def _patch_solicitudes_pendientes(self, existe=False):
        solicitudes = MagicMock()
        solicitudes.exists.return_value = existe
        return patch(
            "apps.finanzas.services.SolicitudPagoPrestamo.objects.filter",
            return_value=solicitudes,
        )

    def _patch_solicitud_bloqueada(self, solicitud):
        return patch(
            "apps.finanzas.services.SolicitudPagoPrestamo.objects.select_for_update",
            return_value=LockedSolicitudPagoQuerySet(solicitud),
        )

    def test_socio_crea_solicitud_para_prestamo_propio(self):
        prestamo = prestamo_solicitud_stub(self.socio)
        solicitud_creada = SolicitudPagoPrestamo(idsolicitudpago=1)
        bloqueo_patch, prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic,
            bloqueo_patch,
            self._patch_solicitudes_pendientes(False),
            patch(
                "apps.finanzas.services.SolicitudPagoPrestamo.objects.create",
                return_value=solicitud_creada,
            ) as solicitud_create,
            patch("apps.finanzas.services.PagoPrestamo.objects.create") as pago_create,
        ):
            solicitud = crear_solicitud_pago_prestamo(
                self.jugador,
                prestamo.idprestamo,
                self._datos_solicitud(),
            )

        self.assertIs(solicitud, solicitud_creada)
        atomic.assert_called_once()
        prestamos_bloqueados.get.assert_called_once_with(idprestamo=10)
        solicitud_create.assert_called_once()
        datos_creacion = solicitud_create.call_args.kwargs
        self.assertIs(datos_creacion["idprestamo"], prestamo)
        self.assertEqual(datos_creacion["idsocio_id"], self.socio.idsocio)
        self.assertIs(datos_creacion["idjugador"], self.jugador)
        self.assertIs(datos_creacion["idmetodopago"], self.metodo_pago)
        self.assertEqual(datos_creacion["monto"], Decimal("100.00"))
        self.assertEqual(datos_creacion["referencia"], "REF-PORTAL")
        self.assertEqual(datos_creacion["rutacomprobante"], "TRX-001")
        self.assertEqual(datos_creacion["observacionsocio"], "Pago desde portal")
        self.assertEqual(datos_creacion["estado"], "Pendiente")
        pago_create.assert_not_called()

    def test_jugador_sin_socio_no_puede_solicitar_pago(self):
        jugador = jugador_stub(2, None)

        with self.assertRaisesMessage(
            SolicitudPagoPrestamoError,
            "El jugador no está vinculado a un socio.",
        ):
            crear_solicitud_pago_prestamo(
                jugador,
                10,
                self._datos_solicitud(),
            )

    def test_socio_no_puede_solicitar_pago_de_prestamo_ajeno(self):
        prestamo = prestamo_solicitud_stub(self.otro_socio)
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
                "apps.finanzas.services.SolicitudPagoPrestamo.objects.create"
            ) as solicitud_create,
        ):
            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "El préstamo no pertenece al socio autenticado.",
            ):
                crear_solicitud_pago_prestamo(
                    self.jugador,
                    prestamo.idprestamo,
                    self._datos_solicitud(),
                )

        solicitud_create.assert_not_called()

    def test_monto_cero_se_rechaza(self):
        with self.assertRaisesMessage(
            SolicitudPagoPrestamoError,
            "El monto debe ser mayor que cero.",
        ):
            crear_solicitud_pago_prestamo(
                self.jugador,
                10,
                self._datos_solicitud(monto=Decimal("0.00")),
            )

    def test_monto_negativo_se_rechaza(self):
        with self.assertRaisesMessage(
            SolicitudPagoPrestamoError,
            "El monto debe ser mayor que cero.",
        ):
            crear_solicitud_pago_prestamo(
                self.jugador,
                10,
                self._datos_solicitud(monto=Decimal("-1.00")),
            )

    def test_sobrepago_se_rechaza(self):
        prestamo = prestamo_solicitud_stub(self.socio, saldo=Decimal("50.00"))
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
                "apps.finanzas.services.SolicitudPagoPrestamo.objects.create"
            ) as solicitud_create,
        ):
            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "El monto no puede superar el saldo pendiente.",
            ):
                crear_solicitud_pago_prestamo(
                    self.jugador,
                    prestamo.idprestamo,
                    self._datos_solicitud(monto=Decimal("51.00")),
                )

        solicitud_create.assert_not_called()

    def test_solicitud_pendiente_no_modifica_saldopendiente(self):
        prestamo = prestamo_solicitud_stub(self.socio, saldo=Decimal("300.00"))
        saldo_original = prestamo.saldopendiente
        bloqueo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            bloqueo_patch,
            self._patch_solicitudes_pendientes(False),
            patch(
                "apps.finanzas.services.SolicitudPagoPrestamo.objects.create",
                return_value=SolicitudPagoPrestamo(idsolicitudpago=1),
            ),
            patch("apps.finanzas.services.PagoPrestamo.objects.create") as pago_create,
        ):
            crear_solicitud_pago_prestamo(
                self.jugador,
                prestamo.idprestamo,
                self._datos_solicitud(),
            )

        self.assertEqual(prestamo.saldopendiente, saldo_original)
        prestamo.save.assert_not_called()
        pago_create.assert_not_called()

    def test_no_permite_duplicar_solicitud_pendiente_para_mismo_prestamo(self):
        prestamo = prestamo_solicitud_stub(self.socio)
        bloqueo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            bloqueo_patch,
            self._patch_solicitudes_pendientes(True),
            patch(
                "apps.finanzas.services.SolicitudPagoPrestamo.objects.create"
            ) as solicitud_create,
        ):
            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "Ya existe una solicitud de pago pendiente para este préstamo.",
            ):
                crear_solicitud_pago_prestamo(
                    self.jugador,
                    prestamo.idprestamo,
                    self._datos_solicitud(),
                )

        solicitud_create.assert_not_called()

    def test_admin_aprueba_solicitud_pendiente_crea_pago_y_baja_saldo(self):
        prestamo = prestamo_solicitud_stub(self.socio, saldo=Decimal("300.00"))
        solicitud = solicitud_pago_prestamo_stub(
            prestamo,
            self.jugador,
            monto=Decimal("125.00"),
            metodo_pago=self.metodo_pago,
        )
        pago_creado = PagoPrestamo(idpagoprestamo=7)
        bloqueo_prestamo_patch, prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            self._patch_solicitud_bloqueada(solicitud),
            bloqueo_prestamo_patch as select_for_update,
            patch(
                "apps.finanzas.services.PagoPrestamo.objects.create",
                return_value=pago_creado,
            ) as pago_create,
        ):
            solicitud_resultado, pago = aprobar_solicitud_pago_prestamo(
                solicitud.idsolicitudpago,
                self.admin,
                {"observacionadmin": " Validado "},
            )

        self.assertIs(solicitud_resultado, solicitud)
        self.assertIs(pago, pago_creado)
        self.assertEqual(select_for_update.call_count, 2)
        self.assertEqual(prestamos_bloqueados.get.call_count, 2)
        pago_create.assert_called_once()
        self.assertEqual(prestamo.saldopendiente, Decimal("175.00"))
        prestamo.save.assert_called_once_with(update_fields=["saldopendiente"])
        self.assertEqual(solicitud.estado, SolicitudPagoPrestamo.ESTADO_APROBADA)
        self.assertIs(solicitud.idpagoprestamoresultado, pago_creado)
        self.assertEqual(solicitud.observacionadmin, "Validado")
        solicitud.save.assert_called_once_with(
            update_fields=[
                "estado",
                "fecharespuesta",
                "idusuarioadminrespuesta",
                "observacionadmin",
                "idpagoprestamoresultado",
            ]
        )

    def test_aprobar_pago_exacto_liquida_prestamo(self):
        prestamo = prestamo_solicitud_stub(self.socio, saldo=Decimal("100.00"))
        solicitud = solicitud_pago_prestamo_stub(
            prestamo,
            self.jugador,
            monto=Decimal("100.00"),
        )
        pago_creado = PagoPrestamo(idpagoprestamo=8)
        bloqueo_prestamo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            self._patch_solicitud_bloqueada(solicitud),
            bloqueo_prestamo_patch,
            patch(
                "apps.finanzas.services.PagoPrestamo.objects.create",
                return_value=pago_creado,
            ),
        ):
            aprobar_solicitud_pago_prestamo(solicitud.idsolicitudpago, self.admin)

        self.assertEqual(prestamo.saldopendiente, Decimal("0"))
        self.assertEqual(prestamo.estadoprestamo, "Liquidado")
        prestamo.save.assert_called_once_with(
            update_fields=["saldopendiente", "estadoprestamo"]
        )

    def test_admin_rechaza_solicitud_pendiente_sin_crear_pago_ni_bajar_saldo(self):
        prestamo = prestamo_solicitud_stub(self.socio, saldo=Decimal("300.00"))
        solicitud = solicitud_pago_prestamo_stub(prestamo, self.jugador)

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            self._patch_solicitud_bloqueada(solicitud),
            patch("apps.finanzas.services.PagoPrestamo.objects.create") as pago_create,
        ):
            resultado = rechazar_solicitud_pago_prestamo(
                solicitud.idsolicitudpago,
                self.admin,
                " Referencia no comprobada ",
            )

        self.assertIs(resultado, solicitud)
        self.assertEqual(solicitud.estado, SolicitudPagoPrestamo.ESTADO_RECHAZADA)
        self.assertEqual(solicitud.motivorechazo, "Referencia no comprobada")
        self.assertEqual(prestamo.saldopendiente, Decimal("300.00"))
        prestamo.save.assert_not_called()
        pago_create.assert_not_called()
        solicitud.save.assert_called_once_with(
            update_fields=[
                "estado",
                "fecharespuesta",
                "idusuarioadminrespuesta",
                "motivorechazo",
            ]
        )

    def test_no_se_puede_aprobar_dos_veces(self):
        prestamo = prestamo_solicitud_stub(self.socio)
        solicitud = solicitud_pago_prestamo_stub(
            prestamo,
            self.jugador,
            estado=SolicitudPagoPrestamo.ESTADO_APROBADA,
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            self._patch_solicitud_bloqueada(solicitud),
            patch(
                "apps.finanzas.services.PagoPrestamo.objects.create"
            ) as pago_create,
        ):
            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "La solicitud ya fue resuelta.",
            ):
                aprobar_solicitud_pago_prestamo(solicitud.idsolicitudpago, self.admin)

        pago_create.assert_not_called()

    def test_no_se_puede_rechazar_solicitud_aprobada(self):
        prestamo = prestamo_solicitud_stub(self.socio)
        solicitud = solicitud_pago_prestamo_stub(
            prestamo,
            self.jugador,
            estado=SolicitudPagoPrestamo.ESTADO_APROBADA,
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            self._patch_solicitud_bloqueada(solicitud),
        ):
            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "La solicitud ya fue resuelta.",
            ):
                rechazar_solicitud_pago_prestamo(
                    solicitud.idsolicitudpago,
                    self.admin,
                    "No procede",
                )

        solicitud.save.assert_not_called()

    def test_no_se_puede_aprobar_si_saldo_actual_no_alcanza(self):
        prestamo = prestamo_solicitud_stub(self.socio, saldo=Decimal("50.00"))
        solicitud = solicitud_pago_prestamo_stub(
            prestamo,
            self.jugador,
            monto=Decimal("100.00"),
        )
        bloqueo_prestamo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            self._patch_solicitud_bloqueada(solicitud),
            bloqueo_prestamo_patch,
            patch(
                "apps.finanzas.services.registrar_pago_prestamo"
            ) as registrar_pago,
        ):
            with self.assertRaisesMessage(
                SolicitudPagoPrestamoError,
                "El monto no puede superar el saldo pendiente.",
            ):
                aprobar_solicitud_pago_prestamo(solicitud.idsolicitudpago, self.admin)

        registrar_pago.assert_not_called()
        solicitud.save.assert_not_called()

    def test_aprobar_no_usa_select_related_nullable_con_select_for_update(self):
        prestamo = prestamo_solicitud_stub(self.socio)
        solicitud = solicitud_pago_prestamo_stub(prestamo, self.jugador)
        bloqueo_prestamo_patch, _prestamos_bloqueados = self._patch_prestamo_bloqueado(
            prestamo
        )

        with (
            patch(
                "apps.finanzas.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            self._patch_solicitud_bloqueada(solicitud) as solicitud_lock,
            bloqueo_prestamo_patch,
            patch(
                "apps.finanzas.services.registrar_pago_prestamo",
                return_value=PagoPrestamo(idpagoprestamo=9),
            ),
        ):
            aprobar_solicitud_pago_prestamo(solicitud.idsolicitudpago, self.admin)

        solicitud_lock.assert_called_once_with()


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

    def test_crear_prestamo_con_garantes_normaliza_saldo_inicial_al_total(self):
        datos_prestamo = self._datos_prestamo()
        datos_prestamo["saldopendiente"] = Decimal("9999.00")
        prestamo_creado = Prestamo(idprestamo=101, **self._datos_prestamo())
        atomic_mock = MagicMock(return_value=nullcontext())
        prestamos_creados = []

        def crear_prestamo(**kwargs):
            prestamos_creados.append(kwargs)
            return prestamo_creado

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            patch.object(
                Prestamo.objects,
                "create",
                side_effect=crear_prestamo,
            ) as prestamo_create,
            patch.object(PrestamoGarante.objects, "create") as garante_create,
        ):
            prestamo = crear_prestamo_con_garantes(
                datos_prestamo=datos_prestamo,
                garantes=[],
            )

        self.assertIs(prestamo, prestamo_creado)
        prestamo_create.assert_called_once()
        garante_create.assert_not_called()
        self.assertEqual(
            prestamos_creados[0]["montototalpagar"],
            Decimal("1050.00"),
        )
        self.assertEqual(
            prestamos_creados[0]["saldopendiente"],
            Decimal("1050.00"),
        )

    def test_crear_prestamo_con_garantes_calcula_saldo_si_no_viene_en_datos(self):
        datos_prestamo = self._datos_prestamo()
        datos_prestamo.pop("saldopendiente")
        prestamo_creado = Prestamo(idprestamo=101, **self._datos_prestamo())
        atomic_mock = MagicMock(return_value=nullcontext())
        prestamos_creados = []

        def crear_prestamo(**kwargs):
            prestamos_creados.append(kwargs)
            return prestamo_creado

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            patch.object(
                Prestamo.objects,
                "create",
                side_effect=crear_prestamo,
            ) as prestamo_create,
            patch.object(PrestamoGarante.objects, "create") as garante_create,
        ):
            prestamo = crear_prestamo_con_garantes(
                datos_prestamo=datos_prestamo,
                garantes=[],
            )

        self.assertIs(prestamo, prestamo_creado)
        prestamo_create.assert_called_once()
        garante_create.assert_not_called()
        self.assertEqual(
            prestamos_creados[0]["saldopendiente"],
            Decimal("1050.00"),
        )

    def test_crear_prestamo_con_garantes_rechaza_total_menor_que_monto_solicitado(self):
        datos_prestamo = self._datos_prestamo()
        datos_prestamo["montoprestamosolicitado"] = Decimal("100.00")
        datos_prestamo["montototalpagar"] = Decimal("99.99")
        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            patch.object(Prestamo.objects, "create") as prestamo_create,
            patch.object(PrestamoGarante.objects, "create") as garante_create,
        ):
            with self.assertRaisesMessage(
                PrestamoGarantiaError,
                "El total a pagar no puede ser menor que el monto solicitado.",
            ):
                crear_prestamo_con_garantes(
                    datos_prestamo=datos_prestamo,
                    garantes=[],
                )

        atomic_mock.assert_not_called()
        prestamo_create.assert_not_called()
        garante_create.assert_not_called()

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
