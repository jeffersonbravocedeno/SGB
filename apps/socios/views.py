from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.common.ids import save_new_model_form
from apps.common.views import paginate
from apps.finanzas.models import Ahorro, Aportesemanal, Prestamo

from .forms import CuentaBancariaForm, SocioForm
from .models import Cuentabancaria, Socio


@login_required
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


@login_required
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


@login_required
def detalle(request, idsocio):
    socio = get_object_or_404(Socio.objects.select_related("idtiposocio"), idsocio=idsocio)
    cuentas = Cuentabancaria.objects.filter(idsocio=socio).order_by("nombrebanco")
    ahorros = Ahorro.objects.filter(idsocio=socio).select_related("idbingo").order_by("-fechaahorro")[:10]
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
            "aportes": aportes,
            "prestamos": prestamos,
        },
    )


@login_required
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


@login_required
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


@login_required
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
