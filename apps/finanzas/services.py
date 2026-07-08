from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.socios.models import Socio

from .models import Ahorro, Prestamo, PrestamoGarante


PORCENTAJE_GARANTIA_PRESTAMO = Decimal("0.50")
ESTADOS_PRESTAMO_SIN_SALDO_GARANTE = (
    "Liquidado",
    "Pagado",
    "Cerrado",
    "Cancelado",
    "Rechazado",
    "Anulado",
)
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
    "saldopendiente",
    "fechasolicitud",
    "fechavencimiento",
    "estadoprestamo",
}


class PrestamoGarantiaError(ValueError):
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

    return datos_normalizados, socio_id


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
