import json
import logging
import random
import re
import uuid
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.common.ids import assign_next_integer_pk

from .models import Bingo, Carton, CartonPartidaBingo, Partidabingo


logger = logging.getLogger(__name__)


ESTADO_PARTIDA_PROGRAMADA = "Programada"
ESTADO_PARTIDA_EN_ESPERA = "En espera"
ESTADO_PARTIDA_EN_CURSO = "En curso"
ESTADO_PARTIDA_PAUSADA = "Pausada"
ESTADO_PARTIDA_DESEMPATE = "Desempate"
ESTADO_PARTIDA_FINALIZADA = "Finalizada"
ESTADO_PARTIDA_CANCELADA = "Cancelada"

ESTADOS_PARTIDA = (
    (ESTADO_PARTIDA_PROGRAMADA, ESTADO_PARTIDA_PROGRAMADA),
    (ESTADO_PARTIDA_EN_ESPERA, ESTADO_PARTIDA_EN_ESPERA),
    (ESTADO_PARTIDA_EN_CURSO, ESTADO_PARTIDA_EN_CURSO),
    (ESTADO_PARTIDA_PAUSADA, ESTADO_PARTIDA_PAUSADA),
    (ESTADO_PARTIDA_DESEMPATE, ESTADO_PARTIDA_DESEMPATE),
    (ESTADO_PARTIDA_FINALIZADA, ESTADO_PARTIDA_FINALIZADA),
    (ESTADO_PARTIDA_CANCELADA, ESTADO_PARTIDA_CANCELADA),
)
ESTADOS_PARTIDA_VALORES = tuple(value for value, _label in ESTADOS_PARTIDA)

ESTADOS_ASIGNACION_CARTONES = {
    ESTADO_PARTIDA_PROGRAMADA,
    ESTADO_PARTIDA_EN_ESPERA,
}
CASILLA_LIBRE = "LIBRE"

ESTADOS_PARTIDA_LEGADOS = {
    "En Juego": ESTADO_PARTIDA_EN_CURSO,
    "Verificando": ESTADO_PARTIDA_EN_ESPERA,
}

TRANSICIONES_PARTIDA = {
    ESTADO_PARTIDA_PROGRAMADA: {ESTADO_PARTIDA_EN_ESPERA, ESTADO_PARTIDA_EN_CURSO, ESTADO_PARTIDA_CANCELADA},
    ESTADO_PARTIDA_EN_ESPERA: {ESTADO_PARTIDA_EN_CURSO, ESTADO_PARTIDA_CANCELADA},
    ESTADO_PARTIDA_EN_CURSO: {
        ESTADO_PARTIDA_PAUSADA,
        ESTADO_PARTIDA_DESEMPATE,
        ESTADO_PARTIDA_FINALIZADA,
        ESTADO_PARTIDA_CANCELADA,
    },
    ESTADO_PARTIDA_PAUSADA: {ESTADO_PARTIDA_EN_CURSO, ESTADO_PARTIDA_FINALIZADA, ESTADO_PARTIDA_CANCELADA},
    ESTADO_PARTIDA_DESEMPATE: {ESTADO_PARTIDA_EN_CURSO, ESTADO_PARTIDA_FINALIZADA, ESTADO_PARTIDA_CANCELADA},
    ESTADO_PARTIDA_FINALIZADA: set(),
    ESTADO_PARTIDA_CANCELADA: set(),
}

ACCIONES_CONSOLA = {
    "iniciar": {
        "label": "Iniciar partida",
        "target": ESTADO_PARTIDA_EN_CURSO,
        "allowed_from": {ESTADO_PARTIDA_PROGRAMADA, ESTADO_PARTIDA_EN_ESPERA},
    },
    "pausar": {
        "label": "Pausar partida",
        "target": ESTADO_PARTIDA_PAUSADA,
        "allowed_from": {ESTADO_PARTIDA_EN_CURSO},
    },
    "reanudar": {
        "label": "Reanudar partida",
        "target": ESTADO_PARTIDA_EN_CURSO,
        "allowed_from": {ESTADO_PARTIDA_PAUSADA},
    },
    "finalizar": {
        "label": "Finalizar partida",
        "target": ESTADO_PARTIDA_FINALIZADA,
        "allowed_from": {ESTADO_PARTIDA_EN_CURSO, ESTADO_PARTIDA_PAUSADA},
    },
}


class EstadoPartidaError(ValueError):
    pass


class CartonAsignacionError(ValueError):
    pass


class BolaBingoError(ValueError):
    pass


class BolilleroAgotadoError(BolaBingoError):
    pass


class ValidacionCartonError(ValueError):
    pass


class MatrizCartonInvalidaError(ValidacionCartonError):
    pass


class CartonPublicoError(ValueError):
    pass


class CartonNoCompletoError(ValidacionCartonError):
    def __init__(self, faltantes):
        self.faltantes = list(faltantes)
        codigos = ", ".join(
            formatear_bola_bingo(numero) for numero in self.faltantes
        )
        super().__init__(
            f"Este cartón aún no completa Bingo. Faltan: {codigos}."
        )


class DesempateError(ValueError):
    pass


class DatosDesempateInvalidosError(DesempateError):
    pass


class DesempateIncompletoError(DesempateError):
    pass


def generar_matriz_carton_bingo(generador_aleatorio=None):
    """Genera una matriz de bingo 75 de cinco filas por cinco columnas."""
    generador_aleatorio = generador_aleatorio or random.SystemRandom()
    columna_n_numeros = generador_aleatorio.sample(range(31, 46), 4)
    columnas = (
        generador_aleatorio.sample(range(1, 16), 5),
        generador_aleatorio.sample(range(16, 31), 5),
        columna_n_numeros[:2] + [CASILLA_LIBRE] + columna_n_numeros[2:],
        generador_aleatorio.sample(range(46, 61), 5),
        generador_aleatorio.sample(range(61, 76), 5),
    )
    return [
        [columnas[columna][fila] for columna in range(5)]
        for fila in range(5)
    ]


def serializar_matriz_carton_bingo(matriz):
    """Conserva el formato JSON almacenado históricamente en el TextField."""
    return json.dumps(matriz, ensure_ascii=False, separators=(",", ":"))


def deserializar_matriz_carton_bingo(valor):
    if not valor:
        return None
    try:
        matriz = json.loads(valor) if isinstance(valor, str) else valor
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(matriz, list) or len(matriz) != 5:
        return None
    if any(not isinstance(fila, list) or len(fila) != 5 for fila in matriz):
        return None
    return matriz


def _normalizar_matriz_carton_bingo(matriz):
    matriz = deserializar_matriz_carton_bingo(matriz)
    if matriz is None:
        raise MatrizCartonInvalidaError(
            "La matriz debe ser un JSON con cinco filas y cinco columnas."
        )

    rangos_columnas = (
        range(1, 16),
        range(16, 31),
        range(31, 46),
        range(46, 61),
        range(61, 76),
    )
    normalizada = []
    numeros = []
    for indice_fila, fila in enumerate(matriz):
        fila_normalizada = []
        for indice_columna, valor in enumerate(fila):
            es_centro = indice_fila == 2 and indice_columna == 2
            if es_centro:
                if not (
                    isinstance(valor, str)
                    and valor.strip().upper() == CASILLA_LIBRE
                ):
                    raise MatrizCartonInvalidaError(
                        'La casilla central debe contener "LIBRE".'
                    )
                fila_normalizada.append(CASILLA_LIBRE)
                continue

            if isinstance(valor, bool) or not isinstance(valor, int):
                raise MatrizCartonInvalidaError(
                    "Todas las casillas, excepto el centro, deben ser números enteros."
                )
            if valor not in rangos_columnas[indice_columna]:
                raise MatrizCartonInvalidaError(
                    "La matriz contiene un número fuera del rango de su columna."
                )
            fila_normalizada.append(valor)
            numeros.append(valor)
        normalizada.append(fila_normalizada)

    if len(numeros) != 24 or len(set(numeros)) != 24:
        raise MatrizCartonInvalidaError(
            "La matriz debe contener 24 números únicos y una casilla LIBRE."
        )
    return normalizada


def obtener_numeros_carton(matriz):
    matriz_valida = _normalizar_matriz_carton_bingo(matriz)
    return [
        valor
        for fila in matriz_valida
        for valor in fila
        if valor != CASILLA_LIBRE
    ]


def obtener_numeros_faltantes_carton(matriz, bolas_extraidas):
    numeros_extraidos = set(parsear_bolas_cantadas(bolas_extraidas))
    return [
        numero
        for numero in obtener_numeros_carton(matriz)
        if numero not in numeros_extraidos
    ]


def carton_tiene_bingo_completo(matriz, bolas_extraidas):
    try:
        return not obtener_numeros_faltantes_carton(matriz, bolas_extraidas)
    except MatrizCartonInvalidaError:
        return False


def puede_asignar_cartones(partida):
    estado = str(partida.estadopartida or "").strip()
    return estado in ESTADOS_ASIGNACION_CARTONES


