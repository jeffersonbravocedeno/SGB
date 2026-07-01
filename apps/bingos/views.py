import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.http import Http404, HttpResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.common.decorators import admin_required
from apps.common.ids import save_new_model_form
from apps.common.views import paginate
from apps.jugadores.services import jugador_required

from .forms import (
    AccesoCartonPublicoForm,
    BingoForm,
    CartonForm,
    CartonPartidaForm,
    GenerarAsignarCartonForm,
    GenerarCartonBingoForm,
    PartidaBingoForm,
)
from .models import Bingo, Carton, CartonPartidaBingo, Partidabingo, Sesionjuego
from .realtime import programar_publicacion_partida
from .reportes import (
    PDF_CONTENT_TYPE,
    XLSX_CONTENT_TYPE,
    generar_excel_cartones_partida,
    generar_excel_resumen_bingo,
    generar_pdf_reporte_partida,
    nombre_archivo_seguro,
)
from .services import (
    ACCIONES_CONSOLA,
    BolaBingoError,
    CartonPublicoError,
    CartonAsignacionError,
    DesempateError,
    ESTADO_PARTIDA_CANCELADA,
    ESTADO_PARTIDA_DESEMPATE,
    ESTADO_PARTIDA_EN_CURSO,
    ESTADO_PARTIDA_EN_ESPERA,
    ESTADO_PARTIDA_FINALIZADA,
    ESTADO_PARTIDA_PAUSADA,
    ESTADO_PARTIDA_PROGRAMADA,
    ESTADOS_PARTIDA_VALORES,
    EstadoPartidaError,
    MatrizCartonInvalidaError,
    ValidacionCartonError,
    acciones_disponibles_consola,
    confirmar_y_finalizar_desempate,
    construir_matriz_marcada_carton,
    contar_numeros_marcados_carton,
    crear_carton_maestro_para_bingo,
    crear_y_asignar_carton,
    deserializar_matriz_carton_bingo,
    extraer_siguiente_bola,
    formatear_bola_bingo,
    mensaje_estado_carton_publico,
    normalizar_estado_partida,
    obtener_numeros_faltantes_carton,
    obtener_participaciones_hibridas_partida,
    parse_bolas_cantadas,
    parsear_candidatos_desempate,
    preparar_cartones_para_validacion,
    preparar_datos_carton_jugador,
    preparar_datos_desempate,
    preparar_datos_bolas_partida,
    preparar_datos_tablero_publico,
    preparar_participaciones_hibridas_para_consola,
    preparar_resumen_partida_publica,
    puede_asignar_cartones,
    estado_permite_validar_carton,
    preparar_accion_consola,
    sortear_balota_desempate,
    validar_carton_ganador,
    validar_participacion_ganadora,
    validar_asignacion_cartones,
)


logger = logging.getLogger(__name__)


@require_GET
def sala_juego_publica(request):
    partidas = list(
        Partidabingo.objects.select_related("idbingo")
        .order_by("-horainicio", "idpartidabingo")
    )
    return render(
        request,
        "bingos/sala_juego_publica.html",
        {
            "partidas_publicas": [
                preparar_resumen_partida_publica(partida)
                for partida in partidas
            ]
        },
    )


@require_GET
def tablero_publico(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo.objects.select_related("idbingo", "idjugadorganador"),
        idpartidabingo=idpartidabingo,
    )
    return render(
        request,
        "bingos/tablero_publico.html",
        {
            "partida": partida,
            **preparar_datos_tablero_publico(partida),
        },
    )


@require_http_methods(["GET", "POST"])
def acceder_carton_publico(request):
    form = AccesoCartonPublicoForm(
        request.POST if request.method == "POST" else None
    )
    if request.method == "POST" and form.is_valid():
        codigo = form.cleaned_data["codigocarton"]
        if Carton.objects.filter(codigocarton=codigo).exists():
            return redirect(
                "bingos:carton_publico",
                codigocarton=codigo,
            )
        form.add_error(
            "codigocarton",
            "No encontramos un cartón con ese código. Verifique e intente nuevamente.",
        )
    return render(
        request,
        "bingos/carton_acceso_publico.html",
        {"form": form},
    )


