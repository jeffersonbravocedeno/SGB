from decimal import Decimal, InvalidOperation


PORCENTAJE_GARANTIA_PRESTAMO = Decimal("0.50")


class PrestamoGarantiaError(ValueError):
    pass


_MISSING = object()


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

    garantes_lista = list(garantes or [])
    if not garantes_lista:
        raise PrestamoGarantiaError("Debe seleccionar al menos un garante.")
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
    capacidad_requerida = monto_normalizado * PORCENTAJE_GARANTIA_PRESTAMO

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