def validar_asignacion_cartones(partida):
    if puede_asignar_cartones(partida):
        return
    estado = str(partida.estadopartida or "Sin estado").strip()
    raise CartonAsignacionError(
        "No se puede generar ni asignar cartones porque la partida está en "
        f"estado {estado}. Solo se permite en Programada o En espera."
    )


def generar_codigo_carton(
    idpartida,
    existe_codigo=None,
    generador_token=None,
    max_intentos=20,
):
    """Genera un código legible y comprueba que no exista antes de devolverlo."""
    existe_codigo = existe_codigo or (
        lambda codigo: Carton.objects.filter(codigocarton=codigo).exists()
    )
    generador_token = generador_token or uuid.uuid4
    prefijo = f"P{idpartida}-C-"
    longitud_token = min(10, 30 - len(prefijo))
    if longitud_token < 1:
        raise CartonAsignacionError("No fue posible construir el código del cartón.")

    for _intento in range(max_intentos):
        token_generado = generador_token()
        token = str(getattr(token_generado, "hex", token_generado))
        token = token.replace("-", "").upper()[:longitud_token]
        if token:
            codigo = f"{prefijo}{token}"
            if not existe_codigo(codigo):
                return codigo

    raise CartonAsignacionError(
        "No fue posible generar un código único para el cartón. Inténtalo nuevamente."
    )


def generar_codigo_carton_bingo(
    idbingo,
    existe_codigo=None,
    generador_token=None,
    max_intentos=20,
):
    """Genera un código global para un cartón maestro perteneciente a un Bingo."""
    existe_codigo = existe_codigo or (
        lambda codigo: Carton.objects.filter(codigocarton=codigo).exists()
    )
    generador_token = generador_token or uuid.uuid4
    prefijo = f"B{idbingo}-C-"
    longitud_token = min(10, 30 - len(prefijo))
    if longitud_token < 1:
        raise CartonAsignacionError("No fue posible construir el código del cartón.")

    for _intento in range(max_intentos):
        token_generado = generador_token()
        token = str(getattr(token_generado, "hex", token_generado))
        token = token.replace("-", "").upper()[:longitud_token]
        if token:
            codigo = f"{prefijo}{token}"
            if not existe_codigo(codigo):
                return codigo

    raise CartonAsignacionError(
        "No fue posible generar un código único para el cartón. Inténtalo nuevamente."
    )


def validar_venta_carton_para_bingo(bingo, partidas):
    """Exige al menos una ronda y que todas sigan abiertas para venta."""
    partidas = list(partidas)
    if not partidas:
        raise CartonAsignacionError(
            "No se puede vender un cartón porque el Bingo no tiene partidas."
        )

    partidas_no_aptas = [
        partida
        for partida in partidas
        if not puede_asignar_cartones(partida)
    ]
    if partidas_no_aptas:
        estados = ", ".join(
            f"{partida.nombreronda or partida.pk}: "
            f"{str(partida.estadopartida or 'Sin estado').strip()}"
            for partida in partidas_no_aptas
        )
        raise CartonAsignacionError(
            "No se puede vender un cartón porque todas las partidas del Bingo "
            "deben estar Programada o En espera. Partidas no aptas: "
            f"{estados}."
        )

    return partidas


def crear_carton_maestro_para_bingo(
    bingo,
    jugador,
    precio_pagado,
    fecha_compra=None,
):
    """Crea un maestro y una participación por cada ronda vendible del Bingo."""
    with transaction.atomic():
        if bingo is None or getattr(bingo, "pk", None) is None:
            raise CartonAsignacionError("El Bingo es obligatorio.")
        if jugador is None or getattr(jugador, "pk", None) is None:
            raise CartonAsignacionError("El jugador es obligatorio.")

        try:
            precio_pagado = Decimal(str(precio_pagado))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise CartonAsignacionError(
                "Ingrese un precio pagado válido."
            ) from exc
        if not precio_pagado.is_finite() or precio_pagado <= 0:
            raise CartonAsignacionError(
                "El precio pagado debe ser mayor que cero."
            )

        bingo_bloqueado = Bingo.objects.select_for_update().get(pk=bingo.pk)
        partidas = list(
            Partidabingo.objects.select_for_update()
            .filter(idbingo=bingo_bloqueado)
            .order_by("idpartidabingo")
        )
        validar_venta_carton_para_bingo(bingo_bloqueado, partidas)

        fecha_compra = fecha_compra or timezone.now()
        matriz = generar_matriz_carton_bingo()
        carton = Carton(
            idbingo=bingo_bloqueado,
            idjugador=jugador,
            idpartida=None,
            codigocarton="",
            matriznumeros=serializar_matriz_carton_bingo(matriz),
            indicevictoria=None,
            preciopagado=precio_pagado,
            fechacompra=fecha_compra,
            estadocarton="Vendido",
        )

        # La PK manual pertenece solo al maestro heredado. Las participaciones
        # usan AutoField/IDENTITY y nunca pasan por este helper.
        assign_next_integer_pk(carton)
        carton.codigocarton = generar_codigo_carton_bingo(bingo_bloqueado.pk)
        carton.full_clean(validate_unique=False, validate_constraints=False)
        carton.save(force_insert=True)

        for partida in partidas:
            CartonPartidaBingo.objects.create(
                idcarton=carton,
                idpartida=partida,
                idbingo=bingo_bloqueado,
                estado_participacion=CartonPartidaBingo.ESTADO_PENDIENTE,
                indicevictoria=None,
                es_asignacion_original=False,
                origen_asignacion=CartonPartidaBingo.ORIGEN_APLICACION,
                motivoestado=None,
                fechacreacion=fecha_compra,
                fechavalidacion=None,
            )

    return carton


def crear_y_asignar_carton(partida, jugador, precio_pagado, fecha_compra=None):
    """Flujo heredado: crea un cartón ligado a una sola partida."""
    validar_asignacion_cartones(partida)
    if jugador is None or getattr(jugador, "pk", None) is None:
        raise CartonAsignacionError("El jugador es obligatorio.")

    try:
        precio_pagado = Decimal(str(precio_pagado))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise CartonAsignacionError("Ingrese un precio pagado válido.") from exc
    if not precio_pagado.is_finite() or precio_pagado <= 0:
        raise CartonAsignacionError("El precio pagado debe ser mayor que cero.")

    with transaction.atomic():
        partida_bloqueada = Partidabingo.objects.select_for_update().get(
            pk=partida.pk
        )
        validar_asignacion_cartones(partida_bloqueada)

        matriz = generar_matriz_carton_bingo()
        carton = Carton(
            idjugador=jugador,
            idpartida=partida_bloqueada,
            codigocarton="",
            matriznumeros=serializar_matriz_carton_bingo(matriz),
            indicevictoria=0,
            preciopagado=precio_pagado,
            fechacompra=fecha_compra or timezone.now(),
            estadocarton="Vendido",
        )

        # La tabla física usa una PK entera sin secuencia. Este helper toma el
        # bloqueo y asigna MAX(idcarton) + 1 sin cambiar el esquema existente.
        assign_next_integer_pk(carton)
        carton.codigocarton = generar_codigo_carton(partida_bloqueada.pk)
        carton.full_clean(validate_unique=False, validate_constraints=False)
        carton.save(force_insert=True)

    return carton


def normalizar_estado_partida(estado):
    if estado is None:
        return estado
    valor = str(estado).strip()
    return ESTADOS_PARTIDA_LEGADOS.get(valor, valor)


def estado_partida_mostrar(estado):
    return normalizar_estado_partida(estado)


def estado_partida_valido(estado):
    return normalizar_estado_partida(estado) in ESTADOS_PARTIDA_VALORES


def puede_transicionar_partida(estado_actual, estado_nuevo):
    actual = normalizar_estado_partida(estado_actual)
    nuevo = normalizar_estado_partida(estado_nuevo)
    return nuevo in TRANSICIONES_PARTIDA.get(actual, set())


def preparar_cambio_estado_partida(estado_actual, estado_nuevo, now=None):
    actual = normalizar_estado_partida(estado_actual)
    nuevo = normalizar_estado_partida(estado_nuevo)

    if nuevo not in ESTADOS_PARTIDA_VALORES:
        raise EstadoPartidaError("Seleccione un estado de partida válido.")

    if not puede_transicionar_partida(actual, nuevo):
        raise EstadoPartidaError(
            f"No se puede cambiar una partida de {actual} a {nuevo}."
        )

    cambios = {"estadopartida": nuevo}

    if nuevo == ESTADO_PARTIDA_FINALIZADA:
        cambios["horafin"] = now or timezone.now()

    return cambios


def cambiar_estado_partida(partida, estado_nuevo, now=None):
    cambios = preparar_cambio_estado_partida(partida.estadopartida, estado_nuevo, now=now)
    for field_name, value in cambios.items():
        setattr(partida, field_name, value)
    return list(cambios)


def puede_ejecutar_accion_consola(partida, accion):
    config = ACCIONES_CONSOLA.get(accion)
    if not config:
        return False
    actual = normalizar_estado_partida(partida.estadopartida)
    return actual in config["allowed_from"]


def aplicar_accion_consola(partida, accion, now=None):
    cambios = preparar_accion_consola(partida, accion, now=now)
    for field_name, value in cambios.items():
        setattr(partida, field_name, value)
    return list(cambios)


