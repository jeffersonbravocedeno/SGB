from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.ids import save_new_model_form
from apps.common.views import paginate, safe_count

from .forms import MetodoPagoForm, PlataformaJuegoForm, RegaloForm, TipoSocioForm
from .models import Metodopago, Plataformajuego, Regalo, Tiposocio


SECTIONS = {
    "tipos-socio": {
        "title": "Tipos de socio",
        "singular": "tipo de socio",
        "model": Tiposocio,
        "form": TipoSocioForm,
        "order": "nombretiposocio",
        "columns": ("Nombre", "Rol", "Descripción"),
        "values": lambda obj: (obj.nombretiposocio, obj.roltiposocio, obj.descripciondetiposocio or "-"),
        "detail": lambda obj: (
            ("Nombre", obj.nombretiposocio),
            ("Rol", obj.roltiposocio),
            ("Descripción", obj.descripciondetiposocio or "-"),
        ),
    },
    "metodos-pago": {
        "title": "Métodos de pago",
        "singular": "método de pago",
        "model": Metodopago,
        "form": MetodoPagoForm,
        "order": "nombremetodopago",
        "columns": ("Nombre", "Estado", "URL"),
        "values": lambda obj: (obj.nombremetodopago, "Activo" if obj.estadometodopago else "Inactivo", obj.urlmetodopago),
        "detail": lambda obj: (
            ("Nombre", obj.nombremetodopago),
            ("Descripción", obj.descripcionmetodopago or "-"),
            ("Estado", "Activo" if obj.estadometodopago else "Inactivo"),
            ("URL", obj.urlmetodopago),
        ),
    },
    "plataformas-juego": {
        "title": "Plataformas de juego",
        "singular": "plataforma de juego",
        "model": Plataformajuego,
        "form": PlataformaJuegoForm,
        "order": "nombreplataforma",
        "columns": ("Nombre", "Estado", "Vencimiento"),
        "values": lambda obj: (obj.nombreplataforma, "Activa" if obj.estadoplataforma else "Inactiva", obj.fechavencimientolicencia or "-"),
        "detail": lambda obj: (
            ("Nombre", obj.nombreplataforma),
            ("URL", obj.urlplataforma),
            ("Descripción", obj.descripcionplataforma or "-"),
            ("Estado", "Activa" if obj.estadoplataforma else "Inactiva"),
            ("Adquisición de licencia", obj.fechaadquisicionlicencia or "-"),
            ("Vencimiento de licencia", obj.fechavencimientolicencia or "-"),
            ("Contacto", obj.contactoplataforma or "-"),
        ),
    },
    "regalos": {
        "title": "Regalos",
        "singular": "regalo",
        "model": Regalo,
        "form": RegaloForm,
        "order": "nombreregalo",
        "columns": ("Nombre", "Valor", "Estado"),
        "values": lambda obj: (obj.nombreregalo, f"${obj.valorregalo:.2f}", obj.estadoregalo),
        "detail": lambda obj: (
            ("Nombre", obj.nombreregalo),
            ("Descripción", obj.descripcionregalo or "-"),
            ("Valor", f"${obj.valorregalo:.2f}"),
            ("Estado", obj.estadoregalo),
            ("Imagen", obj.urlimagen),
            ("Última actualización", obj.fechaultimaactualizacion),
        ),
        "before_save": RegaloForm.set_update_timestamp,
    },
}


@login_required
def dashboard(request):
    cards = [
        {"label": "Tipos de socio", "value": safe_count(Tiposocio), "url": "configuracion:tipos_socio_lista"},
        {"label": "Métodos de pago", "value": safe_count(Metodopago), "url": "configuracion:metodos_pago_lista"},
        {"label": "Plataformas de juego", "value": safe_count(Plataformajuego), "url": "configuracion:plataformas_juego_lista"},
        {"label": "Regalos", "value": safe_count(Regalo), "url": "configuracion:regalos_lista"},
    ]
    return render(request, "configuracion/dashboard.html", {"cards": cards})


