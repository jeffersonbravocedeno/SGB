import asyncio
import json
from contextlib import nullcontext
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock, call, patch

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from openpyxl import load_workbook
from django import forms
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse
from django.utils import timezone

from apps.jugadores.models import Jugador

from .forms import (
    AccesoCartonPublicoForm,
    GenerarAsignarCartonForm,
    GenerarCartonBingoForm,
    PartidaBingoForm,
)
from .models import Bingo, Carton, CartonPartidaBingo, Partidabingo
from .consumers import PartidaPublicaConsumer
from .realtime import (
    construir_payload_publico_partida,
    nombre_grupo_partida,
    programar_publicacion_partida,
)
from .reportes import (
    PDF_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    construir_datos_reporte_partida,
    generar_excel_cartones_partida,
    generar_excel_resumen_bingo,
    generar_pdf_reporte_partida,
)
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
    CartonNoCompletoError,
    CartonAsignacionError,
    CartonPublicoError,
    DatosDesempateInvalidosError,
    DesempateError,
    DesempateIncompletoError,
    EstadoPartidaError,
    MatrizCartonInvalidaError,
    ValidacionCartonError,
    acciones_disponibles_consola,
    aplicar_accion_consola,
    carton_tiene_bingo_completo,
    contar_numeros_marcados_carton,
    confirmar_y_finalizar_desempate,
    confirmar_y_finalizar_desempate_participaciones,
    construir_candidato_desempate_participacion,
    crear_carton_maestro_para_bingo,
    crear_y_asignar_carton,
    deserializar_matriz_carton_bingo,
    estado_partida_mostrar,
    evaluar_carton_en_partida,
    evaluar_participacion_en_partida,
    extraer_siguiente_bola,
    formatear_bola_bingo,
    generar_codigo_carton,
    generar_codigo_carton_bingo,
    generar_matriz_carton_bingo,
    letra_bingo,
    normalizar_estado_partida,
    normalizar_candidatos_desempate,
    normalizar_candidatos_desempate_participaciones,
    obtener_participaciones_hibridas_partida,
    obtener_participacion_carton_en_partida,
    obtener_balotas_disponibles_desempate,
    obtener_numeros_carton,
    obtener_numeros_faltantes_carton,
    obtener_resultado_desempate,
    obtener_tiros_desempate,
    obtener_bolas_disponibles,
    parsear_bolas_cantadas,
    parsear_candidatos_desempate,
    preparar_cartones_para_validacion,
    preparar_datos_carton_jugador,
    preparar_datos_desempate,
    preparar_datos_tablero_publico,
    preparar_participaciones_hibridas_para_consola,
    preparar_resumen_partida_publica,
    puede_asignar_cartones,
    serializar_bolas_cantadas,
    serializar_candidatos_desempate,
    serializar_matriz_carton_bingo,
    sortear_balota_desempate,
    validar_carton_ganador,
    validar_participacion_ganadora,
    validar_venta_carton_para_bingo,
)
from .views import (
    _procesar_accion_consola,
    acceder_carton_publico,
    bingo_carton_nuevo,
    carton_publico,
    consola_operador,
    confirmar_desempate,
    desempate_operador,
    bingo_resumen_excel,
    partida_cartones_excel,
    partida_carton_nuevo,
    partida_reporte_pdf,
    partidas_lista,
    sacar_bola,
    sala_juego_publica,
    sortear_desempate,
    tablero_publico,
    validar_carton,
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


def matriz_carton_prueba():
    return [
        [1, 16, 31, 46, 61],
        [2, 17, 32, 47, 62],
        [3, 18, CASILLA_LIBRE, 48, 63],
        [4, 19, 33, 49, 64],
        [5, 20, 34, 50, 65],
    ]


def candidatos_desempate_prueba(tiro_uno=None, tiro_dos=None):
    return [
        {
            "idjugador": 41,
            "jugador": "juan123",
            "cartones": [
                {"idcarton": 31, "codigocarton": "P20-C-31"},
            ],
            "tiro_desempate": tiro_uno,
        },
        {
            "idjugador": 42,
            "jugador": "maria456",
            "cartones": [
                {"idcarton": 32, "codigocarton": "P20-C-32"},
            ],
            "tiro_desempate": tiro_dos,
        },
    ]


def partida_publica_prueba(
    estado=ESTADO_PARTIDA_EN_CURSO,
    bolas=None,
    ultima=None,
    ganador=None,
    pk=20,
):
    bolas = [] if bolas is None else list(bolas)
    bingo = Bingo(
        idbingo=7,
        titulobingo="Bingo público",
        premiomayor=Decimal("500.00"),
    )
    return Partidabingo(
        idpartidabingo=pk,
        idbingo=bingo,
        idjugadorganador=ganador,
        nombreronda="Ronda pública",
        valorefectivo=Decimal("100.00"),
        premiomaterial="Canasta",
        estadopartida=estado,
        bolascantadas=serializar_bolas_cantadas(bolas),
        ultimabola=ultima if ultima is not None else (bolas[-1] if bolas else 0),
        haydesempate=False,
    )


def carton_publico_prueba(partida=None, codigo="PUBLICO-001", jugador=None):
    partida = partida or partida_publica_prueba()
    jugador = jugador or Jugador(idjugador=41, aliasjugador="jugador_publico")
    return Carton(
        idcarton=31,
        idjugador=jugador,
        idpartida=partida,
        codigocarton=codigo,
        matriznumeros=serializar_matriz_carton_bingo(matriz_carton_prueba()),
        estadocarton="Vendido",
        preciopagado=Decimal("9876.54"),
    )


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


class CartonMaestroBingoTests(SimpleTestCase):
    def setUp(self):
        self.bingo = Bingo(idbingo=7, titulobingo="Bingo híbrido")
        self.jugador = Jugador(idjugador=4)
        self.fecha_compra = timezone.now()
        self.partidas = [
            Partidabingo(
                idpartidabingo=21,
                idbingo=self.bingo,
                nombreronda="Ronda 1",
                estadopartida=ESTADO_PARTIDA_PROGRAMADA,
            ),
            Partidabingo(
                idpartidabingo=22,
                idbingo=self.bingo,
                nombreronda="Ronda 2",
                estadopartida=ESTADO_PARTIDA_EN_ESPERA,
            ),
        ]

    def _crear_sin_base(self, partidas=None, error_participacion=None):
        partidas = self.partidas if partidas is None else partidas

        def asignar_pk(carton):
            carton.idcarton = 40
            return carton

        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic_mock,
            patch(
                "apps.bingos.services.Bingo.objects.select_for_update"
            ) as lock_bingo,
            patch(
                "apps.bingos.services.Partidabingo.objects.select_for_update"
            ) as lock_partidas,
            patch(
                "apps.bingos.services.assign_next_integer_pk",
                side_effect=asignar_pk,
            ) as assign_pk_mock,
            patch(
                "apps.bingos.services.generar_codigo_carton_bingo",
                return_value="B7-C-ABC1234567",
            ) as codigo_mock,
            patch(
                "apps.bingos.services.generar_matriz_carton_bingo",
                return_value=matriz_carton_prueba(),
            ) as matriz_mock,
            patch.object(Carton, "full_clean") as full_clean_mock,
            patch.object(Carton, "save") as save_mock,
            patch(
                "apps.bingos.services.CartonPartidaBingo.objects.create",
                side_effect=error_participacion,
            ) as crear_participacion_mock,
        ):
            lock_bingo.return_value.get.return_value = self.bingo
            consulta = lock_partidas.return_value.filter.return_value
            consulta.order_by.return_value = partidas
            carton = crear_carton_maestro_para_bingo(
                bingo=self.bingo,
                jugador=self.jugador,
                precio_pagado=Decimal("5.00"),
                fecha_compra=self.fecha_compra,
            )

        return {
            "carton": carton,
            "atomic": atomic_mock,
            "lock_bingo": lock_bingo,
            "lock_partidas": lock_partidas,
            "assign_pk": assign_pk_mock,
            "codigo": codigo_mock,
            "matriz": matriz_mock,
            "full_clean": full_clean_mock,
            "save": save_mock,
            "crear_participacion": crear_participacion_mock,
        }

    def test_crea_un_maestro_y_una_participacion_por_partida(self):
        resultado = self._crear_sin_base()
        carton = resultado["carton"]

        self.assertEqual(carton.idbingo, self.bingo)
        self.assertIsNone(carton.idpartida)
        self.assertIsNone(carton.indicevictoria)
        self.assertEqual(carton.idjugador, self.jugador)
        self.assertEqual(carton.codigocarton, "B7-C-ABC1234567")
        self.assertEqual(carton.preciopagado, Decimal("5.00"))
        self.assertEqual(carton.fechacompra, self.fecha_compra)
        self.assertEqual(carton.estadocarton, "Vendido")
        self.assertEqual(
            deserializar_matriz_carton_bingo(carton.matriznumeros),
            matriz_carton_prueba(),
        )
        resultado["atomic"].assert_called_once_with()
        resultado["lock_bingo"].return_value.get.assert_called_once_with(pk=7)
        resultado["lock_partidas"].return_value.filter.assert_called_once_with(
            idbingo=self.bingo
        )
        resultado["lock_partidas"].return_value.filter.return_value.order_by.assert_called_once_with(
            "idpartidabingo"
        )
        resultado["assign_pk"].assert_called_once_with(carton)
        resultado["codigo"].assert_called_once_with(7)
        resultado["matriz"].assert_called_once_with()
        resultado["full_clean"].assert_called_once_with(
            validate_unique=False,
            validate_constraints=False,
        )
        resultado["save"].assert_called_once_with(force_insert=True)
        self.assertEqual(resultado["crear_participacion"].call_count, 2)

        partidas_creadas = []
        for llamada in resultado["crear_participacion"].call_args_list:
            valores = llamada.kwargs
            partidas_creadas.append(valores["idpartida"])
            self.assertEqual(valores["idcarton"], carton)
            self.assertEqual(valores["idbingo"], self.bingo)
            self.assertEqual(
                valores["estado_participacion"],
                CartonPartidaBingo.ESTADO_PENDIENTE,
            )
            self.assertIsNone(valores["indicevictoria"])
            self.assertFalse(valores["es_asignacion_original"])
            self.assertEqual(
                valores["origen_asignacion"],
                CartonPartidaBingo.ORIGEN_APLICACION,
            )
            self.assertEqual(valores["fechacreacion"], self.fecha_compra)
            self.assertIsNone(valores["fechavalidacion"])
            self.assertNotIn("idcartonpartidabingo", valores)

        self.assertEqual(partidas_creadas, self.partidas)

    def test_codigo_nuevo_usa_prefijo_de_bingo(self):
        codigo = generar_codigo_carton_bingo(
            17,
            existe_codigo=lambda _codigo: False,
            generador_token=lambda: "abc-def-1234567890",
        )

        self.assertTrue(codigo.startswith("B17-C-"))
        self.assertLessEqual(len(codigo), 30)

    def test_rechaza_bingo_sin_partidas(self):
        with self.assertRaisesMessage(
            CartonAsignacionError,
            "el Bingo no tiene partidas",
        ):
            validar_venta_carton_para_bingo(self.bingo, [])

    def test_rechaza_si_una_partida_no_admite_venta(self):
        estados_bloqueados = (
            ESTADO_PARTIDA_EN_CURSO,
            ESTADO_PARTIDA_PAUSADA,
            ESTADO_PARTIDA_DESEMPATE,
            ESTADO_PARTIDA_FINALIZADA,
            ESTADO_PARTIDA_CANCELADA,
        )
        for estado in estados_bloqueados:
            with self.subTest(estado=estado):
                partida = Partidabingo(
                    idpartidabingo=30,
                    nombreronda="Bloqueada",
                    estadopartida=estado,
                )
                with self.assertRaisesMessage(
                    CartonAsignacionError,
                    "todas las partidas del Bingo deben estar Programada o En espera",
                ):
                    validar_venta_carton_para_bingo(
                        self.bingo,
                        [self.partidas[0], partida],
                    )

    def test_acepta_programada_y_en_espera(self):
        self.assertEqual(
            validar_venta_carton_para_bingo(self.bingo, self.partidas),
            self.partidas,
        )

    def test_error_de_participacion_se_propaga_para_rollback_atomico(self):
        with self.assertRaisesMessage(RuntimeError, "fallo de participacion"):
            self._crear_sin_base(
                error_participacion=RuntimeError("fallo de participacion")
            )


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


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class VentaCartonBingoInterfazTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.usuario_admin = User(username="admin", is_staff=True)
        self.jugador = Jugador(idjugador=4, aliasjugador="jugador4")
        self.bingo = Bingo(
            idbingo=7,
            titulobingo="Bingo híbrido administrativo",
            preciocarton=Decimal("5.00"),
        )

    def _request(self, method="get", data=None, usuario=None, path=None):
        path = path or reverse(
            "bingos:bingo_carton_nuevo",
            kwargs={"idbingo": self.bingo.pk},
        )
        request = getattr(self.factory, method)(path, data or {})
        request.user = usuario or self.usuario_admin
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _form_valido(self, data=None):
        class FormPrueba(forms.Form):
            idjugador = forms.IntegerField()
            preciopagado = forms.DecimalField()

        form = FormPrueba(
            data=data
            or {"idjugador": self.jugador.pk, "preciopagado": "5.00"}
        )
        form.is_valid()
        form.cleaned_data = {
            "idjugador": self.jugador,
            "preciopagado": Decimal("5.00"),
        }
        form.is_valid = Mock(return_value=True)
        return form

    def test_formulario_hibrido_solo_expone_jugador_y_precio(self):
        form = GenerarCartonBingoForm()

        self.assertEqual(list(form.fields), ["idjugador", "preciopagado"])
        for campo_historico in (
            "idpartida",
            "indicevictoria",
            "codigocarton",
            "matriznumeros",
            "estadocarton",
            "idbingo",
        ):
            self.assertNotIn(campo_historico, form.fields)

    def test_formulario_rechaza_precio_cero_y_negativo(self):
        for precio in ("0", "-1"):
            with self.subTest(precio=precio):
                form = GenerarCartonBingoForm(
                    data={"idjugador": "", "preciopagado": precio}
                )
                self.assertFalse(form.is_valid())
                self.assertIn("preciopagado", form.errors)
                self.assertIn(
                    "mayor que cero",
                    " ".join(form.errors["preciopagado"]),
                )

    def test_ruta_nueva_exige_login_y_permiso_administrativo(self):
        request_anonimo = self._request(usuario=AnonymousUser())
        response = bingo_carton_nuevo(request_anonimo, self.bingo.pk)

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

        request_no_admin = self._request(
            usuario=User(username="jugador", is_staff=False)
        )
        with self.assertRaises(PermissionDenied):
            bingo_carton_nuevo(request_no_admin, self.bingo.pk)

    def test_get_muestra_formulario_y_nombre_del_bingo(self):
        request = self._request()
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                return_value=self.bingo,
            ),
            patch(
                "apps.bingos.views.Partidabingo.objects.filter"
            ) as partidas_filter,
            patch(
                "apps.bingos.forms.Jugador.objects.order_by",
                return_value=Jugador.objects.none(),
            ),
        ):
            partidas_filter.return_value.count.return_value = 3
            response = bingo_carton_nuevo(request, self.bingo.pk)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vender cartón para todo el Bingo")
        self.assertContains(response, self.bingo.titulobingo)
        self.assertContains(response, "3 partidas actuales")

    def test_post_valido_llama_servicio_redirige_y_muestra_resumen(self):
        request = self._request(
            method="post",
            data={"idjugador": "4", "preciopagado": "5.00"},
        )
        form = self._form_valido(request.POST)
        carton = Carton(
            idcarton=40,
            idbingo=self.bingo,
            idjugador=self.jugador,
            codigocarton="B7-C-PRUEBA",
        )
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                return_value=self.bingo,
            ),
            patch(
                "apps.bingos.views.GenerarCartonBingoForm",
                return_value=form,
            ),
            patch(
                "apps.bingos.views.crear_carton_maestro_para_bingo",
                return_value=carton,
            ) as crear_mock,
            patch(
                "apps.bingos.views.CartonPartidaBingo.objects.filter"
            ) as participaciones_filter,
        ):
            participaciones_filter.return_value.count.return_value = 3
            response = bingo_carton_nuevo(request, self.bingo.pk)

        crear_mock.assert_called_once_with(
            bingo=self.bingo,
            jugador=self.jugador,
            precio_pagado=Decimal("5.00"),
            fecha_compra=None,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            reverse("bingos:detalle", kwargs={"idbingo": self.bingo.pk}),
        )
        mensajes = [mensaje.message for mensaje in get_messages(request)]
        self.assertTrue(
            any(
                "cartón maestro" in mensaje
                and "3 participaciones" in mensaje
                and "cada ronda" in mensaje
                for mensaje in mensajes
            )
        )

    def test_error_del_servicio_vuelve_al_formulario_sin_crear_directamente(self):
        request = self._request(
            method="post",
            data={"idjugador": "4", "preciopagado": "5.00"},
        )
        form = self._form_valido(request.POST)
        error = "Todas las partidas deben estar Programada o En espera."
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                return_value=self.bingo,
            ),
            patch(
                "apps.bingos.views.GenerarCartonBingoForm",
                return_value=form,
            ),
            patch(
                "apps.bingos.views.crear_carton_maestro_para_bingo",
                side_effect=CartonAsignacionError(error),
            ),
            patch(
                "apps.bingos.views.Partidabingo.objects.filter"
            ) as partidas_filter,
            patch(
                "apps.bingos.views.Carton.objects.create"
            ) as carton_create,
            patch(
                "apps.bingos.views.CartonPartidaBingo.objects.create"
            ) as participacion_create,
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse(status=200),
            ),
        ):
            partidas_filter.return_value.count.return_value = 3
            response = bingo_carton_nuevo(request, self.bingo.pk)

        self.assertEqual(response.status_code, 200)
        self.assertIn(error, form.non_field_errors())
        self.assertEqual(form.data["idjugador"], "4")
        self.assertEqual(form.data["preciopagado"], "5.00")
        carton_create.assert_not_called()
        participacion_create.assert_not_called()

    def test_ruta_heredada_sigue_resolviendo_y_no_usa_servicio_hibrido(self):
        partida = Partidabingo(
            idpartidabingo=21,
            idbingo=self.bingo,
            nombreronda="Ronda heredada",
            estadopartida=ESTADO_PARTIDA_PROGRAMADA,
        )
        url = reverse(
            "bingos:partida_carton_nuevo",
            kwargs={"idpartidabingo": partida.pk},
        )
        self.assertEqual(resolve(url).url_name, "partida_carton_nuevo")
        request = self._request(
            method="post",
            path=url,
            data={"idjugador": "4", "preciopagado": "5.00"},
        )
        form = self._form_valido(request.POST)
        carton = Carton(
            idcarton=41,
            idbingo=self.bingo,
            idpartida=partida,
            idjugador=self.jugador,
            codigocarton="P21-C-PRUEBA",
        )
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                return_value=partida,
            ),
            patch(
                "apps.bingos.views.GenerarAsignarCartonForm",
                return_value=form,
            ),
            patch(
                "apps.bingos.views.crear_y_asignar_carton",
                return_value=carton,
            ) as legado_mock,
            patch(
                "apps.bingos.views.crear_carton_maestro_para_bingo"
            ) as hibrido_mock,
        ):
            response = partida_carton_nuevo(request, partida.pk)

        self.assertEqual(response.status_code, 302)
        legado_mock.assert_called_once()
        hibrido_mock.assert_not_called()

    def test_detalle_administrativo_enlaza_venta_por_bingo(self):
        request = self._request()
        html = render_to_string(
            "bingos/detalle.html",
            {"bingo": self.bingo, "partidas": [], "cartones": []},
            request=request,
        )
        url = reverse(
            "bingos:bingo_carton_nuevo",
            kwargs={"idbingo": self.bingo.pk},
        )

        self.assertIn("Vender cartón para todo el Bingo", html)
        self.assertIn(url, html)
        self.assertIn("se cobra", html)


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
            patch("apps.bingos.views.programar_publicacion_partida") as publicar_mock,
        ):
            response = sacar_bola(request, 1)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/partidas/1/consola/", response["Location"])
        self.assertIn(
            "Bola B-12 extraída correctamente.",
            [message.message for message in get_messages(request)],
        )
        publicar_mock.assert_called_once_with(partida, "bola_extraida")


