from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from apps.jugadores.models import Jugador

from .forms import GenerarAsignarCartonForm, PartidaBingoForm
from .models import Bingo, Carton, Partidabingo
from .services import (
    CASILLA_LIBRE,
    ESTADO_PARTIDA_CANCELADA,
    ESTADO_PARTIDA_DESEMPATE,
    ESTADO_PARTIDA_EN_CURSO,
    ESTADO_PARTIDA_EN_ESPERA,
    ESTADO_PARTIDA_FINALIZADA,
    ESTADO_PARTIDA_PAUSADA,
    ESTADO_PARTIDA_PROGRAMADA,
    BolaBingoError,
    BolilleroAgotadoError,
    CartonAsignacionError,
    EstadoPartidaError,
    acciones_disponibles_consola,
    aplicar_accion_consola,
    crear_y_asignar_carton,
    deserializar_matriz_carton_bingo,
    estado_partida_mostrar,
    extraer_siguiente_bola,
    formatear_bola_bingo,
    generar_codigo_carton,
    generar_matriz_carton_bingo,
    letra_bingo,
    normalizar_estado_partida,
    obtener_bolas_disponibles,
    parsear_bolas_cantadas,
    puede_asignar_cartones,
    serializar_bolas_cantadas,
    serializar_matriz_carton_bingo,
)
from .views import (
    _procesar_accion_consola,
    partida_carton_nuevo,
    partidas_lista,
    sacar_bola,
)


def datos_partida_form(**overrides):
    data = {
        "idjugadorganador": "",
        "nombreronda": "1",
        "valorefectivo": "22",
        "premiomaterial": "cafsf",
        "estadopartida": "Programada",
        "bolascantadas": "[]",
        "ultimabola": "0",
        "haydesempate": "",
        "idbingadores": "",
        "bolamayordesempate": "",
        "horainicio": "2026-06-27T17:00",
        "horafin": "",
    }
    data.update(overrides)
    return data


class PartidaBingoFormTests(SimpleTestCase):
    def test_programada_es_valida_al_crear_partida(self):
        form = PartidaBingoForm(data=datos_partida_form(estadopartida="Programada"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["estadopartida"], "Programada")

    def test_en_espera_es_valida_al_crear_partida(self):
        form = PartidaBingoForm(data=datos_partida_form(estadopartida="En espera"))

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["estadopartida"], "En espera")

    def test_estado_inventado_es_rechazado(self):
        form = PartidaBingoForm(data=datos_partida_form(estadopartida="Estado inventado"))

        self.assertFalse(form.is_valid())
        self.assertIn("estadopartida", form.errors)

    def test_en_juego_legacy_se_normaliza_al_editar(self):
        partida = Partidabingo(idpartidabingo=1, estadopartida="En Juego")
        form = PartidaBingoForm(
            data=datos_partida_form(estadopartida="En Juego"),
            instance=partida,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["estadopartida"], "En curso")

    def test_estados_nuevos_se_mantienen_reales_al_guardar_form(self):
        form = PartidaBingoForm(data=datos_partida_form(estadopartida="Programada"))

        self.assertTrue(form.is_valid(), form.errors)
        partida = form.save(commit=False)
        self.assertEqual(partida.estadopartida, "Programada")

    def test_no_se_crearon_migraciones_de_bingos(self):
        migration_files = sorted(
            path.name
            for path in Path("apps/bingos/migrations").glob("*.py")
            if path.name != "__init__.py"
        )

        self.assertEqual(migration_files, [])


