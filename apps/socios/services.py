from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.ids import assign_next_integer_pk
from apps.jugadores.models import Jugador

from .models import Socio, SolicitudSocio


MENSAJE_JUGADOR_YA_SOCIO = "El jugador ya está vinculado a un socio."
MENSAJE_SOLICITUD_PENDIENTE = "Ya existe una solicitud pendiente para este jugador."
MENSAJE_CEDULA_PENDIENTE = "Ya existe una solicitud pendiente con esta cédula."
MENSAJE_SOLICITUD_RESUELTA = "La solicitud ya fue resuelta."
MENSAJE_JUGADOR_VINCULADO_APROBACION = (
    "No se puede aprobar la solicitud porque el jugador ya fue vinculado a un socio."
)
MENSAJE_MOTIVO_RECHAZO = "Debe ingresar un motivo de rechazo."
MENSAJE_TIPO_SOCIO = "Debe seleccionar un tipo de socio."


def crear_solicitud_socio(jugador, datos_limpios):
    jugador_id = _pk_requerida(jugador, "Debe seleccionar un jugador válido.")
    datos_solicitud = _normalizar_datos_solicitud(datos_limpios)

    with transaction.atomic():
        jugador_bloqueado = Jugador.objects.select_for_update().get(pk=jugador_id)
        if _idsocio_actual(jugador_bloqueado) is not None:
            raise ValidationError(MENSAJE_JUGADOR_YA_SOCIO)

        if SolicitudSocio.objects.filter(
            idjugador=jugador_bloqueado,
            estado=SolicitudSocio.ESTADO_PENDIENTE,
        ).exists():
            raise ValidationError(MENSAJE_SOLICITUD_PENDIENTE)

        if SolicitudSocio.objects.filter(
            cisocio=datos_solicitud["cisocio"],
            estado=SolicitudSocio.ESTADO_PENDIENTE,
        ).exists():
            raise ValidationError(MENSAJE_CEDULA_PENDIENTE)

        try:
            with transaction.atomic():
                return SolicitudSocio.objects.create(
                    idjugador=jugador_bloqueado,
                    estado=SolicitudSocio.ESTADO_PENDIENTE,
                    fechasolicitud=timezone.now(),
                    **datos_solicitud,
                )
        except IntegrityError:
            if SolicitudSocio.objects.filter(
                cisocio=datos_solicitud["cisocio"],
                estado=SolicitudSocio.ESTADO_PENDIENTE,
            ).exists():
                raise ValidationError(MENSAJE_CEDULA_PENDIENTE) from None
            if SolicitudSocio.objects.filter(
                idjugador=jugador_bloqueado,
                estado=SolicitudSocio.ESTADO_PENDIENTE,
            ).exists():
                raise ValidationError(MENSAJE_SOLICITUD_PENDIENTE) from None
            raise ValidationError(
                "No fue posible crear la solicitud. Verifique los datos e inténtelo nuevamente."
            ) from None


def aprobar_solicitud_socio(solicitud_id, usuario_admin, datos_aprobacion=None):
    datos_aprobacion = datos_aprobacion or {}

    with transaction.atomic():
        solicitud = SolicitudSocio.objects.select_for_update().get(pk=solicitud_id)
        _validar_pendiente(solicitud)

        jugador = Jugador.objects.select_for_update().get(pk=solicitud.idjugador_id)
        if _idsocio_actual(jugador) is not None:
            raise ValidationError(MENSAJE_JUGADOR_VINCULADO_APROBACION)

        socio = Socio.objects.filter(cisocio=solicitud.cisocio).first()
        if socio is None:
            socio = _crear_socio_desde_solicitud(solicitud, datos_aprobacion)

        jugador.idsocio = socio
        jugador.save(update_fields=["idsocio"])

        solicitud.estado = SolicitudSocio.ESTADO_APROBADA
        solicitud.fecharespuesta = timezone.now()
        solicitud.idusuarioadminrespuesta = usuario_admin
        solicitud.idsocioresultado = socio
        solicitud.save(
            update_fields=[
                "estado",
                "fecharespuesta",
                "idusuarioadminrespuesta",
                "idsocioresultado",
            ]
        )

    return solicitud, socio