@require_GET
def carton_publico(request, codigocarton):
    carton = (
        Carton.objects.select_related(
            "idjugador",
            "idbingo",
            "idpartida",
            "idpartida__idbingo",
        )
        .filter(codigocarton=codigocarton)
        .first()
    )
    if carton is None:
        form = AccesoCartonPublicoForm(
            {"codigocarton": codigocarton}
        )
        form.is_valid()
        form.add_error(
            "codigocarton",
            "No encontramos un cartón con ese código. Verifique e intente nuevamente.",
        )
        return render(
            request,
            "bingos/carton_acceso_publico.html",
            {"form": form},
            status=404,
        )

    error_carton = None
    es_hibrido = carton.idpartida_id is None
    partida_carton = carton.idpartida
    participacion_seleccionada = None
    participaciones_disponibles = []
    datos_carton = _datos_carton_vacios(partida_carton)
    try:
        if es_hibrido:
            participaciones_disponibles = _participaciones_hibridas_carton(
                carton
            )
            participacion_seleccionada = _seleccionar_participacion_hibrida(
                participaciones_disponibles,
                request.GET.get("partida"),
            )
            partida_carton = participacion_seleccionada.idpartida
            datos_carton = _preparar_datos_carton_hibrido(
                carton,
                partida_carton,
            )
        else:
            datos_carton = preparar_datos_carton_jugador(carton)
    except MatrizCartonInvalidaError as exc:
        logger.warning(
            "Matriz inválida en consulta pública de cartón %s: %s",
            carton.pk,
            exc,
        )
        error_carton = (
            "La matriz de este cartón no está disponible. "
            "Solicite ayuda al operador."
        )
    except CartonPublicoError as exc:
        logger.warning(
            "Cartón %s no disponible para consulta pública: %s",
            carton.pk,
            exc,
        )
        error_carton = str(exc)

    return render(
        request,
        "bingos/carton_publico.html",
        {
            "carton": carton,
            "partida": partida_carton,
            "es_hibrido": es_hibrido,
            "participacion_seleccionada": participacion_seleccionada,
            "participaciones_disponibles": participaciones_disponibles,
            "error_carton": error_carton,
            **datos_carton,
        },
    )


@jugador_required
@require_GET
def mis_cartones(request):
    jugador = request.jugador
    cartones = (
        Carton.objects.filter(idjugador=jugador)
        .select_related("idbingo", "idpartida", "idpartida__idbingo")
        .order_by("-fechacompra", "codigocarton")
    )
    return render(
        request,
        "bingos/mis_cartones.html",
        {
            "jugador": jugador,
            "cartones_resumen": [
                _resumen_carton_privado(carton)
                for carton in cartones
            ],
        },
    )


@jugador_required
@require_GET
def mi_carton_detalle(request, codigocarton):
    jugador = request.jugador
    carton = (
        Carton.objects.select_related(
            "idjugador",
            "idbingo",
            "idpartida",
            "idpartida__idbingo",
        )
        .filter(codigocarton=codigocarton, idjugador=jugador)
        .first()
    )
    if carton is None:
        raise Http404("Cartón no encontrado.")

    error_carton = None
    es_hibrido = carton.idpartida_id is None
    partida_carton = carton.idpartida
    participacion_seleccionada = None
    participaciones_disponibles = []
    datos_carton = _datos_carton_vacios(partida_carton)
    try:
        if es_hibrido:
            participaciones_disponibles = _participaciones_hibridas_carton(
                carton
            )
            participacion_seleccionada = _seleccionar_participacion_hibrida(
                participaciones_disponibles,
                request.GET.get("partida"),
            )
            partida_carton = participacion_seleccionada.idpartida
            datos_carton = _preparar_datos_carton_hibrido(
                carton,
                partida_carton,
            )
        else:
            datos_carton = preparar_datos_carton_jugador(carton)
    except MatrizCartonInvalidaError as exc:
        logger.warning(
            "Matriz inválida en cartón privado %s: %s",
            carton.pk,
            exc,
        )
        error_carton = (
            "La matriz de este cartón no está disponible. "
            "Solicite ayuda al operador."
        )
    except CartonPublicoError as exc:
        logger.warning(
            "Cartón privado %s no disponible: %s",
            carton.pk,
            exc,
        )
        error_carton = str(exc)

    return render(
        request,
        "bingos/mi_carton_detalle.html",
        {
            "jugador": jugador,
            "carton": carton,
            "partida": partida_carton,
            "es_hibrido": es_hibrido,
            "participacion_seleccionada": participacion_seleccionada,
            "participaciones_disponibles": participaciones_disponibles,
            "error_carton": error_carton,
            **datos_carton,
        },
    )


def _resumen_carton_privado(carton):
    partida = carton.idpartida
    resumen = {
        "carton": carton,
        "partida": partida,
        "bingo": partida.idbingo if partida is not None else None,
        "tipo_carton": "historico" if partida is not None else "hibrido",
        "total_rondas": 1 if partida is not None else 0,
        "estado_participacion": None,
        "ultima_bola_codigo": None,
        "numeros_marcados": 0,
        "total_numeros_carton": 24,
        "progreso": 0,
        "error": None,
    }
    if partida is None:
        try:
            participaciones = _participaciones_hibridas_carton(carton)
            participacion = _seleccionar_participacion_hibrida(
                participaciones,
                None,
            )
            partida = participacion.idpartida
            resumen.update(
                {
                    "partida": partida,
                    "bingo": carton.idbingo,
                    "total_rondas": len(participaciones),
                    "estado_participacion": (
                        participacion.estado_participacion
                    ),
                }
            )
            datos_carton = _preparar_datos_carton_hibrido(carton, partida)
        except (MatrizCartonInvalidaError, CartonPublicoError) as exc:
            resumen["error"] = str(exc)
            return resumen
    else:
        try:
            datos_carton = preparar_datos_carton_jugador(carton)
        except (MatrizCartonInvalidaError, CartonPublicoError) as exc:
            resumen["ultima_bola_codigo"] = preparar_datos_bolas_partida(partida)[
                "ultima_bola_codigo"
            ]
            resumen["error"] = str(exc)
            return resumen

    total = datos_carton["total_numeros_carton"] or 24
    marcados = datos_carton["numeros_marcados"]
    resumen.update(
        {
            "ultima_bola_codigo": datos_carton["ultima_bola_codigo"],
            "numeros_marcados": marcados,
            "total_numeros_carton": total,
            "progreso": round((marcados / total) * 100) if total else 0,
        }
    )
    return resumen


