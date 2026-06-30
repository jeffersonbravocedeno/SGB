import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .services import (
    ESTADO_PARTIDA_FINALIZADA,
    estado_partida_mostrar,
    formatear_bola_bingo,
    mensaje_estado_carton_publico,
    mensaje_estado_tablero_publico,
    normalizar_estado_partida,
    parsear_bolas_cantadas,
)


logger = logging.getLogger(__name__)


def nombre_grupo_partida(idpartidabingo):
    idpartidabingo = int(idpartidabingo)
    if idpartidabingo < 1:
        raise ValueError("El identificador de partida debe ser positivo.")
    return f"partida_{idpartidabingo}"


def construir_payload_publico_partida(
    partida,
    evento,
    ganador_publico=None,
):
    bolas = parsear_bolas_cantadas(partida.bolascantadas)
    ultima_bola = bolas[-1] if bolas else None
    estado = normalizar_estado_partida(partida.estadopartida)
    finalizada = estado == ESTADO_PARTIDA_FINALIZADA

    if finalizada and ganador_publico is None and partida.idjugadorganador_id:
        jugador = partida._state.fields_cache.get("idjugadorganador")
        if jugador is not None:
            ganador_publico = jugador.aliasjugador or "Jugador ganador"

    return {
        "tipo": "partida_actualizada",
        "evento": str(evento),
        "partida": {
            "id": partida.pk,
            "estado": estado,
            "estado_visible": estado_partida_mostrar(estado),
            "mensaje_estado": mensaje_estado_tablero_publico(estado),
            "mensaje_estado_carton": mensaje_estado_carton_publico(estado),
            "total_extraidas": len(bolas),
            "cantidad_extraida": len(bolas),
            "restantes": 75 - len(bolas),
            "bolas_extraidas": bolas,
            "ultima_bola": (
                {
                    "numero": ultima_bola,
                    "codigo": formatear_bola_bingo(ultima_bola),
                }
                if ultima_bola is not None
                else None
            ),
            "ganador": ganador_publico if finalizada else None,
            "finalizada": finalizada,
            "resuelta_por_desempate": (
                finalizada and bool(partida.haydesempate)
            ),
        },
    }


def programar_publicacion_partida(
    partida,
    evento,
    ganador_publico=None,
):
    payload = construir_payload_publico_partida(
        partida,
        evento,
        ganador_publico=ganador_publico,
    )
    group_name = nombre_grupo_partida(partida.pk)

    def publicar_despues_del_commit():
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning(
                "No hay capa de canales para publicar la partida %s",
                partida.pk,
            )
            return
        try:
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "partida.actualizada",
                    "payload": payload,
                },
            )
        except Exception:
            logger.exception(
                "No fue posible publicar la actualización pública de la partida %s",
                partida.pk,
            )

    transaction.on_commit(publicar_despues_del_commit)
    return payload