def rechazar_solicitud_socio(solicitud_id, usuario_admin, motivo):
    motivo_limpio = _texto_limpio(motivo)
    if not motivo_limpio:
        raise ValidationError(MENSAJE_MOTIVO_RECHAZO)

    with transaction.atomic():
        solicitud = SolicitudSocio.objects.select_for_update().get(pk=solicitud_id)
        _validar_pendiente(solicitud)

        solicitud.estado = SolicitudSocio.ESTADO_RECHAZADA
        solicitud.fecharespuesta = timezone.now()
        solicitud.idusuarioadminrespuesta = usuario_admin
        solicitud.motivorechazo = motivo_limpio
        solicitud.save(
            update_fields=[
                "estado",
                "fecharespuesta",
                "idusuarioadminrespuesta",
                "motivorechazo",
            ]
        )

    return solicitud


def _crear_socio_desde_solicitud(solicitud, datos_aprobacion):
    tipo_socio = datos_aprobacion.get("idtiposocio") or solicitud.idtiposocio
    if tipo_socio is None:
        raise ValidationError(MENSAJE_TIPO_SOCIO)

    socio = Socio(
        idtiposocio=tipo_socio,
        primernombresocio=solicitud.primernombresocio,
        segundonombresocio=solicitud.segundonombresocio,
        primerapellidosocio=solicitud.primerapellidosocio,
        segundoapellidosocio=solicitud.segundoapellidosocio,
        cisocio=solicitud.cisocio,
        fechanacimientosocio=solicitud.fechanacimientosocio,
        telefonopersonalsocio=solicitud.telefonopersonalsocio,
        telefonotrabajosocio=solicitud.telefonotrabajosocio,
        direcciondomiciliosocio=solicitud.direcciondomiciliosocio,
        direcciontrabajosocio=solicitud.direcciontrabajosocio,
        sexosocio=solicitud.sexosocio,
        estadosocio=datos_aprobacion.get("estadosocio") or "Activo",
    )
    assign_next_integer_pk(socio)
    socio.save(force_insert=True)
    return socio


def _normalizar_datos_solicitud(datos_limpios):
    datos = dict(datos_limpios or {})
    campos_texto_requeridos = (
        "primernombresocio",
        "primerapellidosocio",
        "segundoapellidosocio",
        "cisocio",
        "direcciondomiciliosocio",
    )
    for campo in campos_texto_requeridos:
        datos[campo] = _texto_requerido(datos.get(campo), campo)

    if not datos.get("fechanacimientosocio"):
        raise ValidationError({"fechanacimientosocio": "Este campo es obligatorio."})

    for campo in (
        "segundonombresocio",
        "telefonopersonalsocio",
        "telefonotrabajosocio",
        "direcciontrabajosocio",
        "sexosocio",
        "observacion",
    ):
        datos[campo] = _texto_limpio(datos.get(campo)) or None

    campos_permitidos = {
        "idtiposocio",
        "primernombresocio",
        "segundonombresocio",
        "primerapellidosocio",
        "segundoapellidosocio",
        "cisocio",
        "fechanacimientosocio",
        "telefonopersonalsocio",
        "telefonotrabajosocio",
        "direcciondomiciliosocio",
        "direcciontrabajosocio",
        "sexosocio",
        "observacion",
    }
    return {campo: datos.get(campo) for campo in campos_permitidos}


def _validar_pendiente(solicitud):
    if solicitud.estado != SolicitudSocio.ESTADO_PENDIENTE:
        raise ValidationError(MENSAJE_SOLICITUD_RESUELTA)


def _pk_requerida(objeto, mensaje):
    pk = getattr(objeto, "pk", None)
    if pk is None:
        raise ValidationError(mensaje)
    return pk


def _idsocio_actual(jugador):
    idsocio_id = getattr(jugador, "idsocio_id", None)
    if idsocio_id is not None:
        return idsocio_id
    idsocio = getattr(jugador, "idsocio", None)
    return getattr(idsocio, "pk", None) if idsocio is not None else None


def _texto_limpio(value):
    return str(value).strip() if value not in (None, "") else ""


def _texto_requerido(value, campo):
    value = _texto_limpio(value)
    if not value:
        raise ValidationError({campo: "Este campo es obligatorio."})
    return value
