from django.urls import re_path

from .consumers import PartidaPublicaConsumer


websocket_urlpatterns = [
    re_path(
        r"^ws/juego/partidas/(?P<idpartidabingo>\d+)/$",
        PartidaPublicaConsumer.as_asgi(),
        name="ws_partida_publica",
    ),
]