def _datos_carton_vacios(partida=None):
    return {
        "matriz_carton": None,
        "numeros_marcados": 0,
        "total_numeros_carton": 24,
        "numeros_faltantes": [],
        "ultima_bola_codigo": (
            preparar_datos_bolas_partida(partida)["ultima_bola_codigo"]
            if partida is not None
            else None
        ),
        "mensaje_estado_carton": (
            mensaje_estado_carton_publico(partida.estadopartida)
            if partida is not None
            else None
        ),
    }


def _participaciones_hibridas_carton(carton):
    if carton.idpartida_id is not None:
        return []

    participaciones = getattr(
        carton,
        "participaciones_hibridas_cargadas",
        None,
    )
    if participaciones is None:
        participaciones = list(
            CartonPartidaBingo.objects.filter(idcarton=carton)
            .select_related(
                "idcarton",
                "idcarton__idjugador",
                "idcarton__idbingo",
                "idpartida",
                "idpartida__idbingo",
                "idbingo",
            )
            .order_by("idcartonpartidabingo")
        )
    else:
        participaciones = list(participaciones)

    if not participaciones:
        raise CartonPublicoError(
            "Este cartón no tiene rondas disponibles."
        )

    idbingo_carton = carton.idbingo_id
    for participacion in participaciones:
        if (
            participacion.idcarton_id != carton.pk
            or participacion.idbingo_id != idbingo_carton
            or participacion.idpartida.idbingo_id != idbingo_carton
        ):
            raise CartonPublicoError(
                "La ronda del cartón no pertenece al mismo Bingo."
            )
    return participaciones


def _seleccionar_participacion_hibrida(participaciones, partida_solicitada):
    if partida_solicitada is not None:
        valor = str(partida_solicitada).strip()
        if not valor.isdigit() or int(valor) <= 0:
            raise Http404("Ronda no válida para este cartón.")
        idpartida = int(valor)
        participacion = next(
            (
                item
                for item in participaciones
                if item.idpartida_id == idpartida
            ),
            None,
        )
        if participacion is None:
            raise Http404("Ronda no encontrada para este cartón.")
        return participacion

    prioridades = (
        ESTADO_PARTIDA_EN_CURSO,
        ESTADO_PARTIDA_PAUSADA,
        ESTADO_PARTIDA_DESEMPATE,
        ESTADO_PARTIDA_EN_ESPERA,
        ESTADO_PARTIDA_PROGRAMADA,
        ESTADO_PARTIDA_FINALIZADA,
        ESTADO_PARTIDA_CANCELADA,
    )
    for estado in prioridades:
        candidatas = [
            item
            for item in participaciones
            if normalizar_estado_partida(item.idpartida.estadopartida) == estado
        ]
        if not candidatas:
            continue
        if estado in {ESTADO_PARTIDA_FINALIZADA, ESTADO_PARTIDA_CANCELADA}:
            return max(candidatas, key=_clave_participacion_reciente)
        return min(candidatas, key=lambda item: item.pk)
    return min(participaciones, key=lambda item: item.pk)


def _clave_participacion_reciente(participacion):
    partida = participacion.idpartida
    fecha = partida.horafin or partida.horainicio
    try:
        valor_fecha = fecha.timestamp() if fecha is not None else float("-inf")
    except (AttributeError, OSError, OverflowError, ValueError):
        valor_fecha = float("-inf")
    return valor_fecha, participacion.pk


def _preparar_datos_carton_hibrido(carton, partida):
    matriz = construir_matriz_marcada_carton(
        carton.matriznumeros,
        partida.bolascantadas,
    )
    faltantes = obtener_numeros_faltantes_carton(
        carton.matriznumeros,
        partida.bolascantadas,
    )
    datos_bolas = preparar_datos_bolas_partida(partida)
    return {
        "matriz_carton": matriz,
        "numeros_marcados": contar_numeros_marcados_carton(
            carton.matriznumeros,
            partida.bolascantadas,
        ),
        "total_numeros_carton": 24,
        "numeros_faltantes": faltantes,
        "ultima_bola_codigo": datos_bolas["ultima_bola_codigo"],
        "mensaje_estado_carton": mensaje_estado_carton_publico(
            partida.estadopartida
        ),
    }


