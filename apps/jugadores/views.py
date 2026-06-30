from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.common.decorators import admin_required
from apps.bingos.models import Carton, Sesionjuego
from apps.common.ids import save_new_model_form
from apps.common.views import paginate

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
    cartones = (
        Carton.objects.filter(idjugador=jugador)
        .select_related("idpartida", "idpartida__idbingo")
        .order_by("-fechacompra")[:20]
    )
    sesiones = (
        Sesionjuego.objects.filter(idjugador=jugador)
        .select_related("idplataforma", "idpartida")
        .order_by("-fechainiciosesion")[:20]
    )

    return render(
        request,
        "jugadores/detalle.html",
        {
            "jugador": jugador,
            "cartones": cartones,
            "sesiones": sesiones,
        },
    )


@admin_required
def editar(request, idjugador):
    jugador = get_object_or_404(Jugador, idjugador=idjugador)

    if request.method == "POST":
        form = JugadorForm(request.POST, instance=jugador)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Jugador actualizado correctamente.")
                return redirect("jugadores:detalle", idjugador=jugador.idjugador)
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
