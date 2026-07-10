from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.jugadores.services import registrar_jugador_publico, usuario_es_jugador

from .forms import RegistroJugadorForm, SIABAuthenticationForm


class SIABLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = SIABAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        user = self.request.user
        next_url = self.get_redirect_url()

        if user.is_staff or user.is_superuser:
            if _next_permitido_para_staff(next_url):
                return next_url
            return reverse("home")

        if usuario_es_jugador(user):
            if _next_permitido_para_jugador(next_url):
                return next_url
            return reverse("bingos:mis_cartones")

        return reverse("seguridad:cuenta_sin_acceso")


def _next_permitido_para_jugador(next_url):
    if not next_url:
        return False
    rutas_permitidas = (
        reverse("bingos:mis_cartones"),
        reverse("socios:portal_socio"),
        reverse("socios:mi_solicitud_socio"),
        "/juego/",
        reverse("password_change"),
        reverse("password_change_done"),
    )
    return any(next_url.startswith(ruta) for ruta in rutas_permitidas)


def _next_permitido_para_staff(next_url):
    if not next_url:
        return False
    return not next_url.startswith(reverse("bingos:mis_cartones"))


@require_http_methods(["GET", "POST"])
def registro_jugador(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect("home")
        if usuario_es_jugador(request.user):
            return redirect("bingos:mis_cartones")
        return redirect("seguridad:cuenta_sin_acceso")

    form = RegistroJugadorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            _jugador, user = registrar_jugador_publico(
                alias=form.cleaned_data["aliasjugador"],
                correo=form.cleaned_data["correojugador"],
                password=form.cleaned_data["password1"],
            )
        except (IntegrityError, ValidationError):
            form.add_error(
                None,
                "No fue posible completar el registro. Verifica los datos e inténtalo nuevamente.",
            )
        else:
            login(request, user)
            messages.success(
                request,
                "Registro completado. Ya puedes revisar tus cartones asignados.",
            )
            return redirect("bingos:mis_cartones")

    return render(
        request,
        "registration/registro_jugador.html",
        {"form": form},
    )


@login_required
def cuenta_sin_acceso(request):
    return render(request, "seguridad/cuenta_sin_acceso.html")
