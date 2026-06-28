import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.common.ids import save_new_model_form
from apps.common.views import paginate, safe_count

from .forms import AhorroForm, AporteSemanalForm, PagoForm, PrestamoForm
from .models import Ahorro, Aportesemanal, Pago, Prestamo


logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    cards = [
        {"label": "Préstamos activos", "value": _safe_filtered_count(Prestamo, estadoprestamo__icontains="Aprobado")},
        {"label": "Pagos pendientes", "value": _safe_filtered_count(Pago, estadopago__icontains="Pendiente")},
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


@login_required
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


@login_required
def prestamo_nuevo(request):
    if request.method == "POST":
        form = PrestamoForm(request.POST)
        if form.is_valid():
            try:
                prestamo = save_new_model_form(form)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Préstamo registrado correctamente.")
                return redirect("finanzas:prestamo_detalle", idprestamo=prestamo.idprestamo)
    else:
        today = timezone.localdate()
        form = PrestamoForm(initial={"fechasolicitud": today, "estadoprestamo": "Solicitado"})
    return render(request, "finanzas/prestamo_formulario.html", {"form": form, "titulo": "Nuevo préstamo"})


@login_required
def prestamo_detalle(request, idprestamo):
    prestamo = get_object_or_404(Prestamo.objects.select_related("idsocio"), idprestamo=idprestamo)
    pagos = Pago.objects.filter(idprestamo=prestamo).select_related("idmetodopago").order_by("-fechapago")
    return render(request, "finanzas/prestamo_detalle.html", {"prestamo": prestamo, "pagos": pagos})


@login_required
def prestamo_editar(request, idprestamo):
    prestamo = get_object_or_404(Prestamo, idprestamo=idprestamo)
    if request.method == "POST":
        form = PrestamoForm(request.POST, instance=prestamo)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Préstamo actualizado correctamente.")
                return redirect("finanzas:prestamo_detalle", idprestamo=prestamo.idprestamo)
    else:
        form = PrestamoForm(instance=prestamo)
    return render(request, "finanzas/prestamo_formulario.html", {"form": form, "prestamo": prestamo, "titulo": "Editar préstamo"})


@login_required
def pago_nuevo(request, idprestamo):
    prestamo = get_object_or_404(Prestamo.objects.select_related("idsocio"), idprestamo=idprestamo)
    if request.method == "POST":
        form = PagoForm(request.POST)
        if form.is_valid():
            def before_save(pago):
                pago.idprestamo = prestamo

            try:
                save_new_model_form(form, before_save=before_save)
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, "Pago registrado correctamente.")
                return redirect("finanzas:prestamo_detalle", idprestamo=prestamo.idprestamo)
    else:
        form = PagoForm(initial={"fechapago": timezone.now(), "estadopago": "Pendiente"})
    return render(request, "finanzas/pago_formulario.html", {"form": form, "prestamo": prestamo, "titulo": "Nuevo pago"})


@login_required
def pagos_lista(request):
    busqueda = request.GET.get("q", "").strip()
    pagos = Pago.objects.select_related("idprestamo", "idprestamo__idsocio", "idmetodopago").order_by("-fechapago")
    if busqueda:
        pagos = pagos.filter(Q(numeroreferencia__icontains=busqueda) | Q(estadopago__icontains=busqueda))
    return render(request, "finanzas/pagos_lista.html", {"page_obj": paginate(request, pagos), "busqueda": busqueda, "total": pagos.count()})


@login_required
def ahorros_lista(request):
    ahorros = Ahorro.objects.select_related("idsocio", "idbingo").order_by("-fechaahorro")
    return render(request, "finanzas/ahorros_lista.html", {"page_obj": paginate(request, ahorros), "total": ahorros.count()})


@login_required
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


@login_required
def aportes_lista(request):
    aportes = Aportesemanal.objects.select_related("idsocio", "idregalo", "idpartida").order_by("-fechaplanificadada")
    return render(request, "finanzas/aportes_lista.html", {"page_obj": paginate(request, aportes), "total": aportes.count()})


@login_required
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
