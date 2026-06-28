from django.urls import path

from . import views


app_name = "configuracion"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("tipos-socio/", views.section_list, {"section": "tipos-socio"}, name="tipos_socio_lista"),
    path("tipos-socio/nuevo/", views.section_new, {"section": "tipos-socio"}, name="tipos_socio_nuevo"),
    path("tipos-socio/<int:pk>/", views.section_detail, {"section": "tipos-socio"}, name="tipos_socio_detalle"),
    path("tipos-socio/<int:pk>/editar/", views.section_edit, {"section": "tipos-socio"}, name="tipos_socio_editar"),
    path("metodos-pago/", views.section_list, {"section": "metodos-pago"}, name="metodos_pago_lista"),
    path("metodos-pago/nuevo/", views.section_new, {"section": "metodos-pago"}, name="metodos_pago_nuevo"),
    path("metodos-pago/<int:pk>/", views.section_detail, {"section": "metodos-pago"}, name="metodos_pago_detalle"),
    path("metodos-pago/<int:pk>/editar/", views.section_edit, {"section": "metodos-pago"}, name="metodos_pago_editar"),
    path("plataformas-juego/", views.section_list, {"section": "plataformas-juego"}, name="plataformas_juego_lista"),
    path("plataformas-juego/nuevo/", views.section_new, {"section": "plataformas-juego"}, name="plataformas_juego_nuevo"),
    path("plataformas-juego/<int:pk>/", views.section_detail, {"section": "plataformas-juego"}, name="plataformas_juego_detalle"),
    path("plataformas-juego/<int:pk>/editar/", views.section_edit, {"section": "plataformas-juego"}, name="plataformas_juego_editar"),
    path("regalos/", views.section_list, {"section": "regalos"}, name="regalos_lista"),
    path("regalos/nuevo/", views.section_new, {"section": "regalos"}, name="regalos_nuevo"),
    path("regalos/<int:pk>/", views.section_detail, {"section": "regalos"}, name="regalos_detalle"),
    path("regalos/<int:pk>/editar/", views.section_edit, {"section": "regalos"}, name="regalos_editar"),
]