class ReglaGanadorCartonTests(SimpleTestCase):
    def setUp(self):
        self.matriz = matriz_carton_prueba()
        self.numeros = obtener_numeros_carton(self.matriz)

    def test_matriz_valida_5x5_con_libre_se_interpreta_correctamente(self):
        serializada = serializar_matriz_carton_bingo(self.matriz)

        self.assertEqual(deserializar_matriz_carton_bingo(serializada), self.matriz)
        self.assertEqual(obtener_numeros_carton(serializada), self.numeros)
        self.assertEqual(len(self.numeros), 24)

    def test_carton_con_todos_los_numeros_llamados_es_ganador(self):
        self.assertTrue(
            carton_tiene_bingo_completo(self.matriz, self.numeros)
        )

    def test_carton_con_un_numero_pendiente_no_es_ganador(self):
        bolas = self.numeros[:-1]

        self.assertFalse(carton_tiene_bingo_completo(self.matriz, bolas))
        self.assertEqual(
            obtener_numeros_faltantes_carton(self.matriz, bolas),
            [self.numeros[-1]],
        )

    def test_casilla_libre_no_cuenta_como_numero_pendiente(self):
        faltantes = obtener_numeros_faltantes_carton(
            self.matriz,
            self.numeros,
        )

        self.assertEqual(faltantes, [])
        self.assertNotIn(CASILLA_LIBRE, obtener_numeros_carton(self.matriz))

    def test_matriz_danada_no_puede_ganar(self):
        matriz_danada = "[[1,2,3],[4,5,6]]"

        self.assertFalse(carton_tiene_bingo_completo(matriz_danada, range(1, 76)))
        with self.assertRaises(MatrizCartonInvalidaError):
            obtener_numeros_carton(matriz_danada)


class ValidacionGanadorTests(SimpleTestCase):
    def _partida(self, estado=ESTADO_PARTIDA_EN_CURSO, bolas=None, pk=20):
        return Partidabingo(
            idpartidabingo=pk,
            estadopartida=estado,
            bolascantadas=serializar_bolas_cantadas(bolas or []),
            ultimabola=(bolas or [0])[-1],
            idjugadorganador=None,
            haydesempate=False,
            idbingadores=None,
        )

    def _carton(self, partida, pk=30, jugador_pk=40, matriz=None):
        jugador = Jugador(
            idjugador=jugador_pk,
            aliasjugador=f"Jugador {jugador_pk}",
        )
        carton = Carton(
            idcarton=pk,
            idpartida=partida,
            idjugador=jugador,
            codigocarton=f"P{partida.pk}-C-{pk}",
            matriznumeros=serializar_matriz_carton_bingo(
                matriz or matriz_carton_prueba()
            ),
            estadocarton="Vendido",
        )
        carton.save = Mock()
        return carton

    def _validar_sin_base(self, partida, carton, cartones, save_error=None):
        partida_bloqueada = Partidabingo(
            idpartidabingo=partida.pk,
            estadopartida=partida.estadopartida,
            bolascantadas=partida.bolascantadas,
            ultimabola=partida.ultimabola,
            idjugadorganador=partida.idjugadorganador,
            haydesempate=partida.haydesempate,
            idbingadores=partida.idbingadores,
        )
        partida_bloqueada.save = Mock(side_effect=save_error)

        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic_mock,
            patch(
                "apps.bingos.services.Partidabingo.objects.select_for_update"
            ) as lock_partida,
            patch(
                "apps.bingos.services.Carton.objects.select_for_update"
            ) as lock_cartones,
        ):
            lock_partida.return_value.get.return_value = partida_bloqueada
            consulta = lock_cartones.return_value.filter.return_value
            consulta.select_related.return_value.order_by.return_value = cartones
            resultado = validar_carton_ganador(partida, carton)

        return (
            resultado,
            partida_bloqueada,
            atomic_mock,
            lock_partida,
            lock_cartones,
        )

    def test_carton_no_puede_validarse_si_pertenece_a_otra_partida(self):
        partida = self._partida(pk=1)
        otra_partida = self._partida(pk=2)
        carton = self._carton(otra_partida)

        with patch("apps.bingos.services.transaction.atomic") as atomic_mock:
            with self.assertRaises(ValidacionCartonError):
                validar_carton_ganador(partida, carton)

        atomic_mock.assert_not_called()

    def test_no_se_puede_validar_en_programada(self):
        partida = self._partida(estado=ESTADO_PARTIDA_PROGRAMADA)
        carton = self._carton(partida)

        with self.assertRaises(ValidacionCartonError):
            validar_carton_ganador(partida, carton)

    def test_no_se_puede_validar_en_pausada(self):
        partida = self._partida(estado=ESTADO_PARTIDA_PAUSADA)
        carton = self._carton(partida)

        with self.assertRaises(ValidacionCartonError):
            validar_carton_ganador(partida, carton)

    def test_no_se_puede_validar_en_finalizada(self):
        partida = self._partida(estado=ESTADO_PARTIDA_FINALIZADA)
        carton = self._carton(partida)

        with self.assertRaises(ValidacionCartonError):
            validar_carton_ganador(partida, carton)

    def test_en_espera_desempate_y_cancelada_tambien_bloquean_validacion(self):
        for estado in (
            ESTADO_PARTIDA_EN_ESPERA,
            ESTADO_PARTIDA_DESEMPATE,
            ESTADO_PARTIDA_CANCELADA,
        ):
            with self.subTest(estado=estado):
                partida = self._partida(estado=estado)
                carton = self._carton(partida)
                with self.assertRaises(ValidacionCartonError):
                    validar_carton_ganador(partida, carton)

    def test_si_se_puede_validar_en_curso(self):
        numeros = obtener_numeros_carton(matriz_carton_prueba())
        partida = self._partida(bolas=numeros)
        carton = self._carton(partida)

        resultado, _bloqueada, _atomic, _lock_partida, _lock_cartones = (
            self._validar_sin_base(partida, carton, [carton])
        )

        self.assertEqual(resultado["resultado"], "ganador")

    def test_un_carton_ganador_registra_al_jugador(self):
        numeros = obtener_numeros_carton(matriz_carton_prueba())
        partida = self._partida(bolas=numeros)
        carton = self._carton(partida, jugador_pk=77)

        resultado, bloqueada, _atomic, _lock_partida, _lock_cartones = (
            self._validar_sin_base(partida, carton, [carton])
        )

        self.assertEqual(resultado["resultado"], "ganador")
        self.assertEqual(partida.idjugadorganador_id, 77)
        self.assertFalse(partida.haydesempate)
        registros = parsear_candidatos_desempate(partida.idbingadores)
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0]["idcarton"], carton.pk)
        self.assertEqual(registros[0]["idjugador"], 77)
        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_EN_CURSO)
        bloqueada.save.assert_called_once_with(
            update_fields=[
                "idjugadorganador",
                "haydesempate",
                "idbingadores",
            ]
        )

    def test_varios_cartones_ganadores_cambian_a_desempate(self):
        numeros = obtener_numeros_carton(matriz_carton_prueba())
        partida = self._partida(bolas=numeros)
        carton_uno = self._carton(partida, pk=31, jugador_pk=41)
        carton_dos = self._carton(partida, pk=32, jugador_pk=42)

        resultado, _bloqueada, _atomic, _lock_partida, _lock_cartones = (
            self._validar_sin_base(
                partida,
                carton_uno,
                [carton_uno, carton_dos],
            )
        )

        self.assertEqual(resultado["resultado"], "desempate")
        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_DESEMPATE)
        self.assertTrue(partida.haydesempate)
        candidatos = parsear_candidatos_desempate(partida.idbingadores)
        self.assertEqual(
            [candidato["idcarton"] for candidato in candidatos],
            [31, 32],
        )

    def test_varios_ganadores_no_eligen_un_ganador_arbitrario(self):
        numeros = obtener_numeros_carton(matriz_carton_prueba())
        partida = self._partida(bolas=numeros)
        carton_uno = self._carton(partida, pk=31, jugador_pk=41)
        carton_dos = self._carton(partida, pk=32, jugador_pk=42)

        self._validar_sin_base(
            partida,
            carton_uno,
            [carton_uno, carton_dos],
        )

        self.assertIsNone(partida.idjugadorganador)

    def test_carton_incompleto_no_modifica_partida(self):
        numeros = obtener_numeros_carton(matriz_carton_prueba())
        partida = self._partida(bolas=numeros[:-1])
        carton = self._carton(partida)

        with self.assertRaises(CartonNoCompletoError) as error:
            self._validar_sin_base(partida, carton, [carton])

        self.assertIn(formatear_bola_bingo(numeros[-1]), str(error.exception))
        self.assertIsNone(partida.idjugadorganador)
        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_EN_CURSO)

    def test_validacion_conserva_bolas_y_no_modifica_cartones(self):
        numeros = obtener_numeros_carton(matriz_carton_prueba())
        partida = self._partida(bolas=numeros)
        carton = self._carton(partida)
        bolas_antes = partida.bolascantadas
        matriz_antes = carton.matriznumeros

        self._validar_sin_base(partida, carton, [carton])

        self.assertEqual(partida.bolascantadas, bolas_antes)
        self.assertEqual(carton.matriznumeros, matriz_antes)
        carton.save.assert_not_called()

    def test_validacion_usa_transaccion_y_bloquea_partida_y_cartones(self):
        numeros = obtener_numeros_carton(matriz_carton_prueba())
        partida = self._partida(bolas=numeros)
        carton = self._carton(partida)

        _resultado, _bloqueada, atomic, lock_partida, lock_cartones = (
            self._validar_sin_base(partida, carton, [carton])
        )

        atomic.assert_called_once_with()
        lock_partida.assert_called_once_with()
        lock_partida.return_value.get.assert_called_once_with(pk=partida.pk)
        lock_cartones.assert_called_once_with(of=("self",))

    def test_error_al_guardar_no_sincroniza_cambios_parciales(self):
        numeros = obtener_numeros_carton(matriz_carton_prueba())
        partida = self._partida(bolas=numeros)
        carton = self._carton(partida)

        with self.assertRaises(DatabaseError):
            self._validar_sin_base(
                partida,
                carton,
                [carton],
                save_error=DatabaseError("fallo simulado"),
            )

        self.assertIsNone(partida.idjugadorganador)
        self.assertFalse(partida.haydesempate)
        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_EN_CURSO)

    def test_evaluar_carton_danado_genera_error_controlado_y_evidencia(self):
        partida = self._partida(bolas=range(1, 76))
        carton = self._carton(partida)
        carton.matriznumeros = "[[1,2,3],[4,5,6]]"

        with self.assertRaises(MatrizCartonInvalidaError):
            evaluar_carton_en_partida(carton, partida)
        with self.assertLogs("apps.bingos.services", level="WARNING"):
            preparar_cartones_para_validacion(partida, [carton])

    def test_consola_solo_prepara_cartones_vendidos_y_asignados(self):
        partida = self._partida()
        vendido = self._carton(partida, pk=31)
        disponible = self._carton(partida, pk=32)
        disponible.estadocarton = "Disponible"
        sin_jugador = self._carton(partida, pk=33)
        sin_jugador.idjugador = None

        resultado = preparar_cartones_para_validacion(
            partida,
            [vendido, disponible, sin_jugador],
        )

        self.assertEqual(
            [item["carton"].pk for item in resultado],
            [vendido.pk],
        )


