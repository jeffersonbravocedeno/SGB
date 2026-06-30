from django.urls import path

from . import views


app_name = "jugadores"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nuevo/", views.nuevo, name="nuevo"),
    path("<int:idjugador>/", views.detalle, name="detalle"),
    path("<int:idjugador>/crear-acceso/", views.crear_acceso, name="crear_acceso"),
    path("<int:idjugador>/editar/", views.editar, name="editar"),
]
