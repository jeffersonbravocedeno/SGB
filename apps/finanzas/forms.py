from django import forms

from apps.common.forms import FriendlyModelForm, validate_unique_field
from apps.configuracion.models import Metodopago
from apps.socios.models import Socio

from .models import Ahorro, Aportesemanal, Pago, Prestamo


class PrestamoForm(FriendlyModelForm):
    date_fields = ("fechasolicitud", "fechavencimiento")
    state_fields = ("estadoprestamo",)
    state_choices = {
        "estadoprestamo": (
            ("Solicitado", "Solicitado"),
            ("Aprobado", "Aprobado"),
            ("En espera", "En espera"),
            ("Liquidado", "Liquidado"),
        )
    }
    non_negative_fields = (
        "montoprestamosolicitado",
        "tasainteres",
        "montototalpagar",
        "saldopendiente",
        "numerocuotas",
    )
    integrity_error_map = ()
    constraint_error_messages = {
        "numerocuotas": "Ingrese un número de cuotas mayor o igual a uno.",
    }

    class Meta:
        model = Prestamo
        fields = (
            "idsocio",
            "montoprestamosolicitado",
            "tasainteres",
            "montototalpagar",
            "saldopendiente",
            "numerocuotas",
            "fechasolicitud",
            "fechavencimiento",
            "estadoprestamo",
        )
        labels = {
            "idsocio": "Socio",
            "montoprestamosolicitado": "Monto solicitado",
            "tasainteres": "Tasa de interés",
            "montototalpagar": "Monto total a pagar",
            "saldopendiente": "Saldo pendiente",
            "numerocuotas": "Número de cuotas",
            "fechasolicitud": "Fecha de solicitud",
            "fechavencimiento": "Fecha de vencimiento",
            "estadoprestamo": "Estado",
        }

    def clean_numerocuotas(self):
        value = self.cleaned_data.get("numerocuotas")
        if value is not None and value < 1:
            raise forms.ValidationError("Ingrese un número de cuotas mayor o igual a uno.")
        return value


def _idsocio_modelo(socio):
    if socio is None:
        return None
    return getattr(socio, "idsocio", getattr(socio, "pk", None))


