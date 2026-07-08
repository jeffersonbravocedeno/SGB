from django.urls import path

from . import views


app_name = "bingos"

urlpatterns = [
    path("mis-cartones/", views.mis_cartones, name="mis_cartones"),
    path(
        "mis-cartones/<str:codigocarton>/",
        views.mi_carton_detalle,
        name="mi_carton_detalle",
    ),
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
    path(
        "bingos/<int:idbingo>/resumen/excel/",
        views.bingo_resumen_excel,
        name="bingo_resumen_excel",
    ),
    path(
        "bingos/<int:idbingo>/cartones/nuevo/",
        views.bingo_carton_nuevo,
        name="bingo_carton_nuevo",
    ),
    path(
        "bingos/<int:idbingo>/preliquidacion/",
        views.preliquidacion_financiera,
        name="preliquidacion_financiera",
    ),
    path(
        "bingos/<int:idbingo>/finanzas/",
        views.bingo_finanzas,
        name="bingo_finanzas",
    ),
    path(
        "bingos/<int:idbingo>/finanzas/gastos/registrar/",
        views.bingo_finanzas_gasto_registrar,
        name="bingo_finanzas_gasto_registrar",
    ),
    path(
        "bingos/<int:idbingo>/finanzas/gastos/<int:idgasto>/anular/",
        views.bingo_finanzas_gasto_anular,
        name="bingo_finanzas_gasto_anular",
    ),
    path(
        "bingos/<int:idbingo>/finanzas/costos/registrar/",
        views.bingo_finanzas_costo_registrar,
        name="bingo_finanzas_costo_registrar",
    ),
    path(
        "bingos/<int:idbingo>/finanzas/costos/<int:idcosto>/anular/",
        views.bingo_finanzas_costo_anular,
        name="bingo_finanzas_costo_anular",
    ),
    path(
        "bingos/<int:idbingo>/comprar-carton/",
        views.comprar_carton_bingo,
        name="comprar_carton_bingo",
    ),
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
        "partidas/<int:idpartidabingo>/reporte/pdf/",
        views.partida_reporte_pdf,
        name="partida_reporte_pdf",
    ),
    path(
        "partidas/<int:idpartidabingo>/cartones/excel/",
        views.partida_cartones_excel,
        name="partida_cartones_excel",
    ),
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
