from django.contrib import admin
from django.urls import include, path

from .views import health, home


urlpatterns = [
    path("", home, name="home"),
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("configuracion/", include("apps.configuracion.urls")),
    path("socios/", include("apps.socios.urls")),
    path("jugadores/", include("apps.jugadores.urls")),
    path("finanzas/", include("apps.finanzas.urls")),
    path("bingos/", include("apps.bingos.urls")),
    path("seguridad/", include("apps.seguridad.urls")),
]
