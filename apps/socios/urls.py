from django.urls import path

from . import views


app_name = "socios"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("mi-solicitud/", views.mi_solicitud_socio, name="mi_solicitud_socio"),
    path("mi-solicitud/nueva/", views.solicitud_socio_nueva, name="solicitud_socio_nueva"),
    path("solicitudes/", views.solicitudes_socio_lista, name="solicitudes_socio_lista"),
    path("solicitudes/<int:idsolicitud>/", views.solicitud_socio_detalle, name="solicitud_socio_detalle"),
    path(
        "solicitudes/<int:idsolicitud>/aprobar/",
        views.solicitud_socio_aprobar,
        name="solicitud_socio_aprobar",
    ),
    path(
        "solicitudes/<int:idsolicitud>/rechazar/",
        views.solicitud_socio_rechazar,
        name="solicitud_socio_rechazar",
    ),
    path("nuevo/", views.nuevo, name="nuevo"),
    path("<int:idsocio>/", views.detalle, name="detalle"),
    path("<int:idsocio>/editar/", views.editar, name="editar"),
    path("<int:idsocio>/cuentas/nueva/", views.cuenta_nueva, name="cuenta_nueva"),
    path("cuentas/<int:idcuentabancaria>/editar/", views.cuenta_editar, name="cuenta_editar"),
]