class ParticipacionGanadoraHibridaTests(SimpleTestCase):
    def setUp(self):
        self.bingo = Bingo(idbingo=7, titulobingo="Bingo híbrido")
        self.jugador = Jugador(idjugador=4, aliasjugador="jugador4")
        self.matriz = matriz_carton_prueba()
        self.numeros = obtener_numeros_carton(self.matriz)

    def _partida(
        self,
        pk=21,
        bolas=None,
        estado=ESTADO_PARTIDA_EN_CURSO,
        bingo=None,
    ):
        bolas = self.numeros if bolas is None else list(bolas)
        return Partidabingo(
            idpartidabingo=pk,
            idbingo=bingo or self.bingo,
            nombreronda=f"Ronda {pk}",
            estadopartida=estado,
            bolascantadas=serializar_bolas_cantadas(bolas),
            ultimabola=bolas[-1] if bolas else 0,
            idjugadorganador=None,
            haydesempate=False,
            idbingadores=None,
        )

    def _carton(self, pk=40, jugador=None, bingo=None, matriz=None):
        carton = Carton(
            idcarton=pk,
            idbingo=bingo or self.bingo,
            idjugador=jugador or self.jugador,
            idpartida=None,
            indicevictoria=None,
            codigocarton=f"B7-C-{pk}",
            matriznumeros=serializar_matriz_carton_bingo(
                matriz or self.matriz
            ),
            estadocarton="Vendido",
        )
        carton.save = Mock()
        return carton

    def _participacion(
        self,
        carton,
        partida,
        pk=51,
        estado=CartonPartidaBingo.ESTADO_PENDIENTE,
        bingo=None,
    ):
        participacion = CartonPartidaBingo(
            idcartonpartidabingo=pk,
            idcarton=carton,
            idpartida=partida,
            idbingo=bingo or self.bingo,
            estado_participacion=estado,
            indicevictoria=None,
            es_asignacion_original=False,
            origen_asignacion=CartonPartidaBingo.ORIGEN_APLICACION,
            fechavalidacion=None,
        )
        participacion.save = Mock()
        return participacion

    def _partida_bloqueada(self, partida):
        bloqueada = Partidabingo(
            idpartidabingo=partida.pk,
            idbingo=partida.idbingo,
            nombreronda=partida.nombreronda,
            estadopartida=partida.estadopartida,
            bolascantadas=partida.bolascantadas,
            ultimabola=partida.ultimabola,
            idjugadorganador=partida.idjugadorganador,
            haydesempate=partida.haydesempate,
            idbingadores=partida.idbingadores,
        )
        bloqueada.save = Mock()
        return bloqueada

    def _validar_sin_base(
        self,
        partida,
        carton,
        participaciones,
        indice=24,
        now=None,
    ):
        bloqueada = self._partida_bloqueada(partida)
        cartones = {}
        for participacion in participaciones:
            participacion.idpartida = bloqueada
            cartones[participacion.idcarton_id] = participacion.idcarton
        cartones.setdefault(carton.pk, carton)
        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic_mock,
            patch(
                "apps.bingos.services._bloquear_contexto_participaciones",
                return_value=(bloqueada, participaciones, cartones),
            ) as bloquear_mock,
        ):
            resultado = validar_participacion_ganadora(
                partida,
                carton,
                indice,
                now=now,
            )
        return resultado, bloqueada, atomic_mock, bloquear_mock

    def test_resuelve_participacion_por_carton_y_partida(self):
        partida = self._partida()
        carton = self._carton()
        participacion = self._participacion(carton, partida)

        with (
            patch(
                "apps.bingos.services.Partidabingo.objects.get",
                return_value=partida,
            ) as partida_get,
            patch(
                "apps.bingos.services.Carton.objects.get",
                return_value=carton,
            ) as carton_get,
            patch(
                "apps.bingos.services.CartonPartidaBingo.objects.select_related"
            ) as seleccionar,
        ):
            seleccionar.return_value.get.return_value = participacion
            resultado = obtener_participacion_carton_en_partida(
                partida.pk,
                carton.pk,
            )

        self.assertEqual(resultado, participacion)
        partida_get.assert_called_once_with(pk=partida.pk)
        carton_get.assert_called_once_with(pk=carton.pk)
        seleccionar.return_value.get.assert_called_once_with(
            idcarton_id=carton.pk,
            idpartida_id=partida.pk,
        )

    def test_rechaza_pareja_sin_participacion(self):
        partida = self._partida()
        carton = self._carton()
        with (
            patch(
                "apps.bingos.services.Partidabingo.objects.get",
                return_value=partida,
            ),
            patch(
                "apps.bingos.services.Carton.objects.get",
                return_value=carton,
            ),
            patch(
                "apps.bingos.services.CartonPartidaBingo.objects.select_related"
            ) as seleccionar,
        ):
            seleccionar.return_value.get.side_effect = (
                CartonPartidaBingo.DoesNotExist
            )
            with self.assertRaisesMessage(
                ValidacionCartonError,
                "No existe una participación",
            ):
                obtener_participacion_carton_en_partida(partida, carton)

    def test_rechaza_participacion_de_otro_bingo(self):
        partida = self._partida()
        carton = self._carton()
        otro_bingo = Bingo(idbingo=8, titulobingo="Otro")
        participacion = self._participacion(
            carton,
            partida,
            bingo=otro_bingo,
        )

        with self.assertRaisesMessage(
            ValidacionCartonError,
            "participación pertenece a otro Bingo",
        ):
            evaluar_participacion_en_partida(participacion, partida)

    def test_evalua_solo_bolas_de_la_partida_exacta(self):
        carton = self._carton()
        primera = self._partida(pk=21, bolas=self.numeros)
        segunda = self._partida(pk=22, bolas=self.numeros[:-1])
        participacion_primera = self._participacion(carton, primera, pk=51)
        participacion_segunda = self._participacion(carton, segunda, pk=52)

        self.assertTrue(
            evaluar_participacion_en_partida(
                participacion_primera,
                primera,
            )["completo"]
        )
        resultado_segunda = evaluar_participacion_en_partida(
            participacion_segunda,
            segunda,
        )
        self.assertFalse(resultado_segunda["completo"])
        self.assertEqual(resultado_segunda["faltantes"], [self.numeros[-1]])

    def test_marca_solo_participacion_sin_cambiar_historicos_del_maestro(self):
        partida = self._partida()
        otra_partida = self._partida(pk=22)
        carton = self._carton()
        participacion = self._participacion(carton, partida, pk=51)
        otra_participacion = self._participacion(
            carton,
            otra_partida,
            pk=52,
        )
        fecha = timezone.now()

        resultado, bloqueada, atomic_mock, bloquear_mock = (
            self._validar_sin_base(
                partida,
                carton,
                [participacion],
                indice=24,
                now=fecha,
            )
        )

        self.assertEqual(resultado["resultado"], "ganador")
        self.assertEqual(
            participacion.estado_participacion,
            CartonPartidaBingo.ESTADO_GANADOR,
        )
        self.assertEqual(participacion.indicevictoria, 24)
        self.assertEqual(participacion.fechavalidacion, fecha)
        self.assertEqual(
            otra_participacion.estado_participacion,
            CartonPartidaBingo.ESTADO_PENDIENTE,
        )
        otra_participacion.save.assert_not_called()
        self.assertIsNone(carton.idpartida)
        self.assertIsNone(carton.indicevictoria)
        carton.save.assert_not_called()
        atomic_mock.assert_called_once_with()
        bloquear_mock.assert_called_once_with(
            partida.pk,
            carton_id_adicional=carton.pk,
        )
        participacion.save.assert_called_once_with(
            update_fields=[
                "estado_participacion",
                "indicevictoria",
                "fechavalidacion",
            ]
        )
        bloqueada.save.assert_called_once()

    def test_mismo_carton_gana_dos_rondas_sin_mezclar_resultados(self):
        primera = self._partida(pk=21)
        segunda = self._partida(pk=22)
        carton = self._carton()
        participacion_primera = self._participacion(carton, primera, pk=51)
        participacion_segunda = self._participacion(carton, segunda, pk=52)
        fecha_primera = timezone.now()
        fecha_segunda = fecha_primera + timedelta(seconds=1)

        self._validar_sin_base(
            primera,
            carton,
            [participacion_primera],
            indice=24,
            now=fecha_primera,
        )
        guardados_primera = participacion_primera.save.call_count
        self._validar_sin_base(
            segunda,
            carton,
            [participacion_segunda],
            indice=25,
            now=fecha_segunda,
        )

        self.assertEqual(
            participacion_primera.estado_participacion,
            CartonPartidaBingo.ESTADO_GANADOR,
        )
        self.assertEqual(
            participacion_segunda.estado_participacion,
            CartonPartidaBingo.ESTADO_GANADOR,
        )
        self.assertEqual(participacion_primera.indicevictoria, 24)
        self.assertEqual(participacion_segunda.indicevictoria, 25)
        self.assertEqual(participacion_primera.fechavalidacion, fecha_primera)
        self.assertEqual(participacion_segunda.fechavalidacion, fecha_segunda)
        self.assertEqual(participacion_primera.save.call_count, guardados_primera)
        self.assertIsNone(carton.idpartida)
        self.assertIsNone(carton.indicevictoria)
        carton.save.assert_not_called()

    def test_rechaza_indice_de_victoria_no_positivo(self):
        partida = self._partida()
        carton = self._carton()
        for indice in (0, -1, None, True, "no-numero"):
            with self.subTest(indice=indice):
                with patch(
                    "apps.bingos.services.transaction.atomic"
                ) as atomic_mock:
                    with self.assertRaisesMessage(
                        ValidacionCartonError,
                        "mayor que cero",
                    ):
                        validar_participacion_ganadora(
                            partida,
                            carton,
                            indice,
                        )
                atomic_mock.assert_not_called()

    def test_no_elige_arbitrariamente_si_hay_varias_ganadoras(self):
        partida = self._partida()
        otro_carton = self._carton(pk=41, jugador=self.jugador)
        carton = self._carton(pk=40, jugador=self.jugador)
        primera = self._participacion(carton, partida, pk=51)
        segunda = self._participacion(otro_carton, partida, pk=52)

        resultado, bloqueada, _atomic, _lock = self._validar_sin_base(
            partida,
            carton,
            [primera, segunda],
        )
        candidatos = normalizar_candidatos_desempate_participaciones(
            bloqueada.idbingadores,
            partida=bloqueada,
        )

        self.assertEqual(resultado["resultado"], "desempate")
        self.assertEqual(bloqueada.estadopartida, ESTADO_PARTIDA_DESEMPATE)
        self.assertEqual(
            [item["idcartonpartidabingo"] for item in candidatos],
            [51, 52],
        )
        primera.save.assert_not_called()
        segunda.save.assert_not_called()

    def test_conserva_dos_candidatas_del_mismo_jugador(self):
        partida = self._partida()
        primer_carton = self._carton(pk=40, jugador=self.jugador)
        segundo_carton = self._carton(pk=41, jugador=self.jugador)
        candidatas = [
            construir_candidato_desempate_participacion(
                self._participacion(primer_carton, partida, pk=51)
            ),
            construir_candidato_desempate_participacion(
                self._participacion(segundo_carton, partida, pk=52)
            ),
        ]

        normalizadas = normalizar_candidatos_desempate_participaciones(
            candidatas,
            partida=partida,
        )

        self.assertEqual(len(normalizadas), 2)
        self.assertEqual(
            [item["idjugador"] for item in normalizadas],
            [self.jugador.pk, self.jugador.pk],
        )
        self.assertEqual(
            [item["idcartonpartidabingo"] for item in normalizadas],
            [51, 52],
        )

    def test_rechaza_candidata_y_participacion_de_otra_partida(self):
        primera = self._partida(pk=21)
        segunda = self._partida(pk=22)
        carton = self._carton()
        participacion = self._participacion(carton, primera, pk=51)
        candidato = construir_candidato_desempate_participacion(participacion)

        with self.assertRaisesMessage(
            DatosDesempateInvalidosError,
            "otra partida",
        ):
            normalizar_candidatos_desempate_participaciones(
                [candidato],
                partida=segunda,
            )
        with self.assertRaisesMessage(
            ValidacionCartonError,
            "partida indicada",
        ):
            evaluar_participacion_en_partida(participacion, segunda)

    def test_confirmar_desempate_actualiza_solo_candidatas_de_la_ronda(self):
        partida = self._partida(estado=ESTADO_PARTIDA_DESEMPATE)
        otra_partida = self._partida(pk=22)
        primer_carton = self._carton(pk=40, jugador=self.jugador)
        segundo_carton = self._carton(pk=41, jugador=self.jugador)
        primera = self._participacion(primer_carton, partida, pk=51)
        segunda = self._participacion(segundo_carton, partida, pk=52)
        externa = self._participacion(primer_carton, otra_partida, pk=53)
        candidatos = [
            construir_candidato_desempate_participacion(primera),
            construir_candidato_desempate_participacion(segunda),
        ]
        candidatos[0]["tiro_desempate"] = 70
        candidatos[1]["tiro_desempate"] = 60
        partida.idbingadores = json.dumps(candidatos)
        partida.save = Mock()
        fecha = timezone.now()

        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "apps.bingos.services.Partidabingo.objects.select_for_update"
            ) as lock_partida,
            patch(
                "apps.bingos.services._candidatos_y_participaciones_bloqueadas",
                return_value=(candidatos, {51: primera, 52: segunda}),
            ),
        ):
            lock_partida.return_value.get.return_value = partida
            resultado = confirmar_y_finalizar_desempate_participaciones(
                partida,
                indicevictoria=24,
                now=fecha,
            )

        self.assertEqual(resultado["participacion_ganadora"], primera)
        self.assertEqual(
            primera.estado_participacion,
            CartonPartidaBingo.ESTADO_GANADOR,
        )
        self.assertEqual(
            segunda.estado_participacion,
            CartonPartidaBingo.ESTADO_CERRADO,
        )
        self.assertEqual(primera.indicevictoria, 24)
        self.assertIsNone(segunda.indicevictoria)
        self.assertEqual(primera.fechavalidacion, fecha)
        self.assertEqual(segunda.fechavalidacion, fecha)
        self.assertEqual(
            externa.estado_participacion,
            CartonPartidaBingo.ESTADO_PENDIENTE,
        )
        externa.save.assert_not_called()
        primer_carton.save.assert_not_called()
        segundo_carton.save.assert_not_called()
        self.assertIsNone(primer_carton.idpartida)
        self.assertIsNone(primer_carton.indicevictoria)


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class ConsolaValidacionHibridaTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.bingo = Bingo(idbingo=7, titulobingo="Bingo híbrido")
        self.jugador = Jugador(idjugador=4, aliasjugador="jugador4")
        self.matriz = matriz_carton_prueba()
        self.numeros = obtener_numeros_carton(self.matriz)
        self.partida = Partidabingo(
            idpartidabingo=21,
            idbingo=self.bingo,
            nombreronda="Ronda híbrida",
            estadopartida=ESTADO_PARTIDA_EN_CURSO,
            bolascantadas=serializar_bolas_cantadas(self.numeros),
            ultimabola=self.numeros[-1],
            idbingadores=None,
            haydesempate=False,
        )
        self.carton_hibrido = Carton(
            idcarton=40,
            idbingo=self.bingo,
            idjugador=self.jugador,
            idpartida=None,
            indicevictoria=None,
            codigocarton="B7-C-HIBRIDO",
            matriznumeros=serializar_matriz_carton_bingo(self.matriz),
            estadocarton="Vendido",
        )
        self.participacion = CartonPartidaBingo(
            idcartonpartidabingo=51,
            idcarton=self.carton_hibrido,
            idpartida=self.partida,
            idbingo=self.bingo,
            estado_participacion=CartonPartidaBingo.ESTADO_EN_JUEGO,
            indicevictoria=9,
            es_asignacion_original=False,
            origen_asignacion=CartonPartidaBingo.ORIGEN_APLICACION,
            fechavalidacion=timezone.now(),
        )
        self.carton_heredado = Carton(
            idcarton=41,
            idbingo=self.bingo,
            idjugador=self.jugador,
            idpartida=self.partida,
            indicevictoria=3,
            codigocarton="P21-C-HEREDADO",
            matriznumeros=serializar_matriz_carton_bingo(self.matriz),
            estadocarton="Vendido",
        )

    def _request(self, carton=None):
        carton = carton or self.carton_hibrido
        request = self.factory.post(
            reverse(
                "bingos:validar_carton",
                kwargs={
                    "idpartidabingo": self.partida.pk,
                    "idcarton": carton.pk,
                },
            )
        )
        request.user = User(username="admin", is_staff=True)
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def _consulta_participaciones(self, valores):
        consulta = Mock()
        consulta.select_related.return_value.order_by.return_value = valores
        return consulta

    def test_consulta_participaciones_de_la_partida_correcta(self):
        consulta = self._consulta_participaciones([self.participacion])
        with patch(
            "apps.bingos.services.CartonPartidaBingo.objects.filter",
            return_value=consulta,
        ) as filtrar:
            resultado = obtener_participaciones_hibridas_partida(self.partida)

        self.assertEqual(resultado, [self.participacion])
        filtrar.assert_called_once_with(
            idpartida=self.partida,
            idcarton__idpartida__isnull=True,
        )
        consulta.select_related.assert_called_once_with(
            "idcarton",
            "idcarton__idjugador",
            "idcarton__idbingo",
            "idpartida",
            "idpartida__idbingo",
            "idbingo",
        )

    def test_participacion_de_otra_partida_no_aparece(self):
        otra_partida = Partidabingo(
            idpartidabingo=22,
            idbingo=self.bingo,
            nombreronda="Otra ronda",
        )
        otra_participacion = CartonPartidaBingo(
            idcartonpartidabingo=52,
            idcarton=self.carton_hibrido,
            idpartida=otra_partida,
            idbingo=self.bingo,
        )
        consulta = self._consulta_participaciones([])
        with patch(
            "apps.bingos.services.CartonPartidaBingo.objects.filter",
            return_value=consulta,
        ):
            resultado = obtener_participaciones_hibridas_partida(self.partida)

        self.assertEqual(resultado, [])
        self.assertNotIn(otra_participacion, resultado)

    def test_participacion_de_otro_bingo_se_rechaza(self):
        otro_bingo = Bingo(idbingo=8, titulobingo="Otro Bingo")
        inconsistente = CartonPartidaBingo(
            idcartonpartidabingo=53,
            idcarton=self.carton_hibrido,
            idpartida=self.partida,
            idbingo=otro_bingo,
        )
        consulta = self._consulta_participaciones([inconsistente])
        with patch(
            "apps.bingos.services.CartonPartidaBingo.objects.filter",
            return_value=consulta,
        ):
            with self.assertRaisesMessage(
                ValidacionCartonError,
                "otro Bingo",
            ):
                obtener_participaciones_hibridas_partida(self.partida)

    def test_presentacion_usa_estado_e_indice_de_participacion(self):
        self.carton_hibrido.indicevictoria = 88
        datos = preparar_participaciones_hibridas_para_consola(
            self.partida,
            participaciones=[self.participacion],
        )

        self.assertEqual(len(datos), 1)
        self.assertEqual(
            datos[0]["estado_participacion"],
            CartonPartidaBingo.ESTADO_EN_JUEGO,
        )
        self.assertEqual(datos[0]["indicevictoria"], 9)
        self.assertNotEqual(
            datos[0]["indicevictoria"],
            self.carton_hibrido.indicevictoria,
        )
        self.assertEqual(datos[0]["cantidad_marcados"], 24)
        self.assertEqual(datos[0]["progreso"], 100)

    def test_consola_carga_grupos_heredado_e_hibrido_separados(self):
        request = self.factory.get(
            reverse(
                "bingos:consola_operador",
                kwargs={"idpartidabingo": self.partida.pk},
            )
        )
        request.user = User(username="admin", is_staff=True)
        consulta_cartones = Mock()
        consulta_cartones.select_related.return_value.order_by.return_value = [
            self.carton_heredado
        ]
        item_hibrido = {"participacion": self.participacion}
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                return_value=self.partida,
            ),
            patch(
                "apps.bingos.views.acciones_disponibles_consola",
                return_value=set(),
            ),
            patch(
                "apps.bingos.views.Carton.objects.filter",
                return_value=consulta_cartones,
            ),
            patch(
                "apps.bingos.views.obtener_participaciones_hibridas_partida",
                return_value=[self.participacion],
            ) as obtener_hibridas,
            patch(
                "apps.bingos.views.preparar_participaciones_hibridas_para_consola",
                return_value=[item_hibrido],
            ),
            patch(
                "apps.bingos.views.preparar_cartones_para_validacion",
                return_value=[{"carton": self.carton_heredado}],
            ),
            patch(
                "apps.bingos.views.preparar_datos_bolas_partida",
                return_value={},
            ),
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse(status=200),
            ) as render_mock,
        ):
            response = consola_operador(request, self.partida.pk)

        self.assertEqual(response.status_code, 200)
        obtener_hibridas.assert_called_once_with(self.partida)
        contexto = render_mock.call_args.args[2]
        self.assertEqual(contexto["cartones"], [self.carton_heredado])
        self.assertEqual(
            contexto["participaciones_hibridas"],
            [self.participacion],
        )
        self.assertEqual(
            contexto["participaciones_hibridas_validacion"],
            [item_hibrido],
        )

    def test_validacion_heredada_conserva_servicio_existente(self):
        request = self._request(self.carton_heredado)
        resultado = {
            "resultado": "ganador",
            "partida": self.partida,
            "carton": self.carton_heredado,
        }
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                side_effect=[self.partida, self.carton_heredado],
            ),
            patch(
                "apps.bingos.views.validar_carton_ganador",
                return_value=resultado,
            ) as legado_mock,
            patch(
                "apps.bingos.views.validar_participacion_ganadora"
            ) as hibrido_mock,
            patch("apps.bingos.views.programar_publicacion_partida"),
        ):
            response = validar_carton(
                request,
                self.partida.pk,
                self.carton_heredado.pk,
            )

        self.assertEqual(response.status_code, 302)
        legado_mock.assert_called_once_with(self.partida, self.carton_heredado)
        hibrido_mock.assert_not_called()

    def test_validacion_hibrida_usa_servicio_nuevo_y_no_toca_maestro(self):
        request = self._request()
        resultado = {
            "resultado": "ganador",
            "partida": self.partida,
            "participacion": self.participacion,
        }
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                side_effect=[self.partida, self.carton_hibrido],
            ),
            patch(
                "apps.bingos.views.validar_participacion_ganadora",
                return_value=resultado,
            ) as hibrido_mock,
            patch(
                "apps.bingos.views.validar_carton_ganador"
            ) as legado_mock,
            patch("apps.bingos.views.programar_publicacion_partida"),
        ):
            response = validar_carton(
                request,
                self.partida.pk,
                self.carton_hibrido.pk,
            )

        self.assertEqual(response.status_code, 302)
        hibrido_mock.assert_called_once_with(
            partida=self.partida,
            carton=self.carton_hibrido,
            indicevictoria=len(self.numeros),
        )
        legado_mock.assert_not_called()
        self.assertIsNone(self.carton_hibrido.idpartida)
        self.assertIsNone(self.carton_hibrido.indicevictoria)

    def test_exito_hibrido_comunica_victoria_de_ronda(self):
        request = self._request()
        resultado = {
            "resultado": "ganador",
            "partida": self.partida,
            "participacion": self.participacion,
        }
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                side_effect=[self.partida, self.carton_hibrido],
            ),
            patch(
                "apps.bingos.views.validar_participacion_ganadora",
                return_value=resultado,
            ),
            patch("apps.bingos.views.programar_publicacion_partida"),
        ):
            validar_carton(
                request,
                self.partida.pk,
                self.carton_hibrido.pk,
            )

        mensajes = [mensaje.message for mensaje in get_messages(request)]
        self.assertTrue(
            any(
                self.carton_hibrido.codigocarton in mensaje
                and self.partida.nombreronda in mensaje
                and "ganó la ronda" in mensaje
                for mensaje in mensajes
            )
        )
        self.assertFalse(any("todo el Bingo" in mensaje for mensaje in mensajes))

    def test_error_hibrido_muestra_mensaje_util_sin_fallback(self):
        request = self._request()
        error = "No existe una participación para ese cartón y esa partida."
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                side_effect=[self.partida, self.carton_hibrido],
            ),
            patch(
                "apps.bingos.views.validar_participacion_ganadora",
                side_effect=ValidacionCartonError(error),
            ),
            patch(
                "apps.bingos.views.validar_carton_ganador"
            ) as legado_mock,
        ):
            response = validar_carton(
                request,
                self.partida.pk,
                self.carton_hibrido.pk,
            )

        self.assertEqual(response.status_code, 302)
        legado_mock.assert_not_called()
        self.assertIn(error, [mensaje.message for mensaje in get_messages(request)])

    def test_resultado_hibrido_de_desempate_muestra_senal_clara(self):
        request = self._request()
        resultado = {
            "resultado": "desempate",
            "partida": self.partida,
            "participacion": self.participacion,
        }
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                side_effect=[self.partida, self.carton_hibrido],
            ),
            patch(
                "apps.bingos.views.validar_participacion_ganadora",
                return_value=resultado,
            ),
            patch("apps.bingos.views.programar_publicacion_partida"),
        ):
            validar_carton(
                request,
                self.partida.pk,
                self.carton_hibrido.pk,
            )

        mensajes = [mensaje.message for mensaje in get_messages(request)]
        self.assertTrue(any("Desempate" in mensaje for mensaje in mensajes))

    def test_template_distingue_historico_y_carton_de_bingo(self):
        item = preparar_participaciones_hibridas_para_consola(
            self.partida,
            participaciones=[self.participacion],
        )[0]
        request = self.factory.get("/partidas/21/consola/")
        request.user = User(username="admin", is_staff=True)
        html = render_to_string(
            "bingos/consola_operador.html",
            {
                "partida": self.partida,
                "acciones_consola": [],
                "actualizacion_estados_pendiente": False,
                "cartones": [self.carton_heredado],
                "cartones_validacion": [],
                "participaciones_hibridas": [self.participacion],
                "participaciones_hibridas_validacion": [item],
                "error_participaciones_hibridas": None,
                "candidatos_desempate": [],
                "puede_asignar_cartones": False,
                "puede_validar_cartones": True,
            },
            request=request,
        )

        self.assertIn("Histórico por partida", html)
        self.assertIn("Cartón de Bingo", html)
        self.assertIn(self.carton_hibrido.codigocarton, html)
        self.assertIn(CartonPartidaBingo.ESTADO_EN_JUEGO, html)
        self.assertIn("Índice: 9", html)
        self.assertIn("24 de 24 números marcados", html)

    def test_rutas_principales_heredadas_siguen_resolviendo(self):
        consola_url = reverse(
            "bingos:consola_operador",
            kwargs={"idpartidabingo": self.partida.pk},
        )
        validacion_url = reverse(
            "bingos:validar_carton",
            kwargs={
                "idpartidabingo": self.partida.pk,
                "idcarton": self.carton_heredado.pk,
            },
        )

        self.assertEqual(resolve(consola_url).url_name, "consola_operador")
        self.assertEqual(resolve(validacion_url).url_name, "validar_carton")


class RutaValidacionCartonTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_usuario_no_administrativo_recibe_acceso_denegado(self):
        request = self.factory.post("/partidas/1/cartones/2/validar/")
        request.user = User(username="jugador", is_staff=False, is_superuser=False)

        with patch("apps.bingos.views.validar_carton_ganador") as validar_mock:
            with self.assertRaises(PermissionDenied):
                validar_carton(request, 1, 2)

        validar_mock.assert_not_called()

    def test_get_no_modifica_ganador_ni_estado(self):
        request = self.factory.get("/partidas/1/cartones/2/validar/")
        request.user = User(username="admin", is_staff=True)

        with patch("apps.bingos.views.validar_carton_ganador") as validar_mock:
            response = validar_carton(request, 1, 2)

        self.assertEqual(response.status_code, 405)
        validar_mock.assert_not_called()

    def test_post_busca_el_carton_dentro_de_la_partida_de_la_url(self):
        request = self.factory.post("/partidas/1/cartones/2/validar/")
        request.user = User(username="admin", is_staff=True)
        request.session = {}
        request._messages = FallbackStorage(request)
        partida = Partidabingo(idpartidabingo=1)
        carton = Carton(idcarton=2, idpartida=partida)

        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                side_effect=[partida, carton],
            ) as obtener_mock,
            patch(
                "apps.bingos.views.validar_carton_ganador",
                side_effect=ValidacionCartonError("validación simulada"),
            ),
        ):
            response = validar_carton(request, 1, 2)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            obtener_mock.call_args_list[1],
            call(Carton, idcarton=2),
        )