@admin_required
def bingos_lista(request):
    busqueda = request.GET.get("q", "").strip()
    bingos = Bingo.objects.order_by("-fechaprogramadabingo")
    if busqueda:
        bingos = bingos.filter(
            Q(titulobingo__icontains=busqueda)
            | Q(estadobingo__icontains=busqueda)
            | Q(fechaprogramadabingo__icontains=busqueda)
        )
    return render(
        request,
        "bingos/lista.html",
        {"page_obj": paginate(request, bingos), "busqueda": busqueda, "total": bingos.count()},
    )


@admin_required
def bingo_nuevo(request):
    if request.method == "POST":
        form = BingoForm(request.POST)
        if form.is_valid():
            try:
                bingo = save_new_model_form(form)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Bingo registrado correctamente.")
                return redirect("bingos:detalle", idbingo=bingo.idbingo)
    else:
        form = BingoForm(initial={"estadobingo": "Programado"})
    return render(request, "bingos/formulario.html", {"form": form, "titulo": "Nuevo bingo"})


@admin_required
def bingo_detalle(request, idbingo):
    bingo = get_object_or_404(Bingo, idbingo=idbingo)
    partidas = Partidabingo.objects.filter(idbingo=bingo).select_related("idjugadorganador").order_by("horainicio")
    cartones = Carton.objects.filter(idpartida__idbingo=bingo).select_related("idjugador", "idpartida").order_by("codigocarton")[:50]
    return render(
        request,
        "bingos/detalle.html",
        {"bingo": bingo, "partidas": partidas, "cartones": cartones},
    )


@admin_required
def bingo_carton_nuevo(request, idbingo):
    bingo = get_object_or_404(Bingo, idbingo=idbingo)
    if request.method == "POST":
        form = GenerarCartonBingoForm(request.POST)
        if form.is_valid():
            try:
                carton = crear_carton_maestro_para_bingo(
                    bingo=bingo,
                    jugador=form.cleaned_data["idjugador"],
                    precio_pagado=form.cleaned_data["preciopagado"],
                    fecha_compra=None,
                )
            except CartonAsignacionError as exc:
                form.add_error(None, str(exc))
            except (IntegrityError, ValidationError):
                logger.exception(
                    "No fue posible validar o guardar el cartón maestro del Bingo %s",
                    bingo.idbingo,
                )
                form.add_error(
                    None,
                    "No fue posible generar el cartón para todo el Bingo. "
                    "No se creó ningún registro.",
                )
            except DatabaseError:
                logger.exception(
                    "No fue posible guardar el cartón maestro del Bingo %s",
                    bingo.idbingo,
                )
                form.add_error(
                    None,
                    "No fue posible completar la venta. No se creó ningún registro.",
                )
            else:
                total_participaciones = CartonPartidaBingo.objects.filter(
                    idcarton=carton
                ).count()
                texto_participaciones = (
                    "1 participación"
                    if total_participaciones == 1
                    else f"{total_participaciones} participaciones"
                )
                messages.success(
                    request,
                    "Se creó un cartón maestro para todo el Bingo y "
                    f"{texto_participaciones}, una por cada ronda actual.",
                )
                return redirect("bingos:detalle", idbingo=bingo.idbingo)
    else:
        form = GenerarCartonBingoForm(
            initial={"preciopagado": bingo.preciocarton}
        )

    total_partidas = Partidabingo.objects.filter(idbingo=bingo).count()
    return render(
        request,
        "bingos/bingo_carton_generar.html",
        {
            "form": form,
            "bingo": bingo,
            "total_partidas": total_partidas,
            "titulo": "Vender cartón para todo el Bingo",
        },
    )


@admin_required
def bingo_resumen_excel(request, idbingo):
    bingo = get_object_or_404(Bingo, idbingo=idbingo)
    partidas = list(
        Partidabingo.objects.filter(idbingo=bingo)
        .select_related("idjugadorganador")
        .order_by("horainicio", "idpartidabingo")
    )
    cartones = list(
        Carton.objects.filter(idpartida__in=partidas)
        .select_related("idpartida", "idjugador")
        .order_by("idpartida_id", "idcarton")
    )
    contenido = generar_excel_resumen_bingo(bingo, partidas, cartones)
    return _attachment_response(
        contenido,
        XLSX_CONTENT_TYPE,
        nombre_archivo_seguro("resumen_bingo", bingo.idbingo, "xlsx"),
    )


@admin_required
def bingo_editar(request, idbingo):
    bingo = get_object_or_404(Bingo, idbingo=idbingo)
    if request.method == "POST":
        form = BingoForm(request.POST, instance=bingo)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Bingo actualizado correctamente.")
                return redirect("bingos:detalle", idbingo=bingo.idbingo)
    else:
        form = BingoForm(instance=bingo)
    return render(request, "bingos/formulario.html", {"form": form, "bingo": bingo, "titulo": "Editar bingo"})