class PrestamoConGarantesForm(PrestamoForm):
    garante_1 = forms.ModelChoiceField(
        queryset=Socio.objects.order_by(
            "primerapellidosocio",
            "segundoapellidosocio",
            "primernombresocio",
            "idsocio",
        ),
        label="Garante 1",
        help_text=(
            "Los garantes deben cubrir en conjunto al menos el 50% del monto "
            "solicitado."
        ),
    )
    garante_2 = forms.ModelChoiceField(
        queryset=Socio.objects.order_by(
            "primerapellidosocio",
            "segundoapellidosocio",
            "primernombresocio",
            "idsocio",
        ),
        label="Garante 2",
        required=False,
    )

    def __init__(self, *args, socio_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if socio_queryset is None:
            socio_queryset = Socio.objects.order_by(
                "primerapellidosocio",
                "segundoapellidosocio",
                "primernombresocio",
                "idsocio",
            )
        for field_name in ("idsocio", "garante_1", "garante_2"):
            self.fields[field_name].queryset = socio_queryset

    def clean(self):
        cleaned_data = super().clean()
        socio_deudor = cleaned_data.get("idsocio")
        garante_1 = cleaned_data.get("garante_1")
        garante_2 = cleaned_data.get("garante_2")
        socio_deudor_id = _idsocio_modelo(socio_deudor)
        garante_1_id = _idsocio_modelo(garante_1)
        garante_2_id = _idsocio_modelo(garante_2)

        if garante_1_id and socio_deudor_id and garante_1_id == socio_deudor_id:
            self.add_error(
                "garante_1",
                "El garante no puede ser el mismo socio deudor.",
            )
        if garante_2_id and socio_deudor_id and garante_2_id == socio_deudor_id:
            self.add_error(
                "garante_2",
                "El garante no puede ser el mismo socio deudor.",
            )
        if garante_1_id and garante_2_id and garante_1_id == garante_2_id:
            self.add_error("garante_2", "No puede repetir el mismo garante.")

        return cleaned_data

    def datos_prestamo(self):
        return {
            field_name: self.cleaned_data[field_name]
            for field_name in self.Meta.fields
        }

    def garantes_seleccionados(self):
        garantes = [self.cleaned_data["garante_1"]]
        garante_2 = self.cleaned_data.get("garante_2")
        if garante_2:
            garantes.append(garante_2)
        return garantes


class PagoForm(FriendlyModelForm):
    datetime_fields = ("fechapago",)
    state_fields = ("estadopago",)
    state_choices = {
        "estadopago": (
            ("Pendiente", "Pendiente"),
            ("Validado", "Validado"),
            ("Rechazado", "Rechazado"),
        )
    }
    non_negative_fields = ("montopagado",)
    integrity_error_map = (
        (
            "numeroreferencia",
            ("numeroreferencia", "pago_numeroreferencia", "unique"),
            "Este número de referencia ya existe.",
        ),
    )

    class Meta:
        model = Pago
        fields = (
            "idmetodopago",
            "montopagado",
            "numeroreferencia",
            "fechapago",
            "comprobantepago",
            "estadopago",
        )
        labels = {
            "idmetodopago": "Método de pago",
            "montopagado": "Monto pagado",
            "numeroreferencia": "Número de referencia",
            "fechapago": "Fecha de pago",
            "comprobantepago": "Comprobante de pago",
            "estadopago": "Estado",
        }
        error_messages = {
            "numeroreferencia": {
                "unique": "Este número de referencia ya existe.",
            }
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["idmetodopago"].queryset = Metodopago.objects.order_by("nombremetodopago")

    def clean_numeroreferencia(self):
        value = self.cleaned_data.get("numeroreferencia")
        value = value.strip() if value else None
        self.cleaned_data["numeroreferencia"] = value
        return validate_unique_field(
            self,
            "numeroreferencia",
            "Este número de referencia ya existe.",
        )


class AhorroForm(FriendlyModelForm):
    datetime_fields = ("fechaahorro",)
    state_fields = ("estado",)
    state_choices = {
        "estado": (
            ("Activo", "Activo"),
            ("Inactivo", "Inactivo"),
        )
    }
    non_negative_fields = ("montoahorro",)
    integrity_error_map = ()
    constraint_error_messages = {
        "tipoahorro": "Seleccione un tipo de ahorro válido.",
    }

    class Meta:
        model = Ahorro
        fields = (
            "idsocio",
            "idbingo",
            "tipoahorro",
            "montoahorro",
            "fechaahorro",
            "comentarioahorro",
            "estado",
        )
        labels = {
            "idsocio": "Socio",
            "idbingo": "Bingo",
            "tipoahorro": "Tipo de ahorro",
            "montoahorro": "Monto",
            "fechaahorro": "Fecha de ahorro",
            "comentarioahorro": "Comentario",
            "estado": "Estado",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipoahorro"].widget = forms.Select(
            choices=(
                ("Obligatorio", "Obligatorio"),
                ("Voluntario", "Voluntario"),
            )
        )
        self.fields["tipoahorro"].widget.attrs["class"] = "form-select"

    def clean_tipoahorro(self):
        value = self.cleaned_data.get("tipoahorro")
        if not value:
            return value

        normalized_values = {
            "obligatorio": "Obligatorio",
            "voluntario": "Voluntario",
        }
        normalized = normalized_values.get(value.strip().lower())
        if not normalized:
            raise forms.ValidationError("Seleccione un tipo de ahorro válido.")
        return normalized


class AporteSemanalForm(FriendlyModelForm):
    datetime_fields = ("fechaplanificadada", "fechaentregareal")
    state_fields = ("estadoaporte",)
    state_choices = {
        "estadoaporte": (
            ("Al Dia", "Al día"),
            ("Atrasado", "Atrasado"),
        )
    }
    non_negative_fields = ("numerosemana",)
    integrity_error_map = ()
    constraint_error_messages = {
        "metodoingreso": "Seleccione un método de ingreso válido.",
    }

    class Meta:
        model = Aportesemanal
        fields = (
            "idsocio",
            "idregalo",
            "idpartida",
            "numerosemana",
            "fechaplanificadada",
            "fechaentregareal",
            "metodoingreso",
            "referenciaingreso",
            "estadoaporte",
        )
        labels = {
            "idsocio": "Socio",
            "idregalo": "Regalo",
            "idpartida": "Partida",
            "numerosemana": "Número de semana",
            "fechaplanificadada": "Fecha planificada",
            "fechaentregareal": "Fecha de entrega real",
            "metodoingreso": "Método de ingreso",
            "referenciaingreso": "Referencia de ingreso",
            "estadoaporte": "Estado",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["metodoingreso"].widget = forms.Select(
            choices=(
                ("Efectivo", "Efectivo"),
                ("Transferencia", "Transferencia"),
                ("Fisico", "Físico"),
            )
        )
        self.fields["metodoingreso"].widget.attrs["class"] = "form-select"

    def clean_metodoingreso(self):
        value = self.cleaned_data.get("metodoingreso")
        if not value:
            return value

        normalized_values = {
            "efectivo": "Efectivo",
            "transferencia": "Transferencia",
            "fisico": "Fisico",
            "físico": "Fisico",
        }
        normalized = normalized_values.get(value.strip().lower())
        if not normalized:
            raise forms.ValidationError("Seleccione un método de ingreso válido.")
        return normalized