class GeneracionMatrizCartonTests(SimpleTestCase):
    def setUp(self):
        self.matriz = generar_matriz_carton_bingo()

    def test_matriz_tiene_cinco_filas_y_cinco_columnas(self):
        self.assertEqual(len(self.matriz), 5)
        self.assertTrue(all(len(fila) == 5 for fila in self.matriz))

    def test_columna_b_contiene_numeros_del_1_al_15(self):
        self.assertTrue(all(1 <= fila[0] <= 15 for fila in self.matriz))

    def test_columna_i_contiene_numeros_del_16_al_30(self):
        self.assertTrue(all(16 <= fila[1] <= 30 for fila in self.matriz))

    def test_columna_n_tiene_cuatro_numeros_y_centro_libre(self):
        columna_n = [fila[2] for fila in self.matriz]
        self.assertEqual(columna_n[2], CASILLA_LIBRE)
        numeros = [valor for valor in columna_n if valor != CASILLA_LIBRE]
        self.assertEqual(len(numeros), 4)
        self.assertTrue(all(31 <= numero <= 45 for numero in numeros))

    def test_columna_g_contiene_numeros_del_46_al_60(self):
        self.assertTrue(all(46 <= fila[3] <= 60 for fila in self.matriz))

    def test_columna_o_contiene_numeros_del_61_al_75(self):
        self.assertTrue(all(61 <= fila[4] <= 75 for fila in self.matriz))

    def test_no_hay_numeros_repetidos(self):
        numeros = [
            valor
            for fila in self.matriz
            for valor in fila
            if valor != CASILLA_LIBRE
        ]
        self.assertEqual(len(numeros), len(set(numeros)))

    def test_matriz_se_serializa_como_json_en_lista_de_filas(self):
        serializada = serializar_matriz_carton_bingo(self.matriz)

        self.assertEqual(deserializar_matriz_carton_bingo(serializada), self.matriz)
        self.assertIn('"LIBRE"', serializada)


class AsignacionCartonTests(SimpleTestCase):
    def _crear_carton_sin_base_de_datos(self, estado):
        partida = Partidabingo(
            idpartidabingo=12,
            estadopartida=estado,
        )
        partida_bloqueada = Partidabingo(
            idpartidabingo=12,
            estadopartida=estado,
        )
        jugador = Jugador(idjugador=4)

        def asignar_pk(carton):
            carton.idcarton = 30
            return carton

        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic_mock,
            patch(
                "apps.bingos.services.Partidabingo.objects.select_for_update"
            ) as select_for_update,
            patch(
                "apps.bingos.services.assign_next_integer_pk",
                side_effect=asignar_pk,
            ),
            patch(
                "apps.bingos.services.generar_codigo_carton",
                return_value="P12-C-ABC1234567",
            ),
            patch.object(Carton, "full_clean") as full_clean_mock,
            patch.object(Carton, "save") as save_mock,
        ):
            select_for_update.return_value.get.return_value = partida_bloqueada
            carton = crear_y_asignar_carton(
                partida=partida,
                jugador=jugador,
                precio_pagado=Decimal("5.00"),
            )

        atomic_mock.assert_called_once_with()
        full_clean_mock.assert_called_once_with(
            validate_unique=False,
            validate_constraints=False,
        )
        save_mock.assert_called_once_with(force_insert=True)
        return carton

    def test_no_se_asigna_carton_a_partida_en_curso(self):
        partida = Partidabingo(
            idpartidabingo=1,
            estadopartida=ESTADO_PARTIDA_EN_CURSO,
        )

        with patch.object(Carton, "save") as save_mock:
            with self.assertRaises(CartonAsignacionError):
                crear_y_asignar_carton(partida, Jugador(idjugador=1), "5.00")

        save_mock.assert_not_called()

    def test_no_se_asigna_carton_a_partida_pausada(self):
        partida = Partidabingo(
            idpartidabingo=1,
            estadopartida=ESTADO_PARTIDA_PAUSADA,
        )

        with patch.object(Carton, "save") as save_mock:
            with self.assertRaises(CartonAsignacionError):
                crear_y_asignar_carton(partida, Jugador(idjugador=1), "5.00")

        save_mock.assert_not_called()

    def test_desempate_finalizada_y_cancelada_bloquean_asignacion(self):
        for estado in (
            ESTADO_PARTIDA_DESEMPATE,
            ESTADO_PARTIDA_FINALIZADA,
            ESTADO_PARTIDA_CANCELADA,
        ):
            with self.subTest(estado=estado):
                partida = Partidabingo(estadopartida=estado)
                self.assertFalse(puede_asignar_cartones(partida))

    def test_se_genera_carton_para_partida_programada(self):
        carton = self._crear_carton_sin_base_de_datos(
            ESTADO_PARTIDA_PROGRAMADA
        )

        self.assertEqual(carton.estadocarton, "Vendido")
        self.assertEqual(carton.indicevictoria, 0)
        self.assertEqual(len(deserializar_matriz_carton_bingo(carton.matriznumeros)), 5)

    def test_se_genera_carton_para_partida_en_espera(self):
        carton = self._crear_carton_sin_base_de_datos(
            ESTADO_PARTIDA_EN_ESPERA
        )

        self.assertEqual(carton.idpartida.estadopartida, ESTADO_PARTIDA_EN_ESPERA)
        self.assertEqual(carton.preciopagado, Decimal("5.00"))

    def test_codigo_del_carton_se_genera_de_forma_unica(self):
        codigos_existentes = set()
        tokens = iter(("A" * 32, "B" * 32))

        primero = generar_codigo_carton(
            12,
            existe_codigo=codigos_existentes.__contains__,
            generador_token=lambda: next(tokens),
        )
        codigos_existentes.add(primero)
        segundo = generar_codigo_carton(
            12,
            existe_codigo=codigos_existentes.__contains__,
            generador_token=lambda: next(tokens),
        )

        self.assertNotEqual(primero, segundo)
        self.assertEqual(len({primero, segundo}), 2)
        self.assertTrue(primero.startswith("P12-C-"))

    def test_no_se_crea_carton_si_falla_validacion_del_precio(self):
        partida = Partidabingo(
            idpartidabingo=1,
            estadopartida=ESTADO_PARTIDA_PROGRAMADA,
        )

        with (
            patch("apps.bingos.services.transaction.atomic") as atomic_mock,
            patch.object(Carton, "save") as save_mock,
        ):
            with self.assertRaises(CartonAsignacionError):
                crear_y_asignar_carton(partida, Jugador(idjugador=1), "0")

        atomic_mock.assert_not_called()
        save_mock.assert_not_called()