@admin_required
def partidas_lista(request):
    busqueda = request.GET.get("q", "").strip()
    partidas = (
        Partidabingo.objects.select_related("idbingo", "idjugadorganador")
        .order_by("-horainicio", "nombreronda")
    )
    if busqueda:
        partidas = partidas.filter(
            Q(nombreronda__icontains=busqueda)
            | Q(estadopartida__icontains=busqueda)
            | Q(idbingo__titulobingo__icontains=busqueda)
            | Q(idjugadorganador__aliasjugador__icontains=busqueda)
        )
    return render(
        request,
        "bingos/partidas_lista.html",
        {
            "page_obj": paginate(request, partidas),
            "busqueda": busqueda,
            "total": partidas.count(),
        },
    )


@admin_required
def partida_nueva(request, idbingo):
    bingo = get_object_or_404(Bingo, idbingo=idbingo)
    if request.method == "POST":
        form = PartidaBingoForm(request.POST)
        if form.is_valid():
            def before_save(partida):
                partida.idbingo = bingo

            try:
                partida = save_new_model_form(form, before_save=before_save)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Partida registrada correctamente.")
                return redirect("bingos:partida_detalle", idpartidabingo=partida.idpartidabingo)
    else:
        form = PartidaBingoForm(
            initial={
                "estadopartida": ESTADO_PARTIDA_PROGRAMADA,
                "bolascantadas": "[]",
                "ultimabola": 0,
                "haydesempate": False,
                "horainicio": timezone.now(),
            }
        )
    return render(request, "bingos/partida_formulario.html", {"form": form, "bingo": bingo, "titulo": "Nueva partida"})


@admin_required
def partida_detalle(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo.objects.select_related("idbingo", "idjugadorganador"),
        idpartidabingo=idpartidabingo,
    )
    cartones = Carton.objects.filter(idpartida=partida).select_related("idjugador").order_by("codigocarton")
    carton_generado = None
    matriz_carton_generado = None
    carton_generado_id = request.GET.get("carton_generado", "").strip()
    if carton_generado_id.isdigit():
        carton_generado = (
            Carton.objects.filter(
                idcarton=int(carton_generado_id),
                idpartida=partida,
            )
            .select_related("idjugador")
            .first()
        )
        if carton_generado:
            matriz_carton_generado = deserializar_matriz_carton_bingo(
                carton_generado.matriznumeros
            )
    return render(
        request,
        "bingos/partida_detalle.html",
        {
            "partida": partida,
            "cartones": cartones,
            "bolas_cantadas": parse_bolas_cantadas(partida.bolascantadas),
            "puede_asignar_cartones": puede_asignar_cartones(partida),
            "carton_generado": carton_generado,
            "matriz_carton_generado": matriz_carton_generado,
        },
    )


@admin_required
def partida_reporte_pdf(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo.objects.select_related("idbingo", "idjugadorganador"),
        idpartidabingo=idpartidabingo,
    )
    cartones = list(
        Carton.objects.filter(idpartida=partida)
        .select_related("idjugador")
        .order_by("codigocarton")
    )
    contenido = generar_pdf_reporte_partida(partida, cartones=cartones)
    return _attachment_response(
        contenido,
        PDF_CONTENT_TYPE,
        nombre_archivo_seguro("reporte_partida", partida.idpartidabingo, "pdf"),
    )


@admin_required
def partida_cartones_excel(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo.objects.select_related("idbingo"),
        idpartidabingo=idpartidabingo,
    )
    cartones = list(
        Carton.objects.filter(idpartida=partida)
        .select_related("idjugador")
        .order_by("codigocarton")
    )
    contenido = generar_excel_cartones_partida(partida, cartones)
    return _attachment_response(
        contenido,
        XLSX_CONTENT_TYPE,
        nombre_archivo_seguro("cartones_partida", partida.idpartidabingo, "xlsx"),
    )


@admin_required
def partida_editar(request, idpartidabingo):
    partida = get_object_or_404(Partidabingo.objects.select_related("idbingo"), idpartidabingo=idpartidabingo)
    if request.method == "POST":
        form = PartidaBingoForm(request.POST, instance=partida)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Partida actualizada correctamente.")
                return redirect("bingos:partida_detalle", idpartidabingo=partida.idpartidabingo)
    else:
        form = PartidaBingoForm(instance=partida)
    return render(request, "bingos/partida_formulario.html", {"form": form, "partida": partida, "bingo": partida.idbingo, "titulo": "Editar partida"})


