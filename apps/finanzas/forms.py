from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms

from apps.common.forms import FriendlyModelForm
from apps.configuracion.models import Metodopago
from apps.socios.models import Socio

from .models import (
    Ahorro,
    Aportesemanal,
    PagoPrestamo,
    Prestamo,
    SolicitudPagoPrestamo,
)


MENSAJE_VENCIMIENTO_ANTERIOR = (
    "La fecha de vencimiento no puede ser anterior a la fecha de solicitud."
)
MENSAJE_VENCIMIENTO_FUERA_PERIODO = (
    "El préstamo debe vencer dentro del mismo período anual, máximo hasta el 31 "
    "de diciembre."
)
AYUDA_PERIODO_ANUAL_PRESTAMO = (
    "El vencimiento debe estar dentro del mismo período anual, máximo hasta el "
    "31 de diciembre del año de solicitud."
)
MENSAJE_TOTAL_MENOR_MONTO_SOLICITADO = (
    "El total a pagar no puede ser menor que el monto solicitado."
)


def validar_periodo_anual_prestamo(fechasolicitud, fechavencimiento):
    if not fechasolicitud or not fechavencimiento:
        return

    if fechavencimiento < fechasolicitud:
        raise forms.ValidationError(
            {"fechavencimiento": MENSAJE_VENCIMIENTO_ANTERIOR}
        )

    fecha_maxima = date(fechasolicitud.year, 12, 31)
    if fechavencimiento > fecha_maxima:
        raise forms.ValidationError(
            {"fechavencimiento": MENSAJE_VENCIMIENTO_FUERA_PERIODO}
        )


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "fechavencimiento" in self.fields:
            self.fields["fechavencimiento"].help_text = AYUDA_PERIODO_ANUAL_PRESTAMO

    def clean(self):
        cleaned_data = super().clean()
        validar_periodo_anual_prestamo(
            cleaned_data.get("fechasolicitud"),
            cleaned_data.get("fechavencimiento"),
        )
        monto_solicitado = cleaned_data.get("montoprestamosolicitado")
        monto_total = cleaned_data.get("montototalpagar")
        if (
            monto_solicitado is not None
            and monto_total is not None
            and monto_total < monto_solicitado
        ):
            self.add_error("montototalpagar", MENSAJE_TOTAL_MENOR_MONTO_SOLICITADO)
        return cleaned_data

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
        required=False,
        help_text=(
            "El préstamo puede registrarse sin garantes o con hasta dos "
            "garantes. Si registra garantes, la capacidad total de ellos debe "
            "cubrir al menos el 50% del monto solicitado."
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

    class Meta(PrestamoForm.Meta):
        fields = (
            "idsocio",
            "montoprestamosolicitado",
            "tasainteres",
            "montototalpagar",
            "numerocuotas",
            "fechasolicitud",
            "fechavencimiento",
            "estadoprestamo",
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
        garantes = []
        garante_1 = self.cleaned_data.get("garante_1")
        if garante_1:
            garantes.append(garante_1)
        garante_2 = self.cleaned_data.get("garante_2")
        if garante_2:
            garantes.append(garante_2)
        return garantes


class PrestamoEdicionForm(PrestamoForm):
    state_choices = {
        "estadoprestamo": (
            ("Solicitado", "Solicitado"),
            ("Aprobado", "Aprobado"),
            ("En espera", "En espera"),
        )
    }
    non_negative_fields = (
        "tasainteres",
        "numerocuotas",
    )

    class Meta:
        model = Prestamo
        fields = (
            "tasainteres",
            "numerocuotas",
            "fechasolicitud",
            "fechavencimiento",
            "estadoprestamo",
        )
        labels = {
            "tasainteres": "Tasa de interés",
            "numerocuotas": "Número de cuotas",
            "fechasolicitud": "Fecha de solicitud",
            "fechavencimiento": "Fecha de vencimiento",
            "estadoprestamo": "Estado",
        }


class PagoPrestamoForm(FriendlyModelForm):
    non_negative_fields = ("montopagado",)
    integrity_error_map = ()

    class Meta:
        model = PagoPrestamo
        fields = (
            "idmetodopago",
            "montopagado",
            "numeroreferencia",
            "observacion",
        )
        labels = {
            "idmetodopago": "Método de pago",
            "montopagado": "Monto pagado",
            "numeroreferencia": "Número de referencia",
            "observacion": "Observación",
        }

    def __init__(self, *args, metodo_pago_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if metodo_pago_queryset is None:
            metodo_pago_queryset = Metodopago.objects.order_by("nombremetodopago")
        self.fields["idmetodopago"].queryset = metodo_pago_queryset

    def clean_montopagado(self):
        value = self.cleaned_data.get("montopagado")
        if value is None or value <= 0:
            raise forms.ValidationError("El monto del pago debe ser mayor que cero.")
        return value

    def clean_numeroreferencia(self):
        value = self.cleaned_data.get("numeroreferencia")
        return value.strip() if value else ""

    def clean_observacion(self):
        value = self.cleaned_data.get("observacion")
        return value.strip() if value else ""


class SolicitudPagoPrestamoForm(FriendlyModelForm):
    integrity_error_map = ()

    class Meta:
        model = SolicitudPagoPrestamo
        fields = (
            "monto",
            "idmetodopago",
            "referencia",
            "rutacomprobante",
            "observacionsocio",
        )
        labels = {
            "monto": "Monto",
            "idmetodopago": "Método de pago",
            "referencia": "Referencia",
            "rutacomprobante": "Comprobante o dato de comprobante",
            "observacionsocio": "Observación",
        }
        widgets = {
            "observacionsocio": forms.Textarea(attrs={"rows": 3}),
        }
        error_messages = {
            "referencia": {
                "required": "Debe ingresar una referencia.",
            },
        }

    def __init__(self, *args, prestamo=None, metodo_pago_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.prestamo = prestamo
        self.fields["referencia"].max_length = 80
        self.fields["referencia"].widget.attrs["maxlength"] = 80
        self.fields["rutacomprobante"].max_length = 255
        self.fields["rutacomprobante"].widget.attrs["maxlength"] = 255
        if metodo_pago_queryset is None:
            metodo_pago_queryset = Metodopago.objects.order_by("nombremetodopago")
        self.fields["idmetodopago"].queryset = metodo_pago_queryset
        self.fields["idmetodopago"].required = False
        self.fields["referencia"].error_messages[
            "required"
        ] = "Debe ingresar una referencia."

    def clean_monto(self):
        value = self.cleaned_data.get("monto")
        if value is None or value <= 0:
            raise forms.ValidationError("El monto debe ser mayor que cero.")
        return value

    def clean_referencia(self):
        value = self.cleaned_data.get("referencia")
        value = value.strip() if value else ""
        if not value:
            raise forms.ValidationError("Debe ingresar una referencia.")
        return value

    def clean_rutacomprobante(self):
        return _texto_opcional(self.cleaned_data.get("rutacomprobante"))

    def clean_observacionsocio(self):
        return _texto_opcional(self.cleaned_data.get("observacionsocio"))

    def clean(self):
        cleaned_data = super().clean()
        monto = cleaned_data.get("monto")
        if self.prestamo is None or monto is None:
            return cleaned_data

        try:
            saldo_pendiente = Decimal(str(self.prestamo.saldopendiente))
        except (InvalidOperation, TypeError, ValueError):
            self.add_error("monto", "El préstamo no tiene saldo pendiente.")
            return cleaned_data

        if saldo_pendiente <= 0:
            self.add_error("monto", "El préstamo no tiene saldo pendiente.")
        elif monto > saldo_pendiente:
            self.add_error("monto", "El monto no puede superar el saldo pendiente.")
        return cleaned_data


class AprobarSolicitudPagoPrestamoForm(forms.Form):
    observacionadmin = forms.CharField(
        label="Observación administrativa",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_observacionadmin(self):
        return _texto_opcional(self.cleaned_data.get("observacionadmin")) or ""


class RechazarSolicitudPagoPrestamoForm(forms.Form):
    motivorechazo = forms.CharField(
        label="Motivo de rechazo",
        widget=forms.Textarea(attrs={"rows": 3}),
        error_messages={"required": "Debe ingresar un motivo de rechazo."},
    )

    def clean_motivorechazo(self):
        value = self.cleaned_data.get("motivorechazo")
        value = value.strip() if value else ""
        if not value:
            raise forms.ValidationError("Debe ingresar un motivo de rechazo.")
        return value


def _texto_opcional(value):
    value = value.strip() if value else ""
    return value or None


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

    def clean_montoahorro(self):
        value = self.cleaned_data.get("montoahorro")
        if value is None or value <= 0:
            raise forms.ValidationError("El monto del ahorro debe ser mayor que cero.")
        return value


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
        for field_name in (
            "idsocio",
            "idregalo",
            "numerosemana",
            "fechaplanificadada",
            "estadoaporte",
        ):
            self.fields[field_name].required = True
        self.fields["numerosemana"].widget.attrs["min"] = "1"
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

    def clean_numerosemana(self):
        value = self.cleaned_data.get("numerosemana")
        if value is None or value <= 0:
            raise forms.ValidationError("El número de semana debe ser mayor que cero.")
        return value

    def clean_idregalo(self):
        regalo = self.cleaned_data.get("idregalo")
        if regalo is None:
            return regalo

        valor = getattr(regalo, "valorregalo", None)
        try:
            valor = Decimal(str(valor))
        except (InvalidOperation, TypeError, ValueError):
            raise forms.ValidationError(
                "El regalo asociado al aporte debe tener un valor mayor que cero."
            ) from None
        if not valor.is_finite() or valor <= 0:
            raise forms.ValidationError(
                "El regalo asociado al aporte debe tener un valor mayor que cero."
            )
        return regalo