class GenerarAsignarCartonFormTests(SimpleTestCase):
    def test_formulario_solo_expone_jugador_y_precio(self):
        form = GenerarAsignarCartonForm()

        self.assertEqual(list(form.fields), ["idjugador", "preciopagado"])

    def test_jugador_y_precio_mayor_que_cero_son_obligatorios(self):
        form = GenerarAsignarCartonForm(
            data={"idjugador": "", "preciopagado": "0"}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("idjugador", form.errors)
        self.assertIn("preciopagado", form.errors)


class FlujoAsignacionCartonTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, method="get", data=None):
        request_method = getattr(self.factory, method)
        request = request_method("/partidas/1/cartones/nuevo/", data or {})
        request.user = User(username="admin", is_staff=True)
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _partida(self, estado):
        bingo = Bingo(
            idbingo=2,
            titulobingo="Bingo de prueba",
            preciocarton=Decimal("5.00"),
        )
        return Partidabingo(
            idpartidabingo=1,
            idbingo=bingo,
            estadopartida=estado,
            nombreronda="Ronda 1",
        )

    def test_ingreso_en_estado_bloqueado_muestra_mensaje_y_redirige(self):
        request = self._request()
        partida = self._partida(ESTADO_PARTIDA_EN_CURSO)

        with (
            patch("apps.bingos.views.get_object_or_404", return_value=partida),
            patch("apps.bingos.views.crear_y_asignar_carton") as crear_mock,
        ):
            response = partida_carton_nuevo(request, partida.idpartidabingo)

        self.assertEqual(response.status_code, 302)
        crear_mock.assert_not_called()
        self.assertTrue(
            any(
                "Solo se permite en Programada o En espera" in message.message
                for message in get_messages(request)
            )
        )

    def test_post_invalido_no_invoca_creacion_del_carton(self):
        request = self._request(
            method="post",
            data={"idjugador": "", "preciopagado": "0"},
        )
        partida = self._partida(ESTADO_PARTIDA_PROGRAMADA)

        with (
            patch("apps.bingos.views.get_object_or_404", return_value=partida),
            patch("apps.bingos.views.crear_y_asignar_carton") as crear_mock,
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse(status=200),
            ),
        ):
            response = partida_carton_nuevo(request, partida.idpartidabingo)

        self.assertEqual(response.status_code, 200)
        crear_mock.assert_not_called()


