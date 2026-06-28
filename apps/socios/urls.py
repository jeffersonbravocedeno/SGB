from django.urls import path

from . import views


app_name = "socios"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.nuevo, name="nuevo"),
    path("<int:idsocio>/", views.detalle, name="detalle"),
    path("<int:idsocio>/editar/", views.editar, name="editar"),
    path("<int:idsocio>/cuentas/nueva/", views.cuenta_nueva, name="cuenta_nueva"),
    path("cuentas/<int:idcuentabancaria>/editar/", views.cuenta_editar, name="cuenta_editar"),
]
