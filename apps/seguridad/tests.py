from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import views as auth_views
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from apps.bingos import views as bingo_views
from apps.bingos.models import Bingo, Carton, Partidabingo
from apps.bingos.services import CASILLA_LIBRE, serializar_bolas_cantadas, serializar_matriz_carton_bingo
from apps.configuracion import views as configuracion_views
from apps.finanzas import views as finanzas_views
from apps.jugadores import views as jugadores_views
from apps.jugadores.models import Jugador
from apps.seguridad.forms import SIABPasswordChangeForm
from apps.socios import views as socios_views
from config import views as config_views


class FakeQuerySet(list):
    def all(self):
        return self

    def order_by(self, *fields):
        return self

    def select_related(self, *fields):
        return self

    def filter(self, *args, **kwargs):
        return self

    def count(self):
        return len(self)


class PermisosAdministrativosTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.usuario_normal = User(username="usuario-normal")
        self.usuario_staff = User(username="usuario-staff", is_staff=True)

    def _request(self, path="/", user=None):
        request = self.factory.get(path)
        request.user = AnonymousUser() if user is None else user
        request.session = {}
        return request

    def _admin_view_cases(self):
        return (
            ("dashboard", config_views.home, "/", (), {}),
            ("socios", socios_views.lista, "/socios/", (), {}),
            ("jugadores", jugadores_views.lista, "/jugadores/", (), {}),
            ("finanzas", finanzas_views.dashboard, "/finanzas/", (), {}),
            ("configuracion", configuracion_views.dashboard, "/configuracion/", (), {}),
            ("bingos", bingo_views.bingos_lista, "/bingos/", (), {}),
        )

    def test_anonimo_no_accede_a_vistas_administrativas(self):
        for nombre, view, path, args, kwargs in self._admin_view_cases():
            with self.subTest(nombre=nombre):
                response = view(self._request(path), *args, **kwargs)

                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])
                self.assertIn("next=", response["Location"])

    def test_usuario_normal_no_accede_a_modulos_administrativos(self):
        for nombre, view, path, args, kwargs in self._admin_view_cases():
            with self.subTest(nombre=nombre):
                request = self._request(path, self.usuario_normal)

                with self.assertRaises(PermissionDenied):
                    view(request, *args, **kwargs)

    def test_usuario_normal_puede_abrir_cambio_de_password(self):
        view = auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            form_class=SIABPasswordChangeForm,
            success_url="/password-change/done/",
        )
        response = view(self._request("/password-change/", self.usuario_normal))

        self.assertEqual(response.status_code, 200)

    def test_anonimo_puede_abrir_rutas_publicas_de_bingo(self):
        self._assert_public_bingo_views_open(AnonymousUser())

    def test_usuario_normal_puede_abrir_rutas_publicas_de_bingo(self):
        self._assert_public_bingo_views_open(self.usuario_normal)

    def test_staff_puede_acceder_a_modulos_administrativos(self):
        request = self._request("/", self.usuario_staff)
        with patch("config.views.safe_count", return_value=0), patch(
            "config.views.render",
            return_value=HttpResponse("dashboard"),
        ):
            self.assertEqual(config_views.home(request).status_code, 200)

        queryset = FakeQuerySet()
        request = self._request("/socios/", self.usuario_staff)
        with patch("apps.socios.views.Socio.objects.select_related", return_value=queryset), patch(
            "apps.socios.views.paginate",
            return_value=[],
        ), patch("apps.socios.views.render", return_value=HttpResponse("socios")):
            self.assertEqual(socios_views.lista(request).status_code, 200)

        request = self._request("/jugadores/", self.usuario_staff)
        with patch("apps.jugadores.views.Jugador.objects.select_related", return_value=queryset), patch(
            "apps.jugadores.views.paginate",
            return_value=[],
        ), patch("apps.jugadores.views.render", return_value=HttpResponse("jugadores")):
            self.assertEqual(jugadores_views.lista(request).status_code, 200)

        request = self._request("/finanzas/", self.usuario_staff)
        with patch("apps.finanzas.views._safe_filtered_count", return_value=0), patch(
            "apps.finanzas.views.safe_count",
            return_value=0,
        ), patch("apps.finanzas.views.render", return_value=HttpResponse("finanzas")):
            self.assertEqual(finanzas_views.dashboard(request).status_code, 200)

        request = self._request("/configuracion/", self.usuario_staff)
        with patch("apps.configuracion.views.safe_count", return_value=0), patch(
            "apps.configuracion.views.render",
            return_value=HttpResponse("configuracion"),
        ):
            self.assertEqual(configuracion_views.dashboard(request).status_code, 200)

        request = self._request("/bingos/", self.usuario_staff)
        with patch("apps.bingos.views.Bingo.objects.order_by", return_value=queryset), patch(
            "apps.bingos.views.paginate",
            return_value=[],
        ), patch("apps.bingos.views.render", return_value=HttpResponse("bingos")):
            self.assertEqual(bingo_views.bingos_lista(request).status_code, 200)

    def _assert_public_bingo_views_open(self, user):
        with self.subTest("sala_publica"):
            partida = self._partida_publica()
            consulta = Mock()
            consulta.order_by.return_value = [partida]
            with patch("apps.bingos.views.Partidabingo.objects.select_related", return_value=consulta), patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("sala"),
            ):
                response = bingo_views.sala_juego_publica(
                    self._request("/juego/", user)
                )
                self.assertEqual(response.status_code, 200)

        with self.subTest("tablero_publico"):
            partida = self._partida_publica()
            with patch("apps.bingos.views.get_object_or_404", return_value=partida), patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("tablero"),
            ):
                response = bingo_views.tablero_publico(
                    self._request("/juego/partidas/10/tablero/", user),
                    idpartidabingo=10,
                )
                self.assertEqual(response.status_code, 200)

        with self.subTest("consulta_carton_publico"):
            with patch("apps.bingos.views.render", return_value=HttpResponse("consulta")):
                response = bingo_views.acceder_carton_publico(
                    self._request("/juego/cartones/acceder/", user)
                )
                self.assertEqual(response.status_code, 200)

        with self.subTest("carton_publico"):
            carton = self._carton_publico()
            consulta = Mock()
            consulta.filter.return_value.first.return_value = carton
            with patch("apps.bingos.views.Carton.objects.select_related", return_value=consulta), patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("carton"),
            ):
                response = bingo_views.carton_publico(
                    self._request("/juego/cartones/P10-C-TEST/", user),
                    codigocarton="P10-C-TEST",
                )
                self.assertEqual(response.status_code, 200)

    def _partida_publica(self):
        bingo = Bingo(
            idbingo=1,
            titulobingo="Bingo publico",
            fechaprogramadabingo=timezone.now(),
            tipobingo="Publico",
            preciocarton=Decimal("1.00"),
            premiomayor=Decimal("100.00"),
            descripcionpremiomayor="Premio",
            estadobingo="Programado",
        )
        return Partidabingo(
            idpartidabingo=10,
            idbingo=bingo,
            nombreronda="Ronda publica",
            valorefectivo=Decimal("50.00"),
            premiomaterial="",
            estadopartida="En curso",
            bolascantadas=serializar_bolas_cantadas([1, 16, 31]),
            ultimabola=31,
            haydesempate=False,
            horainicio=timezone.now(),
        )

    def _carton_publico(self):
        jugador = Jugador(
            idjugador=1,
            aliasjugador="jugador-publico",
            correojugador="jugador@example.com",
            fecharegistrojugador=timezone.now(),
            saldocreditojugador=Decimal("0.00"),
            estadocuentajugador="Activo",
        )
        matriz = [
            [1, 16, 31, 46, 61],
            [2, 17, 32, 47, 62],
            [3, 18, CASILLA_LIBRE, 48, 63],
            [4, 19, 34, 49, 64],
            [5, 20, 35, 50, 65],
        ]
        return Carton(
            idcarton=100,
            idjugador=jugador,
            idpartida=self._partida_publica(),
            codigocarton="P10-C-TEST",
            matriznumeros=serializar_matriz_carton_bingo(matriz),
            indicevictoria=0,
            preciopagado=Decimal("1.00"),
            fechacompra=timezone.now(),
            estadocarton="Vendido",
        )