class FormatoBolasBingoTests(SimpleTestCase):
    def test_letra_bingo_1_es_b(self):
        self.assertEqual(letra_bingo(1), "B")

    def test_letra_bingo_15_es_b(self):
        self.assertEqual(letra_bingo(15), "B")

    def test_letra_bingo_16_es_i(self):
        self.assertEqual(letra_bingo(16), "I")

    def test_letra_bingo_30_es_i(self):
        self.assertEqual(letra_bingo(30), "I")

    def test_letra_bingo_31_es_n(self):
        self.assertEqual(letra_bingo(31), "N")

    def test_letra_bingo_45_es_n(self):
        self.assertEqual(letra_bingo(45), "N")

    def test_letra_bingo_46_es_g(self):
        self.assertEqual(letra_bingo(46), "G")

    def test_letra_bingo_60_es_g(self):
        self.assertEqual(letra_bingo(60), "G")

    def test_letra_bingo_61_es_o(self):
        self.assertEqual(letra_bingo(61), "O")

    def test_letra_bingo_75_es_o(self):
        self.assertEqual(letra_bingo(75), "O")

    def test_numeros_fuera_del_rango_producen_error_controlado(self):
        for numero in (0, 76, -1, "doce", None):
            with self.subTest(numero=numero):
                with self.assertRaises(BolaBingoError):
                    letra_bingo(numero)

    def test_formato_de_bola_incluye_letra_y_numero(self):
        self.assertEqual(formatear_bola_bingo(39), "N-39")

    def test_parser_admite_vacios_json_y_texto_separado(self):
        self.assertEqual(parsear_bolas_cantadas(None), [])
        self.assertEqual(parsear_bolas_cantadas(""), [])
        self.assertEqual(parsear_bolas_cantadas("[]"), [])
        self.assertEqual(
            parsear_bolas_cantadas("12, I-24; N-39"),
            [12, 24, 39],
        )

    def test_parser_admite_json_antiguo_con_objetos_y_elimina_duplicados(self):
        valor = '[{"numero":12,"codigo":"B-12"},{"codigo":"I-24"},12]'

        self.assertEqual(parsear_bolas_cantadas(valor), [12, 24])

    def test_serializacion_estable_es_json_compacto_de_enteros(self):
        self.assertEqual(
            serializar_bolas_cantadas([12, "I-24", {"numero": 39}]),
            "[12,24,39]",
        )