class FormatoCandidatosDesempateTests(SimpleTestCase):
    def test_interpreta_json_plano_generado_por_etapa_tres(self):
        valor = (
            '[{"idcarton":31,"codigocarton":"P20-C-31",'
            '"idjugador":41,"jugador":"juan123"},'
            '{"idcarton":32,"codigocarton":"P20-C-32",'
            '"idjugador":42,"jugador":"maria456"}]'
        )

        candidatos = normalizar_candidatos_desempate(
            parsear_candidatos_desempate(valor)
        )

        self.assertEqual([item["idjugador"] for item in candidatos], [41, 42])
        self.assertEqual(candidatos[0]["cartones"][0]["idcarton"], 31)
        self.assertIsNone(candidatos[0]["tiro_desempate"])

    def test_interpreta_ids_antiguos_separados_por_comas(self):
        candidatos = normalizar_candidatos_desempate(
            parsear_candidatos_desempate("41,42")
        )

        self.assertEqual([item["idjugador"] for item in candidatos], [41, 42])
        self.assertEqual(candidatos[0]["cartones"], [])

    def test_unifica_jugador_repetido_y_conserva_todos_sus_cartones(self):
        candidatos = normalizar_candidatos_desempate(
            [
                {
                    "idjugador": 41,
                    "jugador": "juan123",
                    "idcarton": 31,
                    "codigocarton": "P20-C-31",
                },
                {
                    "idjugador": 41,
                    "jugador": "juan123",
                    "idcarton": 33,
                    "codigocarton": "P20-C-33",
                },
            ]
        )

        self.assertEqual(len(candidatos), 1)
        self.assertEqual(
            [carton["idcarton"] for carton in candidatos[0]["cartones"]],
            [31, 33],
        )

    def test_tiro_se_conserva_al_serializar_y_volver_a_leer(self):
        candidatos = candidatos_desempate_prueba(tiro_uno=67)

        persistidos = serializar_candidatos_desempate(candidatos)
        recargados = normalizar_candidatos_desempate(
            parsear_candidatos_desempate(persistidos)
        )

        self.assertEqual(recargados[0]["tiro_desempate"], 67)
        self.assertEqual(recargados[0]["cartones"], candidatos[0]["cartones"])

    def test_formato_persistido_es_json_compacto_y_canonico(self):
        persistidos = serializar_candidatos_desempate(
            [candidatos_desempate_prueba(tiro_uno=67)[0]]
        )

        self.assertEqual(
            persistidos,
            '[{"idjugador":41,"jugador":"juan123","cartones":'
            '[{"idcarton":31,"codigocarton":"P20-C-31"}],'
            '"tiro_desempate":67}]',
        )

    def test_recargar_datos_no_modifica_tiros_persistidos(self):
        valor = serializar_candidatos_desempate(
            candidatos_desempate_prueba(tiro_uno=67)
        )
        partida = Partidabingo(
            idpartidabingo=20,
            estadopartida=ESTADO_PARTIDA_DESEMPATE,
            idbingadores=valor,
        )

        primera_carga = preparar_datos_desempate(partida)
        segunda_carga = preparar_datos_desempate(partida)

        self.assertEqual(
            primera_carga["candidatos_desempate"],
            segunda_carga["candidatos_desempate"],
        )
        self.assertEqual(partida.idbingadores, valor)

    def test_letra_bingo_del_tiro_se_calcula_correctamente(self):
        self.assertEqual(
            [formatear_bola_bingo(numero) for numero in (1, 16, 31, 46, 61, 75)],
            ["B-1", "I-16", "N-31", "G-46", "O-61", "O-75"],
        )

    def test_rechaza_tiros_repetidos_en_datos_persistidos(self):
        with self.assertRaises(DatosDesempateInvalidosError):
            normalizar_candidatos_desempate(
                candidatos_desempate_prueba(tiro_uno=50, tiro_dos=50)
            )


class ServicioDesempateTests(SimpleTestCase):
    def _partida(
        self,
        estado=ESTADO_PARTIDA_DESEMPATE,
        candidatos=None,
        pk=20,
    ):
        candidatos = candidatos or candidatos_desempate_prueba()
        return Partidabingo(
            idpartidabingo=pk,
            estadopartida=estado,
            idbingadores=serializar_candidatos_desempate(candidatos),
            idjugadorganador=None,
            bolamayordesempate=None,
            haydesempate=True,
            bolascantadas="[1,22,73]",
            ultimabola=73,
            horafin=None,
        )

    def _partida_bloqueada(self, partida, save_error=None):
        bloqueada = Partidabingo(
            idpartidabingo=partida.pk,
            estadopartida=partida.estadopartida,
            idbingadores=partida.idbingadores,
            idjugadorganador_id=partida.idjugadorganador_id,
            bolamayordesempate=partida.bolamayordesempate,
            haydesempate=partida.haydesempate,
            bolascantadas=partida.bolascantadas,
            ultimabola=partida.ultimabola,
            horafin=partida.horafin,
        )
        bloqueada.save = Mock(side_effect=save_error)
        return bloqueada

    def _sortear(self, partida, idjugador, balota=67, save_error=None):
        self.bloqueada = self._partida_bloqueada(partida, save_error=save_error)
        generador = Mock()
        generador.choice.return_value = balota
        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic_mock,
            patch(
                "apps.bingos.services.Partidabingo.objects.select_for_update"
            ) as lock_mock,
        ):
            lock_mock.return_value.get.return_value = self.bloqueada
            self.atomic_mock = atomic_mock
            self.lock_mock = lock_mock
            self.generador = generador
            return sortear_balota_desempate(
                partida,
                idjugador,
                generador_aleatorio=generador,
            )

    def _confirmar(self, partida, now=None, save_error=None):
        self.bloqueada = self._partida_bloqueada(partida, save_error=save_error)
        with (
            patch(
                "apps.bingos.services.transaction.atomic",
                return_value=nullcontext(),
            ) as atomic_mock,
            patch(
                "apps.bingos.services.Partidabingo.objects.select_for_update"
            ) as lock_mock,
        ):
            lock_mock.return_value.get.return_value = self.bloqueada
            self.atomic_mock = atomic_mock
            self.lock_mock = lock_mock
            return confirmar_y_finalizar_desempate(partida, now=now)

    def test_cada_jugador_recibe_solo_un_tiro(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67)
        )

        with self.assertRaises(DesempateError):
            self._sortear(partida, 41, balota=68)

        self.bloqueada.save.assert_not_called()
        self.generador.choice.assert_not_called()

    def test_tiro_generado_esta_entre_uno_y_setenta_y_cinco(self):
        partida = self._partida()

        resultado = self._sortear(partida, 41, balota=75)

        self.assertGreaterEqual(resultado["balota"], 1)
        self.assertLessEqual(resultado["balota"], 75)

    def test_dos_candidatos_no_reciben_la_misma_balota(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67)
        )

        resultado = self._sortear(partida, 42, balota=68)

        disponibles = self.generador.choice.call_args.args[0]
        self.assertNotIn(67, disponibles)
        self.assertEqual(resultado["balota"], 68)
        self.assertEqual(obtener_tiros_desempate(resultado["candidatos"]), [67, 68])

    def test_jugador_no_candidato_no_puede_sortear(self):
        partida = self._partida()

        with self.assertRaises(DesempateError):
            self._sortear(partida, 99)

        self.bloqueada.save.assert_not_called()

    def test_no_se_puede_sortear_fuera_de_desempate(self):
        for estado in (
            ESTADO_PARTIDA_PROGRAMADA,
            ESTADO_PARTIDA_EN_ESPERA,
            ESTADO_PARTIDA_PAUSADA,
            ESTADO_PARTIDA_CANCELADA,
        ):
            with self.subTest(estado=estado):
                partida = self._partida(estado=estado)
                with self.assertRaises(DesempateError):
                    sortear_balota_desempate(partida, 41)

    def test_no_se_puede_sortear_en_curso(self):
        partida = self._partida(estado=ESTADO_PARTIDA_EN_CURSO)

        with self.assertRaises(DesempateError):
            sortear_balota_desempate(partida, 41)

    def test_no_se_puede_sortear_en_finalizada(self):
        partida = self._partida(estado=ESTADO_PARTIDA_FINALIZADA)

        with self.assertRaises(DesempateError):
            sortear_balota_desempate(partida, 41)

    def test_primer_tiro_convierte_formato_etapa_tres_sin_perder_cartones(self):
        partida = self._partida()
        partida.idbingadores = (
            '[{"idcarton":31,"codigocarton":"P20-C-31",'
            '"idjugador":41,"jugador":"juan123"},'
            '{"idcarton":33,"codigocarton":"P20-C-33",'
            '"idjugador":41,"jugador":"juan123"},'
            '{"idcarton":32,"codigocarton":"P20-C-32",'
            '"idjugador":42,"jugador":"maria456"}]'
        )

        resultado = self._sortear(partida, 41, balota=67)
        persistidos = normalizar_candidatos_desempate(
            parsear_candidatos_desempate(partida.idbingadores)
        )

        self.assertEqual(resultado["balota"], 67)
        self.assertEqual(persistidos[0]["tiro_desempate"], 67)
        self.assertEqual(
            [carton["idcarton"] for carton in persistidos[0]["cartones"]],
            [31, 33],
        )

    def test_balotas_disponibles_excluyen_tiros_realizados(self):
        disponibles = obtener_balotas_disponibles_desempate(
            candidatos_desempate_prueba(tiro_uno=1, tiro_dos=75)
        )

        self.assertNotIn(1, disponibles)
        self.assertNotIn(75, disponibles)
        self.assertEqual(len(disponibles), 73)

    def test_no_confirma_antes_de_completar_todos_los_tiros(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67)
        )

        with self.assertRaises(DesempateIncompletoError):
            self._confirmar(partida)

        self.bloqueada.save.assert_not_called()

    def test_no_se_puede_confirmar_fuera_de_desempate(self):
        partida = self._partida(
            estado=ESTADO_PARTIDA_FINALIZADA,
            candidatos=candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58),
        )

        with self.assertRaises(DesempateError):
            confirmar_y_finalizar_desempate(partida)

    def test_identifica_correctamente_el_numero_maximo(self):
        resultado = obtener_resultado_desempate(
            candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58)
        )

        self.assertEqual(resultado["idjugador"], 41)
        self.assertEqual(resultado["balota"], 67)
        self.assertEqual(resultado["codigo"], "O-67")

    def test_confirmar_registra_al_jugador_ganador(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58)
        )

        self._confirmar(partida)

        self.assertEqual(partida.idjugadorganador_id, 41)

    def test_confirmar_guarda_la_balota_mayor(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58)
        )

        self._confirmar(partida)

        self.assertEqual(partida.bolamayordesempate, 67)

    def test_confirmar_cambia_la_partida_a_finalizada(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58)
        )

        self._confirmar(partida)

        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_FINALIZADA)

    def test_confirmar_guarda_hora_fin(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58)
        )
        now = timezone.now()

        self._confirmar(partida, now=now)

        self.assertEqual(partida.horafin, now)

    def test_confirmar_conserva_hay_desempate_verdadero(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58)
        )

        self._confirmar(partida)

        self.assertTrue(partida.haydesempate)

    def test_confirmar_no_altera_bolas_normales_ni_ultima_bola(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58)
        )
        bolas_antes = partida.bolascantadas
        ultima_antes = partida.ultimabola

        self._confirmar(partida)

        self.assertEqual(partida.bolascantadas, bolas_antes)
        self.assertEqual(partida.ultimabola, ultima_antes)
        self.assertNotIn("bolascantadas", self.bloqueada.save.call_args.kwargs["update_fields"])
        self.assertNotIn("ultimabola", self.bloqueada.save.call_args.kwargs["update_fields"])

    def test_operaciones_usan_transaccion_y_bloquean_partida(self):
        partida = self._partida()

        self._sortear(partida, 41, balota=67)

        self.atomic_mock.assert_called_once_with()
        self.lock_mock.assert_called_once_with()
        self.lock_mock.return_value.get.assert_called_once_with(pk=partida.pk)

    def test_error_al_guardar_no_sincroniza_cambios_parciales(self):
        partida = self._partida(
            candidatos=candidatos_desempate_prueba(tiro_uno=67, tiro_dos=58)
        )
        valores_antes = (
            partida.idjugadorganador_id,
            partida.bolamayordesempate,
            partida.estadopartida,
            partida.horafin,
            partida.idbingadores,
        )

        with self.assertRaises(DatabaseError):
            self._confirmar(
                partida,
                save_error=DatabaseError("fallo simulado"),
            )

        self.assertEqual(
            (
                partida.idjugadorganador_id,
                partida.bolamayordesempate,
                partida.estadopartida,
                partida.horafin,
                partida.idbingadores,
            ),
            valores_antes,
        )


class RutasDesempateTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_usuario_no_administrativo_recibe_acceso_denegado(self):
        usuario = User(username="jugador", is_staff=False, is_superuser=False)
        solicitudes = (
            (sortear_desempate, self.factory.post("/desempate/41/sortear/"), (20, 41)),
            (confirmar_desempate, self.factory.post("/desempate/confirmar/"), (20,)),
            (desempate_operador, self.factory.get("/desempate/"), (20,)),
        )

        for vista, request, argumentos in solicitudes:
            with self.subTest(vista=vista.__name__):
                request.user = usuario
                with self.assertRaises(PermissionDenied):
                    vista(request, *argumentos)

    def test_get_no_registra_tiros_ni_finaliza(self):
        usuario = User(username="admin", is_staff=True)
        request_sortear = self.factory.get("/desempate/41/sortear/")
        request_sortear.user = usuario
        request_confirmar = self.factory.get("/desempate/confirmar/")
        request_confirmar.user = usuario

        with (
            patch("apps.bingos.views.sortear_balota_desempate") as sortear_mock,
            patch("apps.bingos.views.confirmar_y_finalizar_desempate") as confirmar_mock,
        ):
            response_sortear = sortear_desempate(request_sortear, 20, 41)
            response_confirmar = confirmar_desempate(request_confirmar, 20)

        self.assertEqual(response_sortear.status_code, 405)
        self.assertEqual(response_confirmar.status_code, 405)
        sortear_mock.assert_not_called()
        confirmar_mock.assert_not_called()


