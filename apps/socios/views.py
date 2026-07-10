from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, Q, Sum, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from apps.common.decorators import admin_required
from apps.common.ids import save_new_model_form
from apps.common.views import paginate
from apps.finanzas.models import Ahorro, Aportesemanal, Prestamo
from apps.jugadores.services import jugador_required

from .forms import (
    AprobarSolicitudSocioForm,
    CuentaBancariaForm,
    RechazarSolicitudSocioForm,
    SocioForm,
    SolicitudSocioForm,
)
from .models import Cuentabancaria, Socio, SolicitudSocio
from .services import (
    aprobar_solicitud_socio,
    crear_solicitud_socio,
    rechazar_solicitud_socio,
)


@admin_required
def lista(request):
    busqueda = request.GET.get("q", "").strip()
    socios = Socio.objects.select_related("idtiposocio").order_by(
        "primerapellidosocio",
        "segundoapellidosocio",
        "primernombresocio",
    )
    if busqueda:
        socios = socios.filter(
            Q(cisocio__icontains=busqueda)
            | Q(primernombresocio__icontains=busqueda)
            | Q(segundonombresocio__icontains=busqueda)
            | Q(primerapellidosocio__icontains=busqueda)
            | Q(segundoapellidosocio__icontains=busqueda)
        )

    return render(
        request,
        "socios/lista.html",
        {
            "busqueda": busqueda,
            "page_obj": paginate(request, socios),
            "total": socios.count(),
        },
    )


@jugador_required
def mi_solicitud_socio(request):
    jugador = request.jugador
    solicitud = _ultima_solicitud_jugador(jugador)
    return render(
        request,
        "socios/solicitud_socio_estado.html",
        {
            "jugador": jugador,
            "socio": jugador.idsocio,
            "solicitud": solicitud,
            "tiene_solicitud_pendiente": _jugador_tiene_solicitud_pendiente(
                jugador
            ),
        },
    )


