from contextlib import nullcontext
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import views as auth_views
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from apps.bingos import views as bingo_views
from apps.bingos.models import Bingo, Carton, Partidabingo
from apps.bingos.services import CASILLA_LIBRE, serializar_bolas_cantadas, serializar_matriz_carton_bingo
from apps.configuracion import views as configuracion_views
from apps.finanzas import views as finanzas_views
from apps.jugadores import services as jugadores_services
from apps.jugadores import views as jugadores_views
from apps.jugadores.models import Jugador
from apps.seguridad.forms import RegistroJugadorForm, SIABPasswordChangeForm
from apps.seguridad.views import SIABLoginView
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

    def exclude(self, *args, **kwargs):
        return self

    def count(self):
        return len(self)

    def exists(self):
        return bool(self)

    def first(self):
        return self[0] if self else None


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


class RegistroPublicoJugadorTests(SimpleTestCase):
    def _form_data(self, **overrides):
        data = {
            "aliasjugador": "maria456",
            "correojugador": "maria@example.com",
            "password1": "ClaveSegura2026!",
            "password2": "ClaveSegura2026!",
        }
        data.update(overrides)
        return data

    def _sin_conflictos(self):
        return (
            patch(
                "apps.seguridad.forms.Jugador.objects.filter",
                return_value=FakeQuerySet(),
            ),
            patch(
                "apps.seguridad.forms.User.objects.filter",
                return_value=FakeQuerySet(),
            ),
        )

    def test_formulario_publico_solo_expone_campos_permitidos(self):
        form = RegistroJugadorForm()

        self.assertEqual(
            list(form.fields),
            ["aliasjugador", "correojugador", "password1", "password2"],
        )

    def test_formulario_valido_limpia_alias_y_correo(self):
        with self._sin_conflictos()[0], self._sin_conflictos()[1]:
            form = RegistroJugadorForm(
                data=self._form_data(
                    aliasjugador="  Maria456  ",
                    correojugador="MARIA@EXAMPLE.COM",
                )
            )
            es_valido = form.is_valid()

        self.assertTrue(es_valido, form.errors)
        self.assertEqual(form.cleaned_data["aliasjugador"], "Maria456")
        self.assertEqual(form.cleaned_data["correojugador"], "maria@example.com")

    def test_no_es_valido_si_alias_ya_existe_en_jugador(self):
        def jugador_filter(**kwargs):
            if "aliasjugador__iexact" in kwargs:
                return FakeQuerySet([object()])
            return FakeQuerySet()

        with patch("apps.seguridad.forms.Jugador.objects.filter", side_effect=jugador_filter), patch(
            "apps.seguridad.forms.User.objects.filter",
            return_value=FakeQuerySet(),
        ):
            form = RegistroJugadorForm(data=self._form_data(aliasjugador="Juan"))
            es_valido = form.is_valid()

        self.assertFalse(es_valido)
        self.assertIn("aliasjugador", form.errors)

    def test_no_es_valido_si_alias_ya_existe_en_user(self):
        with patch("apps.seguridad.forms.Jugador.objects.filter", return_value=FakeQuerySet()), patch(
            "apps.seguridad.forms.User.objects.filter",
            return_value=FakeQuerySet([object()]),
        ):
            form = RegistroJugadorForm(data=self._form_data(aliasjugador="Juan"))
            es_valido = form.is_valid()

        self.assertFalse(es_valido)
        self.assertIn("aliasjugador", form.errors)

    def test_no_es_valido_si_passwords_no_coinciden(self):
        with self._sin_conflictos()[0], self._sin_conflictos()[1]:
            form = RegistroJugadorForm(
                data=self._form_data(password2="OtraClave2026!")
            )
            es_valido = form.is_valid()

        self.assertFalse(es_valido)
        self.assertIn("password2", form.errors)

    def test_servicio_crea_jugador_y_user_coherentes(self):
        usuario_creado = None

        def fake_create_user(**kwargs):
            nonlocal usuario_creado
            usuario_creado = User(
                username=kwargs["username"],
                email=kwargs["email"],
                is_staff=kwargs["is_staff"],
                is_superuser=kwargs["is_superuser"],
                is_active=kwargs["is_active"],
            )
            usuario_creado.set_password(kwargs["password"])
            return usuario_creado

        with patch("apps.jugadores.services.transaction.atomic", return_value=nullcontext()), patch(
            "apps.jugadores.services.assign_next_integer_pk",
            side_effect=lambda jugador: setattr(jugador, "idjugador", 10) or jugador,
        ), patch("apps.jugadores.services.Jugador.save") as save_mock, patch(
            "apps.jugadores.services.User.objects.create_user",
            side_effect=fake_create_user,
        ) as create_user_mock, patch(
            "apps.jugadores.services.agregar_usuario_a_grupo_jugador"
        ) as add_group_mock:
            jugador, user = jugadores_services.registrar_jugador_publico(
                "maria456",
                "maria@example.com",
                "ClaveSegura2026!",
            )

        self.assertEqual(jugador.aliasjugador, "maria456")
        self.assertEqual(user.username, jugador.aliasjugador)
        self.assertTrue(user.check_password("ClaveSegura2026!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        save_mock.assert_called_once_with(force_insert=True)
        create_user_mock.assert_called_once()
        add_group_mock.assert_called_once_with(user)

    def test_servicio_usa_transaccion_si_falla_creacion_de_user(self):
        atomic_mock = Mock(return_value=nullcontext())
        with patch("apps.jugadores.services.transaction.atomic", atomic_mock), patch(
            "apps.jugadores.services.assign_next_integer_pk",
            side_effect=lambda jugador: setattr(jugador, "idjugador", 10) or jugador,
        ), patch("apps.jugadores.services.Jugador.save"), patch(
            "apps.jugadores.services.User.objects.create_user",
            side_effect=RuntimeError("fallo simulado"),
        ):
            with self.assertRaises(RuntimeError):
                jugadores_services.registrar_jugador_publico(
                    "maria456",
                    "maria@example.com",
                    "ClaveSegura2026!",
                )

        atomic_mock.assert_called_once()


class AccesoJugadorExistenteTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.jugador = Jugador(
            idjugador=20,
            aliasjugador="juan123",
            correojugador="juan@example.com",
            estadocuentajugador="Activo",
        )

    def test_staff_puede_crear_acceso_para_jugador_activo_con_alias(self):
        usuario = User(username="juan123", email="juan@example.com")
        usuario.set_password("ClaveSegura2026!")

        with patch("apps.jugadores.services.User.objects.filter", return_value=FakeQuerySet()), patch(
            "apps.jugadores.services.transaction.atomic",
            return_value=nullcontext(),
        ), patch(
            "apps.jugadores.services.crear_usuario_jugador",
            return_value=usuario,
        ) as crear_mock:
            resultado = jugadores_services.crear_acceso_para_jugador(
                self.jugador,
                "ClaveSegura2026!",
            )

        self.assertEqual(resultado.username, self.jugador.aliasjugador)
        crear_mock.assert_called_once_with(
            "juan123",
            "juan@example.com",
            "ClaveSegura2026!",
        )

    def test_no_crea_acceso_si_jugador_no_tiene_alias(self):
        self.jugador.aliasjugador = ""

        with patch("apps.jugadores.services.crear_usuario_jugador") as crear_mock:
            with self.assertRaises(ValidationError):
                jugadores_services.crear_acceso_para_jugador(
                    self.jugador,
                    "ClaveSegura2026!",
                )

        crear_mock.assert_not_called()

    def test_no_crea_segunda_cuenta(self):
        with patch(
            "apps.jugadores.services.User.objects.filter",
            return_value=FakeQuerySet([object()]),
        ), patch("apps.jugadores.services.crear_usuario_jugador") as crear_mock:
            with self.assertRaises(ValidationError):
                jugadores_services.crear_acceso_para_jugador(
                    self.jugador,
                    "ClaveSegura2026!",
                )

        crear_mock.assert_not_called()

    def test_anonimo_no_puede_usar_ruta_de_crear_acceso(self):
        request = self.factory.post("/jugadores/20/crear-acceso/")
        request.user = AnonymousUser()

        response = jugadores_views.crear_acceso(request, 20)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_usuario_jugador_no_staff_no_puede_usar_ruta_de_crear_acceso(self):
        request = self.factory.post("/jugadores/20/crear-acceso/")
        request.user = User(username="juan123", is_staff=False)

        with self.assertRaises(PermissionDenied):
            jugadores_views.crear_acceso(request, 20)


class MisCartonesPrivadoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.jugador = Jugador(
            idjugador=41,
            aliasjugador="maria456",
            correojugador="maria@example.com",
            estadocuentajugador="Activo",
            saldocreditojugador=Decimal("0.00"),
        )

    def _request(self, path, user=None):
        request = self.factory.get(path)
        request.user = AnonymousUser() if user is None else user
        request.session = {}
        return request

    def test_visitante_anonimo_es_redirigido_en_mis_cartones(self):
        response = bingo_views.mis_cartones(self._request("/mis-cartones/"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_usuario_sin_grupo_jugador_recibe_403(self):
        usuario = User(username="normal")
        usuario.pk = 5

        with patch("apps.jugadores.services.usuario_es_jugador", return_value=False):
            with self.assertRaises(PermissionDenied):
                bingo_views.mis_cartones(
                    self._request("/mis-cartones/", usuario)
                )

    def test_jugador_ve_solo_cartones_filtrados_por_su_jugador(self):
        usuario = User(username="maria456")
        usuario.pk = 5
        carton = self._carton("M-001", self.jugador)
        captured = {}

        def fake_render(_request, _template, context):
            captured["context"] = context
            return HttpResponse("ok")

        with patch("apps.jugadores.services.obtener_jugador_autenticado", return_value=self.jugador), patch(
            "apps.bingos.views.Carton.objects.filter",
            return_value=FakeQuerySet([carton]),
        ) as filter_mock, patch("apps.bingos.views.render", side_effect=fake_render):
            response = bingo_views.mis_cartones(
                self._request("/mis-cartones/", usuario)
            )

        self.assertEqual(response.status_code, 200)
        filter_mock.assert_called_once_with(idjugador=self.jugador)
        self.assertEqual(
            captured["context"]["cartones_resumen"][0]["carton"].codigocarton,
            "M-001",
        )

    def test_jugador_puede_abrir_su_carton(self):
        usuario = User(username="maria456")
        usuario.pk = 5
        carton = self._carton("M-001", self.jugador)

        with patch("apps.jugadores.services.obtener_jugador_autenticado", return_value=self.jugador), patch(
            "apps.bingos.views.Carton.objects.select_related",
            return_value=FakeQuerySet([carton]),
        ), patch("apps.bingos.views.render", return_value=HttpResponse("ok")):
            response = bingo_views.mi_carton_detalle(
                self._request("/mis-cartones/M-001/", usuario),
                "M-001",
            )

        self.assertEqual(response.status_code, 200)

    def test_jugador_no_puede_abrir_carton_ajeno(self):
        usuario = User(username="maria456")
        usuario.pk = 5

        with patch("apps.jugadores.services.obtener_jugador_autenticado", return_value=self.jugador), patch(
            "apps.bingos.views.Carton.objects.select_related",
            return_value=FakeQuerySet(),
        ):
            with self.assertRaises(Http404):
                bingo_views.mi_carton_detalle(
                    self._request("/mis-cartones/AJENO/", usuario),
                    "AJENO",
                )

    def _partida(self):
        bingo = Bingo(
            idbingo=7,
            titulobingo="Bingo privado",
            preciocarton=Decimal("1.00"),
            premiomayor=Decimal("100.00"),
            descripcionpremiomayor="Premio",
            estadobingo="Programado",
        )
        return Partidabingo(
            idpartidabingo=30,
            idbingo=bingo,
            nombreronda="Ronda privada",
            valorefectivo=Decimal("50.00"),
            premiomaterial="",
            estadopartida="En curso",
            bolascantadas=serializar_bolas_cantadas([1, 16, 31]),
            ultimabola=31,
            haydesempate=False,
            horainicio=timezone.now(),
        )

    def _carton(self, codigo, jugador):
        matriz = [
            [1, 16, 31, 46, 61],
            [2, 17, 32, 47, 62],
            [3, 18, CASILLA_LIBRE, 48, 63],
            [4, 19, 34, 49, 64],
            [5, 20, 35, 50, 65],
        ]
        return Carton(
            idcarton=200,
            idjugador=jugador,
            idpartida=self._partida(),
            codigocarton=codigo,
            matriznumeros=serializar_matriz_carton_bingo(matriz),
            indicevictoria=0,
            preciopagado=Decimal("1.00"),
            fechacompra=timezone.now(),
            estadocarton="Vendido",
        )


class AliasYRedireccionTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _form_alias(self, alias, jugador):
        form = Mock()
        form.cleaned_data = {"aliasjugador": alias}
        form.instance = jugador
        form.save.return_value = jugador
        return form

    def test_cambio_alias_sincroniza_username_de_user_jugador(self):
        jugador = Jugador(idjugador=1, aliasjugador="nuevo")
        user = User(username="anterior")
        user.pk = 10
        user.save = Mock()
        form = self._form_alias("nuevo", jugador)

        with patch("apps.jugadores.services.obtener_usuario_por_alias", return_value=user), patch(
            "apps.jugadores.services.usuario_es_jugador",
            return_value=True,
        ), patch("apps.jugadores.services.User.objects.filter", return_value=FakeQuerySet()), patch(
            "apps.jugadores.services.Jugador.objects.filter",
            return_value=FakeQuerySet(),
        ), patch("apps.jugadores.services.transaction.atomic", return_value=nullcontext()):
            resultado = jugadores_services.sincronizar_alias_jugador_si_corresponde(
                form,
                "anterior",
            )

        self.assertIs(resultado, jugador)
        self.assertEqual(user.username, "nuevo")
        user.save.assert_called_once_with(update_fields=["username"])

    def test_conflicto_alias_no_guarda_cambios_parciales(self):
        jugador = Jugador(idjugador=1, aliasjugador="nuevo")
        user = User(username="anterior")
        user.pk = 10
        user.save = Mock()
        form = self._form_alias("nuevo", jugador)

        with patch("apps.jugadores.services.obtener_usuario_por_alias", return_value=user), patch(
            "apps.jugadores.services.usuario_es_jugador",
            return_value=True,
        ), patch(
            "apps.jugadores.services.User.objects.filter",
            return_value=FakeQuerySet([object()]),
        ):
            resultado = jugadores_services.sincronizar_alias_jugador_si_corresponde(
                form,
                "anterior",
            )

        self.assertIsNone(resultado)
        form.save.assert_not_called()
        user.save.assert_not_called()
        form.add_error.assert_called_once()

    def test_no_sincroniza_user_que_no_pertenece_a_grupo_jugador(self):
        jugador = Jugador(idjugador=1, aliasjugador="nuevo")
        user = User(username="anterior")
        user.pk = 10
        user.save = Mock()
        form = self._form_alias("nuevo", jugador)

        with patch("apps.jugadores.services.obtener_usuario_por_alias", return_value=user), patch(
            "apps.jugadores.services.usuario_es_jugador",
            return_value=False,
        ), patch("apps.jugadores.services.transaction.atomic", return_value=nullcontext()):
            resultado = jugadores_services.sincronizar_alias_jugador_si_corresponde(
                form,
                "anterior",
            )

        self.assertIs(resultado, jugador)
        user.save.assert_not_called()

    def test_login_staff_respeta_next_seguro(self):
        user = User(username="admin", is_staff=True)
        user.pk = 1
        view = SIABLoginView()
        view.request = self._request("/login/", user, {"next": "/socios/"})

        self.assertEqual(view.get_success_url(), "/socios/")

    def test_login_staff_no_usa_next_de_jugador(self):
        user = User(username="admin", is_staff=True)
        user.pk = 1
        view = SIABLoginView()
        view.request = self._request(
            "/login/",
            user,
            {"next": reverse("bingos:mis_cartones")},
        )

        self.assertEqual(view.get_success_url(), reverse("home"))

    def test_login_jugador_va_a_mis_cartones(self):
        user = User(username="maria456")
        user.pk = 2
        view = SIABLoginView()
        view.request = self._request("/login/", user)

        with patch("apps.seguridad.views.usuario_es_jugador", return_value=True):
            self.assertEqual(view.get_success_url(), reverse("bingos:mis_cartones"))

    def test_login_no_permite_open_redirect_externo(self):
        user = User(username="admin", is_staff=True)
        user.pk = 1
        view = SIABLoginView()
        view.request = self._request(
            "/login/",
            user,
            {"next": "https://evil.example/socios/"},
        )

        self.assertEqual(view.get_success_url(), reverse("home"))

    def _request(self, path, user, data=None):
        request = self.factory.get(path, data or {})
        request.user = user
        return request
