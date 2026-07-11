from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.jugadores.models import Jugador
from apps.socios.models import Socio

from .models import (
    Ahorro,
    PagoPrestamo,
    Prestamo,
    PrestamoGarante,
    SolicitudPagoPrestamo,
)


PORCENTAJE_GARANTIA_PRESTAMO = Decimal("0.50")
ESTADOS_PRESTAMO_NO_PAGABLES = (
    "Liquidado",
    "Pagado",
    "Finalizado",
    "Cerrado",
    "Cancelado",
    "Rechazado",
    "Anulado",
)
ESTADOS_PRESTAMO_SIN_SALDO_GARANTE = ESTADOS_PRESTAMO_NO_PAGABLES
PRESTAMO_CAMPOS_PERMITIDOS = {
    "idsocio",
    "montoprestamosolicitado",
    "tasainteres",
    "montototalpagar",
    "saldopendiente",
    "numerocuotas",
    "fechasolicitud",
    "fechavencimiento",
    "estadoprestamo",
}
PRESTAMO_CAMPOS_OBLIGATORIOS = {
    "idsocio",
    "montoprestamosolicitado",
    "montototalpagar",
    "fechasolicitud",
    "fechavencimiento",
    "estadoprestamo",
}
MENSAJE_TOTAL_MENOR_MONTO_SOLICITADO = (
    "El total a pagar no puede ser menor que el monto solicitado."
)


class PrestamoGarantiaError(ValueError):
    pass


class PrestamoPagoError(ValueError):
    pass


class SolicitudPagoPrestamoError(ValueError):
    pass


_MISSING = object()


def _lista_desde_iterable(valores):
    if valores is None:
        return []
    return list(valores)


def _decimal_seguro(valor):
    if valor is None or isinstance(valor, bool):
        raise InvalidOperation
    if isinstance(valor, Decimal):
        decimal = valor
    else:
        texto = str(valor).strip()
        if not texto:
            raise InvalidOperation
        decimal = Decimal(texto)
    if not decimal.is_finite():
        raise InvalidOperation
    return decimal


def _obtener_campo(garante, campo):
    if isinstance(garante, dict):
        return garante.get(campo, _MISSING)
    return getattr(garante, campo, _MISSING)


def _normalizar_idsocio(valor):
    if valor is _MISSING or valor is None or isinstance(valor, bool):
        raise PrestamoGarantiaError("Debe seleccionar un garante válido.")
    if isinstance(valor, str):
        valor = valor.strip()
        if not valor:
            raise PrestamoGarantiaError("Debe seleccionar un garante válido.")
    try:
        return int(valor)
    except (TypeError, ValueError, InvalidOperation):
        raise PrestamoGarantiaError("Debe seleccionar un garante válido.") from None


def _idsocio_desde_valor(valor):
    if hasattr(valor, "idsocio"):
        return _normalizar_idsocio(valor.idsocio)
    if hasattr(valor, "pk") and valor.pk is not None:
        return _normalizar_idsocio(valor.pk)
    return _normalizar_idsocio(valor)


def _normalizar_capacidad(valor):
    try:
        capacidad = _decimal_seguro(valor)
    except (InvalidOperation, ValueError):
        raise PrestamoGarantiaError(
            "La capacidad del garante debe ser un valor numérico válido."
        ) from None
    if capacidad < 0:
        return Decimal("0")
    return capacidad


def _normalizar_monto_pago(valor):
    try:
        monto = _decimal_seguro(valor)
    except (InvalidOperation, ValueError):
        raise PrestamoPagoError(
            "El monto del pago debe ser mayor que cero."
        ) from None
    if monto <= 0:
        raise PrestamoPagoError("El monto del pago debe ser mayor que cero.")
    return monto


def _normalizar_saldo_pendiente_pago(valor):
    try:
        saldo = _decimal_seguro(valor)
    except (InvalidOperation, ValueError):
        raise PrestamoPagoError("El préstamo no tiene saldo pendiente.") from None
    if saldo <= 0:
        raise PrestamoPagoError("El préstamo no tiene saldo pendiente.")
    return saldo