@admin_required
def partida_carton_nuevo(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo.objects.select_related("idbingo"),
        idpartidabingo=idpartidabingo,
    )

    if not puede_asignar_cartones(partida):
        try:
            validar_asignacion_cartones(partida)
        except CartonAsignacionError as exc:
            messages.error(request, str(exc))
        return redirect(
            "bingos:partida_detalle",
            idpartidabingo=partida.idpartidabingo,
        )

    if request.method == "POST":
        form = GenerarAsignarCartonForm(request.POST)
        if form.is_valid():
            try:
                carton = crear_y_asignar_carton(
                    partida=partida,
                    jugador=form.cleaned_data["idjugador"],
                    precio_pagado=form.cleaned_data["preciopagado"],
                )
            except CartonAsignacionError as exc:
                messages.error(request, str(exc))
                return redirect(
                    "bingos:partida_detalle",
                    idpartidabingo=partida.idpartidabingo,
                )
            except (IntegrityError, ValidationError):
                logger.exception(
                    "No fue posible validar o guardar el cartón para la partida %s",
                    partida.idpartidabingo,
                )
                form.add_error(
                    None,
                    "No fue posible generar un cartón completo y único. No se creó ningún cartón.",
                )
            except DatabaseError:
                logger.exception(
                    "No fue posible guardar el cartón para la partida %s",
                    partida.idpartidabingo,
                )
                form.add_error(
                    None,
                    "No fue posible generar el cartón. No se creó ningún cartón.",
                )
            else:
                messages.success(
                    request,
                    f"Cartón {carton.codigocarton} generado y asignado correctamente.",
                )
                detalle_url = reverse(
                    "bingos:partida_detalle",
                    kwargs={"idpartidabingo": partida.idpartidabingo},
                )
                return redirect(
                    f"{detalle_url}?carton_generado={carton.idcarton}"
                )
    else:
        form = GenerarAsignarCartonForm(
            initial={
                "preciopagado": partida.idbingo.preciocarton,
            }
        )
    return render(
        request,
        "bingos/partida_carton_generar.html",
        {
            "form": form,
            "partida": partida,
            "titulo": "Generar y asignar cartón",
        },
    )


@admin_required
def partida_carton_editar(request, idpartidabingo, idcarton):
    partida = get_object_or_404(
        Partidabingo.objects.select_related("idbingo"),
        idpartidabingo=idpartidabingo,
    )
    carton = get_object_or_404(Carton, idcarton=idcarton, idpartida=partida)
    if request.method == "POST":
        form = CartonPartidaForm(request.POST, instance=carton)
        if form.is_valid():
            try:
                with transaction.atomic():
                    carton = form.save(commit=False)
                    carton.idpartida = partida
                    carton.save()
                    form.save_m2m()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Cartón actualizado correctamente.")
                return redirect("bingos:partida_detalle", idpartidabingo=partida.idpartidabingo)
    else:
        form = CartonPartidaForm(instance=carton)
    return render(
        request,
        "bingos/partida_carton_formulario.html",
        {
            "form": form,
            "partida": partida,
            "carton": carton,
            "titulo": "Editar cartón de partida",
        },
    )


@admin_required
def consola_operador(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo.objects.select_related("idbingo", "idjugadorganador"),
        idpartidabingo=idpartidabingo,
    )

    if request.method == "POST":
        accion = request.POST.get("accion", "").strip()
        if _procesar_accion_consola(request, partida, accion):
            return redirect("bingos:consola_operador", idpartidabingo=partida.idpartidabingo)

    acciones_disponibles = acciones_disponibles_consola(partida)
    acciones_consola = []
    actualizacion_estados_pendiente = False
    for accion, config in ACCIONES_CONSOLA.items():
        disponible_por_estado = accion in acciones_disponibles
        requiere_actualizacion = (
            disponible_por_estado
            and not _base_datos_permite_estado_partida(config["target"])
        )
        if requiere_actualizacion:
            actualizacion_estados_pendiente = True
        acciones_consola.append(
            (
                accion,
                config["label"],
                disponible_por_estado and not requiere_actualizacion,
                requiere_actualizacion,
            )
        )
    cartones = list(
        Carton.objects.filter(idpartida=partida)
        .select_related("idjugador")
        .order_by("codigocarton")
    )
    error_participaciones_hibridas = None
    try:
        participaciones_hibridas = obtener_participaciones_hibridas_partida(
            partida
        )
        participaciones_hibridas_validacion = (
            preparar_participaciones_hibridas_para_consola(
                partida,
                participaciones=participaciones_hibridas,
            )
        )
    except ValidacionCartonError as exc:
        logger.warning(
            "No fue posible preparar participaciones híbridas de la partida %s: %s",
            partida.idpartidabingo,
            exc,
        )
        error_participaciones_hibridas = str(exc)
        participaciones_hibridas = []
        participaciones_hibridas_validacion = []
    datos_bolas = preparar_datos_bolas_partida(partida)
    return render(
        request,
        "bingos/consola_operador.html",
        {
            "partida": partida,
            "acciones_consola": acciones_consola,
            "actualizacion_estados_pendiente": actualizacion_estados_pendiente,
            "bolas_cantadas": parse_bolas_cantadas(partida.bolascantadas),
            "cartones": cartones,
            "participaciones_hibridas": participaciones_hibridas,
            "participaciones_hibridas_validacion": (
                participaciones_hibridas_validacion
            ),
            "error_participaciones_hibridas": error_participaciones_hibridas,
            "puede_asignar_cartones": puede_asignar_cartones(partida),
            "puede_validar_cartones": estado_permite_validar_carton(partida),
            "cartones_validacion": preparar_cartones_para_validacion(
                partida,
                cartones,
            ),
            "candidatos_desempate": parsear_candidatos_desempate(
                partida.idbingadores
            ),
            **datos_bolas,
        },
    )