class ServiciosPublicosBingoTests(SimpleTestCase):
    def test_tablero_prepara_ultima_bola_y_totales(self):
        partida = partida_publica_prueba(bolas=[1, 27, 73], ultima=73)

        datos = preparar_datos_tablero_publico(partida)

        self.assertEqual(datos["ultima_bola_codigo"], "O-73")
        self.assertEqual(datos["total_bolas_extraidas"], 3)
        self.assertEqual(datos["total_bolas_faltantes"], 72)

    def test_tablero_marca_las_bolas_extraidas(self):
        partida = partida_publica_prueba(bolas=[1, 27, 73])

        datos = preparar_datos_tablero_publico(partida)
        bolas = {
            bola["numero"]: bola["extraida"]
            for columna in datos["tablero_bingo"]
            for bola in columna["bolas"]
        }

        self.assertTrue(bolas[1])
        self.assertTrue(bolas[27])
        self.assertTrue(bolas[73])
        self.assertFalse(bolas[2])

    def test_partida_sin_bolas_se_prepara_de_forma_controlada(self):
        partida = partida_publica_prueba(bolas=[], ultima=0)

        datos = preparar_datos_tablero_publico(partida)

        self.assertIsNone(datos["ultima_bola_codigo"])
        self.assertEqual(datos["total_bolas_extraidas"], 0)
        self.assertEqual(datos["historial_bolas"], [])

    def test_partida_pausada_muestra_mensaje_publico(self):
        partida = partida_publica_prueba(estado=ESTADO_PARTIDA_PAUSADA)

        datos = preparar_datos_tablero_publico(partida)

        self.assertEqual(
            datos["mensaje_estado_publico"],
            "La partida está pausada temporalmente.",
        )
        self.assertNotIn("puede_sacar_bola", datos)

    def test_ganador_solo_se_expone_al_finalizar(self):
        ganador = Jugador(idjugador=41, aliasjugador="campeon_publico")
        en_curso = partida_publica_prueba(ganador=ganador)
        finalizada = partida_publica_prueba(
            estado=ESTADO_PARTIDA_FINALIZADA,
            ganador=ganador,
        )

        self.assertIsNone(preparar_datos_tablero_publico(en_curso)["ganador_publico"])
        self.assertEqual(
            preparar_datos_tablero_publico(finalizada)["ganador_publico"],
            "campeon_publico",
        )

    def test_resumen_publico_no_incluye_datos_de_desempate(self):
        partida = partida_publica_prueba(bolas=[12])
        partida.idbingadores = '[{"idjugador":99,"tiro_desempate":75}]'

        resumen = preparar_resumen_partida_publica(partida)

        self.assertEqual(resumen["total_bolas_extraidas"], 1)
        self.assertNotIn("idbingadores", resumen)
        self.assertNotIn("candidatos", resumen)

    def test_carton_prepara_matriz_cinco_por_cinco_y_libre(self):
        carton = carton_publico_prueba()

        datos = preparar_datos_carton_jugador(carton)

        self.assertEqual(len(datos["matriz_carton"]), 5)
        self.assertTrue(all(len(fila) == 5 for fila in datos["matriz_carton"]))
        self.assertTrue(datos["matriz_carton"][2][2]["libre"])
        self.assertEqual(datos["matriz_carton"][2][2]["valor"], CASILLA_LIBRE)

    def test_carton_diferencia_numeros_marcados_y_pendientes(self):
        partida = partida_publica_prueba(bolas=[1, 16])
        carton = carton_publico_prueba(partida=partida)

        datos = preparar_datos_carton_jugador(carton)

        self.assertTrue(datos["matriz_carton"][0][0]["marcada"])
        self.assertTrue(datos["matriz_carton"][0][1]["marcada"])
        self.assertFalse(datos["matriz_carton"][0][2]["marcada"])

    def test_contador_ignora_libre(self):
        matriz = matriz_carton_prueba()

        self.assertEqual(contar_numeros_marcados_carton(matriz, []), 0)
        self.assertEqual(contar_numeros_marcados_carton(matriz, [1, 16]), 2)
        self.assertEqual(
            contar_numeros_marcados_carton(matriz, obtener_numeros_carton(matriz)),
            24,
        )

    def test_matriz_invalida_no_se_considera_dato_publico_valido(self):
        carton = carton_publico_prueba()
        carton.matriznumeros = "[[1,2],[3,4]]"

        with self.assertRaises(MatrizCartonInvalidaError):
            preparar_datos_carton_jugador(carton)

    def test_carton_sin_partida_genera_error_controlado(self):
        carton = carton_publico_prueba()
        carton.idpartida = None

        with self.assertRaises(CartonPublicoError):
            preparar_datos_carton_jugador(carton)


class VistasPublicasBingoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, path, usuario=None, method="get", data=None):
        request = getattr(self.factory, method)(path, data=data or {})
        request.user = usuario or AnonymousUser()
        return request

    def test_sala_publica_abre_sin_iniciar_sesion(self):
        request = self._request("/juego/")
        partida = partida_publica_prueba()
        consulta = Mock()
        consulta.order_by.return_value = [partida]

        with (
            patch(
                "apps.bingos.views.Partidabingo.objects.select_related",
                return_value=consulta,
            ),
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("Sala pública"),
            ) as render_mock,
        ):
            response = sala_juego_publica(request)

        self.assertEqual(response.status_code, 200)
        contexto = render_mock.call_args.args[2]
        self.assertEqual(contexto["partidas_publicas"][0]["partida"], partida)

    def test_tablero_publico_abre_sin_iniciar_sesion(self):
        request = self._request("/juego/partidas/20/tablero/")
        partida = partida_publica_prueba()

        with (
            patch("apps.bingos.views.get_object_or_404", return_value=partida),
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("Tablero público"),
            ),
        ):
            response = tablero_publico(request, 20)

        self.assertEqual(response.status_code, 200)

    def test_usuario_no_administrativo_puede_abrir_rutas_publicas(self):
        usuario = User(username="publico", is_staff=False, is_superuser=False)
        request = self._request(
            "/juego/partidas/20/tablero/",
            usuario=usuario,
        )
        partida = partida_publica_prueba()

        with (
            patch("apps.bingos.views.get_object_or_404", return_value=partida),
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("Tablero público"),
            ),
        ):
            response = tablero_publico(request, 20)

        self.assertEqual(response.status_code, 200)

    def test_post_al_tablero_no_puede_modificar_partida(self):
        request = self._request(
            "/juego/partidas/20/tablero/",
            method="post",
        )

        with patch("apps.bingos.views.get_object_or_404") as obtener_mock:
            response = tablero_publico(request, 20)

        self.assertEqual(response.status_code, 405)
        obtener_mock.assert_not_called()

    def test_get_publico_no_cambia_datos_de_partida(self):
        request = self._request("/juego/partidas/20/tablero/")
        partida = partida_publica_prueba(bolas=[1, 22], ultima=22)
        partida.idbingadores = "evidencia-privada"
        partida.save = Mock()
        antes = (
            partida.estadopartida,
            partida.bolascantadas,
            partida.ultimabola,
            partida.idjugadorganador_id,
            partida.idbingadores,
        )

        with (
            patch("apps.bingos.views.get_object_or_404", return_value=partida),
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("Tablero público"),
            ),
        ):
            tablero_publico(request, 20)

        self.assertEqual(
            (
                partida.estadopartida,
                partida.bolascantadas,
                partida.ultimabola,
                partida.idjugadorganador_id,
                partida.idbingadores,
            ),
            antes,
        )
        partida.save.assert_not_called()

    def test_codigo_valido_muestra_el_carton_correcto(self):
        request = self._request("/juego/cartones/PUBLICO-001/")
        carton = carton_publico_prueba()
        consulta = Mock()
        consulta.filter.return_value.first.return_value = carton

        with (
            patch(
                "apps.bingos.views.Carton.objects.select_related",
                return_value=consulta,
            ),
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("Mi cartón"),
            ) as render_mock,
        ):
            response = carton_publico(request, carton.codigocarton)

        self.assertEqual(response.status_code, 200)
        self.assertIs(render_mock.call_args.args[2]["carton"], carton)
        consulta.filter.assert_called_once_with(codigocarton="PUBLICO-001")

    def test_formulario_valido_redirige_al_carton_sin_modificarlo(self):
        request = self._request(
            "/juego/cartones/acceder/",
            method="post",
            data={"codigocarton": "PUBLICO-001"},
        )

        with patch("apps.bingos.views.Carton.objects.filter") as filtrar_mock:
            filtrar_mock.return_value.exists.return_value = True
            response = acceder_carton_publico(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/juego/cartones/PUBLICO-001/", response["Location"])
        filtrar_mock.return_value.update.assert_not_called()

    def test_codigo_invalido_muestra_mensaje_sin_detalles_internos(self):
        request = self._request(
            "/juego/cartones/acceder/",
            method="post",
            data={"codigocarton": "NO-EXISTE"},
        )

        with (
            patch("apps.bingos.views.Carton.objects.filter") as filtrar_mock,
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("Código no encontrado"),
            ) as render_mock,
        ):
            filtrar_mock.return_value.exists.return_value = False
            response = acceder_carton_publico(request)

        self.assertEqual(response.status_code, 200)
        errores = str(render_mock.call_args.args[2]["form"].errors)
        self.assertIn("No encontramos un cartón", errores)
        self.assertNotIn("SELECT", errores)
        self.assertNotIn("carton.idcarton", errores)

    def test_url_de_codigo_invalido_devuelve_404_controlado(self):
        request = self._request("/juego/cartones/NO-EXISTE/")
        consulta = Mock()
        consulta.filter.return_value.first.return_value = None

        def render_controlado(_request, _template, _context, status=200):
            return HttpResponse("No encontramos un cartón", status=status)

        with (
            patch(
                "apps.bingos.views.Carton.objects.select_related",
                return_value=consulta,
            ),
            patch("apps.bingos.views.render", side_effect=render_controlado),
        ):
            response = carton_publico(request, "NO-EXISTE")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "No encontramos un cartón", status_code=404)

    def test_matriz_invalida_no_rompe_vista_y_deja_evidencia(self):
        request = self._request("/juego/cartones/PUBLICO-001/")
        carton = carton_publico_prueba()
        carton.matriznumeros = "[[1,2],[3,4]]"
        consulta = Mock()
        consulta.filter.return_value.first.return_value = carton

        with (
            patch(
                "apps.bingos.views.Carton.objects.select_related",
                return_value=consulta,
            ),
            patch(
                "apps.bingos.views.render",
                return_value=HttpResponse("Error controlado"),
            ) as render_mock,
            self.assertLogs("apps.bingos.views", level="WARNING"),
        ):
            response = carton_publico(request, carton.codigocarton)

        self.assertEqual(response.status_code, 200)
        self.assertIn("no está disponible", render_mock.call_args.args[2]["error_carton"])

    def test_rutas_administrativas_conservan_restriccion(self):
        request = self._request(
            "/partidas/",
            usuario=User(username="publico", is_staff=False),
        )

        with self.assertRaises(PermissionDenied):
            partidas_lista(request)


@override_settings(
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
)
class PlantillasPublicasBingoTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, path):
        request = self.factory.get(path)
        request.user = AnonymousUser()
        return request

    def test_sala_no_expone_cartones_jugadores_ni_candidatos(self):
        partida = partida_publica_prueba()
        partida.idbingadores = (
            '[{"jugador":"jugador_privado","codigocarton":'
            '"CARTON-PRIVADO","tiro_desempate":75}]'
        )

        html = render_to_string(
            "bingos/sala_juego_publica.html",
            {
                "partidas_publicas": [
                    preparar_resumen_partida_publica(partida)
                ]
            },
            request=self._request("/juego/"),
        )

        self.assertNotIn("jugador_privado", html)
        self.assertNotIn("CARTON-PRIVADO", html)
        self.assertNotIn("tiro_desempate", html)

    def test_tablero_renderiza_ultima_bola_conteo_y_resaltados(self):
        partida = partida_publica_prueba(bolas=[1, 27, 73], ultima=73)
        contexto = {
            "partida": partida,
            **preparar_datos_tablero_publico(partida),
        }

        html = render_to_string(
            "bingos/tablero_publico.html",
            contexto,
            request=self._request("/juego/partidas/20/tablero/"),
        )

        self.assertIn("O-73", html)
        self.assertIn("3", html)
        self.assertIn("<dt>Extraídas</dt>", html)
        self.assertIn("<dt>Restantes</dt>", html)
        self.assertEqual(html.count('class="public-bingo-column col"'), 5)
        self.assertIn("public-bingo-ball is-drawn", html)
        self.assertIn("public-ball-check", html)
        self.assertIn("Extraída", html)
        self.assertEqual(html.count("public-history-ball"), 3)
        self.assertIn("B-1", html)
        self.assertIn("I-27", html)
        self.assertIn("O-73", html)
        self.assertNotIn("Sacar siguiente bola", html)
        self.assertNotIn("Validar cartón", html)

    def test_tablero_sin_bolas_muestra_mensaje_controlado(self):
        partida = partida_publica_prueba(bolas=[], ultima=0)

        html = render_to_string(
            "bingos/tablero_publico.html",
            {"partida": partida, **preparar_datos_tablero_publico(partida)},
            request=self._request("/juego/partidas/20/tablero/"),
        )

        self.assertIn("Aún no se han extraído bolas.", html)

    def test_tablero_pausado_no_muestra_acciones_administrativas(self):
        partida = partida_publica_prueba(estado=ESTADO_PARTIDA_PAUSADA)

        html = render_to_string(
            "bingos/tablero_publico.html",
            {"partida": partida, **preparar_datos_tablero_publico(partida)},
            request=self._request("/juego/partidas/20/tablero/"),
        )

        self.assertIn("La partida está pausada temporalmente.", html)
        self.assertNotIn("Reanudar partida", html)
        self.assertNotIn("Pausar partida", html)

    def test_finalizada_muestra_ganador_solo_si_existe(self):
        ganador = Jugador(idjugador=41, aliasjugador="campeon_publico")
        con_ganador = partida_publica_prueba(
            estado=ESTADO_PARTIDA_FINALIZADA,
            ganador=ganador,
        )
        sin_ganador = partida_publica_prueba(
            estado=ESTADO_PARTIDA_FINALIZADA,
            ganador=None,
        )

        html_con = render_to_string(
            "bingos/tablero_publico.html",
            {"partida": con_ganador, **preparar_datos_tablero_publico(con_ganador)},
            request=self._request("/juego/partidas/20/tablero/"),
        )
        html_sin = render_to_string(
            "bingos/tablero_publico.html",
            {"partida": sin_ganador, **preparar_datos_tablero_publico(sin_ganador)},
            request=self._request("/juego/partidas/20/tablero/"),
        )

        self.assertIn("Ganador: campeon_publico", html_con)
        self.assertNotIn("campeon_publico", html_sin)

    def test_carton_renderiza_matriz_libre_marcados_pendientes_y_contador(self):
        partida = partida_publica_prueba(bolas=[1, 16])
        carton = carton_publico_prueba(partida=partida)
        datos = preparar_datos_carton_jugador(carton)

        html = render_to_string(
            "bingos/carton_publico.html",
            {
                "carton": carton,
                "partida": partida,
                "error_carton": None,
                **datos,
            },
            request=self._request("/juego/cartones/PUBLICO-001/"),
        )

        self.assertEqual(html.count("<tr>"), 6)
        self.assertIn("<dt>Bingo</dt>", html)
        self.assertIn("<dt>Ronda</dt>", html)
        self.assertIn("<dt>Estado</dt>", html)
        self.assertIn("<dt>Progreso</dt>", html)
        self.assertIn("LIBRE", html)
        self.assertIn("public-card-cell--marked", html)
        self.assertIn("public-card-cell--pending", html)
        self.assertIn("public-card-cell--free", html)
        self.assertIn("✓ Marcado", html)
        self.assertIn("○ Pendiente", html)
        self.assertIn("★ Automática", html)
        self.assertIn("2 de 24 números marcados.", html)
        self.assertIn("La casilla LIBRE se marca automáticamente.", html)

    def test_carton_no_expone_precio_otros_cartones_ni_otros_jugadores(self):
        partida = partida_publica_prueba(bolas=[1])
        carton = carton_publico_prueba(partida=partida)

        html = render_to_string(
            "bingos/carton_publico.html",
            {
                "carton": carton,
                "partida": partida,
                "error_carton": None,
                **preparar_datos_carton_jugador(carton),
            },
            request=self._request("/juego/cartones/PUBLICO-001/"),
        )

        self.assertNotIn("9876.54", html)
        self.assertNotIn("OTRO-CARTON-PRIVADO", html)
        self.assertNotIn("otro_jugador_privado", html)
        self.assertNotIn("Editar", html)
        self.assertNotIn("Validar cartón", html)


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
            acciones_disponibles_consola(Partidabingo(estadopartida=ESTADO_PARTIDA_DESEMPATE)),
            set(),
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
            patch("apps.bingos.views.programar_publicacion_partida"),
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
            patch("apps.bingos.views.programar_publicacion_partida"),
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