def _idprestamo_desde_valor(valor):
    if hasattr(valor, "idprestamo"):
        valor = valor.idprestamo
    elif hasattr(valor, "pk") and valor.pk is not None:
        valor = valor.pk

    if valor is None or isinstance(valor, bool):
        raise PrestamoPagoError("Debe seleccionar un préstamo válido.")
    if isinstance(valor, str):
        valor = valor.strip()
        if not valor:
            raise PrestamoPagoError("Debe seleccionar un préstamo válido.")
    try:
        return int(valor)
    except (TypeError, ValueError, InvalidOperation):
        raise PrestamoPagoError("Debe seleccionar un préstamo válido.") from None


def _texto_limpio_pago(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _texto_limpio_solicitud_pago(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def _texto_requerido_solicitud_pago(valor, mensaje):
    texto = _texto_limpio_solicitud_pago(valor)
    if not texto:
        raise SolicitudPagoPrestamoError(mensaje)
    return texto


def _normalizar_monto_solicitud_pago(valor):
    try:
        monto = _decimal_seguro(valor)
    except (InvalidOperation, ValueError):
        raise SolicitudPagoPrestamoError("El monto debe ser mayor que cero.") from None
    if monto <= 0:
        raise SolicitudPagoPrestamoError("El monto debe ser mayor que cero.")
    return monto


def _normalizar_saldo_solicitud_pago(valor):
    try:
        saldo = _decimal_seguro(valor)
    except (InvalidOperation, ValueError):
        raise SolicitudPagoPrestamoError("El préstamo no tiene saldo pendiente.") from None
    if saldo <= 0:
        raise SolicitudPagoPrestamoError("El préstamo no tiene saldo pendiente.")
    return saldo


def _id_entero_or_none(valor):
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, str):
        valor = valor.strip()
        if not valor:
            return None
    try:
        return int(valor)
    except (TypeError, ValueError, InvalidOperation):
        return None


def _id_modelo(objeto, nombre_pk):
    if objeto is None:
        return None
    valor = getattr(objeto, nombre_pk, None)
    if valor is None:
        valor = getattr(objeto, "pk", None)
    return _id_entero_or_none(valor)


def _id_relacion(objeto, nombre_relacion, nombre_pk):
    valor = getattr(objeto, f"{nombre_relacion}_id", None)
    if valor is not None:
        return _id_entero_or_none(valor)
    relacionado = getattr(objeto, nombre_relacion, None)
    return _id_modelo(relacionado, nombre_pk)


def _idsocio_jugador(jugador):
    return _id_relacion(jugador, "idsocio", "idsocio")


def _idsocio_prestamo(prestamo):
    return _id_relacion(prestamo, "idsocio", "idsocio")


def _observacion_pago_desde_solicitud(solicitud, observacion_admin):
    partes = []
    observacion_socio = _texto_limpio_solicitud_pago(solicitud.observacionsocio)
    comprobante = _texto_limpio_solicitud_pago(solicitud.rutacomprobante)
    observacion_admin = _texto_limpio_solicitud_pago(observacion_admin)
    if observacion_socio:
        partes.append(f"Socio: {observacion_socio}")
    if comprobante:
        partes.append(f"Comprobante: {comprobante}")
    if observacion_admin:
        partes.append(f"Admin: {observacion_admin}")
    return " | ".join(partes)[:255]


def _dato_aprobacion(datos_aprobacion, campo, default=""):
    if datos_aprobacion is None:
        return default
    if hasattr(datos_aprobacion, "get"):
        return datos_aprobacion.get(campo, default)
    return getattr(datos_aprobacion, campo, default)


def _prestamo_admite_pagos(prestamo):
    estado_normalizado = str(prestamo.estadoprestamo or "").strip().lower()
    return not any(
        estado_normalizado == estado_no_pagable.lower()
        for estado_no_pagable in ESTADOS_PRESTAMO_NO_PAGABLES
    )


def _es_entrada_vacia(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _sumar_decimal_agregado(queryset, campo):
    total = queryset.aggregate(total=Sum(campo)).get("total")
    return total or Decimal("0")


def _q_estados_prestamo_finales():
    filtros = Q()
    for estado in ESTADOS_PRESTAMO_SIN_SALDO_GARANTE:
        filtros |= Q(estadoprestamo__iexact=estado)
    return filtros


def calcular_capacidad_garante(socio):
    socio_id = _idsocio_desde_valor(socio)
    total_ahorros = _sumar_decimal_agregado(
        Ahorro.objects.filter(idsocio_id=socio_id, estado__iexact="Activo"),
        "montoahorro",
    )
    total_pendiente = _sumar_decimal_agregado(
        Prestamo.objects.filter(idsocio_id=socio_id)
        .exclude(_q_estados_prestamo_finales()),
        "saldopendiente",
    )

    capacidad = total_ahorros - total_pendiente
    if capacidad < 0:
        return Decimal("0")
    return capacidad


def construir_datos_garantes(garantes):
    datos = []
    for garante in _lista_desde_iterable(garantes):
        if _es_entrada_vacia(garante):
            continue
        idsocio = _idsocio_desde_valor(garante)
        datos.append(
            {
                "idsocio": idsocio,
                "capacidad": calcular_capacidad_garante(garante),
            }
        )
    return datos


def _datos_prestamo_desde_objeto(datos_prestamo):
    if hasattr(datos_prestamo, "items"):
        return dict(datos_prestamo)
    if datos_prestamo is None:
        return {}
    return {
        campo: getattr(datos_prestamo, campo)
        for campo in PRESTAMO_CAMPOS_PERMITIDOS
        if hasattr(datos_prestamo, campo)
    }


def _normalizar_datos_prestamo(datos_prestamo):
    datos = _datos_prestamo_desde_objeto(datos_prestamo)
    campos_no_permitidos = set(datos) - PRESTAMO_CAMPOS_PERMITIDOS
    if campos_no_permitidos:
        campo = sorted(campos_no_permitidos)[0]
        raise PrestamoGarantiaError(f"Dato de préstamo no permitido: {campo}.")

    for campo in sorted(PRESTAMO_CAMPOS_OBLIGATORIOS):
        valor = datos.get(campo, _MISSING)
        if valor is _MISSING or valor is None:
            raise PrestamoGarantiaError(
                f"Falta el dato obligatorio del préstamo: {campo}."
            )
        if isinstance(valor, str) and not valor.strip():
            raise PrestamoGarantiaError(
                f"Falta el dato obligatorio del préstamo: {campo}."
            )

    socio = datos["idsocio"]
    socio_id = _idsocio_desde_valor(socio)
    datos_normalizados = {}
    if isinstance(socio, Socio):
        datos_normalizados["idsocio"] = socio
    else:
        datos_normalizados["idsocio_id"] = socio_id

    for campo in PRESTAMO_CAMPOS_PERMITIDOS - {"idsocio"}:
        if campo in datos:
            datos_normalizados[campo] = datos[campo]

    _normalizar_montos_creacion_prestamo(datos_normalizados)

    return datos_normalizados, socio_id


def _normalizar_montos_creacion_prestamo(datos_prestamo):
    try:
        monto_solicitado = _decimal_seguro(datos_prestamo["montoprestamosolicitado"])
    except (InvalidOperation, ValueError):
        raise PrestamoGarantiaError(
            "El monto solicitado del préstamo debe ser mayor que cero."
        ) from None

    if monto_solicitado <= 0:
        raise PrestamoGarantiaError(
            "El monto solicitado del préstamo debe ser mayor que cero."
        )

    try:
        monto_total = _decimal_seguro(datos_prestamo["montototalpagar"])
    except (InvalidOperation, ValueError):
        raise PrestamoGarantiaError(
            "El total a pagar del préstamo debe ser un valor numérico válido."
        ) from None

    if monto_total < monto_solicitado:
        raise PrestamoGarantiaError(MENSAJE_TOTAL_MENOR_MONTO_SOLICITADO)

    datos_prestamo["montoprestamosolicitado"] = monto_solicitado
    datos_prestamo["montototalpagar"] = monto_total
    datos_prestamo["saldopendiente"] = monto_total


def _ids_garantes_limpios(garantes):
    ids = []
    for garante in _lista_desde_iterable(garantes):
        if _es_entrada_vacia(garante):
            continue
        ids.append(_idsocio_desde_valor(garante))
    return ids


def _bloquear_socios_garantes(ids_garantes):
    if not ids_garantes:
        return []

    ids_unicos = list(dict.fromkeys(ids_garantes))
    socios_bloqueados = list(
        Socio.objects.select_for_update().filter(idsocio__in=ids_unicos)
    )
    ids_bloqueados = {_idsocio_desde_valor(socio) for socio in socios_bloqueados}
    if ids_bloqueados != set(ids_unicos):
        raise PrestamoGarantiaError("Debe seleccionar un garante válido.")
    return socios_bloqueados


def crear_prestamo_con_garantes(*, datos_prestamo, garantes, usuario=None):
    datos_normalizados, socio_deudor_id = _normalizar_datos_prestamo(datos_prestamo)
    garantes_lista = _lista_desde_iterable(garantes)
    del usuario

    with transaction.atomic():
        ids_garantes = _ids_garantes_limpios(garantes_lista)
        socios_garantes = _bloquear_socios_garantes(ids_garantes)
        socios_garantes_por_id = {
            _idsocio_desde_valor(socio): socio
            for socio in socios_garantes
        }
        datos_garantes = construir_datos_garantes(garantes_lista)
        validacion = validar_garantes_prestamo(
            socio_deudor_id=socio_deudor_id,
            monto_solicitado=datos_normalizados["montoprestamosolicitado"],
            garantes=datos_garantes,
        )

        datos_normalizados["montoprestamosolicitado"] = validacion[
            "monto_solicitado"
        ]
        prestamo = Prestamo.objects.create(**datos_normalizados)

        fecha_registro = timezone.now()
        for garante in validacion["garantes_normalizados"]:
            socio_garante = socios_garantes_por_id[garante["idsocio"]]
            PrestamoGarante.objects.create(
                idprestamo=prestamo,
                idgarante=socio_garante,
                capacidadcalculada=garante["capacidad"],
                fecharegistro=fecha_registro,
                estado=PrestamoGarante.ESTADO_ACTIVO,
            )

    return prestamo


def registrar_pago_prestamo(
    prestamo,
    *,
    monto_pagado,
    metodo_pago=None,
    numero_referencia="",
    observacion="",
    fecha_pago=None,
):
    monto_normalizado = _normalizar_monto_pago(monto_pagado)
    prestamo_id = _idprestamo_desde_valor(prestamo)
    referencia_limpia = _texto_limpio_pago(numero_referencia)
    observacion_limpia = _texto_limpio_pago(observacion)
    fecha_pago_normalizada = fecha_pago or timezone.now()

    with transaction.atomic():
        try:
            prestamo_bloqueado = (
                Prestamo.objects.select_for_update().get(idprestamo=prestamo_id)
            )
        except Prestamo.DoesNotExist:
            raise PrestamoPagoError("Debe seleccionar un préstamo válido.") from None

        if not _prestamo_admite_pagos(prestamo_bloqueado):
            raise PrestamoPagoError("El préstamo no admite nuevos pagos.")

        saldo_pendiente = _normalizar_saldo_pendiente_pago(
            prestamo_bloqueado.saldopendiente
        )
        if monto_normalizado > saldo_pendiente:
            raise PrestamoPagoError(
                "El monto del pago no puede superar el saldo pendiente."
            )

        pago = PagoPrestamo.objects.create(
            idprestamo=prestamo_bloqueado,
            idmetodopago=metodo_pago,
            fechapago=fecha_pago_normalizada,
            montopagado=monto_normalizado,
            numeroreferencia=referencia_limpia,
            observacion=observacion_limpia,
            estado=PagoPrestamo.ESTADO_REGISTRADO,
        )

        nuevo_saldo = saldo_pendiente - monto_normalizado
        prestamo_bloqueado.saldopendiente = nuevo_saldo
        update_fields = ["saldopendiente"]
        if nuevo_saldo == Decimal("0"):
            prestamo_bloqueado.saldopendiente = Decimal("0")
            prestamo_bloqueado.estadoprestamo = "Liquidado"
            update_fields.append("estadoprestamo")
        prestamo_bloqueado.save(update_fields=update_fields)

    return pago


def crear_solicitud_pago_prestamo(jugador, idprestamo, datos_limpios):
    jugador_id = _id_modelo(jugador, "idjugador")
    if jugador_id is None:
        raise SolicitudPagoPrestamoError("Debe seleccionar un jugador válido.")

    try:
        prestamo_id = _idprestamo_desde_valor(idprestamo)
    except PrestamoPagoError as exc:
        raise SolicitudPagoPrestamoError(str(exc)) from None

    datos_limpios = datos_limpios or {}
    monto = _normalizar_monto_solicitud_pago(datos_limpios.get("monto"))
    referencia = _texto_requerido_solicitud_pago(
        datos_limpios.get("referencia"),
        "Debe ingresar una referencia.",
    )
    rutacomprobante = (
        _texto_limpio_solicitud_pago(datos_limpios.get("rutacomprobante")) or None
    )
    observacionsocio = (
        _texto_limpio_solicitud_pago(datos_limpios.get("observacionsocio")) or None
    )

    with transaction.atomic():
        try:
            jugador_bloqueado = Jugador.objects.select_for_update().get(
                idjugador=jugador_id
            )
        except Jugador.DoesNotExist:
            raise SolicitudPagoPrestamoError(
                "Debe seleccionar un jugador válido."
            ) from None

        socio_id = _idsocio_jugador(jugador_bloqueado)
        if socio_id is None:
            raise SolicitudPagoPrestamoError(
                "El jugador no está vinculado a un socio."
            )

        try:
            prestamo = Prestamo.objects.select_for_update().get(
                idprestamo=prestamo_id
            )
        except Prestamo.DoesNotExist:
            raise SolicitudPagoPrestamoError(
                "Debe seleccionar un préstamo válido."
            ) from None

        if _idsocio_prestamo(prestamo) != socio_id:
            raise SolicitudPagoPrestamoError(
                "El préstamo no pertenece al socio autenticado."
            )

        if not _prestamo_admite_pagos(prestamo):
            raise SolicitudPagoPrestamoError("El préstamo no admite nuevos pagos.")

        saldo_pendiente = _normalizar_saldo_solicitud_pago(prestamo.saldopendiente)
        if monto > saldo_pendiente:
            raise SolicitudPagoPrestamoError(
                "El monto no puede superar el saldo pendiente."
            )

        if SolicitudPagoPrestamo.objects.filter(
            idprestamo=prestamo,
            estado=SolicitudPagoPrestamo.ESTADO_PENDIENTE,
        ).exists():
            raise SolicitudPagoPrestamoError(
                "Ya existe una solicitud de pago pendiente para este préstamo."
            )

        return SolicitudPagoPrestamo.objects.create(
            idprestamo=prestamo,
            idsocio_id=socio_id,
            idjugador=jugador_bloqueado,
            idmetodopago=datos_limpios.get("idmetodopago"),
            monto=monto,
            referencia=referencia,
            rutacomprobante=rutacomprobante,
            observacionsocio=observacionsocio,
            estado=SolicitudPagoPrestamo.ESTADO_PENDIENTE,
            fechasolicitud=timezone.now(),
        )


def aprobar_solicitud_pago_prestamo(
    idsolicitudpago,
    usuario_admin,
    datos_aprobacion=None,
):
    observacion_admin = _texto_limpio_solicitud_pago(
        _dato_aprobacion(datos_aprobacion, "observacionadmin", "")
    )

    with transaction.atomic():
        try:
            solicitud = SolicitudPagoPrestamo.objects.select_for_update().get(
                idsolicitudpago=idsolicitudpago
            )
        except SolicitudPagoPrestamo.DoesNotExist:
            raise SolicitudPagoPrestamoError(
                "Debe seleccionar una solicitud válida."
            ) from None

        if solicitud.estado != SolicitudPagoPrestamo.ESTADO_PENDIENTE:
            raise SolicitudPagoPrestamoError("La solicitud ya fue resuelta.")

        try:
            prestamo = Prestamo.objects.select_for_update().get(
                idprestamo=solicitud.idprestamo_id
            )
        except Prestamo.DoesNotExist:
            raise SolicitudPagoPrestamoError(
                "Debe seleccionar un préstamo válido."
            ) from None

        try:
            jugador = Jugador.objects.select_for_update().get(
                idjugador=solicitud.idjugador_id
            )
        except Jugador.DoesNotExist:
            raise SolicitudPagoPrestamoError(
                "La solicitud no conserva una relación válida entre jugador, socio y préstamo."
            ) from None

        if (
            solicitud.idjugador_id != jugador.pk
            or solicitud.idsocio_id != _idsocio_jugador(jugador)
            or _idsocio_prestamo(prestamo) != solicitud.idsocio_id
            or prestamo.pk != solicitud.idprestamo_id
        ):
            raise SolicitudPagoPrestamoError(
                "La solicitud no conserva una relación válida entre jugador, socio y préstamo."
            )

        if not _prestamo_admite_pagos(prestamo):
            raise SolicitudPagoPrestamoError("El préstamo no admite nuevos pagos.")

        monto = _normalizar_monto_solicitud_pago(solicitud.monto)
        saldo_pendiente = _normalizar_saldo_solicitud_pago(prestamo.saldopendiente)
        if monto > saldo_pendiente:
            raise SolicitudPagoPrestamoError(
                "El monto no puede superar el saldo pendiente."
            )

        try:
            pago = registrar_pago_prestamo(
                prestamo,
                monto_pagado=monto,
                metodo_pago=solicitud.idmetodopago
                if solicitud.idmetodopago_id
                else None,
                numero_referencia=solicitud.referencia,
                observacion=_observacion_pago_desde_solicitud(
                    solicitud,
                    observacion_admin,
                ),
            )
        except PrestamoPagoError as exc:
            raise SolicitudPagoPrestamoError(str(exc)) from None

        solicitud.estado = SolicitudPagoPrestamo.ESTADO_APROBADA
        solicitud.fecharespuesta = timezone.now()
        solicitud.idusuarioadminrespuesta = usuario_admin
        solicitud.observacionadmin = observacion_admin or None
        solicitud.idpagoprestamoresultado = pago
        solicitud.save(
            update_fields=[
                "estado",
                "fecharespuesta",
                "idusuarioadminrespuesta",
                "observacionadmin",
                "idpagoprestamoresultado",
            ]
        )

    return solicitud, pago


def rechazar_solicitud_pago_prestamo(idsolicitudpago, usuario_admin, motivo):
    motivo_limpio = _texto_requerido_solicitud_pago(
        motivo,
        "Debe ingresar un motivo de rechazo.",
    )

    with transaction.atomic():
        try:
            solicitud = SolicitudPagoPrestamo.objects.select_for_update().get(
                idsolicitudpago=idsolicitudpago
            )
        except SolicitudPagoPrestamo.DoesNotExist:
            raise SolicitudPagoPrestamoError(
                "Debe seleccionar una solicitud válida."
            ) from None

        if solicitud.estado != SolicitudPagoPrestamo.ESTADO_PENDIENTE:
            raise SolicitudPagoPrestamoError("La solicitud ya fue resuelta.")

        solicitud.estado = SolicitudPagoPrestamo.ESTADO_RECHAZADA
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


def validar_garantes_prestamo(*, socio_deudor_id, monto_solicitado, garantes):
    try:
        monto_normalizado = _decimal_seguro(monto_solicitado)
    except (InvalidOperation, ValueError):
        raise PrestamoGarantiaError(
            "El monto solicitado del préstamo debe ser mayor que cero."
        ) from None

    if monto_normalizado <= 0:
        raise PrestamoGarantiaError(
            "El monto solicitado del préstamo debe ser mayor que cero."
        )

    garantes_lista = _lista_desde_iterable(garantes)
    capacidad_requerida = monto_normalizado * PORCENTAJE_GARANTIA_PRESTAMO
    if not garantes_lista:
        return {
            "monto_solicitado": monto_normalizado,
            "porcentaje_requerido": PORCENTAJE_GARANTIA_PRESTAMO,
            "capacidad_requerida": capacidad_requerida,
            "capacidad_total": Decimal("0.00"),
            "garantes_normalizados": [],
        }
    if len(garantes_lista) > 2:
        raise PrestamoGarantiaError("Un préstamo no puede tener más de dos garantes.")

    socio_deudor_normalizado = _normalizar_idsocio(socio_deudor_id)
    ids_garantes = set()
    garantes_normalizados = []

    for garante in garantes_lista:
        idsocio = _normalizar_idsocio(_obtener_campo(garante, "idsocio"))
        if idsocio == socio_deudor_normalizado:
            raise PrestamoGarantiaError(
                "El garante no puede ser el mismo socio deudor."
            )
        if idsocio in ids_garantes:
            raise PrestamoGarantiaError("No puede repetir el mismo garante.")
        ids_garantes.add(idsocio)

        capacidad = _normalizar_capacidad(_obtener_campo(garante, "capacidad"))
        garantes_normalizados.append(
            {
                "idsocio": idsocio,
                "capacidad": capacidad,
            }
        )

    capacidad_total = sum(
        (garante["capacidad"] for garante in garantes_normalizados),
        Decimal("0"),
    )
    if capacidad_total < capacidad_requerida:
        raise PrestamoGarantiaError(
            "La capacidad total de los garantes debe cubrir al menos el 50% del "
            "monto solicitado."
        )

    return {
        "monto_solicitado": monto_normalizado,
        "porcentaje_requerido": PORCENTAJE_GARANTIA_PRESTAMO,
        "capacidad_requerida": capacidad_requerida,
        "capacidad_total": capacidad_total,
        "garantes_normalizados": garantes_normalizados,
    }
