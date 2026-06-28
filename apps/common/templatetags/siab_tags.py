from django import template
from django import forms
from django.forms.forms import NON_FIELD_ERRORS

from apps.bingos.services import estado_partida_mostrar


register = template.Library()


@register.filter
def estado_class(value):
    estado = str(estado_partida_mostrar(value) or "").strip().upper()
    if estado in {"ACTIVO", "VALIDADO", "AL DIA", "DISPONIBLE", "COMPLETADO", "EN CURSO"}:
        return "text-bg-success"
    if estado in {"PENDIENTE", "PROGRAMADO", "PROGRAMADA", "EN ESPERA"}:
        return "text-bg-primary"
    if estado in {"ATRASADO", "SUSPENDIDO", "PAUSADA", "DESEMPATE"}:
        return "text-bg-warning"
    if estado in {"RECHAZADO", "INACTIVO", "CERRADO", "CANCELADO", "CANCELADA"}:
        return "text-bg-danger"
    if estado in {"FINALIZADO", "FINALIZADA", "VENDIDO"}:
        return "text-bg-secondary"
    return "text-bg-info"


@register.filter
def estado_partida_display(value):
    return estado_partida_mostrar(value)


@register.filter
def valor_si_no(value):
    if value is True:
        return "Sí"
    if value is False:
        return "No"
    return "Sin definir"


@register.filter
def default_dash(value):
    return value if value not in (None, "") else "-"


@register.filter(is_safe=True)
def bootstrap_widget(bound_field):
    widget = bound_field.field.widget
    attrs = widget.attrs.copy()
    classes = set(attrs.get("class", "").split())

    if isinstance(widget, forms.CheckboxInput):
        classes.add("form-check-input")
    elif isinstance(widget, forms.Select):
        classes.add("form-select")
    else:
        classes.add("form-control")

    if bound_field.errors:
        classes.add("is-invalid")

    attrs["class"] = " ".join(sorted(classes))
    return bound_field.as_widget(attrs=attrs)


@register.filter
def has_field_errors(form):
    return any(field_name != NON_FIELD_ERRORS for field_name in form.errors)