@override_settings(
    ALLOWED_HOSTS=["localhost", "testserver"],
    CHANNEL_LAYERS={
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    },
)
class WebSocketPublicoBingoTests(SimpleTestCase):
    class CapaCanalesPrueba:
        def __init__(self):
            self.grupos_agregados = []
            self.grupos_descartados = []

        async def group_add(self, group_name, channel_name):
            self.grupos_agregados.append((group_name, channel_name))

        async def group_discard(self, group_name, channel_name):
            self.grupos_descartados.append((group_name, channel_name))

    def test_aplicacion_asgi_carga_correctamente(self):
        from config.asgi import application

        self.assertIsNotNone(application)

    def test_ruta_websocket_publica_existe(self):
        from apps.bingos.routing import websocket_urlpatterns

        rutas_partida = [
            ruta
            for ruta in websocket_urlpatterns
            if getattr(ruta, "name", None) == "ws_partida_publica"
        ]

        self.assertEqual(len(rutas_partida), 1)
        self.assertEqual(
            rutas_partida[0].callback.consumer_class,
            PartidaPublicaConsumer,
        )

    def test_consumidor_acepta_partida_existente(self):
        async def partida_existe(_consumer, _idpartidabingo):
            return True

        async def escenario():
            consumidor = PartidaPublicaConsumer()
            consumidor.scope = {
                "url_route": {"kwargs": {"idpartidabingo": "20"}}
            }
            consumidor.channel_layer = self.CapaCanalesPrueba()
            consumidor.channel_name = "canal-prueba"
            consumidor.base_send = AsyncMock()

            with patch.object(
                PartidaPublicaConsumer,
                "_partida_existe",
                new=partida_existe,
            ):
                await consumidor.connect()

            return consumidor

        consumidor = asyncio.run(escenario())
        consumidor.base_send.assert_awaited_once_with(
            {"type": "websocket.accept", "subprotocol": None}
        )
        self.assertEqual(
            consumidor.channel_layer.grupos_agregados,
            [(nombre_grupo_partida(20), "canal-prueba")],
        )

    def test_partida_inexistente_se_cierra_de_forma_controlada(self):
        async def partida_existe(_consumer, _idpartidabingo):
            return False

        async def escenario():
            consumidor = PartidaPublicaConsumer()
            consumidor.scope = {
                "url_route": {"kwargs": {"idpartidabingo": "9999"}}
            }
            consumidor.channel_layer = self.CapaCanalesPrueba()
            consumidor.channel_name = "canal-prueba"
            consumidor.base_send = AsyncMock()

            with patch.object(
                PartidaPublicaConsumer,
                "_partida_existe",
                new=partida_existe,
            ):
                await consumidor.connect()

            return consumidor

        consumidor = asyncio.run(escenario())
        consumidor.base_send.assert_awaited_once_with(
            {"type": "websocket.close", "code": 4404}
        )
        self.assertEqual(consumidor.channel_layer.grupos_agregados, [])

    def test_mensajes_del_cliente_se_ignoran_sin_acciones_admin(self):
        consumidor = PartidaPublicaConsumer()
        with patch("apps.bingos.models.Partidabingo.save") as guardar_mock:
            resultado = asyncio.run(
                consumidor.receive(
                    text_data='{"accion": "sacar_bola", "estadopartida": "Finalizada"}'
                )
            )

        self.assertIsNone(resultado)
        guardar_mock.assert_not_called()

    def test_evento_de_bola_llega_al_cliente_con_payload_publico(self):
        from config.asgi import application

        async def partida_existe(_consumer, _idpartidabingo):
            return True

        partida = partida_publica_prueba(bolas=[2, 23], ultima=23)
        payload = construir_payload_publico_partida(
            partida,
            "bola_extraida",
        )

        async def escenario():
            with patch.object(
                PartidaPublicaConsumer,
                "_partida_existe",
                new=partida_existe,
            ), patch("apps.bingos.models.Partidabingo.save") as guardar_mock:
                comunicador = WebsocketCommunicator(
                    application,
                    "/ws/juego/partidas/20/",
                    headers=[(b"origin", b"http://localhost")],
                )
                await get_channel_layer().flush()
                try:
                    conectado, _subprotocolo = await comunicador.connect(
                        timeout=0.5
                    )
                    await comunicador.send_json_to(
                        {
                            "accion": "sacar_bola",
                            "estadopartida": "Finalizada",
                        }
                    )
                    sin_respuesta = await comunicador.receive_nothing(
                        timeout=0.05
                    )
                    guardar_mock.assert_not_called()
                    await get_channel_layer().group_send(
                        nombre_grupo_partida(20),
                        {
                            "type": "partida.actualizada",
                            "payload": payload,
                        },
                    )
                    await asyncio.sleep(0.05)
                    recibido = await comunicador.receive_json_from(
                        timeout=0.5
                    )
                finally:
                    comunicador.stop(exceptions=False)
                return conectado, sin_respuesta, recibido

        conectado, sin_respuesta, recibido = asyncio.run(escenario())
        self.assertTrue(conectado)
        self.assertTrue(sin_respuesta)
        self.assertEqual(recibido, payload)
        self.assertEqual(recibido["partida"]["ultima_bola"]["codigo"], "I-23")
        self.assertEqual(recibido["partida"]["estado"], ESTADO_PARTIDA_EN_CURSO)
        self.assertEqual(recibido["partida"]["total_extraidas"], 2)
        self.assertEqual(recibido["partida"]["cantidad_extraida"], 2)
        self.assertEqual(recibido["partida"]["restantes"], 73)

    def test_consumidor_sin_capa_de_canales_cierra_controladamente(self):
        async def partida_existe(_consumer, _idpartidabingo):
            return True

        async def escenario():
            consumidor = PartidaPublicaConsumer()
            consumidor.scope = {
                "url_route": {"kwargs": {"idpartidabingo": "20"}}
            }
            consumidor.channel_layer = None
            consumidor.channel_name = "canal-prueba"
            consumidor.base_send = AsyncMock()

            with patch.object(
                PartidaPublicaConsumer,
                "_partida_existe",
                new=partida_existe,
            ):
                await consumidor.connect()

            return consumidor

        consumidor = asyncio.run(escenario())
        consumidor.base_send.assert_awaited_once_with(
            {"type": "websocket.close", "code": 1011}
        )

    def test_desconexion_descarta_el_grupo_publico(self):
        async def escenario():
            consumidor = PartidaPublicaConsumer()
            consumidor.group_name = nombre_grupo_partida(20)
            consumidor.channel_layer = self.CapaCanalesPrueba()
            consumidor.channel_name = "canal-prueba"

            await consumidor.disconnect(1000)
            return consumidor

        consumidor = asyncio.run(escenario())
        self.assertEqual(
            consumidor.channel_layer.grupos_descartados,
            [(nombre_grupo_partida(20), "canal-prueba")],
        )

    def test_payload_websocket_no_incluye_privados_y_contiene_resumen_publico(self):
        partida = partida_publica_prueba(bolas=[2, 23], ultima=23)
        partida.idbingadores = (
            '[{"idjugador":41,"tiro_desempate":75,'
            '"codigocarton":"PRIVADO-001"}]'
        )

        payload = construir_payload_publico_partida(
            partida,
            "bola_extraida",
        )
        partida_payload = payload["partida"]
        serializado = json.dumps(payload)

        self.assertEqual(partida_payload["estado"], ESTADO_PARTIDA_EN_CURSO)
        self.assertEqual(partida_payload["ultima_bola"]["codigo"], "I-23")
        self.assertEqual(partida_payload["bolas_extraidas"], [2, 23])
        self.assertEqual(partida_payload["total_extraidas"], 2)
        self.assertEqual(partida_payload["cantidad_extraida"], 2)
        self.assertEqual(partida_payload["restantes"], 73)
        self.assertIsNone(partida_payload["ganador"])
        self.assertNotIn("idbingadores", serializado)
        self.assertNotIn("tiro_desempate", serializado)
        self.assertNotIn("codigocarton", serializado)
        self.assertNotIn("preciopagado", serializado)
        self.assertNotIn("PRIVADO-001", serializado)


class PayloadPublicoTiempoRealTests(SimpleTestCase):
    def test_payload_excluye_datos_privados(self):
        partida = partida_publica_prueba(bolas=[12])
        partida.idbingadores = (
            '[{"idjugador":41,"tiro_desempate":75,'
            '"codigocarton":"PRIVADO-001"}]'
        )
        payload = construir_payload_publico_partida(partida, "actualizacion")
        serializado = json.dumps(payload)

        self.assertNotIn("idbingadores", serializado)
        self.assertNotIn("tiro_desempate", serializado)
        self.assertNotIn("codigocarton", serializado)
        self.assertNotIn("preciopagado", serializado)
        self.assertNotIn("PRIVADO-001", serializado)

    def test_payload_refleja_pausa_reanudacion_y_desempate(self):
        partida = partida_publica_prueba(estado=ESTADO_PARTIDA_PAUSADA)
        pausada = construir_payload_publico_partida(partida, "partida_pausada")
        partida.estadopartida = ESTADO_PARTIDA_EN_CURSO
        reanudada = construir_payload_publico_partida(
            partida,
            "partida_reanudada",
        )
        partida.estadopartida = ESTADO_PARTIDA_DESEMPATE
        partida.idbingadores = '[{"idjugador":41,"tiro_desempate":70}]'
        desempate = construir_payload_publico_partida(
            partida,
            "desempate_detectado",
        )

        self.assertEqual(pausada["partida"]["estado"], ESTADO_PARTIDA_PAUSADA)
        self.assertEqual(reanudada["partida"]["estado"], ESTADO_PARTIDA_EN_CURSO)
        self.assertEqual(desempate["partida"]["estado"], ESTADO_PARTIDA_DESEMPATE)
        self.assertNotIn("idbingadores", desempate["partida"])

    def test_ganador_solo_se_publica_cuando_finaliza(self):
        ganador = Jugador(idjugador=41, aliasjugador="campeon_publico")
        partida = partida_publica_prueba(ganador=ganador)
        en_curso = construir_payload_publico_partida(partida, "ganador_detectado")
        partida.estadopartida = ESTADO_PARTIDA_FINALIZADA
        partida.haydesempate = True
        finalizada = construir_payload_publico_partida(
            partida,
            "desempate_finalizado",
        )

        self.assertIsNone(en_curso["partida"]["ganador"])
        self.assertEqual(finalizada["partida"]["ganador"], "campeon_publico")
        self.assertTrue(finalizada["partida"]["finalizada"])
        self.assertTrue(finalizada["partida"]["resuelta_por_desempate"])

    def test_publicacion_se_difiere_hasta_on_commit(self):
        partida = partida_publica_prueba(bolas=[12])
        callbacks = []
        capa = Mock()
        capa.group_send = AsyncMock()

        with (
            patch(
                "apps.bingos.realtime.transaction.on_commit",
                side_effect=callbacks.append,
            ),
            patch("apps.bingos.realtime.get_channel_layer", return_value=capa),
        ):
            programar_publicacion_partida(partida, "bola_extraida")
            capa.group_send.assert_not_awaited()
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()

        capa.group_send.assert_awaited_once()


class IntegracionPublicacionTiempoRealTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request_con_mensajes(self, path, data=None):
        request = self.factory.post(path, data or {})
        request.user = User(username="admin", is_staff=True)
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_pausar_y_reanudar_publican_el_estado_confirmado(self):
        casos = (
            ("pausar", ESTADO_PARTIDA_EN_CURSO, "partida_pausada"),
            ("reanudar", ESTADO_PARTIDA_PAUSADA, "partida_reanudada"),
        )
        for accion, estado_inicial, evento in casos:
            with self.subTest(accion=accion):
                request = self._request_con_mensajes(
                    "/partidas/20/consola/",
                    {"accion": accion},
                )
                partida = Partidabingo(
                    idpartidabingo=20,
                    estadopartida=estado_inicial,
                    bolascantadas="[]",
                )
                partida.save = Mock()
                with (
                    patch(
                        "apps.bingos.views._base_datos_permite_estado_partida",
                        return_value=True,
                    ),
                    patch(
                        "apps.bingos.views.transaction.atomic",
                        return_value=nullcontext(),
                    ),
                    patch(
                        "apps.bingos.views.programar_publicacion_partida"
                    ) as publicar_mock,
                ):
                    resultado = _procesar_accion_consola(
                        request,
                        partida,
                        accion,
                    )

                self.assertTrue(resultado)
                publicar_mock.assert_called_once_with(partida, evento)

    def test_detectar_desempate_publica_solo_actualizacion_publica(self):
        request = self._request_con_mensajes(
            "/partidas/20/cartones/31/validar/"
        )
        partida = partida_publica_prueba(estado=ESTADO_PARTIDA_DESEMPATE)
        carton = carton_publico_prueba(partida=partida)
        resultado = {
            "resultado": "desempate",
            "partida": partida,
            "carton": carton,
        }
        with (
            patch(
                "apps.bingos.views.get_object_or_404",
                side_effect=[partida, carton],
            ),
            patch(
                "apps.bingos.views.validar_carton_ganador",
                return_value=resultado,
            ),
            patch(
                "apps.bingos.views.programar_publicacion_partida"
            ) as publicar_mock,
        ):
            response = validar_carton(request, 20, 31)

        self.assertEqual(response.status_code, 302)
        publicar_mock.assert_called_once_with(partida, "desempate_detectado")

    def test_confirmar_desempate_publica_finalizacion_con_ganador(self):
        request = self._request_con_mensajes(
            "/partidas/20/desempate/confirmar/"
        )
        partida = partida_publica_prueba(estado=ESTADO_PARTIDA_FINALIZADA)
        confirmacion = {
            "partida": partida,
            "resultado": {
                "idjugador": 41,
                "jugador": "juan123",
                "codigo": "O-67",
            },
        }
        with (
            patch("apps.bingos.views.get_object_or_404", return_value=partida),
            patch(
                "apps.bingos.views.confirmar_y_finalizar_desempate",
                return_value=confirmacion,
            ),
            patch(
                "apps.bingos.views.programar_publicacion_partida"
            ) as publicar_mock,
        ):
            response = confirmar_desempate(request, 20)

        self.assertEqual(response.status_code, 302)
        publicar_mock.assert_called_once_with(
            partida,
            "desempate_finalizado",
            ganador_publico="juan123",
        )

    def test_error_de_transaccion_no_publica_cambio_parcial(self):
        request = self._request_con_mensajes(
            "/partidas/20/consola/",
            {"accion": "pausar"},
        )
        partida = Partidabingo(
            idpartidabingo=20,
            estadopartida=ESTADO_PARTIDA_EN_CURSO,
        )
        partida.save = Mock(side_effect=DatabaseError("fallo simulado"))
        with (
            patch(
                "apps.bingos.views._base_datos_permite_estado_partida",
                return_value=True,
            ),
            patch(
                "apps.bingos.views.transaction.atomic",
                return_value=nullcontext(),
            ),
            patch(
                "apps.bingos.views.programar_publicacion_partida"
            ) as publicar_mock,
        ):
            resultado = _procesar_accion_consola(
                request,
                partida,
                "pausar",
            )

        self.assertFalse(resultado)
        self.assertEqual(partida.estadopartida, ESTADO_PARTIDA_EN_CURSO)
        publicar_mock.assert_not_called()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class PlantillasTiempoRealBingoTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/juego/")
        self.request.user = AnonymousUser()

    def test_tablero_conserva_actualizacion_manual_y_no_agrega_acciones_admin(self):
        partida = partida_publica_prueba(bolas=[1, 23])
        html = render_to_string(
            "bingos/tablero_publico.html",
            {"partida": partida, **preparar_datos_tablero_publico(partida)},
            request=self.request,
        )

        self.assertIn("Actualizar tablero", html)
        self.assertIn("data-realtime-bingo", html)
        self.assertIn("realtime_bingo.js", html)
        self.assertNotIn("Sacar siguiente bola", html)
        self.assertNotIn("Validar cartón", html)

    def test_carton_conserva_actualizacion_manual_sin_reclamo(self):
        partida = partida_publica_prueba(bolas=[1, 23])
        carton = carton_publico_prueba(partida=partida)
        html = render_to_string(
            "bingos/carton_publico.html",
            {
                "partida": partida,
                "carton": carton,
                "error_carton": None,
                **preparar_datos_carton_jugador(carton),
            },
            request=self.request,
        )

        self.assertIn("Actualizar cartón", html)
        self.assertIn("data-carton-cell", html)
        self.assertIn("realtime_bingo.js", html)
        self.assertNotIn("Reclamar", html)
        self.assertNotIn("Validar cartón", html)


class FakeReportQuerySet(list):
    def select_related(self, *fields):
        return self

    def order_by(self, *fields):
        return self

    def filter(self, *args, **kwargs):
        return self


class ReportesAdministrativosTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.bingo = self._bingo()
        self.ganador = Jugador(idjugador=41, aliasjugador="juan123")
        self.partida = self._partida(
            estado=ESTADO_PARTIDA_FINALIZADA,
            ganador=self.ganador,
            hay_desempate=True,
            balota=67,
        )
        self.cartones = [
            self._carton(31, "P20-C-31", self.ganador, Decimal("5.00"), "Vendido"),
            self._carton(32, "P20-C-32", Jugador(idjugador=42, aliasjugador="maria456"), Decimal("5.00"), "Vendido"),
            self._carton(33, "P20-C-33", None, None, "Disponible"),
        ]

    def _request(self, path, user):
        request = self.factory.get(path)
        request.user = user
        return request

    def _staff(self):
        return User(username="admin", is_staff=True)

    def _usuario_normal(self):
        return User(username="usuario", is_staff=False, is_superuser=False)

    def _bingo(self):
        return Bingo(
            idbingo=7,
            titulobingo="Bingo de reportes",
            fechaprogramadabingo=timezone.now(),
            tipobingo="Virtual",
            lugarbingo="CoopBingo",
            preciocarton=Decimal("5.00"),
            premiomayor=Decimal("100.00"),
            descripcionpremiomayor="Premio mayor",
            estadobingo="Programado",
        )

    def _partida(
        self,
        estado=ESTADO_PARTIDA_EN_CURSO,
        ganador=None,
        hay_desempate=False,
        balota=None,
    ):
        return Partidabingo(
            idpartidabingo=20,
            idbingo=self.bingo,
            idjugadorganador=ganador,
            nombreronda="Ronda reportes",
            valorefectivo=Decimal("100.00"),
            premiomaterial="Canasta",
            estadopartida=estado,
            bolascantadas=serializar_bolas_cantadas([1, 16, 31]),
            ultimabola=31,
            haydesempate=hay_desempate,
            idbingadores='[{"privado": "NO_EXPORTAR"}]',
            bolamayordesempate=balota,
            horainicio=timezone.now(),
            horafin=timezone.now() if estado == ESTADO_PARTIDA_FINALIZADA else None,
        )

    def _carton(self, pk, codigo, jugador, precio, estado):
        return Carton(
            idcarton=pk,
            idjugador=jugador,
            idpartida=self.partida,
            codigocarton=codigo,
            matriznumeros=serializar_matriz_carton_bingo(matriz_carton_prueba()),
            indicevictoria=1 if jugador == self.ganador else None,
            preciopagado=precio,
            fechacompra=timezone.now(),
            estadocarton=estado,
        )

    def _patch_partida_reportes(self):
        return (
            patch("apps.bingos.views.get_object_or_404", return_value=self.partida),
            patch(
                "apps.bingos.views.Carton.objects.filter",
                return_value=FakeReportQuerySet(self.cartones),
            ),
        )

    def _patch_bingo_resumen(self):
        return (
            patch("apps.bingos.views.get_object_or_404", return_value=self.bingo),
            patch(
                "apps.bingos.views.Partidabingo.objects.filter",
                return_value=FakeReportQuerySet([self.partida]),
            ),
            patch(
                "apps.bingos.views.Carton.objects.filter",
                return_value=FakeReportQuerySet(self.cartones),
            ),
        )

    def test_anonimo_es_redirigido_al_descargar_reportes(self):
        casos = (
            (partida_reporte_pdf, "/partidas/20/reporte/pdf/", (20,)),
            (partida_cartones_excel, "/partidas/20/cartones/excel/", (20,)),
            (bingo_resumen_excel, "/bingos/7/resumen/excel/", (7,)),
        )
        for view, path, args in casos:
            with self.subTest(path=path):
                response = view(self._request(path, AnonymousUser()), *args)

                self.assertEqual(response.status_code, 302)
                self.assertIn("/login/", response["Location"])

    def test_usuario_normal_y_jugador_reciben_403(self):
        casos = (
            (partida_reporte_pdf, "/partidas/20/reporte/pdf/", (20,)),
            (partida_cartones_excel, "/partidas/20/cartones/excel/", (20,)),
            (bingo_resumen_excel, "/bingos/7/resumen/excel/", (7,)),
        )
        for user in (self._usuario_normal(), User(username="jugador", is_staff=False)):
            for view, path, args in casos:
                with self.subTest(user=user.username, path=path):
                    with self.assertRaises(PermissionDenied):
                        view(self._request(path, user), *args)

    def test_staff_descarga_pdf_de_partida(self):
        reportes_patches = self._patch_partida_reportes()
        with reportes_patches[0], reportes_patches[1]:
            response = partida_reporte_pdf(
                self._request("/partidas/20/reporte/pdf/", self._staff()),
                20,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], PDF_CONTENT_TYPE)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("reporte_partida_20.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_superusuario_descarga_reporte(self):
        superuser = User(username="root", is_superuser=True)
        reportes_patches = self._patch_partida_reportes()
        with reportes_patches[0], reportes_patches[1]:
            response = partida_reporte_pdf(
                self._request("/partidas/20/reporte/pdf/", superuser),
                20,
            )

        self.assertEqual(response.status_code, 200)

    def test_staff_descarga_excel_de_cartones(self):
        reportes_patches = self._patch_partida_reportes()
        with reportes_patches[0], reportes_patches[1]:
            response = partida_cartones_excel(
                self._request("/partidas/20/cartones/excel/", self._staff()),
                20,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX_CONTENT_TYPE)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("cartones_partida_20.xlsx", response["Content-Disposition"])
        workbook = load_workbook(BytesIO(response.content))
        self.assertIn("Cartones", workbook.sheetnames)

    def test_staff_descarga_excel_resumen_de_bingo(self):
        resumen_patches = self._patch_bingo_resumen()
        with resumen_patches[0], resumen_patches[1], resumen_patches[2]:
            response = bingo_resumen_excel(
                self._request("/bingos/7/resumen/excel/", self._staff()),
                7,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], XLSX_CONTENT_TYPE)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("resumen_bingo_7.xlsx", response["Content-Disposition"])
        workbook = load_workbook(BytesIO(response.content))
        self.assertIn("Resumen de partidas", workbook.sheetnames)

    def test_excel_cartones_contiene_headers_resumen_y_no_privados(self):
        contenido = generar_excel_cartones_partida(self.partida, self.cartones)
        workbook = load_workbook(BytesIO(contenido))
        worksheet = workbook["Cartones"]
        headers = [cell.value for cell in worksheet[1]]

        self.assertEqual(
            headers,
            [
                "ID de cartón",
                "Código de cartón",
                "Jugador",
                "Estado del cartón",
                "Fecha de compra",
                "Precio pagado",
                "Índice de victoria",
                "ID de partida",
                "Nombre de ronda",
                "Estado de partida",
            ],
        )
        headers_lower = " ".join(str(header).lower() for header in headers)
        for prohibido in ("correo", "contraseña", "password", "hash", "idbingadores"):
            self.assertNotIn(prohibido, headers_lower)

        resumen = {
            worksheet.cell(row=row, column=1).value: worksheet.cell(row=row, column=2).value
            for row in range(worksheet.max_row - 4, worksheet.max_row + 1)
        }
        self.assertEqual(resumen["Total de cartones"], 3)
        self.assertEqual(resumen["Total recaudado"], 10)
        self.assertEqual(resumen["Cartones vendidos"], 2)
        self.assertEqual(resumen["Cartones disponibles"], 1)

    def test_excel_resumen_bingo_contiene_headers_resumen_y_no_privados(self):
        contenido = generar_excel_resumen_bingo(
            self.bingo,
            [self.partida],
            self.cartones,
        )
        workbook = load_workbook(BytesIO(contenido))
        worksheet = workbook["Resumen de partidas"]
        headers = [cell.value for cell in worksheet[1]]

        self.assertIn("ID de Bingo", headers)
        self.assertIn("Recaudación total", headers)
        self.assertIn("Balota mayor de desempate", headers)
        headers_lower = " ".join(str(header).lower() for header in headers)
        for prohibido in ("correo", "contraseña", "password", "hash", "idbingadores"):
            self.assertNotIn(prohibido, headers_lower)

        resumen = {
            worksheet.cell(row=row, column=1).value: worksheet.cell(row=row, column=2).value
            for row in range(worksheet.max_row - 5, worksheet.max_row + 1)
        }
        self.assertEqual(resumen["Total de partidas"], 1)
        self.assertEqual(resumen["Partidas finalizadas"], 1)
        self.assertEqual(resumen["Total de cartones"], 3)
        self.assertEqual(resumen["Recaudación total"], 10)
        self.assertEqual(resumen["Total de partidas con desempate"], 1)

    def test_generar_reportes_no_modifica_objetos_ni_llama_save(self):
        estado = self.partida.estadopartida
        bolas = self.partida.bolascantadas
        ganador = self.partida.idjugadorganador
        self.partida.save = Mock()
        for carton in self.cartones:
            carton.save = Mock()

        generar_pdf_reporte_partida(self.partida, self.cartones)
        generar_excel_cartones_partida(self.partida, self.cartones)
        generar_excel_resumen_bingo(self.bingo, [self.partida], self.cartones)

        self.partida.save.assert_not_called()
        for carton in self.cartones:
            carton.save.assert_not_called()
        self.assertEqual(self.partida.estadopartida, estado)
        self.assertEqual(self.partida.bolascantadas, bolas)
        self.assertEqual(self.partida.idjugadorganador, ganador)

    def test_datos_partida_finalizada_incluyen_ganador_y_desempate_seguro(self):
        datos = construir_datos_reporte_partida(self.partida, self.cartones)
        pdf = generar_pdf_reporte_partida(self.partida, self.cartones)

        self.assertTrue(datos["finalizada"])
        self.assertEqual(datos["ganador"], "juan123")
        self.assertEqual(datos["carton_ganador"], "P20-C-31")
        self.assertTrue(datos["hubo_desempate"])
        self.assertEqual(datos["balota_mayor_desempate"], "O-67")
        self.assertNotIn("idbingadores", datos)
        self.assertIn(b"juan123", pdf)
        self.assertNotIn(b"NO_EXPORTAR", pdf)
        self.assertNotIn(b"idbingadores", pdf)

    def test_datos_partida_no_finalizada_no_inventan_ganador(self):
        partida = self._partida(
            estado=ESTADO_PARTIDA_EN_CURSO,
            ganador=self.ganador,
            hay_desempate=False,
        )
        datos = construir_datos_reporte_partida(partida, self.cartones)

        self.assertFalse(datos["finalizada"])
        self.assertIsNone(datos["ganador"])
        self.assertIsNone(datos["carton_ganador"])
        self.assertEqual(datos["mensaje_resultado"], "La partida aún no está finalizada.")