class ExtraccionBolasTests(SimpleTestCase):
    def _partida(self, estado=ESTADO_PARTIDA_EN_CURSO, historial="[]"):
        partida = Partidabingo(
            idpartidabingo=8,
            estadopartida=estado,
            bolascantadas=historial,
            ultimabola=0,
        )
        partida.save = Mock()
        return partida

    def _extraer_sin_base(self, historial="[]", bola=12):
        partida = self._partida(historial=historial)
        generador = Mock()
        generador.choice.return_value = bola
        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic_mock,
            patch(
                "apps.bingos.services.Partidabingo.objects.select_for_update"
            ) as select_for_update,
        ):
            select_for_update.return_value.get.return_value = partida
            nueva_bola = extraer_siguiente_bola(
                partida,
                generador_aleatorio=generador,
            )
        return partida, nueva_bola, generador, atomic_mock, select_for_update

    def test_una_bola_extraida_no_vuelve_a_salir(self):
        partida, nueva_bola, generador, _atomic, _select = self._extraer_sin_base(
            historial="[12,24]",
            bola=13,
        )

        disponibles_entregadas = generador.choice.call_args.args[0]
        self.assertNotIn(12, disponibles_entregadas)
        self.assertNotIn(24, disponibles_entregadas)
        self.assertEqual(nueva_bola, 13)
        self.assertEqual(parsear_bolas_cantadas(partida.bolascantadas), [12, 24, 13])

    def test_bolas_disponibles_disminuyen_correctamente(self):
        antes = obtener_bolas_disponibles([1, 2])
        despues = obtener_bolas_disponibles([1, 2, 3])

        self.assertEqual(len(antes), 73)
        self.assertEqual(len(despues), 72)
        self.assertNotIn(3, despues)

    def test_al_llegar_a_75_bolas_no_se_extrae_otra(self):
        historial = serializar_bolas_cantadas(range(1, 76))
        partida = self._partida(historial=historial)
        generador = Mock()

        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "apps.bingos.services.Partidabingo.objects.select_for_update"
            ) as select_for_update,
        ):
            select_for_update.return_value.get.return_value = partida
            with self.assertRaises(BolilleroAgotadoError):
                extraer_siguiente_bola(partida, generador_aleatorio=generador)

        self.assertEqual(partida.bolascantadas, historial)
        partida.save.assert_not_called()
        generador.choice.assert_not_called()

    def test_no_se_puede_sacar_bola_en_programada(self):
        partida = self._partida(estado=ESTADO_PARTIDA_PROGRAMADA)

        with patch("apps.bingos.services.transaction.atomic") as atomic_mock:
            with self.assertRaises(BolaBingoError):
                extraer_siguiente_bola(partida)

        atomic_mock.assert_not_called()
        partida.save.assert_not_called()

    def test_no_se_puede_sacar_bola_en_pausada(self):
        partida = self._partida(estado=ESTADO_PARTIDA_PAUSADA)

        with self.assertRaises(BolaBingoError):
            extraer_siguiente_bola(partida)

        partida.save.assert_not_called()

    def test_no_se_puede_sacar_bola_en_finalizada(self):
        partida = self._partida(estado=ESTADO_PARTIDA_FINALIZADA)

        with self.assertRaises(BolaBingoError):
            extraer_siguiente_bola(partida)

        partida.save.assert_not_called()

    def test_en_espera_desempate_y_cancelada_tambien_bloquean_extraccion(self):
        for estado in (
            ESTADO_PARTIDA_EN_ESPERA,
            ESTADO_PARTIDA_DESEMPATE,
            ESTADO_PARTIDA_CANCELADA,
        ):
            with self.subTest(estado=estado):
                partida = self._partida(estado=estado)
                with self.assertRaises(BolaBingoError):
                    extraer_siguiente_bola(partida)
                partida.save.assert_not_called()

    def test_si_se_puede_sacar_bola_en_curso(self):
        partida, nueva_bola, _generador, _atomic, _select = self._extraer_sin_base(
            bola=55
        )

        self.assertEqual(nueva_bola, 55)
        partida.save.assert_called_once_with(
            update_fields=["bolascantadas", "ultimabola"]
        )

    def test_extraccion_actualiza_ultima_bola(self):
        partida, _nueva_bola, _generador, _atomic, _select = self._extraer_sin_base(
            bola=73
        )

        self.assertEqual(partida.ultimabola, 73)

    def test_extraccion_conserva_historial_previo(self):
        partida, _nueva_bola, _generador, _atomic, _select = self._extraer_sin_base(
            historial="1, I-16, 31",
            bola=46,
        )

        self.assertEqual(partida.bolascantadas, "[1,16,31,46]")

    def test_extraccion_usa_transaccion_y_select_for_update(self):
        _partida, _bola, _generador, atomic_mock, select_for_update = (
            self._extraer_sin_base(bola=7)
        )

        atomic_mock.assert_called_once_with()
        select_for_update.assert_called_once_with()
        select_for_update.return_value.get.assert_called_once_with(pk=8)


class RutaExtraccionBolaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_ruta_post_rechaza_usuario_no_administrativo(self):
        request = self.factory.post("/partidas/1/sacar-bola/")
        request.user = User(username="jugador", is_staff=False, is_superuser=False)

        with patch("apps.bingos.views.extraer_siguiente_bola") as extraer_mock:
            with self.assertRaises(PermissionDenied):
                sacar_bola(request, 1)

        extraer_mock.assert_not_called()

    def test_ruta_get_no_ejecuta_extraccion(self):
        request = self.factory.get("/partidas/1/sacar-bola/")
        request.user = User(username="admin", is_staff=True)

        with patch("apps.bingos.views.extraer_siguiente_bola") as extraer_mock:
            response = sacar_bola(request, 1)

        self.assertEqual(response.status_code, 405)
        extraer_mock.assert_not_called()

    def test_ruta_post_extrae_y_redirige_a_consola(self):
        request = self.factory.post("/partidas/1/sacar-bola/")
        request.user = User(username="admin", is_staff=True)
        request.session = {}
        request._messages = FallbackStorage(request)
        partida = Partidabingo(
            idpartidabingo=1,
            estadopartida=ESTADO_PARTIDA_EN_CURSO,
        )

        with (
            patch("apps.bingos.views.get_object_or_404", return_value=partida),
            patch("apps.bingos.views.extraer_siguiente_bola", return_value=12),
        ):
            response = sacar_bola(request, 1)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/partidas/1/consola/", response["Location"])
        self.assertIn(
            "Bola B-12 extraída correctamente.",
            [message.message for message in get_messages(request)],
        )


class EstadoPartidaTests(SimpleTestCase):
    def test_en_juego_se_normaliza_a_en_curso(self):
        self.assertEqual(normalizar_estado_partida("En Juego"), ESTADO_PARTIDA_EN_CURSO)
        self.assertEqual(estado_partida_mostrar("En Juego"), ESTADO_PARTIDA_EN_CURSO)

    def test_verificando_se_normaliza_a_en_espera(self):
        self.assertEqual(normalizar_estado_partida("Verificando"), ESTADO_PARTIDA_EN_ESPERA)
        self.assertEqual(estado_partida_mostrar("Verificando"), ESTADO_PARTIDA_EN_ESPERA)

    def test_iniciar_partida_programada_cambia_a_en_curso(self):
        partida = Partidabingo(estadopartida=ESTADO_PARTIDA_PROGRAMADA)

        update_fields = aplicar_accion_consola(partida, "iniciar")

        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_EN_CURSO)
        self.assertEqual(update_fields, ["estadopartida"])

    def test_pausar_partida_programada_no_es_valido(self):
        partida = Partidabingo(estadopartida=ESTADO_PARTIDA_PROGRAMADA)

        with self.assertRaises(EstadoPartidaError):
            aplicar_accion_consola(partida, "pausar")

    def test_finalizar_partida_en_curso_asigna_hora_fin(self):
        now = timezone.now()
        partida = Partidabingo(estadopartida=ESTADO_PARTIDA_EN_CURSO)

        update_fields = aplicar_accion_consola(partida, "finalizar", now=now)

        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_FINALIZADA)
        self.assertEqual(partida.horafin, now)
        self.assertEqual(update_fields, ["estadopartida", "horafin"])

    def test_reanudar_partida_pausada_cambia_a_en_curso(self):
        partida = Partidabingo(estadopartida=ESTADO_PARTIDA_PAUSADA)

        aplicar_accion_consola(partida, "reanudar")

        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_EN_CURSO)

    def test_en_juego_puede_pasar_a_pausada(self):
        partida = Partidabingo(estadopartida="En Juego")

        aplicar_accion_consola(partida, "pausar")

        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_PAUSADA)

    def test_transicion_invalida_no_modifica_estado(self):
        partida = Partidabingo(estadopartida=ESTADO_PARTIDA_PROGRAMADA)

        with self.assertRaises(EstadoPartidaError):
            aplicar_accion_consola(partida, "reanudar")

        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_PROGRAMADA)

    def test_acciones_disponibles_por_estado(self):
        self.assertEqual(
            acciones_disponibles_consola(Partidabingo(estadopartida=ESTADO_PARTIDA_PROGRAMADA)),
            {"iniciar"},
        )
        self.assertEqual(
            acciones_disponibles_consola(Partidabingo(estadopartida=ESTADO_PARTIDA_EN_ESPERA)),
            {"iniciar"},
        )
        self.assertEqual(
            acciones_disponibles_consola(Partidabingo(estadopartida="En Juego")),
            {"pausar", "finalizar"},
        )
        self.assertEqual(
            acciones_disponibles_consola(Partidabingo(estadopartida=ESTADO_PARTIDA_PAUSADA)),
            {"reanudar", "finalizar"},
        )
        self.assertEqual(
            acciones_disponibles_consola(Partidabingo(estadopartida=ESTADO_PARTIDA_FINALIZADA)),
            set(),
        )
        self.assertEqual(
            acciones_disponibles_consola(Partidabingo(estadopartida=ESTADO_PARTIDA_CANCELADA)),
            set(),
        )


class PermisosBingoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_usuario_no_staff_no_accede_a_lista_de_partidas(self):
        request = self.factory.get("/partidas/")
        request.user = User(username="jugador", is_staff=False, is_superuser=False)

        with self.assertRaises(PermissionDenied):
            partidas_lista(request)

    def test_usuario_anonimo_es_redirigido_a_login(self):
        request = self.factory.get("/partidas/")
        request.user = AnonymousUser()

        response = partidas_lista(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])


class ConsolaOperadorTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request_with_messages(self, accion):
        request = self.factory.post("/partidas/1/consola/", {"accion": accion})
        request.user = User(username="admin", is_staff=True)
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_consola_muestra_exito_despues_de_pausar(self):
        request = self._request_with_messages("pausar")
        partida = Partidabingo(idpartidabingo=1, estadopartida="En Juego")
        partida.save = Mock()

        with (
            patch("apps.bingos.views._base_datos_permite_estado_partida", return_value=True),
            patch("apps.bingos.views.transaction.atomic", return_value=nullcontext()),
        ):
            resultado = _procesar_accion_consola(request, partida, "pausar")

        self.assertTrue(resultado)
        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_PAUSADA)
        partida.save.assert_called_once_with(update_fields=["estadopartida"])
        self.assertIn(
            "Pausar partida realizada correctamente.",
            [message.message for message in get_messages(request)],
        )

    def test_consola_muestra_exito_despues_de_reanudar(self):
        request = self._request_with_messages("reanudar")
        partida = Partidabingo(idpartidabingo=1, estadopartida=ESTADO_PARTIDA_PAUSADA)
        partida.save = Mock()

        with (
            patch("apps.bingos.views._base_datos_permite_estado_partida", return_value=True),
            patch("apps.bingos.views.transaction.atomic", return_value=nullcontext()),
        ):
            resultado = _procesar_accion_consola(request, partida, "reanudar")

        self.assertTrue(resultado)
        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_EN_CURSO)
        partida.save.assert_called_once_with(update_fields=["estadopartida"])
        self.assertIn(
            "Reanudar partida realizada correctamente.",
            [message.message for message in get_messages(request)],
        )

    def test_consola_bloquea_estado_si_check_no_esta_actualizada(self):
        request = self._request_with_messages("pausar")
        partida = Partidabingo(idpartidabingo=1, estadopartida="En Juego")
        partida.save = Mock()

        with patch("apps.bingos.views._base_datos_permite_estado_partida", return_value=False):
            resultado = _procesar_accion_consola(request, partida, "pausar")

        self.assertFalse(resultado)
        self.assertEqual(partida.estadopartida, "En Juego")
        partida.save.assert_not_called()
        self.assertTrue(
            any(
                "Esta acción requiere actualizar la restricción de estados en PostgreSQL."
                in message.message
                for message in get_messages(request)
            )
        )
