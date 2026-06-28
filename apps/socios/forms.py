from django import forms

from apps.common.forms import FriendlyModelForm, validate_unique_field
from apps.configuracion.models import Tiposocio

from .models import Cuentabancaria, Socio


class SocioForm(FriendlyModelForm):
    date_fields = ("fechanacimientosocio",)
    state_fields = ("estadosocio",)
    state_choices = {
        "estadosocio": (
            ("Activo", "Activo"),
            ("Inactivo", "Inactivo"),
        )
    }
    integrity_error_map = (
        ("cisocio", ("cisocio", "socio_cisocio", "unique"), "Esta cédula ya está registrada."),
    )
    constraint_error_messages = {
        "estadosocio": "Seleccione un estado válido.",
        "sexosocio": "Seleccione un sexo válido.",
    }

    class Meta:
        model = Socio
        fields = (
            "idtiposocio",
            "primernombresocio",
            "segundonombresocio",
            "primerapellidosocio",
            "segundoapellidosocio",
            "cisocio",
            "fechanacimientosocio",
            "telefonopersonalsocio",
            "telefonotrabajosocio",
            "direcciondomiciliosocio",
            "direcciontrabajosocio",
            "sexosocio",
            "estadosocio",
        )
        labels = {
            "idtiposocio": "Tipo de socio",
            "primernombresocio": "Primer nombre",
            "segundonombresocio": "Segundo nombre",
            "primerapellidosocio": "Primer apellido",
            "segundoapellidosocio": "Segundo apellido",
            "cisocio": "Cédula",
            "fechanacimientosocio": "Fecha de nacimiento",
            "telefonopersonalsocio": "Teléfono personal",
            "telefonotrabajosocio": "Teléfono de trabajo",
            "direcciondomiciliosocio": "Dirección de domicilio",
            "direcciontrabajosocio": "Dirección de trabajo",
            "sexosocio": "Sexo",
            "estadosocio": "Estado",
        }
        widgets = {
            "direcciondomiciliosocio": forms.Textarea(attrs={"rows": 2}),
            "direcciontrabajosocio": forms.Textarea(attrs={"rows": 2}),
        }
        error_messages = {
            "cisocio": {
                "unique": "Esta cédula ya está registrada.",
                "max_length": "La cédula no puede superar los 10 caracteres.",
            }
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["idtiposocio"].queryset = Tiposocio.objects.order_by("nombretiposocio")
        self.fields["sexosocio"].widget = forms.Select(
            choices=(
                ("", "Sin especificar"),
                ("H", "Hombre"),
                ("M", "Mujer"),
            )
        )
        self.fields["sexosocio"].widget.attrs["class"] = "form-select"

    def clean_cisocio(self):
        value = self.cleaned_data.get("cisocio")
        value = value.strip() if value else value
        self.cleaned_data["cisocio"] = value
        return validate_unique_field(
            self,
            "cisocio",
            "Esta cédula ya está registrada.",
        )

    def clean_sexosocio(self):
        value = self.cleaned_data.get("sexosocio")
        if value not in ("", None, "H", "M"):
            raise forms.ValidationError("Seleccione un sexo válido.")
        return value


class CuentaBancariaForm(FriendlyModelForm):
    state_fields = ("estadocuenta",)
    state_choices = {
        "estadocuenta": (
            ("Activa", "Activa"),
            ("Inactiva", "Inactiva"),
        )
    }
    integrity_error_map = (
        (
            "numerocuenta",
            ("numerocuenta", "cuentabancaria_numerocuenta", "unique"),
            "Este número de cuenta ya existe.",
        ),
        (
            "esprincipal",
            ("esprincipal", "cuentabancaria_esprincipal"),
            "Ya existe otra cuenta con esta misma marca. Use 'Sin marcar' si no es cuenta principal.",
        ),
    )
    constraint_error_messages = {
        "tipocuenta": "Seleccione un tipo de cuenta válido.",
        "estadocuenta": "Seleccione un estado válido.",
    }
    esprincipal = forms.TypedChoiceField(
        required=False,
        label="Cuenta principal",
        coerce=lambda value: None if value == "" else value == "true",
        empty_value=None,
        choices=(
            ("", "Sin marcar"),
            ("true", "Sí"),
            ("false", "No"),
        ),
    )

    class Meta:
        model = Cuentabancaria
        fields = (
            "nombrebanco",
            "numerocuenta",
            "tipocuenta",
            "esprincipal",
            "estadocuenta",
        )
        labels = {
            "nombrebanco": "Banco",
            "numerocuenta": "Número de cuenta",
            "tipocuenta": "Tipo de cuenta",
            "estadocuenta": "Estado",
        }
        error_messages = {
            "numerocuenta": {
                "unique": "Este número de cuenta ya existe.",
                "max_length": "El número de cuenta no puede superar los 30 caracteres.",
            }
        }

    def clean_numerocuenta(self):
        value = self.cleaned_data.get("numerocuenta")
        value = value.strip() if value else value
        self.cleaned_data["numerocuenta"] = value
        return validate_unique_field(
            self,
            "numerocuenta",
            "Este número de cuenta ya existe.",
        )

    def clean_esprincipal(self):
        value = self.cleaned_data.get("esprincipal")
        if value is None:
            return value

        queryset = Cuentabancaria.objects.filter(esprincipal=value)
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError(
                "Ya existe otra cuenta con esta misma marca. Use 'Sin marcar' si no es cuenta principal."
            )
        return value

    def clean_tipocuenta(self):
        value = self.cleaned_data.get("tipocuenta")
        if not value:
            return value

        normalized_values = {
            "ahorro": "Ahorro",
            "corriente": "Corriente",
        }
        normalized = normalized_values.get(value.strip().lower())
        if not normalized:
            raise forms.ValidationError("Seleccione un tipo de cuenta válido.")
        return normalized

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipocuenta"].widget = forms.Select(
            choices=(
                ("Ahorro", "Ahorro"),
                ("Corriente", "Corriente"),
            )
        )
        self.fields["tipocuenta"].widget.attrs["class"] = "form-select"
