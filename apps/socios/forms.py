from django import forms

from apps.common.forms import FriendlyModelForm, apply_bootstrap, validate_unique_field
from apps.configuracion.models import Tiposocio

from .models import Cuentabancaria, Socio, SolicitudSocio


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


class SolicitudSocioForm(FriendlyModelForm):
    date_fields = ("fechanacimientosocio",)
    integrity_error_map = ()

    class Meta:
        model = SolicitudSocio
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
            "observacion",
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
            "observacion": "Observación",
        }
        widgets = {
            "direcciondomiciliosocio": forms.Textarea(attrs={"rows": 2}),
            "direcciontrabajosocio": forms.Textarea(attrs={"rows": 2}),
            "observacion": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "cisocio": {
                "max_length": "La cédula no puede superar los 10 caracteres.",
            }
        }

    def __init__(self, *args, tipo_socio_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tipo_socio_queryset is None:
            tipo_socio_queryset = Tiposocio.objects.order_by("nombretiposocio")
        self.fields["idtiposocio"].queryset = tipo_socio_queryset
        self.fields["idtiposocio"].required = False
        self.fields["idtiposocio"].empty_label = "Se definirá en la aprobación"
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
        return _texto_requerido(value)

    def clean_primernombresocio(self):
        value = self.cleaned_data.get("primernombresocio")
        return _texto_requerido(value)

    def clean_primerapellidosocio(self):
        value = self.cleaned_data.get("primerapellidosocio")
        return _texto_requerido(value)

    def clean_segundoapellidosocio(self):
        value = self.cleaned_data.get("segundoapellidosocio")
        return _texto_requerido(value)

    def clean_direcciondomiciliosocio(self):
        value = self.cleaned_data.get("direcciondomiciliosocio")
        return _texto_requerido(value)

    def clean_sexosocio(self):
        value = self.cleaned_data.get("sexosocio")
        if value not in ("", None, "H", "M"):
            raise forms.ValidationError("Seleccione un sexo válido.")
        return value

    def clean_observacion(self):
        value = self.cleaned_data.get("observacion")
        return value.strip() if value else None


class AprobarSolicitudSocioForm(forms.Form):
    idtiposocio = forms.ModelChoiceField(
        queryset=Tiposocio.objects.none(),
        label="Tipo de socio",
        required=False,
        help_text="Obligatorio si la solicitud no trae tipo de socio y se debe crear un socio nuevo.",
    )
    estadosocio = forms.ChoiceField(
        label="Estado del socio",
        required=False,
        choices=(
            ("Activo", "Activo"),
            ("Inactivo", "Inactivo"),
        ),
        initial="Activo",
    )
    observacion = forms.CharField(
        label="Observación",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, tipo_socio_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tipo_socio_queryset is None:
            tipo_socio_queryset = Tiposocio.objects.order_by("nombretiposocio")
        self.fields["idtiposocio"].queryset = tipo_socio_queryset
        apply_bootstrap(self)

    def clean_observacion(self):
        value = self.cleaned_data.get("observacion")
        return value.strip() if value else ""


class RechazarSolicitudSocioForm(forms.Form):
    motivorechazo = forms.CharField(
        label="Motivo de rechazo",
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"required": "Debe ingresar un motivo de rechazo."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)

    def clean_motivorechazo(self):
        value = self.cleaned_data.get("motivorechazo")
        value = value.strip() if value else ""
        if not value:
            raise forms.ValidationError("Debe ingresar un motivo de rechazo.")
        return value


def _texto_requerido(value):
    value = value.strip() if value else ""
    if not value:
        raise forms.ValidationError("Este campo es obligatorio.")
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
