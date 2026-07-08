from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.db import models as django_models
from django.test import SimpleTestCase

from apps.socios.models import Socio

from . import services as finanzas_services
from .models import Prestamo, PrestamoGarante
from .services import (
    PrestamoGarantiaError,
    calcular_capacidad_garante,
    construir_datos_garantes,
    crear_prestamo_con_garantes,
    validar_garantes_prestamo,
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

    def test_crear_prestamo_con_garantes_no_crea_si_capacidad_insuficiente(self):
        bloqueo_patch, _socios_qs = self._patch_bloqueo_socios([2])
        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.calcular_capacidad_garante",
                return_value=Decimal("499.99"),
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
                    garantes=[Socio(idsocio=2)],
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
        bloqueo_patch, _socios_qs = self._patch_bloqueo_socios([1])
        atomic_mock = MagicMock(return_value=nullcontext())

        with (
            patch("apps.finanzas.services.transaction.atomic", atomic_mock),
            bloqueo_patch,
            patch(
                "apps.finanzas.services.calcular_capacidad_garante",
                return_value=Decimal("500.00"),
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
                    garantes=[Socio(idsocio=1)],
                )

        atomic_mock.assert_called_once()
        prestamo_create.assert_not_called()
        garante_create.assert_not_called()


class ValidarGarantesPrestamoTests(SimpleTestCase):
    def test_un_garante_suficiente_es_valido(self):
        resultado = validar_garantes_prestamo(
            socio_deudor_id=1,
            monto_solicitado=Decimal("1000"),
            garantes=[{"idsocio": 2, "capacidad": Decimal("500")}],
        )

        self.assertEqual(resultado["capacidad_total"], Decimal("500"))
        self.assertEqual(resultado["capacidad_requerida"], Decimal("500.00"))

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
                garantes=[{"idsocio": 2, "capacidad": Decimal("499.99")}],
            )

    def test_cero_garantes_rechaza_prestamo(self):
        with self.assertRaisesMessage(
            PrestamoGarantiaError,
            "Debe seleccionar al menos un garante.",
        ):
            validar_garantes_prestamo(
                socio_deudor_id=1,
                monto_solicitado=Decimal("1000"),
                garantes=[],
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
                garantes=[{"idsocio": 1, "capacidad": Decimal("500")}],
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
                garantes=[{"capacidad": Decimal("500")}],
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
                        garantes=[{"idsocio": 2, "capacidad": Decimal("500")}],
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
                        garantes=[{"idsocio": 2, "capacidad": valor}],
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