@jugador_required
@require_http_methods(["GET", "POST"])
def solicitud_socio_nueva(request):
    jugador = request.jugador
    if jugador.idsocio_id is not None:
        messages.info(request, "El jugador ya está vinculado a un socio.")
        return redirect("socios:mi_solicitud_socio")

    if _jugador_tiene_solicitud_pendiente(jugador):
        messages.info(request, "Ya existe una solicitud pendiente para este jugador.")
        return redirect("socios:mi_solicitud_socio")

    if request.method == "POST":
        form = SolicitudSocioForm(request.POST)
        if form.is_valid():
            try:
                crear_solicitud_socio(jugador, form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Solicitud enviada correctamente.")
                return redirect("socios:mi_solicitud_socio")
    else:
        form = SolicitudSocioForm()

    return render(
        request,
        "socios/solicitud_socio_formulario.html",
        {"form": form, "jugador": jugador},
    )


@admin_required
def solicitudes_socio_lista(request):
    solicitudes = (
        SolicitudSocio.objects.select_related(
            "idjugador",
            "idtiposocio",
            "idsocioresultado",
            "idusuarioadminrespuesta",
        )
        .annotate(
            prioridad_estado=Case(
                When(estado=SolicitudSocio.ESTADO_PENDIENTE, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("prioridad_estado", "-fechasolicitud", "-idsolicitud")
    )
    return render(
        request,
        "socios/solicitudes_socio_lista.html",
        {
            "page_obj": paginate(request, solicitudes),
            "total": solicitudes.count(),
        },
    )


@admin_required
def solicitud_socio_detalle(request, idsolicitud):
    solicitud = _obtener_solicitud_admin(idsolicitud)
    return render(
        request,
        "socios/solicitud_socio_detalle.html",
        _contexto_solicitud_admin(solicitud),
    )


@admin_required
@require_POST
def solicitud_socio_aprobar(request, idsolicitud):
    solicitud = _obtener_solicitud_admin(idsolicitud)
    form = AprobarSolicitudSocioForm(request.POST)
    if form.is_valid():
        try:
            solicitud, socio = aprobar_solicitud_socio(
                solicitud.idsolicitud,
                request.user,
                form.cleaned_data,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                f"Solicitud aprobada. Socio vinculado: {socio}.",
            )
            return redirect(
                "socios:solicitud_socio_detalle",
                idsolicitud=solicitud.idsolicitud,
            )

    return render(
        request,
        "socios/solicitud_socio_detalle.html",
        _contexto_solicitud_admin(solicitud, aprobar_form=form),
        status=400,
    )


@admin_required
@require_POST
def solicitud_socio_rechazar(request, idsolicitud):
    solicitud = _obtener_solicitud_admin(idsolicitud)
    form = RechazarSolicitudSocioForm(request.POST)
    if form.is_valid():
        try:
            solicitud = rechazar_solicitud_socio(
                solicitud.idsolicitud,
                request.user,
                form.cleaned_data["motivorechazo"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Solicitud rechazada correctamente.")
            return redirect(
                "socios:solicitud_socio_detalle",
                idsolicitud=solicitud.idsolicitud,
            )

    return render(
        request,
        "socios/solicitud_socio_detalle.html",
        _contexto_solicitud_admin(solicitud, rechazo_form=form),
        status=400,
    )


def _ultima_solicitud_jugador(jugador):
    return (
        SolicitudSocio.objects.filter(idjugador=jugador)
        .select_related("idtiposocio", "idsocioresultado")
        .order_by("-fechasolicitud", "-idsolicitud")
        .first()
    )


def _jugador_tiene_solicitud_pendiente(jugador):
    return SolicitudSocio.objects.filter(
        idjugador=jugador,
        estado=SolicitudSocio.ESTADO_PENDIENTE,
    ).exists()


def _obtener_solicitud_admin(idsolicitud):
    return get_object_or_404(
        SolicitudSocio.objects.select_related(
            "idjugador",
            "idtiposocio",
            "idsocioresultado",
            "idusuarioadminrespuesta",
        ),
        idsolicitud=idsolicitud,
    )


def _contexto_solicitud_admin(
    solicitud,
    *,
    aprobar_form=None,
    rechazo_form=None,
):
    return {
        "solicitud": solicitud,
        "aprobar_form": aprobar_form or AprobarSolicitudSocioForm(
            initial={
                "idtiposocio": solicitud.idtiposocio_id,
                "estadosocio": "Activo",
            }
        ),
        "rechazo_form": rechazo_form or RechazarSolicitudSocioForm(),
    }


@admin_required
def nuevo(request):
    if request.method == "POST":
        form = SocioForm(request.POST)
        if form.is_valid():
            try:
                socio = save_new_model_form(form)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Socio registrado correctamente.")
                return redirect("socios:detalle", idsocio=socio.idsocio)
    else:
        form = SocioForm(initial={"estadosocio": "Activo"})

    return render(
        request,
        "socios/formulario.html",
        {"form": form, "titulo": "Nuevo socio", "cancel_url": "socios:lista"},
    )


@admin_required
def detalle(request, idsocio):
    socio = get_object_or_404(Socio.objects.select_related("idtiposocio"), idsocio=idsocio)
    cuentas = Cuentabancaria.objects.filter(idsocio=socio).order_by("nombrebanco")
    ahorros = Ahorro.objects.filter(idsocio=socio).select_related("idbingo").order_by("-fechaahorro")[:10]
    total_ahorro_activo = (
        Ahorro.objects.filter(idsocio=socio, estado__iexact="Activo")
        .aggregate(total=Sum("montoahorro"))
        .get("total")
        or Decimal("0")
    )
    aportes = (
        Aportesemanal.objects.filter(idsocio=socio)
        .select_related("idregalo", "idpartida")
        .order_by("-fechaplanificadada")[:10]
    )
    prestamos = Prestamo.objects.filter(idsocio=socio).order_by("-fechasolicitud")[:10]

    return render(
        request,
        "socios/detalle.html",
        {
            "socio": socio,
            "cuentas": cuentas,
            "ahorros": ahorros,
            "total_ahorro_activo": total_ahorro_activo,
            "aportes": aportes,
            "prestamos": prestamos,
        },
    )


@admin_required
def editar(request, idsocio):
    socio = get_object_or_404(Socio, idsocio=idsocio)
    if request.method == "POST":
        form = SocioForm(request.POST, instance=socio)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Socio actualizado correctamente.")
                return redirect("socios:detalle", idsocio=socio.idsocio)
    else:
        form = SocioForm(instance=socio)

    return render(
        request,
        "socios/formulario.html",
        {
            "form": form,
            "socio": socio,
            "titulo": "Editar socio",
            "cancel_url": "socios:detalle",
        },
    )


@admin_required
def cuenta_nueva(request, idsocio):
    socio = get_object_or_404(Socio, idsocio=idsocio)
    if request.method == "POST":
        form = CuentaBancariaForm(request.POST)
        if form.is_valid():
            def before_save(cuenta):
                cuenta.idsocio = socio
                cuenta.fecharegistro = timezone.now()

            try:
                save_new_model_form(form, before_save=before_save)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Cuenta bancaria registrada correctamente.")
                return redirect("socios:detalle", idsocio=socio.idsocio)
    else:
        form = CuentaBancariaForm(initial={"estadocuenta": "Activa"})

    return render(
        request,
        "socios/cuenta_formulario.html",
        {"form": form, "socio": socio, "titulo": "Nueva cuenta bancaria"},
    )


@admin_required
def cuenta_editar(request, idcuentabancaria):
    cuenta = get_object_or_404(
        Cuentabancaria.objects.select_related("idsocio"),
        idcuentabancaria=idcuentabancaria,
    )
    if request.method == "POST":
        form = CuentaBancariaForm(request.POST, instance=cuenta)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Cuenta bancaria actualizada correctamente.")
                return redirect("socios:detalle", idsocio=cuenta.idsocio_id)
    else:
        form = CuentaBancariaForm(instance=cuenta)

    return render(
        request,
        "socios/cuenta_formulario.html",
        {"form": form, "socio": cuenta.idsocio, "cuenta": cuenta, "titulo": "Editar cuenta bancaria"},
    )
