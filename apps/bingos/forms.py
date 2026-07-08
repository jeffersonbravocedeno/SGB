from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.common.forms import (
    FriendlyModelForm,
    apply_bootstrap,
    validate_optional_url,
    validate_optional_url_or_path,
    validate_unique_field,
)
from apps.jugadores.models import Jugador

from .models import Bingo, Carton, Partidabingo
from .services import (
    ESTADOS_PARTIDA,
    ESTADO_PARTIDA_PROGRAMADA,
    estado_partida_valido,
    normalizar_estado_partida,
)


class BingoForm(FriendlyModelForm):
    datetime_fields = ("fechaprogramadabingo",)
    state_fields = ("estadobingo",)
    state_choices = {
        "estadobingo": (
            ("Programado", "Programado"),
            ("En Curso", "En curso"),
            ("Finalizado", "Finalizado"),
            ("Cancelado", "Cancelado"),
        )
    }
    non_negative_fields = ("preciocarton", "premiomayor")

    integrity_error_map = ()

    class Meta:
        model = Bingo
        fields = (
            "titulobingo",
            "fechaprogramadabingo",
            "tipobingo",
            "lugarbingo",
            "urlsesionbingo",
            "preciocarton",
            "premiomayor",
            "descripcionpremiomayor",
            "estadobingo",
            "rutaimagenpremiomayor",
            "urlvideopromocional",
            "descripcionpremios",
        )
        labels = {
            "titulobingo": "Título",
            "fechaprogramadabingo": "Fecha programada",
            "tipobingo": "Tipo de bingo",
            "lugarbingo": "Lugar",
            "urlsesionbingo": "URL de sesión",
            "preciocarton": "Precio del cartón",
            "premiomayor": "Premio mayor",
            "descripcionpremiomayor": "Descripción del premio mayor",
            "estadobingo": "Estado",
            "rutaimagenpremiomayor": "Imagen del premio mayor",
            "urlvideopromocional": "Video promocional",
            "descripcionpremios": "Descripción de premios",
        }
        widgets = {
            "descripcionpremios": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_urlsesionbingo(self):
        return validate_optional_url(self.cleaned_data.get("urlsesionbingo"))

    def clean_urlvideopromocional(self):
        return validate_optional_url_or_path(self.cleaned_data.get("urlvideopromocional"))

    def clean_rutaimagenpremiomayor(self):
        return validate_optional_url_or_path(self.cleaned_data.get("rutaimagenpremiomayor"))


class PartidaBingoForm(FriendlyModelForm):
    datetime_fields = ("horainicio", "horafin")
    state_fields = ("estadopartida",)
    state_choices = {
        "estadopartida": ESTADOS_PARTIDA,
    }
    non_negative_fields = (
        "valorefectivo",
        "ultimabola",
        "bolamayordesempate",
    )
    integrity_error_map = ()
    constraint_error_messages = {
        "estadopartida": (
            "La base de datos aún no permite guardar este estado. "
            "Debe aplicarse el script DATABASE/actualizar_estados_partidabingo.sql."
        ),
    }

    class Meta:
        model = Partidabingo
        fields = (
            "idjugadorganador",
            "nombreronda",
            "valorefectivo",
            "premiomaterial",
            "estadopartida",
            "patronganador",
            "bolascantadas",
            "ultimabola",
            "haydesempate",
            "idbingadores",
            "bolamayordesempate",
            "horainicio",
            "horafin",
        )
        labels = {
            "idjugadorganador": "Jugador ganador",
            "nombreronda": "Nombre de ronda",
            "valorefectivo": "Premio en efectivo",
            "premiomaterial": "Premio material",
            "estadopartida": "Estado",
            "patronganador": "Patrón ganador",
            "bolascantadas": "Bolas cantadas",
            "ultimabola": "Última bola",
            "haydesempate": "Hay desempate",
            "idbingadores": "Bingadores",
            "bolamayordesempate": "Bola mayor de desempate",
            "horainicio": "Hora de inicio",
            "horafin": "Hora de finalización",
        }
        widgets = {
            "bolascantadas": forms.Textarea(attrs={"rows": 3}),
            "idbingadores": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["idjugadorganador"].queryset = Jugador.objects.order_by("aliasjugador")
        self.fields["idjugadorganador"].empty_label = "Sin ganador definido"
        patronganador_field = self.fields["patronganador"]
        patronganador_field.initial = (
            patronganador_field.initial
            or self._meta.model._meta.get_field("patronganador").default
        )
        if self.instance and self.instance.pk:
            estado = normalizar_estado_partida(self.instance.estadopartida)
            if estado != ESTADO_PARTIDA_PROGRAMADA:
                patronganador_field.disabled = True
                patronganador_field.help_text = (
                    "Solo se puede cambiar cuando la ronda está Programada."
                )

    def clean_estadopartida(self):
        estado = normalizar_estado_partida(self.cleaned_data.get("estadopartida"))
        if estado and not estado_partida_valido(estado):
            raise ValidationError("Seleccione un estado válido.")
        return estado


class CartonForm(FriendlyModelForm):
    datetime_fields = ("fechacompra",)
    state_fields = ("estadocarton",)
    state_choices = {
        "estadocarton": (
            ("Disponible", "Disponible"),
            ("Vendido", "Vendido"),
            ("Cerrado", "Cerrado"),
        )
    }
    non_negative_fields = ("indicevictoria", "preciopagado")
    integrity_error_map = (
        ("codigocarton", ("codigocarton", "carton_codigocarton", "unique"), "Este código de cartón ya existe."),
    )

    class Meta:
        model = Carton
        fields = (
            "idjugador",
            "idpartida",
            "codigocarton",
            "matriznumeros",
            "indicevictoria",
            "preciopagado",
            "fechacompra",
            "estadocarton",
        )
        labels = {
            "idjugador": "Jugador",
            "idpartida": "Partida",
            "codigocarton": "Código del cartón",
            "matriznumeros": "Matriz de números",
            "indicevictoria": "Índice de victoria",
            "preciopagado": "Precio pagado",
            "fechacompra": "Fecha de compra",
            "estadocarton": "Estado",
        }
        widgets = {
            "matriznumeros": forms.Textarea(attrs={"rows": 4}),
        }
        error_messages = {
            "codigocarton": {
                "unique": "Este código de cartón ya existe.",
            }
        }

    def clean_codigocarton(self):
        value = self.cleaned_data.get("codigocarton")
        value = value.strip() if value else value
        self.cleaned_data["codigocarton"] = value
        return validate_unique_field(
            self,
            "codigocarton",
            "Este código de cartón ya existe.",
        )


class GenerarAsignarCartonForm(FriendlyModelForm):
    non_negative_fields = ("preciopagado",)

    class Meta:
        model = Carton
        fields = ("idjugador", "preciopagado")
        labels = {
            "idjugador": "Jugador",
            "preciopagado": "Precio pagado",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["idjugador"].required = True
        self.fields["idjugador"].empty_label = "Seleccione un jugador"
        self.fields["idjugador"].queryset = Jugador.objects.order_by("aliasjugador")
        self.fields["preciopagado"].required = True
        self.fields["preciopagado"].min_value = Decimal("0.01")
        self.fields["preciopagado"].widget.attrs.update(
            {"min": "0.01", "step": "0.01"}
        )

    def clean_preciopagado(self):
        precio = self.cleaned_data.get("preciopagado")
        if precio is None or precio <= 0:
            raise ValidationError("El precio pagado debe ser mayor que cero.")
        return precio


class GenerarCartonBingoForm(FriendlyModelForm):
    """Datos mínimos para vender un maestro híbrido para todo un Bingo."""

    non_negative_fields = ("preciopagado",)

    class Meta:
        model = Carton
        fields = ("idjugador", "preciopagado")
        labels = {
            "idjugador": "Jugador",
            "preciopagado": "Precio pagado",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["idjugador"].required = True
        self.fields["idjugador"].empty_label = "Seleccione un jugador"
        self.fields["idjugador"].queryset = Jugador.objects.order_by(
            "aliasjugador"
        )
        self.fields["preciopagado"].required = True
        self.fields["preciopagado"].min_value = Decimal("0.01")
        self.fields["preciopagado"].error_messages["min_value"] = (
            "El precio pagado debe ser mayor que cero."
        )
        self.fields["preciopagado"].widget.attrs.update(
            {"min": "0.01", "step": "0.01"}
        )

    def clean_preciopagado(self):
        precio = self.cleaned_data.get("preciopagado")
        if precio is None or precio <= 0:
            raise ValidationError("El precio pagado debe ser mayor que cero.")
        return precio


class CompraCartonJugadorForm(forms.Form):
    confirmar_compra = forms.BooleanField(
        label="Confirmo la compra de este cartón para el Bingo.",
        required=True,
        error_messages={
            "required": "Confirme la compra para continuar.",
        },
    )


class GastoOperativoBingoForm(forms.Form):
    concepto = forms.CharField(
        label="Concepto",
        max_length=150,
        error_messages={"required": "Ingrese el concepto del gasto."},
    )
    monto = forms.DecimalField(
        label="Monto",
        max_digits=12,
        decimal_places=2,
        error_messages={
            "required": "Ingrese el monto del gasto.",
            "invalid": "Ingrese un valor numérico válido.",
        },
    )
    fechagasto = forms.DateTimeField(
        label="Fecha de gasto",
        required=False,
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        error_messages={"invalid": "Ingrese una fecha y hora válidas."},
        help_text="Opcional. Si se deja vacía, se usará la fecha actual.",
    )
    observacion = forms.CharField(
        label="Observación",
        max_length=300,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["monto"].widget.attrs.update({"step": "0.01"})
        apply_bootstrap(self)


class MotivoAnulacionForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo de anulación",
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 2}),
        error_messages={"required": "Ingrese el motivo de anulación."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)


class CartonPartidaForm(CartonForm):
    class Meta(CartonForm.Meta):
        fields = (
            "idjugador",
            "codigocarton",
            "matriznumeros",
            "indicevictoria",
            "preciopagado",
            "fechacompra",
            "estadocarton",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["idjugador"].required = True
        self.fields["idjugador"].empty_label = "Seleccione un jugador"


class AccesoCartonPublicoForm(forms.Form):
    codigocarton = forms.CharField(
        label="Código del cartón",
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "placeholder": "Ej. P20-C-ABC123",
            }
        ),
    )

    def clean_codigocarton(self):
        codigo = self.cleaned_data["codigocarton"].strip()
        if not codigo:
            raise ValidationError("Ingrese el código de su cartón.")
        return codigo