@admin_required
@require_GET
def desempate_operador(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo.objects.select_related("idbingo", "idjugadorganador"),
        idpartidabingo=idpartidabingo,
    )
    error_desempate = None
    try:
        datos_desempate = preparar_datos_desempate(partida)
    except DesempateError as exc:
        logger.warning(
            "No fue posible preparar el desempate de la partida %s: %s",
            partida.idpartidabingo,
            exc,
        )
        error_desempate = str(exc)
        datos_desempate = {
            "candidatos_desempate": [],
            "total_candidatos": 0,
            "total_pendientes": 0,
            "desempate_completo": False,
            "resultado_desempate": None,
            "puede_operar_desempate": False,
            "puede_confirmar_desempate": False,
        }
    return render(
        request,
        "bingos/desempate_operador.html",
        {
            "partida": partida,
            "error_desempate": error_desempate,
            **datos_desempate,
        },
    )


@admin_required
@require_POST
def sortear_desempate(request, idpartidabingo, idjugador):
    partida = get_object_or_404(
        Partidabingo,
        idpartidabingo=idpartidabingo,
    )
    try:
        resultado = sortear_balota_desempate(partida, idjugador)
    except DesempateError as exc:
        messages.error(request, str(exc))
    except DatabaseError:
        logger.exception(
            "No fue posible sortear la balota para jugador %s en partida %s",
            idjugador,
            partida.idpartidabingo,
        )
        messages.error(
            request,
            "No fue posible registrar el tiro. No se guardaron cambios parciales.",
        )
    else:
        nombre = resultado["candidato"]["jugador"] or f"Jugador #{idjugador}"
        messages.success(
            request,
            f"{nombre} obtuvo la balota {resultado['codigo']}.",
        )
    return redirect(
        "bingos:desempate_operador",
        idpartidabingo=partida.idpartidabingo,
    )


@admin_required
@require_POST
def confirmar_desempate(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo,
        idpartidabingo=idpartidabingo,
    )
    try:
        confirmacion = confirmar_y_finalizar_desempate(partida)
    except DesempateError as exc:
        messages.error(request, str(exc))
    except DatabaseError:
        logger.exception(
            "No fue posible confirmar el desempate de la partida %s",
            partida.idpartidabingo,
        )
        messages.error(
            request,
            "No fue posible finalizar el desempate. No se guardaron cambios parciales.",
        )
    else:
        resultado = confirmacion["resultado"]
        nombre = resultado["jugador"] or f"Jugador #{resultado['idjugador']}"
        programar_publicacion_partida(
            confirmacion["partida"],
            "desempate_finalizado",
            ganador_publico=nombre,
        )
        messages.success(
            request,
            f"Ganador confirmado: {nombre} con {resultado['codigo']}.",
        )
    return redirect(
        "bingos:desempate_operador",
        idpartidabingo=partida.idpartidabingo,
    )


@admin_required
@require_POST
def sacar_bola(request, idpartidabingo):
    partida = get_object_or_404(
        Partidabingo,
        idpartidabingo=idpartidabingo,
    )
    try:
        nueva_bola = extraer_siguiente_bola(partida)
    except BolaBingoError as exc:
        messages.error(request, str(exc))
    except DatabaseError:
        logger.exception(
            "No fue posible extraer una bola para la partida %s",
            partida.idpartidabingo,
        )
        messages.error(
            request,
            "No fue posible sacar la siguiente bola. La partida no fue modificada.",
        )
    else:
        programar_publicacion_partida(partida, "bola_extraida")
        messages.success(
            request,
            f"Bola {formatear_bola_bingo(nueva_bola)} extraída correctamente.",
        )

    return redirect(
        "bingos:consola_operador",
        idpartidabingo=partida.idpartidabingo,
    )


@admin_required
@require_POST
def validar_carton(request, idpartidabingo, idcarton):
    partida = get_object_or_404(
        Partidabingo,
        idpartidabingo=idpartidabingo,
    )
    carton = get_object_or_404(
        Carton,
        idcarton=idcarton,
    )
    es_hibrido = carton.idpartida_id is None
    if not es_hibrido and carton.idpartida_id != partida.pk:
        raise Http404("El cartón no pertenece a la partida indicada.")
    try:
        if es_hibrido:
            resultado = validar_participacion_ganadora(
                partida=partida,
                carton=carton,
                indicevictoria=len(
                    parse_bolas_cantadas(partida.bolascantadas)
                ),
            )
        else:
            resultado = validar_carton_ganador(partida, carton)
    except ValidacionCartonError as exc:
        messages.error(request, str(exc))
    except DatabaseError:
        logger.exception(
            "No fue posible validar el cartón %s de la partida %s",
            carton.idcarton,
            partida.idpartidabingo,
        )
        messages.error(
            request,
            "No fue posible validar el cartón. No se guardaron cambios parciales.",
        )
    else:
        if resultado["resultado"] == "desempate":
            programar_publicacion_partida(
                resultado["partida"],
                "desempate_detectado",
            )
            messages.warning(
                request,
                "Se detectaron varios cartones ganadores. La partida pasó a Desempate.",
            )
        else:
            programar_publicacion_partida(
                resultado["partida"],
                "ganador_detectado",
            )
            if es_hibrido:
                messages.success(
                    request,
                    (
                        f"El cartón {carton.codigocarton} ganó la ronda "
                        f"{partida.nombreronda}."
                    ),
                )
            else:
                messages.success(
                    request,
                    (
                        f"Bingo confirmado para {resultado['carton'].idjugador} "
                        f"con el cartón {resultado['carton'].codigocarton}."
                    ),
                )

    return redirect(
        "bingos:consola_operador",
        idpartidabingo=partida.idpartidabingo,
    )


