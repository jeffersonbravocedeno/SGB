from django.test import SimpleTestCase

from .templatetags.siab_tags import estado_class


class EstadoClassTests(SimpleTestCase):
    def test_estados_de_solicitudes_tienen_colores_distintos(self):
        self.assertEqual(estado_class("Pendiente"), "text-bg-warning")
        self.assertEqual(estado_class("Aprobada"), "text-bg-success")
        self.assertEqual(estado_class("Rechazada"), "text-bg-danger")

    def test_estados_operativos_y_cerrados_conservan_semantica(self):
        casos = {
            "Activo": "text-bg-success",
            "Registrado": "text-bg-success",
            "En curso": "text-bg-success",
            "Finalizado": "text-bg-secondary",
            "Liquidado": "text-bg-secondary",
            "Cancelado": "text-bg-danger",
            "Anulado": "text-bg-danger",
        }
        for estado, clase in casos.items():
            with self.subTest(estado=estado):
                self.assertEqual(estado_class(estado), clase)
