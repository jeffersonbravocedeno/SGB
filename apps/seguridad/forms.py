from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm


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
