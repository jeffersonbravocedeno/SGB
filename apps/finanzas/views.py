import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.common.decorators import admin_required
from apps.common.ids import save_new_model_form
from apps.common.views import paginate, safe_count

from .forms import (
    AhorroForm,
    AporteSemanalForm,
    PagoPrestamoForm,
    PrestamoConGarantesForm,
    PrestamoEdicionForm,
    PrestamoForm,
)
from .models import Ahorro, Aportesemanal, PagoPrestamo, Prestamo, PrestamoGarante
from .services import (
    ESTADOS_PRESTAMO_SIN_SALDO_GARANTE,
    PrestamoGarantiaError,
    PrestamoPagoError,
    crear_prestamo_con_garantes,
    registrar_pago_prestamo,
)


logger = logging.getLogger(__name__)


@admin_required
def dashboard(request):
    cards = [
        {"label": "Préstamos activos", "value": _safe_filtered_count(Prestamo, estadoprestamo__icontains="Aprobado")},
        {"label": "Pagos registrados", "value": _safe_filtered_count(PagoPrestamo, estado=PagoPrestamo.ESTADO_REGISTRADO)},
        {"label": "Ahorros registrados", "value": safe_count(Ahorro)},
        {"label": "Aportes atrasados", "value": _safe_filtered_count(Aportesemanal, estadoaporte__icontains="Atrasado")},
    ]
    return render(request, "finanzas/dashboard.html", {"cards": cards})


def _safe_filtered_count(model, **filters):
    try:
        return model.objects.filter(**filters).count()
    except DatabaseError:
        logger.exception("Could not count %s with filters %s", model.__name__, filters)
        return None


@admin_required
def prestamos_lista(request):
    busqueda = request.GET.get("q", "").strip()
    prestamos = Prestamo.objects.select_related("idsocio").order_by("-fechasolicitud")
    if busqueda:
        prestamos = prestamos.filter(
            Q(idsocio__cisocio__icontains=busqueda)
            | Q(idsocio__primernombresocio__icontains=busqueda)
            | Q(idsocio__primerapellidosocio__icontains=busqueda)
            | Q(estadoprestamo__icontains=busqueda)
        )
    return render(request, "finanzas/prestamos_lista.html", {"page_obj": paginate(request, prestamos), "busqueda": busqueda, "total": prestamos.count()})


@admin_required
def prestamo_nuevo(request):
    if request.method == "POST":
        form = PrestamoConGarantesForm(request.POST)
        if form.is_valid():
            datos_prestamo = form.datos_prestamo()
            datos_prestamo["saldopendiente"] = datos_prestamo["montototalpagar"]
            try:
                prestamo = crear_prestamo_con_garantes(
                    datos_prestamo=datos_prestamo,
                    garantes=form.garantes_seleccionados(),
                    usuario=request.user,
                )
            except PrestamoGarantiaError as exc:
                mensaje = str(exc)
                form.add_error(None, mensaje)
                messages.error(request, mensaje)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(
                    request,
                    "Préstamo registrado correctamente con sus garantes.",
                )
                return redirect("finanzas:prestamo_detalle", idprestamo=prestamo.idprestamo)
    else:
        today = timezone.localdate()
        form = PrestamoConGarantesForm(
            initial={"fechasolicitud": today, "estadoprestamo": "Solicitado"}
        )
    return render(request, "finanzas/prestamo_formulario.html", {"form": form, "titulo": "Nuevo préstamo"})


@admin_required
def prestamo_detalle(request, idprestamo):
    prestamo = get_object_or_404(Prestamo.objects.select_related("idsocio"), idprestamo=idprestamo)
    garantes = (
        PrestamoGarante.objects.filter(
            idprestamo=prestamo,
            estado=PrestamoGarante.ESTADO_ACTIVO,
        )
        .select_related("idgarante")
        .order_by("idprestamogarante")
    )
    pagos = (
        PagoPrestamo.objects.filter(idprestamo=prestamo)
        .select_related("idmetodopago")
        .order_by("-fechapago", "-idpagoprestamo")
    )
    total_pagado = (
        PagoPrestamo.objects.filter(
            idprestamo=prestamo,
            estado=PagoPrestamo.ESTADO_REGISTRADO,
        )
        .aggregate(total=Sum("montopagado"))
        .get("total")
        or Decimal("0.00")
    )
    return render(
        request,
        "finanzas/prestamo_detalle.html",
        {
            "prestamo": prestamo,
            "garantes": garantes,
            "pagos": pagos,
            "total_pagado": total_pagado,
            "puede_registrar_pago": _prestamo_permite_registrar_pago(prestamo),
        },
    )


