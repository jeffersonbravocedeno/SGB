from django.urls import path

from . import views


app_name = "seguridad"

urlpatterns = [
    path("cuenta-sin-acceso/", views.cuenta_sin_acceso, name="cuenta_sin_acceso"),
]
