import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.common.decorators import admin_required
from apps.common.ids import save_new_model_form
from apps.common.views import paginate

from .forms import (
    BingoForm,
    CartonForm,
    CartonPartidaForm,
    GenerarAsignarCartonForm,
    PartidaBingoForm,
)
from .models import Bingo, Carton, Partidabingo, Sesionjuego
from .services import (
    ACCIONES_CONSOLA,
    BolaBingoError,
    CartonAsignacionError,
    ESTADO_PARTIDA_PROGRAMADA,
    ESTADOS_PARTIDA_VALORES,
    EstadoPartidaError,
    acciones_disponibles_consola,
    crear_y_asignar_carton,
    deserializar_matriz_carton_bingo,
    extraer_siguiente_bola,
    formatear_bola_bingo,
    normalizar_estado_partida,
    parse_bolas_cantadas,
    preparar_datos_bolas_partida,
    puede_asignar_cartones,
    preparar_accion_consola,
    validar_asignacion_cartones,
)


logger = logging.getLogger(__name__)


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
    cartones = Carton.objects.filter(idpartida=partida).select_related("idjugador").order_by("codigocarton")
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
            "puede_asignar_cartones": puede_asignar_cartones(partida),
            **datos_bolas,
        },
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
        messages.success(
            request,
            f"Bola {formatear_bola_bingo(nueva_bola)} extraída correctamente.",
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