@admin_required
def prestamo_editar(request, idprestamo):
    prestamo = get_object_or_404(Prestamo, idprestamo=idprestamo)
    if _prestamo_tiene_estado_final(prestamo):
        messages.error(request, "No se puede editar un préstamo cerrado o liquidado.")
        return redirect("finanzas:prestamo_detalle", idprestamo=prestamo.idprestamo)

    tiene_pagos_registrados = PagoPrestamo.objects.filter(
        idprestamo=prestamo,
        estado=PagoPrestamo.ESTADO_REGISTRADO,
    ).exists()

    if request.method == "POST":
        form = PrestamoEdicionForm(request.POST, instance=prestamo)
        if form.is_valid():
            campos_bloqueados = _campos_bloqueados_edicion_en_post(
                request.POST,
                tiene_pagos_registrados,
            )
            if campos_bloqueados:
                form.add_error(
                    None,
                    "No se permite modificar saldo pendiente ni montos base "
                    "desde la edición del préstamo.",
                )
            else:
                try:
                    with transaction.atomic():
                        form.save()
                except IntegrityError as exc:
                    form.add_integrity_error(exc)
                else:
                    messages.success(request, "Préstamo actualizado correctamente.")
                    return redirect("finanzas:prestamo_detalle", idprestamo=prestamo.idprestamo)
    else:
        form = PrestamoEdicionForm(instance=prestamo)
    return render(
        request,
        "finanzas/prestamo_formulario.html",
        {
            "form": form,
            "prestamo": prestamo,
            "titulo": "Editar préstamo",
            "tiene_pagos_registrados": tiene_pagos_registrados,
        },
    )


@admin_required
def pago_nuevo(request, idprestamo):
    prestamo = get_object_or_404(Prestamo.objects.select_related("idsocio"), idprestamo=idprestamo)
    if request.method == "POST":
        form = PagoPrestamoForm(request.POST)
        if form.is_valid():
            try:
                registrar_pago_prestamo(
                    prestamo,
                    monto_pagado=form.cleaned_data["montopagado"],
                    metodo_pago=form.cleaned_data.get("idmetodopago"),
                    numero_referencia=form.cleaned_data.get("numeroreferencia", ""),
                    observacion=form.cleaned_data.get("observacion", ""),
                )
            except PrestamoPagoError as exc:
                mensaje = str(exc)
                form.add_error(None, mensaje)
                messages.error(request, mensaje)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Pago registrado correctamente.")
                return redirect("finanzas:prestamo_detalle", idprestamo=prestamo.idprestamo)
    else:
        form = PagoPrestamoForm()
    return render(request, "finanzas/pago_formulario.html", {"form": form, "prestamo": prestamo, "titulo": "Nuevo pago"})


@admin_required
def pagos_lista(request):
    busqueda = request.GET.get("q", "").strip()
    pagos = PagoPrestamo.objects.select_related("idprestamo", "idprestamo__idsocio", "idmetodopago").order_by("-fechapago", "-idpagoprestamo")
    if busqueda:
        pagos = pagos.filter(
            Q(numeroreferencia__icontains=busqueda)
            | Q(estado__icontains=busqueda)
            | Q(idprestamo__idsocio__cisocio__icontains=busqueda)
            | Q(idprestamo__idsocio__primernombresocio__icontains=busqueda)
            | Q(idprestamo__idsocio__primerapellidosocio__icontains=busqueda)
        )
    return render(request, "finanzas/pagos_lista.html", {"page_obj": paginate(request, pagos), "busqueda": busqueda, "total": pagos.count()})


def _prestamo_permite_registrar_pago(prestamo):
    if _prestamo_tiene_estado_final(prestamo):
        return False
    try:
        saldo = Decimal(str(prestamo.saldopendiente))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return saldo > 0


def _prestamo_tiene_estado_final(prestamo):
    estado = str(prestamo.estadoprestamo or "").strip().lower()
    return any(
        estado == estado_final.lower()
        for estado_final in ESTADOS_PRESTAMO_SIN_SALDO_GARANTE
    )


def _campos_bloqueados_edicion_en_post(post_data, tiene_pagos_registrados):
    campos_bloqueados = {"saldopendiente"}
    if tiene_pagos_registrados:
        campos_bloqueados.update(
            {
                "montoprestamosolicitado",
                "montototalpagar",
            }
        )
    return sorted(campo for campo in campos_bloqueados if campo in post_data)


@admin_required
def ahorros_lista(request):
    ahorros = Ahorro.objects.select_related("idsocio", "idbingo").order_by("-fechaahorro")
    return render(request, "finanzas/ahorros_lista.html", {"page_obj": paginate(request, ahorros), "total": ahorros.count()})


@admin_required
def ahorro_nuevo(request):
    if request.method == "POST":
        form = AhorroForm(request.POST)
        if form.is_valid():
            try:
                save_new_model_form(form)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Ahorro registrado correctamente.")
                return redirect("finanzas:ahorros_lista")
    else:
        form = AhorroForm(initial={"fechaahorro": timezone.now(), "estado": "Activo"})
    return render(request, "finanzas/ahorro_formulario.html", {"form": form, "titulo": "Nuevo ahorro"})


@admin_required
def aportes_lista(request):
    aportes = Aportesemanal.objects.select_related("idsocio", "idregalo", "idpartida").order_by("-fechaplanificadada")
    return render(request, "finanzas/aportes_lista.html", {"page_obj": paginate(request, aportes), "total": aportes.count()})


@admin_required
def aporte_nuevo(request):
    if request.method == "POST":
        form = AporteSemanalForm(request.POST)
        if form.is_valid():
            try:
                save_new_model_form(form)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Aporte semanal registrado correctamente.")
                return redirect("finanzas:aportes_lista")
    else:
        form = AporteSemanalForm(initial={"fechaplanificadada": timezone.now(), "estadoaporte": "Al Dia"})
    return render(request, "finanzas/aporte_formulario.html", {"form": form, "titulo": "Nuevo aporte semanal"})
