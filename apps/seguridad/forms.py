from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.jugadores.models import Jugador
from apps.jugadores.services import (
    estado_cuenta_acceso_jugador,
    normalizar_alias_jugador,
)


class SIABAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "Usuario o contraseña incorrectos.",
        "inactive": "Esta cuenta está inactiva.",
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].label = "Usuario"
        self.fields["password"].label = "Contraseña"
        for field in self.fields.values():
            field.error_messages["required"] = "Este campo es obligatorio."


class SIABPasswordChangeForm(PasswordChangeForm):
    error_messages = {
        **PasswordChangeForm.error_messages,
        "password_incorrect": "La contraseña actual no es correcta.",
    }

    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        labels = {
            "old_password": "Contraseña actual",
            "new_password1": "Nueva contraseña",
            "new_password2": "Confirmar nueva contraseña",
        }
        for name, field in self.fields.items():
            field.label = labels.get(name, field.label)
            field.error_messages["required"] = "Este campo es obligatorio."


class RegistroJugadorForm(forms.Form):
    aliasjugador = forms.CharField(
        label="Alias de jugador",
        max_length=100,
        error_messages={
            "required": "Ingrese un alias.",
            "max_length": "El alias no puede superar los 100 caracteres.",
        },
    )
    correojugador = forms.EmailField(
        label="Correo electrónico",
        max_length=200,
        error_messages={
            "required": "Ingrese un correo electrónico.",
            "invalid": "Ingrese un correo electrónico válido.",
            "max_length": "El correo no puede superar los 200 caracteres.",
        },
    )
    password1 = forms.CharField(
        label="Contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Ingrese una contraseña."},
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Confirme la contraseña."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["aliasjugador"].widget.attrs.update(
            {
                "autocomplete": "username",
                "placeholder": "maria456",
            }
        )
        self.fields["correojugador"].widget.attrs.update(
            {
                "autocomplete": "email",
                "placeholder": "correo@ejemplo.com",
            }
        )

    def clean_aliasjugador(self):
        alias = normalizar_alias_jugador(self.cleaned_data.get("aliasjugador"))
        if not alias:
            raise ValidationError("Ingrese un alias.")
        if Jugador.objects.filter(aliasjugador__iexact=alias).exists():
            raise ValidationError("Este alias ya está registrado como jugador.")
        if User.objects.filter(username__iexact=alias).exists():
            raise ValidationError("Este alias ya está ocupado por una cuenta.")
        return alias

    def clean_correojugador(self):
        correo = (self.cleaned_data.get("correojugador") or "").strip().lower()
        if Jugador.objects.filter(correojugador__iexact=correo).exists():
            raise ValidationError("Este correo ya está registrado como jugador.")
        return correo

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")

        if password1:
            user = User(
                username=cleaned_data.get("aliasjugador") or "",
                email=cleaned_data.get("correojugador") or "",
            )
            try:
                validate_password(password1, user=user)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data


class CrearAccesoJugadorForm(forms.Form):
    username = forms.CharField(
        label="Usuario",
        required=False,
        disabled=True,
    )
    password1 = forms.CharField(
        label="Contraseña inicial",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Ingrese una contraseña inicial."},
    )
    password2 = forms.CharField(
        label="Confirmar contraseña",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        error_messages={"required": "Confirme la contraseña inicial."},
    )

    def __init__(self, jugador, *args, **kwargs):
        self.jugador = jugador
        super().__init__(*args, **kwargs)
        self.fields["username"].initial = normalizar_alias_jugador(
            jugador.aliasjugador
        )

    def clean(self):
        cleaned_data = super().clean()
        estado = estado_cuenta_acceso_jugador(self.jugador)
        if not estado["puede_crear"]:
            self.add_error(None, estado["mensaje"])

        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")

        if password1:
            user = User(
                username=normalizar_alias_jugador(self.jugador.aliasjugador),
                email=self.jugador.correojugador or "",
            )
            try:
                validate_password(password1, user=user)
            except ValidationError as exc:
                self.add_error("password1", exc)

        return cleaned_data
