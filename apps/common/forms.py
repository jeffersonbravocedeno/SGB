import logging
import re

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


logger = logging.getLogger(__name__)
RELATIVE_ASSET_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]+\.[A-Za-z0-9]{2,8}([?#].*)?$")

UNEXPECTED_OPERATION_ERROR = (
    "No fue posible completar la operación por un problema inesperado. "
    "Inténtalo nuevamente o informa al administrador."
)


COMMON_STATE_CHOICES = (
    ("Activo", "Activo"),
    ("Inactivo", "Inactivo"),
    ("Activa", "Activa"),
    ("Inactiva", "Inactiva"),
    ("Pendiente", "Pendiente"),
    ("Validado", "Validado"),
    ("Rechazado", "Rechazado"),
    ("Al Dia", "Al día"),
    ("Atrasado", "Atrasado"),
    ("Programado", "Programado"),
    ("En Curso", "En curso"),
    ("Finalizado", "Finalizado"),
    ("Cancelado", "Cancelado"),
    ("En Juego", "En juego"),
    ("Verificando", "Verificando"),
    ("Desempate", "Desempate"),
    ("Finalizada", "Finalizada"),
    ("Suspendido", "Suspendido"),
    ("Moroso", "Moroso"),
    ("Disponible", "Disponible"),
    ("Vendido", "Vendido"),
    ("Cerrado", "Cerrado"),
    ("Solicitado", "Solicitado"),
    ("Aprobado", "Aprobado"),
    ("En espera", "En espera"),
    ("Liquidado", "Liquidado"),
    ("Acumulado", "Acumulado"),
    ("Sorteado", "Sorteado"),
    ("Entregado", "Entregado"),
)


def apply_bootstrap(form):
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = "form-check-input"
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = "form-select"
        else:
            widget.attrs["class"] = "form-control"


def set_state_select(form, field_name, current_value=None, blank=False, choices=None):
    choices = list(choices or COMMON_STATE_CHOICES)
    values = [value for value, _label in choices]
    if current_value and current_value not in values:
        choices.insert(0, (current_value, current_value))
    if blank:
        choices.insert(0, ("", "Sin estado"))
    form.fields[field_name].widget = forms.Select(choices=choices)
    form.fields[field_name].widget.attrs["class"] = "form-select"


def normalize_upper(value):
    return value.strip().upper() if isinstance(value, str) and value.strip() else value


def validate_unique_field(form, field_name, message, lookup=None, normalize=None):
    value = form.cleaned_data.get(field_name)
    if value in (None, ""):
        return value

    if normalize:
        value = normalize(value)

    lookup = lookup or field_name
    queryset = form._meta.model._default_manager.filter(**{lookup: value})
    if form.instance and form.instance.pk:
        queryset = queryset.exclude(pk=form.instance.pk)

    if queryset.exists():
        raise ValidationError(message)

    return value


def validate_optional_url(value):
    if value in (None, ""):
        return value

    value = value.strip()
    validator = URLValidator(message="Ingrese una URL válida.")
    validator(value)
    return value


def validate_optional_url_or_path(value):
    if value in (None, ""):
        return value

    value = value.strip()
    if "://" in value:
        validator = URLValidator(message="Ingrese una URL válida.")
        validator(value)
        return value

    if RELATIVE_ASSET_PATH_RE.match(value):
        return value

    raise ValidationError("Ingrese una URL o ruta de archivo válida.")


class FriendlyModelForm(forms.ModelForm):
    date_fields = ()
    datetime_fields = ()
    state_fields = ()
    state_choices = {}
    non_negative_fields = ()
    integrity_error_map = ()
    constraint_error_messages = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._allowed_state_values = {}
        self._configure_date_widgets()
        self._configure_state_widgets()
        self._configure_error_messages()
        self._configure_numeric_widgets()
        apply_bootstrap(self)

    def _configure_error_messages(self):
        for field in self.fields.values():
            field.error_messages["required"] = "Este campo es obligatorio."

            if isinstance(field, forms.EmailField):
                field.error_messages["invalid"] = "Ingrese un correo electrónico válido."
            elif isinstance(field, (forms.DateField, forms.DateTimeField)):
                field.error_messages["invalid"] = "Ingrese una fecha válida."
            elif isinstance(field, (forms.DecimalField, forms.IntegerField, forms.FloatField)):
                field.error_messages["invalid"] = "Ingrese un valor numérico válido."

    def _configure_numeric_widgets(self):
        for field_name in self.non_negative_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs["min"] = "0"

    def _configure_date_widgets(self):
        for field_name in self.date_fields:
            if field_name in self.fields:
                self.fields[field_name].widget = forms.DateInput(
                    attrs={"type": "date"},
                    format="%Y-%m-%d",
                )
                self.fields[field_name].input_formats = ["%Y-%m-%d"]

        for field_name in self.datetime_fields:
            if field_name in self.fields:
                self.fields[field_name].widget = forms.DateTimeInput(
                    attrs={"type": "datetime-local"},
                    format="%Y-%m-%dT%H:%M",
                )
                self.fields[field_name].input_formats = ["%Y-%m-%dT%H:%M"]

    def _configure_state_widgets(self):
        for field_name in self.state_fields:
            if field_name in self.fields:
                current_value = self.initial.get(field_name)
                if not current_value and self.instance and self.instance.pk:
                    current_value = getattr(self.instance, field_name, None)
                choices = self._state_choices_for(field_name)
                set_state_select(self, field_name, current_value=current_value, choices=choices)
                allowed_values = {value for value, _label in choices}
                if current_value:
                    allowed_values.add(current_value)
                self._allowed_state_values[field_name] = allowed_values

    def _state_choices_for(self, field_name):
        configured = self.state_choices.get(field_name, COMMON_STATE_CHOICES)
        if callable(configured):
            configured = configured()
        return tuple(configured)

    def add_integrity_error(self, exc):
        error_text = str(exc).lower()
        for field_name, markers, message in self.integrity_error_map:
            if any(marker.lower() in error_text for marker in markers):
                self.add_error(field_name, message)
                return

        if self._add_constraint_field_error(error_text):
            return

        logger.exception("Unexpected database integrity error while saving %s", self.__class__.__name__)
        self.add_error(None, UNEXPECTED_OPERATION_ERROR)

    def _add_constraint_field_error(self, error_text):
        for field_name in self.fields:
            if field_name.lower() not in error_text:
                continue

            self.add_error(field_name, self._constraint_message_for(field_name))
            return True
        return False

    def _constraint_message_for(self, field_name):
        if field_name in self.constraint_error_messages:
            return self.constraint_error_messages[field_name]
        if field_name in self.state_fields:
            return "Seleccione un estado válido."
        if field_name in self.non_negative_fields:
            return "Ingrese un valor mayor o igual a cero."
        field = self.fields.get(field_name)
        if field and getattr(field, "choices", None):
            return "Seleccione una opción válida."
        return "El valor ingresado no cumple una restricción de la base de datos."

    def clean(self):
        cleaned_data = super().clean()
        for field_name in self.state_fields:
            if field_name in cleaned_data:
                value = cleaned_data[field_name]
                if isinstance(value, str):
                    value = value.strip()
                cleaned_data[field_name] = value
                allowed_values = self._allowed_state_values.get(field_name, set())
                if value not in (None, "") and value not in allowed_values:
                    self.add_error(field_name, "Seleccione un estado válido.")

        for field_name in self.non_negative_fields:
            value = cleaned_data.get(field_name)
            if value is not None and value < 0:
                self.add_error(field_name, "Ingrese un valor mayor o igual a cero.")

        return cleaned_data
