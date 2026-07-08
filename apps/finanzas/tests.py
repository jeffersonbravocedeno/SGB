from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from .services import PrestamoGarantiaError, validar_garantes_prestamo


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