def _procesar_accion_consola(request, partida, accion):
    try:
        cambios = preparar_accion_consola(partida, accion)
    except EstadoPartidaError as exc:
        messages.error(request, str(exc))
        return False

    estado_destino = cambios.get("estadopartida")
    if estado_destino and not _base_datos_permite_estado_partida(estado_destino):
        messages.error(
            request,
            (
                "Esta acción requiere actualizar la restricción de estados en "
                "PostgreSQL. Revise y ejecute manualmente "
                "DATABASE/actualizar_estados_partidabingo.sql antes de continuar."
            ),
        )
        return False

    valores_originales = {
        field_name: getattr(partida, field_name, None)
        for field_name in cambios
    }

    try:
        for field_name, value in cambios.items():
            setattr(partida, field_name, value)
        with transaction.atomic():
            partida.save(update_fields=list(cambios))
            eventos = {
                "iniciar": "partida_iniciada",
                "pausar": "partida_pausada",
                "reanudar": "partida_reanudada",
                "finalizar": "partida_finalizada",
            }
            programar_publicacion_partida(partida, eventos[accion])
    except DatabaseError:
        for field_name, value in valores_originales.items():
            setattr(partida, field_name, value)
        logger.exception(
            "No fue posible actualizar la partida %s con la accion %s",
            partida.idpartidabingo,
            accion,
        )
        messages.error(request, "No fue posible actualizar el estado de la partida.")
        return False

    label = ACCIONES_CONSOLA[accion]["label"]
    messages.success(request, f"{label} realizada correctamente.")
    return True


def _base_datos_permite_estado_partida(estado):
    estado = normalizar_estado_partida(estado)
    if estado not in ESTADOS_PARTIDA_VALORES:
        return False

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'partidabingo'::regclass
                  AND conname = %s
                """,
                ["chk_partidabingo_estadopartida"],
            )
            row = cursor.fetchone()
    except DatabaseError:
        logger.exception("No fue posible verificar la CHECK de estados de partidabingo.")
        return False

    if not row:
        return True

    constraint_definition = row[0] or ""
    return f"'{estado}'" in constraint_definition


def _attachment_response(content, content_type, filename):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@admin_required
def cartones_lista(request):
    busqueda = request.GET.get("q", "").strip()
    cartones = Carton.objects.select_related("idjugador", "idpartida", "idpartida__idbingo").order_by("-fechacompra", "codigocarton")
    if busqueda:
        cartones = cartones.filter(
            Q(codigocarton__icontains=busqueda)
            | Q(estadocarton__icontains=busqueda)
            | Q(idjugador__aliasjugador__icontains=busqueda)
        )
    return render(request, "bingos/cartones_lista.html", {"page_obj": paginate(request, cartones), "busqueda": busqueda, "total": cartones.count()})


@admin_required
def carton_nuevo(request):
    if request.method == "POST":
        form = CartonForm(request.POST)
        if form.is_valid():
            try:
                carton = save_new_model_form(form)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Cartón registrado correctamente.")
                return redirect("bingos:cartones_lista")
    else:
        form = CartonForm(initial={"estadocarton": "Disponible", "fechacompra": timezone.now()})
    return render(request, "bingos/carton_formulario.html", {"form": form, "titulo": "Nuevo cartón"})


@admin_required
def carton_editar(request, idcarton):
    carton = get_object_or_404(Carton, idcarton=idcarton)
    if request.method == "POST":
        form = CartonForm(request.POST, instance=carton)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Cartón actualizado correctamente.")
                return redirect("bingos:cartones_lista")
    else:
        form = CartonForm(instance=carton)
    return render(request, "bingos/carton_formulario.html", {"form": form, "carton": carton, "titulo": "Editar cartón"})


@admin_required
def sesiones_lista(request):
    busqueda = request.GET.get("q", "").strip()
    sesiones = Sesionjuego.objects.select_related("idplataforma", "idjugador", "idpartida").order_by("-fechainiciosesion")
    if busqueda:
        sesiones = sesiones.filter(
            Q(idjugador__aliasjugador__icontains=busqueda)
            | Q(idplataforma__nombreplataforma__icontains=busqueda)
            | Q(estadosesion__icontains=busqueda)
        )
    return render(request, "bingos/sesiones_lista.html", {"page_obj": paginate(request, sesiones), "busqueda": busqueda, "total": sesiones.count()})