def preparar_accion_consola(partida, accion, now=None):
    config = ACCIONES_CONSOLA.get(accion)
    if not config:
        raise EstadoPartidaError("La acción solicitada no existe.")

    if not puede_ejecutar_accion_consola(partida, accion):
        actual = normalizar_estado_partida(partida.estadopartida)
        raise EstadoPartidaError(
            f"No se puede ejecutar esta acción con la partida en estado {actual}."
        )

    return preparar_cambio_estado_partida(partida.estadopartida, config["target"], now=now)


def acciones_disponibles_consola(partida):
    return {
        accion
        for accion in ACCIONES_CONSOLA
        if puede_ejecutar_accion_consola(partida, accion)
    }


def letra_bingo(numero):
    if isinstance(numero, bool) or not isinstance(numero, int):
        raise BolaBingoError("El número de la bola debe ser un entero entre 1 y 75.")
    if not 1 <= numero <= 75:
        raise BolaBingoError("El número de la bola debe estar entre 1 y 75.")
    return "BINGO"[(numero - 1) // 15]


def formatear_bola_bingo(numero):
    return f"{letra_bingo(numero)}-{numero}"


def _numero_desde_valor_bola(valor):
    if isinstance(valor, dict):
        valor = valor.get("numero", valor.get("codigo"))

    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        numero = valor
    elif isinstance(valor, str):
        texto = valor.strip()
        coincidencia = re.fullmatch(
            r"(?:[BINGO]\s*[-:]?\s*)?(\d{1,2})",
            texto,
            flags=re.IGNORECASE,
        )
        if not coincidencia:
            return None
        numero = int(coincidencia.group(1))
    else:
        return None

    return numero if 1 <= numero <= 75 else None


def parsear_bolas_cantadas(valor):
    """Lee JSON actual y formatos legados sin propagar datos inválidos."""
    if valor in (None, ""):
        return []

    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return []
        try:
            datos = json.loads(texto)
        except json.JSONDecodeError:
            datos = re.split(r"[,;|\s]+", texto)
    else:
        datos = valor

    if isinstance(datos, (str, dict)) or not isinstance(datos, Iterable):
        datos = [datos]
    else:
        datos = list(datos)

    bolas = []
    vistas = set()
    for dato in datos:
        numero = _numero_desde_valor_bola(dato)
        if numero is not None and numero not in vistas:
            vistas.add(numero)
            bolas.append(numero)
    return bolas


def parse_bolas_cantadas(raw_value):
    """Compatibilidad para vistas existentes que esperan etiquetas legibles."""
    return [
        formatear_bola_bingo(numero)
        for numero in parsear_bolas_cantadas(raw_value)
    ]


def serializar_bolas_cantadas(bolas):
    bolas_normalizadas = parsear_bolas_cantadas(bolas)
    return json.dumps(bolas_normalizadas, separators=(",", ":"))


def obtener_bolas_disponibles(bolas_extraidas):
    extraidas = set(parsear_bolas_cantadas(bolas_extraidas))
    return [numero for numero in range(1, 76) if numero not in extraidas]


def estado_permite_extraer_bola(partida):
    return str(partida.estadopartida or "").strip() == ESTADO_PARTIDA_EN_CURSO


def validar_estado_extraccion_bola(partida):
    if estado_permite_extraer_bola(partida):
        return
    estado = str(partida.estadopartida or "Sin estado").strip()
    raise BolaBingoError(
        f"No se puede sacar una bola porque la partida está en estado {estado}. "
        "Solo se permite cuando está En curso."
    )


def construir_tablero_bingo(bolas_extraidas):
    extraidas = set(parsear_bolas_cantadas(bolas_extraidas))
    tablero = []
    for indice, letra in enumerate("BINGO"):
        inicio = (indice * 15) + 1
        tablero.append(
            {
                "letra": letra,
                "bolas": [
                    {
                        "numero": numero,
                        "codigo": formatear_bola_bingo(numero),
                        "extraida": numero in extraidas,
                    }
                    for numero in range(inicio, inicio + 15)
                ],
            }
        )
    return tablero


def preparar_datos_bolas_partida(partida):
    bolas = parsear_bolas_cantadas(partida.bolascantadas)
    disponibles = obtener_bolas_disponibles(bolas)
    ultima_bola = _numero_desde_valor_bola(partida.ultimabola)
    if ultima_bola is None and bolas:
        ultima_bola = bolas[-1]

    return {
        "bolas_extraidas": bolas,
        "historial_bolas": [
            {"numero": numero, "codigo": formatear_bola_bingo(numero)}
            for numero in bolas
        ],
        "tablero_bingo": construir_tablero_bingo(bolas),
        "ultima_bola_codigo": (
            formatear_bola_bingo(ultima_bola) if ultima_bola else None
        ),
        "total_bolas_extraidas": len(bolas),
        "total_bolas_faltantes": len(disponibles),
        "hay_bolas_disponibles": bool(disponibles),
        "puede_sacar_bola": (
            estado_permite_extraer_bola(partida) and bool(disponibles)
        ),
    }


def mensaje_estado_tablero_publico(estado):
    mensajes = {
        ESTADO_PARTIDA_PROGRAMADA: "La partida aún no ha comenzado.",
        ESTADO_PARTIDA_EN_ESPERA: "La partida aún no ha comenzado.",
        ESTADO_PARTIDA_EN_CURSO: "La partida está en juego.",
        ESTADO_PARTIDA_PAUSADA: "La partida está pausada temporalmente.",
        ESTADO_PARTIDA_DESEMPATE: "La partida está resolviendo un desempate.",
        ESTADO_PARTIDA_FINALIZADA: "La partida ha finalizado.",
        ESTADO_PARTIDA_CANCELADA: "La partida fue cancelada.",
    }
    estado = normalizar_estado_partida(estado)
    return mensajes.get(estado, "Estado de partida no disponible.")


def mensaje_estado_carton_publico(estado):
    mensajes = {
        ESTADO_PARTIDA_PROGRAMADA: "La partida aún no comienza.",
        ESTADO_PARTIDA_EN_ESPERA: "La partida aún no comienza.",
        ESTADO_PARTIDA_EN_CURSO: "La partida está en juego.",
        ESTADO_PARTIDA_PAUSADA: "La partida está pausada.",
        ESTADO_PARTIDA_DESEMPATE: "La partida se encuentra en desempate.",
        ESTADO_PARTIDA_FINALIZADA: "La partida terminó.",
        ESTADO_PARTIDA_CANCELADA: "La partida fue cancelada.",
    }
    estado = normalizar_estado_partida(estado)
    return mensajes.get(estado, "Estado de partida no disponible.")


def preparar_resumen_partida_publica(partida):
    datos_bolas = preparar_datos_bolas_partida(partida)
    return {
        "partida": partida,
        "total_bolas_extraidas": datos_bolas["total_bolas_extraidas"],
        "ultima_bola_codigo": datos_bolas["ultima_bola_codigo"],
    }


def preparar_datos_tablero_publico(partida):
    datos_bolas = preparar_datos_bolas_partida(partida)
    estado = normalizar_estado_partida(partida.estadopartida)
    ganador = None
    if estado == ESTADO_PARTIDA_FINALIZADA and partida.idjugadorganador_id:
        ganador = partida.idjugadorganador.aliasjugador or "Jugador ganador"
    return {
        "bolas_extraidas": datos_bolas["bolas_extraidas"],
        "historial_bolas": datos_bolas["historial_bolas"],
        "tablero_bingo": datos_bolas["tablero_bingo"],
        "ultima_bola_codigo": datos_bolas["ultima_bola_codigo"],
        "total_bolas_extraidas": datos_bolas["total_bolas_extraidas"],
        "total_bolas_faltantes": datos_bolas["total_bolas_faltantes"],
        "mensaje_estado_publico": mensaje_estado_tablero_publico(estado),
        "ganador_publico": ganador,
        "resuelta_por_desempate": (
            estado == ESTADO_PARTIDA_FINALIZADA
            and bool(partida.haydesempate)
        ),
    }


def extraer_siguiente_bola(partida, generador_aleatorio=None):
    """Extrae y persiste una bola sin repetición bajo bloqueo de fila."""
    validar_estado_extraccion_bola(partida)
    generador_aleatorio = generador_aleatorio or random.SystemRandom()

    with transaction.atomic():
        partida_bloqueada = Partidabingo.objects.select_for_update().get(
            pk=partida.pk
        )
        validar_estado_extraccion_bola(partida_bloqueada)
        bolas = parsear_bolas_cantadas(partida_bloqueada.bolascantadas)
        disponibles = obtener_bolas_disponibles(bolas)

        if not disponibles:
            raise BolilleroAgotadoError(
                "Ya se extrajeron las 75 bolas. No hay bolas disponibles."
            )

        nueva_bola = generador_aleatorio.choice(disponibles)
        bolas.append(nueva_bola)
        partida_bloqueada.bolascantadas = serializar_bolas_cantadas(bolas)
        partida_bloqueada.ultimabola = nueva_bola
        partida_bloqueada.save(
            update_fields=["bolascantadas", "ultimabola"]
        )

    # Mantiene sincronizada la instancia recibida para consumidores y pruebas.
    partida.bolascantadas = partida_bloqueada.bolascantadas
    partida.ultimabola = nueva_bola
    return nueva_bola


def estado_permite_validar_carton(partida):
    return str(partida.estadopartida or "").strip() == ESTADO_PARTIDA_EN_CURSO


def validar_estado_validacion_carton(partida):
    if estado_permite_validar_carton(partida):
        return
    estado = str(partida.estadopartida or "Sin estado").strip()
    raise ValidacionCartonError(
        f"No se puede validar un cartón porque la partida está en estado {estado}. "
        "Solo se permite cuando está En curso."
    )


def _carton_pertenece_a_partida(carton, partida):
    return carton.idpartida_id == partida.pk


def _carton_vendido_y_asignado(carton):
    return (
        carton.idjugador_id is not None
        and str(carton.estadocarton or "").strip().lower() == "vendido"
    )


def evaluar_carton_en_partida(carton, partida):
    if not _carton_pertenece_a_partida(carton, partida):
        raise ValidacionCartonError(
            "El cartón no pertenece a la partida indicada."
        )
    if not _carton_vendido_y_asignado(carton):
        raise ValidacionCartonError(
            "Solo se pueden validar cartones vendidos y asignados a un jugador."
        )

    matriz = _normalizar_matriz_carton_bingo(carton.matriznumeros)
    faltantes = obtener_numeros_faltantes_carton(
        matriz,
        partida.bolascantadas,
    )
    return {
        "carton": carton,
        "matriz": matriz,
        "faltantes": faltantes,
        "completo": not faltantes,
    }


def buscar_cartones_ganadores(partida, cartones=None):
    if cartones is None:
        cartones = (
            Carton.objects.filter(idpartida=partida)
            .select_related("idjugador")
            .order_by("idcarton")
        )

    ganadores = []
    for carton in cartones:
        if not _carton_vendido_y_asignado(carton):
            continue
        try:
            evaluacion = evaluar_carton_en_partida(carton, partida)
        except MatrizCartonInvalidaError as exc:
            logger.warning(
                "Cartón %s omitido al buscar ganadores de la partida %s: %s",
                carton.pk,
                partida.pk,
                exc,
            )
            continue
        if evaluacion["completo"]:
            ganadores.append(carton)
    return ganadores


def construir_matriz_marcada_carton(matriz, bolas_extraidas):
    matriz_valida = _normalizar_matriz_carton_bingo(matriz)
    extraidas = set(parsear_bolas_cantadas(bolas_extraidas))
    return [
        [
            {
                "valor": valor,
                "libre": valor == CASILLA_LIBRE,
                "marcada": valor == CASILLA_LIBRE or valor in extraidas,
            }
            for valor in fila
        ]
        for fila in matriz_valida
    ]


def contar_numeros_marcados_carton(matriz, bolas_extraidas):
    faltantes = obtener_numeros_faltantes_carton(matriz, bolas_extraidas)
    return 24 - len(faltantes)


def preparar_datos_carton_jugador(carton):
    partida = carton.idpartida
    if partida is None:
        raise CartonPublicoError(
            "Este cartón no está asociado a una partida disponible."
        )
    matriz = construir_matriz_marcada_carton(
        carton.matriznumeros,
        partida.bolascantadas,
    )
    faltantes = obtener_numeros_faltantes_carton(
        carton.matriznumeros,
        partida.bolascantadas,
    )
    datos_bolas = preparar_datos_bolas_partida(partida)
    return {
        "matriz_carton": matriz,
        "numeros_marcados": contar_numeros_marcados_carton(
            carton.matriznumeros,
            partida.bolascantadas,
        ),
        "total_numeros_carton": 24,
        "numeros_faltantes": faltantes,
        "ultima_bola_codigo": datos_bolas["ultima_bola_codigo"],
        "mensaje_estado_carton": mensaje_estado_carton_publico(
            partida.estadopartida
        ),
    }


def preparar_cartones_para_validacion(partida, cartones):
    resultado = []
    for carton in cartones:
        # La consola de validación solo expone cartones que pueden competir.
        # La misma condición vuelve a comprobarse dentro de la transacción.
        if not _carton_vendido_y_asignado(carton):
            continue

        error = None
        matriz_marcada = None
        faltantes = []
        try:
            matriz_marcada = construir_matriz_marcada_carton(
                carton.matriznumeros,
                partida.bolascantadas,
            )
            faltantes = obtener_numeros_faltantes_carton(
                carton.matriznumeros,
                partida.bolascantadas,
            )
        except MatrizCartonInvalidaError as exc:
            error = "La matriz de este cartón es inválida y no puede ganar."
            logger.warning(
                "Matriz inválida en cartón %s de partida %s: %s",
                carton.pk,
                partida.pk,
                exc,
            )

        resultado.append(
            {
                "carton": carton,
                "matriz": matriz_marcada,
                "faltantes": faltantes,
                "faltantes_codigos": [
                    formatear_bola_bingo(numero) for numero in faltantes
                ],
                "cantidad_marcados": 24 - len(faltantes) if matriz_marcada else 0,
                "completo": matriz_marcada is not None and not faltantes,
                "error": error,
                "puede_validar": (
                    error is None and estado_permite_validar_carton(partida)
                ),
            }
        )
    return resultado


def _candidato_desempate_desde_carton(carton):
    return {
        "idcarton": carton.pk,
        "codigocarton": carton.codigocarton,
        "idjugador": carton.idjugador_id,
        "jugador": str(carton.idjugador),
    }


def _serializar_cartones_ganadores_desempate(cartones):
    """Conserva el formato plano producido históricamente por la Etapa 3."""
    candidatos = [
        _candidato_desempate_desde_carton(carton)
        for carton in sorted(cartones, key=lambda item: item.pk)
    ]
    return json.dumps(candidatos, ensure_ascii=False, separators=(",", ":"))


def parsear_candidatos_desempate(valor):
    """Lee JSON actual, JSON plano de Etapa 3 e IDs separados por texto."""
    if valor in (None, ""):
        return []
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return []
        try:
            candidatos = json.loads(texto)
        except json.JSONDecodeError:
            candidatos = re.split(r"[,;|\s]+", texto)
    else:
        candidatos = valor

    if not isinstance(candidatos, list):
        candidatos = [candidatos]

    normalizados = []
    for candidato in candidatos:
        if isinstance(candidato, dict):
            normalizados.append(dict(candidato))
            continue
        numero = _numero_entero_positivo(candidato)
        if numero is not None:
            normalizados.append(
                {
                    "idcarton": None,
                    "codigocarton": None,
                    "idjugador": numero,
                    "jugador": None,
                }
            )
    return normalizados


def _numero_entero_positivo(valor):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    if isinstance(valor, str) and valor.strip().isdigit():
        numero = int(valor.strip())
        return numero if numero > 0 else None
    return None


def _normalizar_tiro_desempate(valor):
    if valor is None or valor == "":
        return None
    numero = _numero_entero_positivo(valor)
    if numero is None or numero > 75:
        raise DatosDesempateInvalidosError(
            "Los tiros de desempate deben ser números enteros entre 1 y 75."
        )
    return numero


def _normalizar_carton_candidato(valor):
    if not isinstance(valor, dict):
        return None
    idcarton = _numero_entero_positivo(valor.get("idcarton"))
    codigo = valor.get("codigocarton")
    codigo = str(codigo).strip() if codigo not in (None, "") else None
    if idcarton is None and codigo is None:
        return None
    return {"idcarton": idcarton, "codigocarton": codigo}


def _agregar_carton_candidato(cartones, carton):
    if carton is None:
        return
    for existente in cartones:
        mismo_id = (
            carton["idcarton"] is not None
            and existente["idcarton"] == carton["idcarton"]
        )
        mismo_codigo = (
            carton["idcarton"] is None
            and existente["idcarton"] is None
            and carton["codigocarton"] is not None
            and existente["codigocarton"] == carton["codigocarton"]
        )
        if mismo_id or mismo_codigo:
            if not existente["codigocarton"] and carton["codigocarton"]:
                existente["codigocarton"] = carton["codigocarton"]
            return
    cartones.append(carton)


def normalizar_candidatos_desempate(candidatos):
    """Agrupa por jugador, conserva cartones y valida los tiros persistidos."""
    if isinstance(candidatos, str) or candidatos is None:
        candidatos = parsear_candidatos_desempate(candidatos)
    elif isinstance(candidatos, dict):
        candidatos = [candidatos]
    else:
        candidatos = list(candidatos)

    agrupados = {}
    orden = []
    for candidato in candidatos:
        if not isinstance(candidato, dict):
            numero = _numero_entero_positivo(candidato)
            candidato = {"idjugador": numero} if numero is not None else {}

        idjugador = _numero_entero_positivo(candidato.get("idjugador"))
        if idjugador is None:
            raise DatosDesempateInvalidosError(
                "Se encontró un candidato de desempate sin jugador válido."
            )

        nombre = candidato.get("jugador")
        nombre = str(nombre).strip() if nombre not in (None, "") else None
        tiro = _normalizar_tiro_desempate(candidato.get("tiro_desempate"))

        if idjugador not in agrupados:
            agrupados[idjugador] = {
                "idjugador": idjugador,
                "jugador": nombre,
                "cartones": [],
                "tiro_desempate": tiro,
            }
            orden.append(idjugador)
        else:
            agrupado = agrupados[idjugador]
            if not agrupado["jugador"] and nombre:
                agrupado["jugador"] = nombre
            if (
                agrupado["tiro_desempate"] is not None
                and tiro is not None
                and agrupado["tiro_desempate"] != tiro
            ):
                raise DatosDesempateInvalidosError(
                    f"El jugador #{idjugador} tiene tiros de desempate contradictorios."
                )
            if agrupado["tiro_desempate"] is None and tiro is not None:
                agrupado["tiro_desempate"] = tiro

        destino = agrupados[idjugador]["cartones"]
        cartones = candidato.get("cartones", [])
        if isinstance(cartones, dict):
            cartones = [cartones]
        if isinstance(cartones, Iterable) and not isinstance(cartones, str):
            for carton in cartones:
                _agregar_carton_candidato(
                    destino,
                    _normalizar_carton_candidato(carton),
                )
        _agregar_carton_candidato(
            destino,
            _normalizar_carton_candidato(
                {
                    "idcarton": candidato.get("idcarton"),
                    "codigocarton": candidato.get("codigocarton"),
                }
            ),
        )

    resultado = [agrupados[idjugador] for idjugador in orden]
    tiros = [
        candidato["tiro_desempate"]
        for candidato in resultado
        if candidato["tiro_desempate"] is not None
    ]
    if len(tiros) != len(set(tiros)):
        raise DatosDesempateInvalidosError(
            "Existen balotas de desempate repetidas entre candidatos."
        )
    return resultado


def serializar_candidatos_desempate(candidatos):
    """Guarda la estructura canónica de candidatos agrupados y sus tiros."""
    normalizados = normalizar_candidatos_desempate(candidatos)
    return json.dumps(normalizados, ensure_ascii=False, separators=(",", ":"))


def obtener_tiros_desempate(candidatos):
    return [
        candidato["tiro_desempate"]
        for candidato in normalizar_candidatos_desempate(candidatos)
        if candidato["tiro_desempate"] is not None
    ]


def obtener_balotas_disponibles_desempate(candidatos):
    tiros = set(obtener_tiros_desempate(candidatos))
    return [numero for numero in range(1, 76) if numero not in tiros]


def desempate_esta_completo(candidatos):
    normalizados = normalizar_candidatos_desempate(candidatos)
    return bool(normalizados) and all(
        candidato["tiro_desempate"] is not None
        for candidato in normalizados
    )


def obtener_resultado_desempate(candidatos):
    normalizados = normalizar_candidatos_desempate(candidatos)
    if not desempate_esta_completo(normalizados):
        raise DesempateIncompletoError(
            "No se puede confirmar el desempate hasta que todos los candidatos sorteen."
        )
    ganador = max(normalizados, key=lambda candidato: candidato["tiro_desempate"])
    balota = ganador["tiro_desempate"]
    return {
        "candidato": ganador,
        "idjugador": ganador["idjugador"],
        "jugador": ganador["jugador"],
        "balota": balota,
        "codigo": formatear_bola_bingo(balota),
    }


def estado_permite_operar_desempate(partida):
    return str(partida.estadopartida or "").strip() == ESTADO_PARTIDA_DESEMPATE


def validar_estado_desempate(partida):
    if estado_permite_operar_desempate(partida):
        return
    estado = str(partida.estadopartida or "Sin estado").strip()
    raise DesempateError(
        f"No se puede operar el desempate porque la partida está en estado {estado}. "
        "Solo se permite cuando está en Desempate."
    )


def _obtener_candidatos_partida_desempate(partida):
    candidatos = normalizar_candidatos_desempate(
        parsear_candidatos_desempate(partida.idbingadores)
    )
    if not candidatos:
        raise DatosDesempateInvalidosError(
            "La partida no tiene candidatos válidos para el desempate."
        )
    return candidatos


def preparar_datos_desempate(partida):
    candidatos = _obtener_candidatos_partida_desempate(partida)
    candidatos_interfaz = []
    for candidato in candidatos:
        item = {
            **candidato,
            "nombre_mostrar": candidato["jugador"] or (
                f"Jugador #{candidato['idjugador']}"
            ),
            "tiro_codigo": (
                formatear_bola_bingo(candidato["tiro_desempate"])
                if candidato["tiro_desempate"] is not None
                else None
            ),
        }
        candidatos_interfaz.append(item)

    pendientes = sum(
        candidato["tiro_desempate"] is None
        for candidato in candidatos
    )
    completo = desempate_esta_completo(candidatos)
    return {
        "candidatos_desempate": candidatos_interfaz,
        "total_candidatos": len(candidatos),
        "total_pendientes": pendientes,
        "desempate_completo": completo,
        "resultado_desempate": (
            obtener_resultado_desempate(candidatos) if completo else None
        ),
        "puede_operar_desempate": estado_permite_operar_desempate(partida),
        "puede_confirmar_desempate": (
            estado_permite_operar_desempate(partida) and completo
        ),
    }


def sortear_balota_desempate(partida, idjugador, generador_aleatorio=None):
    validar_estado_desempate(partida)
    idjugador = _numero_entero_positivo(idjugador)
    if idjugador is None:
        raise DesempateError("El jugador indicado no es válido.")
    generador_aleatorio = generador_aleatorio or random.SystemRandom()

    with transaction.atomic():
        partida_bloqueada = Partidabingo.objects.select_for_update().get(
            pk=partida.pk
        )
        validar_estado_desempate(partida_bloqueada)
        candidatos = _obtener_candidatos_partida_desempate(partida_bloqueada)
        candidato = next(
            (
                item
                for item in candidatos
                if item["idjugador"] == idjugador
            ),
            None,
        )
        if candidato is None:
            raise DesempateError(
                "El jugador indicado no es candidato de este desempate."
            )
        if candidato["tiro_desempate"] is not None:
            raise DesempateError(
                "Este jugador ya realizó su único tiro de desempate."
            )

        disponibles = obtener_balotas_disponibles_desempate(candidatos)
        if not disponibles:
            raise DesempateError(
                "No quedan balotas disponibles para completar el desempate."
            )
        balota = generador_aleatorio.choice(disponibles)
        if balota not in disponibles:
            raise DatosDesempateInvalidosError(
                "El generador produjo una balota de desempate no disponible."
            )

        candidato["tiro_desempate"] = balota
        partida_bloqueada.idbingadores = serializar_candidatos_desempate(
            candidatos
        )
        partida_bloqueada.save(update_fields=["idbingadores"])

    partida.idbingadores = partida_bloqueada.idbingadores
    return {
        "partida": partida_bloqueada,
        "candidato": candidato,
        "candidatos": candidatos,
        "balota": balota,
        "codigo": formatear_bola_bingo(balota),
    }


def confirmar_y_finalizar_desempate(partida, now=None):
    validar_estado_desempate(partida)

    with transaction.atomic():
        partida_bloqueada = Partidabingo.objects.select_for_update().get(
            pk=partida.pk
        )
        validar_estado_desempate(partida_bloqueada)
        candidatos = _obtener_candidatos_partida_desempate(partida_bloqueada)
        resultado = obtener_resultado_desempate(candidatos)

        partida_bloqueada.idjugadorganador_id = resultado["idjugador"]
        partida_bloqueada.bolamayordesempate = resultado["balota"]
        partida_bloqueada.estadopartida = ESTADO_PARTIDA_FINALIZADA
        partida_bloqueada.horafin = now or timezone.now()
        partida_bloqueada.haydesempate = True
        partida_bloqueada.idbingadores = serializar_candidatos_desempate(
            candidatos
        )
        update_fields = [
            "idjugadorganador",
            "bolamayordesempate",
            "estadopartida",
            "horafin",
            "haydesempate",
            "idbingadores",
        ]
        partida_bloqueada.save(update_fields=update_fields)

    partida.idjugadorganador_id = partida_bloqueada.idjugadorganador_id
    partida.bolamayordesempate = partida_bloqueada.bolamayordesempate
    partida.estadopartida = partida_bloqueada.estadopartida
    partida.horafin = partida_bloqueada.horafin
    partida.haydesempate = partida_bloqueada.haydesempate
    partida.idbingadores = partida_bloqueada.idbingadores
    return {
        "partida": partida_bloqueada,
        "candidatos": candidatos,
        "resultado": resultado,
    }


def validar_carton_ganador(partida, carton):
    validar_estado_validacion_carton(partida)
    if not _carton_pertenece_a_partida(carton, partida):
        raise ValidacionCartonError(
            "El cartón no pertenece a la partida indicada."
        )

    with transaction.atomic():
        partida_bloqueada = Partidabingo.objects.select_for_update().get(
            pk=partida.pk
        )
        validar_estado_validacion_carton(partida_bloqueada)
        cartones_bloqueados = list(
            # idjugador es nullable: limitar FOR UPDATE a carton evita que
            # PostgreSQL intente bloquear el lado nullable del OUTER JOIN.
            Carton.objects.select_for_update(of=("self",))
            .filter(idpartida=partida_bloqueada)
            .select_related("idjugador")
            .order_by("idcarton")
        )
        carton_bloqueado = next(
            (
                candidato
                for candidato in cartones_bloqueados
                if candidato.pk == carton.pk
            ),
            None,
        )
        if carton_bloqueado is None:
            raise ValidacionCartonError(
                "El cartón no pertenece a la partida indicada."
            )

        try:
            evaluacion = evaluar_carton_en_partida(
                carton_bloqueado,
                partida_bloqueada,
            )
        except MatrizCartonInvalidaError as exc:
            logger.warning(
                "Validación rechazada por matriz inválida: partida=%s cartón=%s error=%s",
                partida_bloqueada.pk,
                carton_bloqueado.pk,
                exc,
            )
            raise MatrizCartonInvalidaError(
                "La matriz del cartón es inválida y no puede ganar."
            ) from exc

        if not evaluacion["completo"]:
            raise CartonNoCompletoError(evaluacion["faltantes"])

        cartones_ganadores = buscar_cartones_ganadores(
            partida_bloqueada,
            cartones=cartones_bloqueados,
        )
        if not cartones_ganadores:
            raise ValidacionCartonError(
                "No se encontró un cartón ganador válido con las bolas actuales."
            )
        if len(cartones_ganadores) > 1:
            partida_bloqueada.idjugadorganador = None
            partida_bloqueada.estadopartida = ESTADO_PARTIDA_DESEMPATE
            partida_bloqueada.haydesempate = True
            partida_bloqueada.idbingadores = _serializar_cartones_ganadores_desempate(
                cartones_ganadores
            )
            update_fields = [
                "idjugadorganador",
                "estadopartida",
                "haydesempate",
                "idbingadores",
            ]
            resultado = "desempate"
        else:
            ganador = cartones_ganadores[0]
            partida_bloqueada.idjugadorganador = ganador.idjugador
            partida_bloqueada.haydesempate = False
            partida_bloqueada.idbingadores = _serializar_cartones_ganadores_desempate(
                [ganador]
            )
            update_fields = [
                "idjugadorganador",
                "haydesempate",
                "idbingadores",
            ]
            resultado = "ganador"

        partida_bloqueada.save(update_fields=update_fields)

    for field_name in update_fields:
        setattr(partida, field_name, getattr(partida_bloqueada, field_name))
    return {
        "resultado": resultado,
        "carton": carton_bloqueado,
        "cartones_ganadores": cartones_ganadores,
        "partida": partida_bloqueada,
    }


def _id_positivo_modelo_o_valor(valor, etiqueta):
    identificador = getattr(valor, "pk", valor)
    identificador = _numero_entero_positivo(identificador)
    if identificador is None:
        raise ValidacionCartonError(f"{etiqueta} no es válido.")
    return identificador


def _validar_coherencia_participacion(participacion, carton, partida):
    if participacion.idcarton_id != carton.pk:
        raise ValidacionCartonError(
            "La participación no pertenece al cartón indicado."
        )
    if participacion.idpartida_id != partida.pk:
        raise ValidacionCartonError(
            "La participación no pertenece a la partida indicada."
        )
    if carton.idbingo_id != partida.idbingo_id:
        raise ValidacionCartonError(
            "El cartón pertenece a otro Bingo."
        )
    if participacion.idbingo_id != partida.idbingo_id:
        raise ValidacionCartonError(
            "La participación pertenece a otro Bingo."
        )


def obtener_participacion_carton_en_partida(partida, carton):
    """Resuelve la participación híbrida exacta sin consultar campos históricos."""
    idpartida = _id_positivo_modelo_o_valor(partida, "La partida")
    idcarton = _id_positivo_modelo_o_valor(carton, "El cartón")

    try:
        partida_real = Partidabingo.objects.get(pk=idpartida)
    except Partidabingo.DoesNotExist as exc:
        raise ValidacionCartonError("La partida indicada no existe.") from exc
    try:
        carton_real = Carton.objects.get(pk=idcarton)
    except Carton.DoesNotExist as exc:
        raise ValidacionCartonError("El cartón indicado no existe.") from exc
    try:
        participacion = (
            CartonPartidaBingo.objects.select_related(
                "idcarton",
                "idcarton__idjugador",
                "idpartida",
                "idbingo",
            ).get(idcarton_id=idcarton, idpartida_id=idpartida)
        )
    except CartonPartidaBingo.DoesNotExist as exc:
        raise ValidacionCartonError(
            "No existe una participación para ese cartón y esa partida."
        ) from exc

    _validar_coherencia_participacion(
        participacion,
        carton_real,
        partida_real,
    )
    return participacion


def evaluar_participacion_en_partida(participacion, partida=None):
    """Evalúa el maestro con las bolas de la ronda exacta de la participación."""
    carton = participacion.idcarton
    partida = partida or participacion.idpartida
    _validar_coherencia_participacion(participacion, carton, partida)

    if participacion.estado_participacion == CartonPartidaBingo.ESTADO_ANULADO:
        raise ValidacionCartonError(
            "Una participación anulada no puede validarse."
        )
    if not _carton_vendido_y_asignado(carton):
        raise ValidacionCartonError(
            "Solo se pueden validar cartones vendidos y asignados a un jugador."
        )

    matriz = _normalizar_matriz_carton_bingo(carton.matriznumeros)
    faltantes = obtener_numeros_faltantes_carton(
        matriz,
        partida.bolascantadas,
    )
    return {
        "participacion": participacion,
        "carton": carton,
        "partida": partida,
        "matriz": matriz,
        "faltantes": faltantes,
        "completo": not faltantes,
    }


def obtener_participaciones_hibridas_partida(partida):
    """Obtiene maestros híbridos de la ronda sin duplicar sus datos."""
    participaciones = list(
        CartonPartidaBingo.objects.filter(
            idpartida=partida,
            idcarton__idpartida__isnull=True,
        )
        .select_related(
            "idcarton",
            "idcarton__idjugador",
            "idcarton__idbingo",
            "idpartida",
            "idpartida__idbingo",
            "idbingo",
        )
        .order_by("idcarton__codigocarton", "idcartonpartidabingo")
    )
    for participacion in participaciones:
        carton = participacion.idcarton
        _validar_coherencia_participacion(participacion, carton, partida)
        if carton.idpartida_id is not None:
            raise ValidacionCartonError(
                "Una participación híbrida referencia un cartón histórico."
            )
    return participaciones


def preparar_participaciones_hibridas_para_consola(
    partida,
    participaciones=None,
):
    """Prepara estado y progreso por participación para la consola."""
    participaciones = (
        obtener_participaciones_hibridas_partida(partida)
        if participaciones is None
        else list(participaciones)
    )
    resultado = []
    for participacion in participaciones:
        carton = participacion.idcarton
        _validar_coherencia_participacion(participacion, carton, partida)
        if carton.idpartida_id is not None:
            raise ValidacionCartonError(
                "La consola híbrida recibió un cartón histórico."
            )

        error = None
        matriz_marcada = None
        faltantes = []
        try:
            matriz_marcada = construir_matriz_marcada_carton(
                carton.matriznumeros,
                partida.bolascantadas,
            )
            faltantes = obtener_numeros_faltantes_carton(
                carton.matriznumeros,
                partida.bolascantadas,
            )
        except MatrizCartonInvalidaError as exc:
            error = "La matriz de este cartón es inválida y no puede ganar."
            logger.warning(
                "Matriz inválida en participación %s de partida %s: %s",
                participacion.pk,
                partida.pk,
                exc,
            )

        cantidad_marcados = 24 - len(faltantes) if matriz_marcada else 0
        resultado.append(
            {
                "tipo_registro": "hibrido",
                "etiqueta_tipo": "Cartón de Bingo",
                "participacion": participacion,
                "carton": carton,
                "matriz": matriz_marcada,
                "faltantes": faltantes,
                "faltantes_codigos": [
                    formatear_bola_bingo(numero) for numero in faltantes
                ],
                "cantidad_marcados": cantidad_marcados,
                "progreso": round((cantidad_marcados / 24) * 100),
                "completo": matriz_marcada is not None and not faltantes,
                "estado_participacion": participacion.estado_participacion,
                "indicevictoria": participacion.indicevictoria,
                "fechavalidacion": participacion.fechavalidacion,
                "error": error,
                "puede_validar": (
                    error is None
                    and participacion.estado_participacion
                    in {
                        CartonPartidaBingo.ESTADO_PENDIENTE,
                        CartonPartidaBingo.ESTADO_EN_JUEGO,
                    }
                    and estado_permite_validar_carton(partida)
                ),
            }
        )
    return resultado


def buscar_participaciones_ganadoras(partida, participaciones=None):
    """Busca ganadores por ronda conservando cada participación individual."""
    if participaciones is None:
        participaciones = (
            CartonPartidaBingo.objects.filter(idpartida=partida)
            .select_related("idcarton", "idcarton__idjugador", "idpartida")
            .order_by("idcartonpartidabingo")
        )

    ganadoras = []
    for participacion in participaciones:
        if participacion.idpartida_id != partida.pk:
            raise ValidacionCartonError(
                "Se recibió una participación de otra partida."
            )
        carton = participacion.idcarton
        _validar_coherencia_participacion(participacion, carton, partida)
        if participacion.estado_participacion not in {
            CartonPartidaBingo.ESTADO_PENDIENTE,
            CartonPartidaBingo.ESTADO_EN_JUEGO,
            CartonPartidaBingo.ESTADO_GANADOR,
        } or not _carton_vendido_y_asignado(carton):
            continue
        try:
            evaluacion = evaluar_participacion_en_partida(
                participacion,
                partida,
            )
        except MatrizCartonInvalidaError as exc:
            logger.warning(
                "Participación %s omitida al buscar ganadores de la partida %s: %s",
                participacion.pk,
                partida.pk,
                exc,
            )
            continue
        if evaluacion["completo"]:
            ganadoras.append(participacion)
    return ganadoras


def construir_candidato_desempate_participacion(participacion):
    """Serializa un candidato sin deduplicarlo por jugador o cartón maestro."""
    carton = participacion.idcarton
    partida = participacion.idpartida
    _validar_coherencia_participacion(participacion, carton, partida)
    return {
        "idcartonpartidabingo": participacion.pk,
        "idcarton": carton.pk,
        "idpartida": partida.pk,
        "idbingo": participacion.idbingo_id,
        "idjugador": carton.idjugador_id,
        "codigocarton": carton.codigocarton,
        "jugador": str(carton.idjugador),
        "tiro_desempate": None,
    }


def normalizar_candidatos_desempate_participaciones(candidatos, partida=None):
    """Valida candidatos híbridos y conserva una fila por participación."""
    if isinstance(candidatos, str):
        try:
            candidatos = json.loads(candidatos)
        except json.JSONDecodeError as exc:
            raise DatosDesempateInvalidosError(
                "Los candidatos híbridos no contienen JSON válido."
            ) from exc
    if isinstance(candidatos, dict):
        candidatos = [candidatos]
    if not isinstance(candidatos, Iterable) or isinstance(candidatos, str):
        raise DatosDesempateInvalidosError(
            "Los candidatos híbridos deben ser una lista."
        )

    idpartida_esperada = (
        _id_positivo_modelo_o_valor(partida, "La partida")
        if partida is not None
        else None
    )
    idbingo_esperado = (
        getattr(partida, "idbingo_id", None) if partida is not None else None
    )
    normalizados = []
    ids_participacion = set()
    for candidato in candidatos:
        if not isinstance(candidato, dict):
            raise DatosDesempateInvalidosError(
                "Cada candidato híbrido debe ser un objeto."
            )
        campos = {
            nombre: _numero_entero_positivo(candidato.get(nombre))
            for nombre in (
                "idcartonpartidabingo",
                "idcarton",
                "idpartida",
                "idbingo",
                "idjugador",
            )
        }
        if any(valor is None for valor in campos.values()):
            raise DatosDesempateInvalidosError(
                "Un candidato híbrido tiene identificadores inválidos."
            )
        idparticipacion = campos["idcartonpartidabingo"]
        if idparticipacion in ids_participacion:
            raise DatosDesempateInvalidosError(
                "Una participación aparece repetida en el desempate."
            )
        if (
            idpartida_esperada is not None
            and campos["idpartida"] != idpartida_esperada
        ):
            raise DatosDesempateInvalidosError(
                "Un candidato pertenece a otra partida."
            )
        if (
            idbingo_esperado is not None
            and campos["idbingo"] != idbingo_esperado
        ):
            raise DatosDesempateInvalidosError(
                "Un candidato pertenece a otro Bingo."
            )

        codigo = str(candidato.get("codigocarton") or "").strip()
        if not codigo:
            raise DatosDesempateInvalidosError(
                "Un candidato híbrido no tiene código de cartón."
            )
        jugador = candidato.get("jugador")
        jugador = str(jugador).strip() if jugador not in (None, "") else None
        normalizados.append(
            {
                **campos,
                "codigocarton": codigo,
                "jugador": jugador,
                "tiro_desempate": _normalizar_tiro_desempate(
                    candidato.get("tiro_desempate")
                ),
            }
        )
        ids_participacion.add(idparticipacion)

    tiros = [
        candidato["tiro_desempate"]
        for candidato in normalizados
        if candidato["tiro_desempate"] is not None
    ]
    if len(tiros) != len(set(tiros)):
        raise DatosDesempateInvalidosError(
            "Existen balotas repetidas entre participaciones candidatas."
        )
    return normalizados


def serializar_candidatos_desempate_participaciones(candidatos, partida=None):
    normalizados = normalizar_candidatos_desempate_participaciones(
        candidatos,
        partida=partida,
    )
    return json.dumps(normalizados, ensure_ascii=False, separators=(",", ":"))


def _normalizar_indice_victoria_participacion(indicevictoria):
    indice = _numero_entero_positivo(indicevictoria)
    if indice is None:
        raise ValidacionCartonError(
            "El índice de victoria debe ser un entero mayor que cero."
        )
    return indice


def _bloquear_contexto_participaciones(partida_id, carton_id_adicional=None):
    """Bloquea, en orden, partida, participaciones de ronda y maestros."""
    try:
        partida = Partidabingo.objects.select_for_update().get(pk=partida_id)
    except Partidabingo.DoesNotExist as exc:
        raise ValidacionCartonError("La partida indicada no existe.") from exc

    participaciones = list(
        CartonPartidaBingo.objects.select_for_update()
        .filter(idpartida_id=partida_id)
        .order_by("idcartonpartidabingo")
    )
    ids_carton = {item.idcarton_id for item in participaciones}
    if carton_id_adicional is not None:
        ids_carton.add(carton_id_adicional)
    cartones = list(
        Carton.objects.select_for_update(of=("self",))
        .filter(pk__in=ids_carton)
        .select_related("idjugador")
        .order_by("idcarton")
    )
    cartones_por_id = {carton.pk: carton for carton in cartones}
    for participacion in participaciones:
        carton = cartones_por_id.get(participacion.idcarton_id)
        if carton is not None:
            participacion.idcarton = carton
        participacion.idpartida = partida
    return partida, participaciones, cartones_por_id


def _sincronizar_partida_recibida(partida_recibida, partida_bloqueada, campos):
    if not isinstance(partida_recibida, Partidabingo):
        return
    for campo in campos:
        setattr(partida_recibida, campo, getattr(partida_bloqueada, campo))


def validar_participacion_ganadora(
    partida,
    carton,
    indicevictoria,
    now=None,
):
    """Valida una victoria híbrida sin escribir campos históricos del maestro."""
    idpartida = _id_positivo_modelo_o_valor(partida, "La partida")
    idcarton = _id_positivo_modelo_o_valor(carton, "El cartón")
    indice = _normalizar_indice_victoria_participacion(indicevictoria)

    with transaction.atomic():
        partida_bloqueada, participaciones, cartones_por_id = (
            _bloquear_contexto_participaciones(
                idpartida,
                carton_id_adicional=idcarton,
            )
        )
        validar_estado_validacion_carton(partida_bloqueada)
        carton_bloqueado = cartones_por_id.get(idcarton)
        if carton_bloqueado is None:
            raise ValidacionCartonError("El cartón indicado no existe.")
        participacion = next(
            (
                item
                for item in participaciones
                if item.idcarton_id == idcarton
                and item.idpartida_id == idpartida
            ),
            None,
        )
        if participacion is None:
            raise ValidacionCartonError(
                "No existe una participación para ese cartón y esa partida."
            )
        _validar_coherencia_participacion(
            participacion,
            carton_bloqueado,
            partida_bloqueada,
        )
        if (
            participacion.estado_participacion
            == CartonPartidaBingo.ESTADO_GANADOR
        ):
            if participacion.indicevictoria != indice:
                raise ValidacionCartonError(
                    "La participación ya fue validada con otro índice de victoria."
                )
            return {
                "resultado": "ganador",
                "participacion": participacion,
                "participaciones_ganadoras": [participacion],
                "partida": partida_bloqueada,
                "ya_validada": True,
            }
        if (
            participacion.estado_participacion
            == CartonPartidaBingo.ESTADO_ANULADO
        ):
            raise ValidacionCartonError(
                "Una participación anulada no puede validarse."
            )
        if participacion.estado_participacion not in {
            CartonPartidaBingo.ESTADO_PENDIENTE,
            CartonPartidaBingo.ESTADO_EN_JUEGO,
        }:
            raise ValidacionCartonError(
                "El estado de la participación no permite validarla."
            )

        try:
            evaluacion = evaluar_participacion_en_partida(
                participacion,
                partida_bloqueada,
            )
        except MatrizCartonInvalidaError as exc:
            raise MatrizCartonInvalidaError(
                "La matriz del cartón es inválida y no puede ganar."
            ) from exc
        if not evaluacion["completo"]:
            raise CartonNoCompletoError(evaluacion["faltantes"])

        participaciones_ganadoras = buscar_participaciones_ganadoras(
            partida_bloqueada,
            participaciones=participaciones,
        )
        if len(participaciones_ganadoras) > 1:
            candidatos = [
                construir_candidato_desempate_participacion(item)
                for item in participaciones_ganadoras
            ]
            partida_bloqueada.idjugadorganador = None
            partida_bloqueada.estadopartida = ESTADO_PARTIDA_DESEMPATE
            partida_bloqueada.haydesempate = True
            partida_bloqueada.idbingadores = (
                serializar_candidatos_desempate_participaciones(
                    candidatos,
                    partida=partida_bloqueada,
                )
            )
            campos_partida = [
                "idjugadorganador",
                "estadopartida",
                "haydesempate",
                "idbingadores",
            ]
            partida_bloqueada.save(update_fields=campos_partida)
            resultado = "desempate"
        else:
            fecha = now or timezone.now()
            participacion.estado_participacion = (
                CartonPartidaBingo.ESTADO_GANADOR
            )
            participacion.indicevictoria = indice
            participacion.fechavalidacion = fecha
            participacion.save(
                update_fields=[
                    "estado_participacion",
                    "indicevictoria",
                    "fechavalidacion",
                ]
            )
            candidato = construir_candidato_desempate_participacion(
                participacion
            )
            partida_bloqueada.idjugadorganador = carton_bloqueado.idjugador
            partida_bloqueada.haydesempate = False
            partida_bloqueada.idbingadores = (
                serializar_candidatos_desempate_participaciones(
                    [candidato],
                    partida=partida_bloqueada,
                )
            )
            campos_partida = [
                "idjugadorganador",
                "haydesempate",
                "idbingadores",
            ]
            partida_bloqueada.save(update_fields=campos_partida)
            resultado = "ganador"

    _sincronizar_partida_recibida(
        partida,
        partida_bloqueada,
        campos_partida,
    )
    return {
        "resultado": resultado,
        "participacion": participacion,
        "participaciones_ganadoras": participaciones_ganadoras,
        "partida": partida_bloqueada,
        "ya_validada": False,
    }


def _candidatos_y_participaciones_bloqueadas(partida_bloqueada):
    candidatos = normalizar_candidatos_desempate_participaciones(
        partida_bloqueada.idbingadores,
        partida=partida_bloqueada,
    )
    if not candidatos:
        raise DatosDesempateInvalidosError(
            "La partida no tiene participaciones candidatas para el desempate."
        )
    ids = {item["idcartonpartidabingo"] for item in candidatos}
    _partida, participaciones, _cartones = _bloquear_contexto_participaciones(
        partida_bloqueada.pk
    )
    por_id = {item.pk: item for item in participaciones if item.pk in ids}
    if set(por_id) != ids:
        raise DatosDesempateInvalidosError(
            "Un candidato no pertenece a las participaciones de esta partida."
        )
    for candidato in candidatos:
        participacion = por_id[candidato["idcartonpartidabingo"]]
        carton = participacion.idcarton
        _validar_coherencia_participacion(
            participacion,
            carton,
            partida_bloqueada,
        )
        if (
            participacion.estado_participacion
            == CartonPartidaBingo.ESTADO_ANULADO
        ):
            raise DatosDesempateInvalidosError(
                "Una participación candidata fue anulada."
            )
        if not _carton_vendido_y_asignado(carton):
            raise DatosDesempateInvalidosError(
                "Un cartón candidato ya no está vendido y asignado."
            )
        if (
            candidato["idcarton"] != carton.pk
            or candidato["idpartida"] != partida_bloqueada.pk
            or candidato["idbingo"] != participacion.idbingo_id
            or candidato["idjugador"] != carton.idjugador_id
            or candidato["codigocarton"] != carton.codigocarton
        ):
            raise DatosDesempateInvalidosError(
                "Los datos de un candidato no coinciden con su participación."
            )
    return candidatos, por_id


def sortear_balota_desempate_participacion(
    partida,
    idcartonpartidabingo,
    generador_aleatorio=None,
):
    """Asigna un tiro a una participación, aunque comparta jugador con otra."""
    idpartida = _id_positivo_modelo_o_valor(partida, "La partida")
    idparticipacion = _id_positivo_modelo_o_valor(
        idcartonpartidabingo,
        "La participación",
    )
    generador_aleatorio = generador_aleatorio or random.SystemRandom()

    with transaction.atomic():
        try:
            partida_bloqueada = (
                Partidabingo.objects.select_for_update().get(pk=idpartida)
            )
        except Partidabingo.DoesNotExist as exc:
            raise DesempateError("La partida indicada no existe.") from exc
        validar_estado_desempate(partida_bloqueada)
        candidatos, _participaciones = (
            _candidatos_y_participaciones_bloqueadas(partida_bloqueada)
        )
        candidato = next(
            (
                item
                for item in candidatos
                if item["idcartonpartidabingo"] == idparticipacion
            ),
            None,
        )
        if candidato is None:
            raise DesempateError(
                "La participación indicada no es candidata de este desempate."
            )
        if candidato["tiro_desempate"] is not None:
            raise DesempateError(
                "Esta participación ya realizó su único tiro de desempate."
            )
        usados = {
            item["tiro_desempate"]
            for item in candidatos
            if item["tiro_desempate"] is not None
        }
        disponibles = [numero for numero in range(1, 76) if numero not in usados]
        if not disponibles:
            raise DesempateError(
                "No quedan balotas disponibles para completar el desempate."
            )
        balota = generador_aleatorio.choice(disponibles)
        if balota not in disponibles:
            raise DatosDesempateInvalidosError(
                "El generador produjo una balota de desempate no disponible."
            )
        candidato["tiro_desempate"] = balota
        partida_bloqueada.idbingadores = (
            serializar_candidatos_desempate_participaciones(
                candidatos,
                partida=partida_bloqueada,
            )
        )
        partida_bloqueada.save(update_fields=["idbingadores"])

    _sincronizar_partida_recibida(
        partida,
        partida_bloqueada,
        ["idbingadores"],
    )
    return {
        "partida": partida_bloqueada,
        "candidato": candidato,
        "candidatos": candidatos,
        "balota": balota,
        "codigo": formatear_bola_bingo(balota),
    }


def confirmar_y_finalizar_desempate_participaciones(
    partida,
    indicevictoria,
    now=None,
):
    """Finaliza un desempate actualizando solo candidatas de la ronda exacta."""
    idpartida = _id_positivo_modelo_o_valor(partida, "La partida")
    indice = _normalizar_indice_victoria_participacion(indicevictoria)

    with transaction.atomic():
        try:
            partida_bloqueada = (
                Partidabingo.objects.select_for_update().get(pk=idpartida)
            )
        except Partidabingo.DoesNotExist as exc:
            raise DesempateError("La partida indicada no existe.") from exc
        validar_estado_desempate(partida_bloqueada)
        candidatos, participaciones_por_id = (
            _candidatos_y_participaciones_bloqueadas(partida_bloqueada)
        )
        if any(item["tiro_desempate"] is None for item in candidatos):
            raise DesempateIncompletoError(
                "No se puede confirmar hasta que todas las participaciones sorteen."
            )
        candidato_ganador = max(
            candidatos,
            key=lambda item: item["tiro_desempate"],
        )
        idparticipacion_ganadora = candidato_ganador[
            "idcartonpartidabingo"
        ]
        fecha = now or timezone.now()
        for idparticipacion, participacion in participaciones_por_id.items():
            es_ganadora = idparticipacion == idparticipacion_ganadora
            participacion.estado_participacion = (
                CartonPartidaBingo.ESTADO_GANADOR
                if es_ganadora
                else CartonPartidaBingo.ESTADO_CERRADO
            )
            participacion.indicevictoria = indice if es_ganadora else None
            participacion.fechavalidacion = fecha
            participacion.save(
                update_fields=[
                    "estado_participacion",
                    "indicevictoria",
                    "fechavalidacion",
                ]
            )

        participacion_ganadora = participaciones_por_id[
            idparticipacion_ganadora
        ]
        partida_bloqueada.idjugadorganador = (
            participacion_ganadora.idcarton.idjugador
        )
        partida_bloqueada.bolamayordesempate = candidato_ganador[
            "tiro_desempate"
        ]
        partida_bloqueada.estadopartida = ESTADO_PARTIDA_FINALIZADA
        partida_bloqueada.horafin = fecha
        partida_bloqueada.haydesempate = True
        partida_bloqueada.idbingadores = (
            serializar_candidatos_desempate_participaciones(
                candidatos,
                partida=partida_bloqueada,
            )
        )
        campos_partida = [
            "idjugadorganador",
            "bolamayordesempate",
            "estadopartida",
            "horafin",
            "haydesempate",
            "idbingadores",
        ]
        partida_bloqueada.save(update_fields=campos_partida)

    _sincronizar_partida_recibida(
        partida,
        partida_bloqueada,
        campos_partida,
    )
    return {
        "partida": partida_bloqueada,
        "candidatos": candidatos,
        "candidato_ganador": candidato_ganador,
        "participacion_ganadora": participacion_ganadora,
    }
