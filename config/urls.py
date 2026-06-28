from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.seguridad.forms import SIABAuthenticationForm, SIABPasswordChangeForm

from .views import health, home


urlpatterns = [
    path("", home, name="home"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=SIABAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            form_class=SIABPasswordChangeForm,
            success_url="/password-change/done/",
        ),
        name="password_change",
    ),
    path(
        "password-change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("configuracion/", include("apps.configuracion.urls")),
    path("socios/", include("apps.socios.urls")),
    path("jugadores/", include("apps.jugadores.urls")),
    path("finanzas/", include("apps.finanzas.urls")),
    path("", include("apps.bingos.urls")),
    path("seguridad/", include("apps.seguridad.urls")),
]
