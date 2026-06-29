from django.urls import path

from . import views


app_name = "bingos"

urlpatterns = [
    path("juego/", views.sala_juego_publica, name="sala_juego_publica"),
    path(
        "juego/partidas/<int:idpartidabingo>/tablero/",
        views.tablero_publico,
        name="tablero_publico",
    ),
    path(
        "juego/cartones/acceder/",
        views.acceder_carton_publico,
        name="acceder_carton_publico",
    ),
    path(
        "juego/cartones/<str:codigocarton>/",
        views.carton_publico,
        name="carton_publico",
    ),
    path("bingos/", views.bingos_lista, name="lista"),
    path("bingos/nuevo/", views.bingo_nuevo, name="nuevo"),
    path("bingos/<int:idbingo>/", views.bingo_detalle, name="detalle"),
    path("bingos/<int:idbingo>/editar/", views.bingo_editar, name="editar"),
    path("bingos/<int:idbingo>/partidas/nueva/", views.partida_nueva, name="partida_nueva"),
    path("partidas/", views.partidas_lista, name="partidas_lista"),
    path("partidas/<int:idpartidabingo>/consola/", views.consola_operador, name="consola_operador"),
    path(
        "partidas/<int:idpartidabingo>/desempate/",
        views.desempate_operador,
        name="desempate_operador",
    ),
    path(
        "partidas/<int:idpartidabingo>/desempate/<int:idjugador>/sortear/",
        views.sortear_desempate,
        name="sortear_desempate",
    ),
    path(
        "partidas/<int:idpartidabingo>/desempate/confirmar/",
        views.confirmar_desempate,
        name="confirmar_desempate",
    ),
    path("partidas/<int:idpartidabingo>/sacar-bola/", views.sacar_bola, name="sacar_bola"),
    path("partidas/<int:idpartidabingo>/cartones/nuevo/", views.partida_carton_nuevo, name="partida_carton_nuevo"),
    path(
        "partidas/<int:idpartidabingo>/cartones/<int:idcarton>/validar/",
        views.validar_carton,
        name="validar_carton",
    ),
    path(
        "partidas/<int:idpartidabingo>/cartones/<int:idcarton>/editar/",
        views.partida_carton_editar,
        name="partida_carton_editar",
    ),
    path("partidas/<int:idpartidabingo>/", views.partida_detalle, name="partida_detalle"),
    path("partidas/<int:idpartidabingo>/editar/", views.partida_editar, name="partida_editar"),
    path("cartones/", views.cartones_lista, name="cartones_lista"),
    path("cartones/nuevo/", views.carton_nuevo, name="carton_nuevo"),
    path("cartones/<int:idcarton>/editar/", views.carton_editar, name="carton_editar"),
    path("sesiones-juego/", views.sesiones_lista, name="sesiones_lista"),
]
