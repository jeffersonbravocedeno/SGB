from django import forms

from apps.common.forms import FriendlyModelForm, validate_unique_field
from apps.socios.models import Socio

from .models import Jugador


class JugadorForm(FriendlyModelForm):
    state_fields = ("estadocuentajugador",)
    state_choices = {
        "estadocuentajugador": (
            ("Activo", "Activo"),
            ("Suspendido", "Suspendido"),
            ("Moroso", "Moroso"),
        )
    }
    non_negative_fields = ("saldocreditojugador",)
    integrity_error_map = (
        ("aliasjugador", ("aliasjugador", "jugador_aliasjugador", "unique"), "Este alias ya está en uso."),
        ("correojugador", ("correojugador", "jugador_correojugador"), "Este correo ya está en uso."),
    )
    correojugador = forms.EmailField(
        required=False,
        label="Correo",
        max_length=200,
        error_messages={
            "invalid": "Ingrese un correo electrónico válido.",
            "max_length": "El correo no puede superar los 200 caracteres.",
        },
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder": "correo@ejemplo.com",
            }
        ),
    )

    class Meta:
        model = Jugador
        fields = (
            "idsocio",
            "avatarjugador",
            "aliasjugador",
            "correojugador",
            "saldocreditojugador",
            "estadocuentajugador",
        )
        labels = {
            "idsocio": "Socio vinculado",
            "avatarjugador": "Avatar",
            "aliasjugador": "Alias",
            "saldocreditojugador": "Saldo de crédito",
            "estadocuentajugador": "Estado de cuenta",
        }
        help_texts = {
            "idsocio": "Seleccione un socio solo si corresponde. Puede dejarlo vacío.",
            "avatarjugador": "URL o ruta del avatar. Campo opcional.",
            "estadocuentajugador": "Estado operativo de la cuenta.",
        }
        error_messages = {
            "aliasjugador": {
                "unique": "Este alias ya está en uso.",
                "max_length": "El alias no puede superar los 100 caracteres.",
            },
            "correojugador": {
                "unique": "Este correo ya está en uso.",
                "max_length": "El correo no puede superar los 200 caracteres.",
            },
            "saldocreditojugador": {
                "required": "Este campo es obligatorio.",
                "invalid": "Ingrese un valor numérico válido.",
            },
            "estadocuentajugador": {
                "required": "Este campo es obligatorio.",
                "max_length": "El estado no puede superar los 20 caracteres.",
            },
        }
        widgets = {
            "avatarjugador": forms.TextInput(
                attrs={
                    "autocomplete": "off",
                    "placeholder": "https://...",
                }
            ),
            "aliasjugador": forms.TextInput(
                attrs={
                    "autocomplete": "nickname",
                    "placeholder": "Alias público",
                }
            ),
            "saldocreditojugador": forms.NumberInput(
                attrs={
                    "min": "0",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "estadocuentajugador": forms.TextInput(
                attrs={
                    "autocomplete": "off",
                    "placeholder": "Activo",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["idsocio"].queryset = Socio.objects.order_by(
            "primerapellidosocio",
            "segundoapellidosocio",
            "primernombresocio",
        )
        self.fields["idsocio"].empty_label = "Sin socio vinculado"

    def clean_aliasjugador(self):
        value = self.cleaned_data.get("aliasjugador")
        value = value.strip() if value else None
        self.cleaned_data["aliasjugador"] = value
        return validate_unique_field(
            self,
            "aliasjugador",
            "Este alias ya está en uso.",
        )

    def clean_correojugador(self):
        value = self.cleaned_data.get("correojugador")
        value = value.strip().lower() if value else None
        self.cleaned_data["correojugador"] = value
        return validate_unique_field(
            self,
            "correojugador",
            "Este correo ya está en uso.",
        )

    def clean_avatarjugador(self):
        value = self.cleaned_data.get("avatarjugador")
        return value.strip() if value else None

    def clean(self):
        cleaned_data = super().clean()
        alias = cleaned_data.get("aliasjugador")
        correo = cleaned_data.get("correojugador")

        if not alias and not correo:
            message = "Ingrese un alias o un correo para identificar al jugador."
            self.add_error("aliasjugador", message)
            self.add_error("correojugador", message)

        return cleaned_data
