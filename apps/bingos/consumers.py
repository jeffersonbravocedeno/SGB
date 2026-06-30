from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import Partidabingo
from .realtime import nombre_grupo_partida


class PartidaPublicaConsumer(AsyncJsonWebsocketConsumer):
    group_name = None

    async def connect(self):
        idpartidabingo = int(
            self.scope["url_route"]["kwargs"]["idpartidabingo"]
        )
        if not await self._partida_existe(idpartidabingo):
            await self.close(code=4404)
            return

        if self.channel_layer is None:
            await self.close(code=1011)
            return

        self.group_name = nombre_grupo_partida(idpartidabingo)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if self.group_name and self.channel_layer is not None:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )
            self.group_name = None

    async def receive(self, text_data=None, bytes_data=None):
        """El canal público ignora cualquier comando enviado por clientes."""
        return

    async def partida_actualizada(self, event):
        await self.send_json(event["payload"])

    @database_sync_to_async
    def _partida_existe(self, idpartidabingo):
        return Partidabingo.objects.filter(
            pk=idpartidabingo
        ).exists()
