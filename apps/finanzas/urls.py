from django.urls import path

from . import views


app_name = "finanzas"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("prestamos/", views.prestamos_lista, name="prestamos_lista"),
    path("prestamos/nuevo/", views.prestamo_nuevo, name="prestamo_nuevo"),
    path("prestamos/<int:idprestamo>/", views.prestamo_detalle, name="prestamo_detalle"),
    path("prestamos/<int:idprestamo>/editar/", views.prestamo_editar, name="prestamo_editar"),
    path("prestamos/<int:idprestamo>/pagos/nuevo/", views.pago_nuevo, name="pago_nuevo"),
    path("pagos/", views.pagos_lista, name="pagos_lista"),
    path(
        "solicitudes-pago/",
        views.solicitudes_pago_prestamo_lista,
        name="solicitudes_pago_prestamo_lista",
    ),
    path(
        "solicitudes-pago/<int:idsolicitudpago>/",
        views.solicitud_pago_prestamo_detalle,
        name="solicitud_pago_prestamo_detalle",
    ),
    path(
        "solicitudes-pago/<int:idsolicitudpago>/aprobar/",
        views.solicitud_pago_prestamo_aprobar,
        name="solicitud_pago_prestamo_aprobar",
    ),
    path(
        "solicitudes-pago/<int:idsolicitudpago>/rechazar/",
        views.solicitud_pago_prestamo_rechazar,
        name="solicitud_pago_prestamo_rechazar",
    ),
    path("ahorros/", views.ahorros_lista, name="ahorros_lista"),
    path("ahorros/nuevo/", views.ahorro_nuevo, name="ahorro_nuevo"),
    path("aportes/", views.aportes_lista, name="aportes_lista"),
    path("aportes/nuevo/", views.aporte_nuevo, name="aporte_nuevo"),
]
