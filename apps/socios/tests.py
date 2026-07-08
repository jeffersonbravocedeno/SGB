from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from . import views as socios_views
from .models import Socio


def socio_stub(idsocio=1):
    return Socio(
        idsocio=idsocio,
        primernombresocio="Socio",
        segundonombresocio="",
        primerapellidosocio="Prueba",
        segundoapellidosocio="",
        cisocio=str(idsocio).zfill(10),
        estadosocio="Activo",
    )


def ahorro_stub(monto, estado="Activo", tipo="Obligatorio"):
    return SimpleNamespace(
        tipoahorro=tipo,
        idbingo="Bingo prueba",
        montoahorro=Decimal(monto),
        fechaahorro=datetime(2026, 7, 8, 10, 30),
        estado=estado,
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
