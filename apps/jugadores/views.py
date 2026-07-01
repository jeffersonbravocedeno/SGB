from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.common.decorators import admin_required
from apps.bingos.models import Carton, CartonPartidaBingo, Sesionjuego
from apps.common.ids import save_new_model_form
from apps.common.views import paginate
from apps.jugadores.services import (
    crear_acceso_para_jugador,
    estado_cuenta_acceso_jugador,
    sincronizar_alias_jugador_si_corresponde,
)
from apps.seguridad.forms import CrearAccesoJugadorForm

from .forms import JugadorForm
from .models import Jugador


@admin_required
def lista(request):
    busqueda = request.GET.get("q", "").strip()
    jugadores = (
        Jugador.objects.select_related("idsocio")
        .all()
        .order_by("aliasjugador", "idjugador")
    )

    if busqueda:
        jugadores = jugadores.filter(
            Q(aliasjugador__icontains=busqueda)
            | Q(correojugador__icontains=busqueda)
        )

    return render(
        request,
        "jugadores/lista.html",
        {
            "busqueda": busqueda,
            "page_obj": paginate(request, jugadores),
            "total_jugadores": jugadores.count(),
        },
    )


@admin_required
def nuevo(request):
    if request.method == "POST":
        form = JugadorForm(request.POST)
        if form.is_valid():
            try:
                jugador = save_new_model_form(
                    form,
                    before_save=lambda instance: setattr(
                        instance,
                        "fecharegistrojugador",
                        timezone.now(),
                    ),
                )
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Jugador registrado correctamente.")
                return redirect("jugadores:detalle", idjugador=jugador.idjugador)
    else:
        form = JugadorForm(
            initial={
                "saldocreditojugador": "0.00",
                "estadocuentajugador": "Activo",
            }
        )

    return render(
        request,
        "jugadores/formulario.html",
        {
            "form": form,
            "titulo": "Nuevo jugador",
            "es_edicion": False,
        },
    )


@admin_required
def detalle(request, idjugador):
    jugador = get_object_or_404(
        Jugador.objects.select_related("idsocio"),
        idjugador=idjugador,
    )
    return render(
        request,
        "jugadores/detalle.html",
        _detalle_context(jugador),
    )


def _detalle_context(jugador, cuenta_acceso_form=None):
    cartones = (
        Carton.objects.filter(idjugador=jugador)
        .select_related("idbingo", "idpartida", "idpartida__idbingo")
        .prefetch_related(
            Prefetch(
                "participaciones",
                queryset=CartonPartidaBingo.objects.select_related(
                    "idpartida",
                    "idpartida__idbingo",
                    "idbingo",
                ).order_by("idcartonpartidabingo"),
                to_attr="participaciones_hibridas_cargadas",
            )
        )
        .order_by("-fechacompra")[:20]
    )
    sesiones = (
        Sesionjuego.objects.filter(idjugador=jugador)
        .select_related("idplataforma", "idpartida")
        .order_by("-fechainiciosesion")[:20]
    )
    cuenta_acceso = estado_cuenta_acceso_jugador(jugador)
    if cuenta_acceso_form is None and cuenta_acceso["puede_crear"]:
        cuenta_acceso_form = CrearAccesoJugadorForm(jugador)

    return {
        "jugador": jugador,
        "cartones": cartones,
        "sesiones": sesiones,
        "cuenta_acceso": cuenta_acceso,
        "cuenta_acceso_form": cuenta_acceso_form,
    }


@admin_required
def crear_acceso(request, idjugador):
    jugador = get_object_or_404(Jugador, idjugador=idjugador)
    if request.method != "POST":
        return redirect("jugadores:detalle", idjugador=jugador.idjugador)

    form = CrearAccesoJugadorForm(jugador, request.POST)
    if form.is_valid():
        try:
            crear_acceso_para_jugador(
                jugador,
                form.cleaned_data["password1"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError as exc:
            form.add_error(None, "No fue posible crear la cuenta de acceso.")
        else:
            messages.success(
                request,
                "Cuenta de acceso creada correctamente.",
            )
            return redirect("jugadores:detalle", idjugador=jugador.idjugador)

    return render(
        request,
        "jugadores/detalle.html",
        _detalle_context(jugador, cuenta_acceso_form=form),
    )


@admin_required
def editar(request, idjugador):
    jugador = get_object_or_404(Jugador, idjugador=idjugador)
    alias_anterior = jugador.aliasjugador

    if request.method == "POST":
        form = JugadorForm(request.POST, instance=jugador)
        if form.is_valid():
            try:
                jugador_guardado = sincronizar_alias_jugador_si_corresponde(
                    form,
                    alias_anterior,
                )
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                if jugador_guardado is not None:
                    messages.success(request, "Jugador actualizado correctamente.")
                    return redirect(
                        "jugadores:detalle",
                        idjugador=jugador_guardado.idjugador,
                    )
    else:
        form = JugadorForm(instance=jugador)

    return render(
        request,
        "jugadores/formulario.html",
        {
            "form": form,
            "jugador": jugador,
            "titulo": "Editar jugador",
            "es_edicion": True,
        },
    )
