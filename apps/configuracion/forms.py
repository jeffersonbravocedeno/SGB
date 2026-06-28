from django import forms
from django.utils import timezone

from apps.common.forms import (
    FriendlyModelForm,
    validate_optional_url,
    validate_optional_url_or_path,
    validate_unique_field,
)

from .models import Metodopago, Plataformajuego, Regalo, Tiposocio


class TipoSocioForm(FriendlyModelForm):
    integrity_error_map = (
        ("nombretiposocio", ("nombretiposocio", "tiposocio_nombretiposocio"), "Este tipo de socio ya existe."),
        ("roltiposocio", ("roltiposocio", "tiposocio_roltiposocio"), "Este rol ya está en uso."),
    )

    class Meta:
        model = Tiposocio
        fields = ("nombretiposocio", "roltiposocio", "descripciondetiposocio")
        labels = {
            "nombretiposocio": "Nombre del tipo de socio",
            "roltiposocio": "Rol",
            "descripciondetiposocio": "Descripción",
        }
        widgets = {
            "descripciondetiposocio": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "nombretiposocio": {"unique": "Este tipo de socio ya existe."},
            "roltiposocio": {"unique": "Este rol ya está en uso."},
        }

    def clean_nombretiposocio(self):
        value = self.cleaned_data.get("nombretiposocio")
        value = value.strip() if value else value
        self.cleaned_data["nombretiposocio"] = value
        return validate_unique_field(
            self,
            "nombretiposocio",
            "Este tipo de socio ya existe.",
        )

    def clean_roltiposocio(self):
        value = self.cleaned_data.get("roltiposocio")
        value = value.strip() if value else value
        self.cleaned_data["roltiposocio"] = value
        return validate_unique_field(
            self,
            "roltiposocio",
            "Este rol ya está en uso.",
        )


class MetodoPagoForm(FriendlyModelForm):
    integrity_error_map = (
        ("nombremetodopago", ("nombremetodopago", "metodopago_nombremetodopago"), "Este método de pago ya existe."),
    )

    class Meta:
        model = Metodopago
        fields = ("nombremetodopago", "descripcionmetodopago", "estadometodopago", "urlmetodopago")
        labels = {
            "nombremetodopago": "Nombre",
            "descripcionmetodopago": "Descripción",
            "estadometodopago": "Activo",
            "urlmetodopago": "URL o referencia",
        }
        widgets = {
            "descripcionmetodopago": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "nombremetodopago": {"unique": "Este método de pago ya existe."},
        }

    def clean_nombremetodopago(self):
        value = self.cleaned_data.get("nombremetodopago")
        value = value.strip() if value else value
        self.cleaned_data["nombremetodopago"] = value
        return validate_unique_field(
            self,
            "nombremetodopago",
            "Este método de pago ya existe.",
        )

    def clean_urlmetodopago(self):
        return validate_optional_url(self.cleaned_data.get("urlmetodopago"))


class PlataformaJuegoForm(FriendlyModelForm):
    date_fields = ("fechaadquisicionlicencia", "fechavencimientolicencia")
    integrity_error_map = (
        ("nombreplataforma", ("nombreplataforma", "plataformajuego_nombreplataforma"), "Esta plataforma ya existe."),
    )

    class Meta:
        model = Plataformajuego
        fields = (
            "nombreplataforma",
            "urlplataforma",
            "descripcionplataforma",
            "estadoplataforma",
            "fechaadquisicionlicencia",
            "fechavencimientolicencia",
            "contactoplataforma",
        )
        labels = {
            "nombreplataforma": "Nombre de plataforma",
            "urlplataforma": "URL",
            "descripcionplataforma": "Descripción",
            "estadoplataforma": "Activa",
            "fechaadquisicionlicencia": "Fecha de adquisición de licencia",
            "fechavencimientolicencia": "Fecha de vencimiento de licencia",
            "contactoplataforma": "Contacto",
        }
        widgets = {
            "descripcionplataforma": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "nombreplataforma": {"unique": "Esta plataforma ya existe."},
        }

    def clean_nombreplataforma(self):
        value = self.cleaned_data.get("nombreplataforma")
        value = value.strip() if value else value
        self.cleaned_data["nombreplataforma"] = value
        return validate_unique_field(
            self,
            "nombreplataforma",
            "Esta plataforma ya existe.",
        )

    def clean_urlplataforma(self):
        return validate_optional_url(self.cleaned_data.get("urlplataforma"))


class RegaloForm(FriendlyModelForm):
    state_fields = ("estadoregalo",)
    state_choices = {
        "estadoregalo": (
            ("Acumulado", "Acumulado"),
            ("Sorteado", "Sorteado"),
            ("Entregado", "Entregado"),
        )
    }
    non_negative_fields = ("valorregalo",)
    integrity_error_map = ()

    class Meta:
        model = Regalo
        fields = ("nombreregalo", "descripcionregalo", "valorregalo", "estadoregalo", "urlimagen")
        labels = {
            "nombreregalo": "Nombre",
            "descripcionregalo": "Descripción",
            "valorregalo": "Valor",
            "estadoregalo": "Estado",
            "urlimagen": "URL de imagen",
        }
        widgets = {
            "descripcionregalo": forms.Textarea(attrs={"rows": 3}),
        }

    @staticmethod
    def set_update_timestamp(instance):
        instance.fechaultimaactualizacion = timezone.now()

    def clean_urlimagen(self):
        return validate_optional_url_or_path(self.cleaned_data.get("urlimagen"))