def _section(section):
    return SECTIONS[section]


def _object_pk(obj):
    return getattr(obj, obj._meta.pk.attname)


def _rows(queryset, config):
    return [{"object": obj, "pk": _object_pk(obj), "values": config["values"](obj)} for obj in queryset]


@login_required
def section_list(request, section):
    config = _section(section)
    queryset = config["model"].objects.order_by(config["order"])
    page_obj = paginate(request, queryset)
    page_obj.object_list = _rows(page_obj.object_list, config)
    return render(
        request,
        "configuracion/lista.html",
        {
            "section": section,
            "config": config,
            "page_obj": page_obj,
            "total": queryset.count(),
            "new_url": _new_name(section),
            "detail_url": _detail_name(section),
            "edit_url": _edit_name(section),
        },
    )


@login_required
def section_new(request, section):
    config = _section(section)
    form_class = config["form"]
    if request.method == "POST":
        form = form_class(request.POST)
        if form.is_valid():
            try:
                obj = save_new_model_form(form, before_save=config.get("before_save"))
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, f"Registro creado correctamente.")
                return redirect(_detail_name(section), pk=_object_pk(obj))
    else:
        form = form_class()
    return render(
        request,
        "configuracion/formulario.html",
        {
            "form": form,
            "config": config,
            "section": section,
            "titulo": f"Nuevo {config['singular']}",
            "list_url": _list_name(section),
        },
    )


@login_required
def section_detail(request, section, pk):
    config = _section(section)
    obj = get_object_or_404(config["model"], pk=pk)
    return render(
        request,
        "configuracion/detalle.html",
        {
            "config": config,
            "section": section,
            "object": obj,
            "fields": config["detail"](obj),
            "pk": pk,
            "list_url": _list_name(section),
            "edit_url": _edit_name(section),
        },
    )


@login_required
def section_edit(request, section, pk):
    config = _section(section)
    obj = get_object_or_404(config["model"], pk=pk)
    form_class = config["form"]
    if request.method == "POST":
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            try:
                with transaction.atomic():
                    instance = form.save(commit=False)
                    before_save = config.get("before_save")
                    if before_save:
                        before_save(instance)
                    instance.save()
                    form.save_m2m()
            except IntegrityError as exc:
                form.add_integrity_error(exc)
            else:
                messages.success(request, f"{config['title']} actualizado correctamente.")
                return redirect(_detail_name(section), pk=pk)
    else:
        form = form_class(instance=obj)
    return render(
        request,
        "configuracion/formulario.html",
        {
            "form": form,
            "config": config,
            "section": section,
            "object": obj,
            "pk": pk,
            "titulo": f"Editar {config['singular']}",
            "list_url": _list_name(section),
            "detail_url": _detail_name(section),
        },
    )


def _list_name(section):
    return {
        "tipos-socio": "configuracion:tipos_socio_lista",
        "metodos-pago": "configuracion:metodos_pago_lista",
        "plataformas-juego": "configuracion:plataformas_juego_lista",
        "regalos": "configuracion:regalos_lista",
    }[section]


def _detail_name(section):
    return {
        "tipos-socio": "configuracion:tipos_socio_detalle",
        "metodos-pago": "configuracion:metodos_pago_detalle",
        "plataformas-juego": "configuracion:plataformas_juego_detalle",
        "regalos": "configuracion:regalos_detalle",
    }[section]


def _new_name(section):
    return {
        "tipos-socio": "configuracion:tipos_socio_nuevo",
        "metodos-pago": "configuracion:metodos_pago_nuevo",
        "plataformas-juego": "configuracion:plataformas_juego_nuevo",
        "regalos": "configuracion:regalos_nuevo",
    }[section]


def _edit_name(section):
    return {
        "tipos-socio": "configuracion:tipos_socio_editar",
        "metodos-pago": "configuracion:metodos_pago_editar",
        "plataformas-juego": "configuracion:plataformas_juego_editar",
        "regalos": "configuracion:regalos_editar",
    }[section]
