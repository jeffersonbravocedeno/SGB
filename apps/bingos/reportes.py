import re
from collections import Counter, defaultdict
from decimal import Decimal
from io import BytesIO

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .services import (
    ESTADO_PARTIDA_FINALIZADA,
    estado_partida_mostrar,
    formatear_bola_bingo,
    parsear_bolas_cantadas,
    preparar_datos_bolas_partida,
)


PDF_CONTENT_TYPE = "application/pdf"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

MONEDA_FORMAT = '"$"#,##0.00'
FECHA_FORMAT = "dd/mm/yyyy hh:mm"


def nombre_archivo_seguro(prefijo, identificador, extension):
    base = f"{prefijo}_{identificador}"
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", str(base)).strip("_")
    return f"{base}.{extension}"


def construir_datos_reporte_partida(partida, cartones=None, generado_en=None):
    cartones = list(cartones or [])
    datos_bolas = preparar_datos_bolas_partida(partida)
    bolas_extraidas = datos_bolas["bolas_extraidas"]
    estado = estado_partida_mostrar(partida.estadopartida)
    finalizada = estado == ESTADO_PARTIDA_FINALIZADA
    ganador = _alias_ganador(partida) if finalizada else None
    carton_ganador = _carton_ganador(partida, cartones) if finalizada else None

    return {
        "generado_en": generado_en or timezone.localtime(timezone.now()),
        "bingo": partida.idbingo,
        "partida": partida,
        "estado": estado,
        "finalizada": finalizada,
        "bolas_extraidas": bolas_extraidas,
        "bolas_extraidas_codigos": [_formatear_bola(numero) for numero in bolas_extraidas],
        "cantidad_extraida": len(bolas_extraidas),
        "cantidad_restante": 75 - len(bolas_extraidas),
        "ultima_bola": datos_bolas["ultima_bola_codigo"],
        "hubo_desempate": bool(partida.haydesempate),
        "balota_mayor_desempate": _formatear_bola(partida.bolamayordesempate),
        "ganador": ganador,
        "carton_ganador": carton_ganador.codigocarton if carton_ganador else None,
        "mensaje_resultado": (
            "Partida finalizada."
            if finalizada
            else "La partida aún no está finalizada."
        ),
    }


def generar_pdf_reporte_partida(partida, cartones=None):
    datos = construir_datos_reporte_partida(partida, cartones=cartones)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=f"Reporte de partida {partida.idpartidabingo}",
        pageCompression=0,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("SIAB / Sistema Integral de Administración de Bingos", styles["Title"]),
        Paragraph("Reporte de partida", styles["Heading1"]),
        Paragraph(f"Generado: {_formatear_fecha(datos['generado_en'])}", styles["Normal"]),
        Spacer(1, 12),
    ]

    bingo = datos["bingo"]
    story.append(Paragraph("Datos del Bingo", styles["Heading2"]))
    story.append(
        _tabla_pdf(
            [
                ("ID de Bingo", bingo.idbingo),
                ("Título", bingo.titulobingo),
                ("Fecha programada", _formatear_fecha(bingo.fechaprogramadabingo)),
                ("Tipo", bingo.tipobingo),
                ("Precio del cartón", _formatear_moneda(bingo.preciocarton)),
                (
                    "Premio mayor",
                    _premio_bingo(bingo),
                ),
            ]
        )
    )
    story.append(Spacer(1, 10))

    partida = datos["partida"]
    story.append(Paragraph("Datos de la partida", styles["Heading2"]))
    story.append(
        _tabla_pdf(
            [
                ("ID de partida", partida.idpartidabingo),
                ("Ronda", partida.nombreronda),
                ("Estado", datos["estado"]),
                ("Inicio", _formatear_fecha(partida.horainicio)),
                ("Finalización", _formatear_fecha(partida.horafin)),
                ("Bolas extraídas", datos["cantidad_extraida"]),
                ("Bolas restantes", datos["cantidad_restante"]),
                ("Última bola", datos["ultima_bola"] or "-"),
                ("Hubo desempate", _si_no(datos["hubo_desempate"])),
                ("Balota mayor de desempate", datos["balota_mayor_desempate"] or "-"),
            ]
        )
    )
    story.append(Spacer(1, 10))

    story.append(Paragraph("Bolas extraídas", styles["Heading2"]))
    bolas = ", ".join(datos["bolas_extraidas_codigos"]) or "Sin bolas extraídas."
    story.append(Paragraph(bolas, styles["Normal"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Resultado", styles["Heading2"]))
    resultado = [(datos["mensaje_resultado"], "")]
    if datos["finalizada"]:
        resultado.extend(
            [
                ("Ganador", datos["ganador"] or "Sin ganador registrado"),
                ("Resuelta por desempate", _si_no(datos["hubo_desempate"])),
            ]
        )
        if datos["carton_ganador"]:
            resultado.append(("Cartón ganador", datos["carton_ganador"]))
    story.append(_tabla_pdf(resultado))

    doc.build(story)
    return buffer.getvalue()


def generar_excel_cartones_partida(partida, cartones):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Cartones"

    headers = [
        "ID de cartón",
        "Código de cartón",
        "Jugador",
        "Estado del cartón",
        "Fecha de compra",
        "Precio pagado",
        "Índice de victoria",
        "ID de partida",
        "Nombre de ronda",
        "Estado de partida",
    ]
    worksheet.append(headers)

    total_recaudado = Decimal("0.00")
    estados = Counter()
    for carton in cartones:
        precio = _decimal(carton.preciopagado)
        total_recaudado += precio
        estados[_estado_normalizado(carton.estadocarton)] += 1
        worksheet.append(
            [
                carton.idcarton,
                carton.codigocarton,
                _nombre_jugador(carton.idjugador),
                carton.estadocarton,
                _fecha_para_excel(carton.fechacompra),
                float(precio),
                carton.indicevictoria,
                partida.idpartidabingo,
                partida.nombreronda,
                estado_partida_mostrar(partida.estadopartida),
            ]
        )

    resumen_row = worksheet.max_row + 2
    resumen = [
        ("Total de cartones", len(cartones)),
        ("Total recaudado", float(total_recaudado)),
        ("Cartones vendidos", estados.get("vendido", 0)),
        ("Cartones anulados", _cantidad_estados(estados, {"anulado", "anulada", "cancelado", "cancelada"})),
        ("Cartones disponibles", estados.get("disponible", 0)),
    ]
    for offset, (label, value) in enumerate(resumen):
        row = resumen_row + offset
        worksheet.cell(row=row, column=1, value=label)
        worksheet.cell(row=row, column=2, value=value)
    worksheet.cell(row=resumen_row + 1, column=2).number_format = MONEDA_FORMAT

    _aplicar_formato_basico_excel(worksheet)
    _aplicar_formato_columnas(worksheet, money_columns={6}, date_columns={5})
    return _workbook_bytes(workbook)


def generar_excel_resumen_bingo(bingo, partidas, cartones):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Resumen de partidas"

    headers = [
        "ID de Bingo",
        "Título del Bingo",
        "ID de partida",
        "Ronda",
        "Estado de partida",
        "Fecha programada",
        "Hora de inicio",
        "Hora de finalización",
        "Total de cartones",
        "Recaudación total",
        "Cantidad de bolas extraídas",
        "Ganador",
        "Hubo desempate",
        "Balota mayor de desempate",
    ]
    worksheet.append(headers)

    cartones_por_partida = defaultdict(list)
    for carton in cartones:
        cartones_por_partida[getattr(carton, "idpartida_id", None)].append(carton)

    total_cartones = 0
    total_recaudado = Decimal("0.00")
    finalizadas = 0
    en_curso = 0
    con_desempate = 0

    for partida in partidas:
        cartones_partida = cartones_por_partida.get(partida.idpartidabingo, [])
        recaudacion = sum(
            (_decimal(carton.preciopagado) for carton in cartones_partida),
            Decimal("0.00"),
        )
        bolas = parsear_bolas_cantadas(partida.bolascantadas)
        estado = estado_partida_mostrar(partida.estadopartida)
        total_cartones += len(cartones_partida)
        total_recaudado += recaudacion
        finalizadas += 1 if estado == ESTADO_PARTIDA_FINALIZADA else 0
        en_curso += 1 if estado == "En curso" else 0
        con_desempate += 1 if partida.haydesempate else 0
        worksheet.append(
            [
                bingo.idbingo,
                bingo.titulobingo,
                partida.idpartidabingo,
                partida.nombreronda,
                estado,
                _fecha_para_excel(bingo.fechaprogramadabingo),
                _fecha_para_excel(partida.horainicio),
                _fecha_para_excel(partida.horafin),
                len(cartones_partida),
                float(recaudacion),
                len(bolas),
                _alias_ganador(partida) or "-",
                _si_no(partida.haydesempate),
                _formatear_bola(partida.bolamayordesempate) or "-",
            ]
        )

    resumen_row = worksheet.max_row + 2
    resumen = [
        ("Total de partidas", len(partidas)),
        ("Partidas finalizadas", finalizadas),
        ("Partidas en curso", en_curso),
        ("Total de cartones", total_cartones),
        ("Recaudación total", float(total_recaudado)),
        ("Total de partidas con desempate", con_desempate),
    ]
    for offset, (label, value) in enumerate(resumen):
        row = resumen_row + offset
        worksheet.cell(row=row, column=1, value=label)
        worksheet.cell(row=row, column=2, value=value)
    worksheet.cell(row=resumen_row + 4, column=2).number_format = MONEDA_FORMAT

    _aplicar_formato_basico_excel(worksheet)
    _aplicar_formato_columnas(
        worksheet,
        money_columns={10},
        date_columns={6, 7, 8},
    )
    return _workbook_bytes(workbook)


def _tabla_pdf(rows):
    table = Table([[str(label), str(value)] for label, value in rows], colWidths=[170, 340])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f8")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#172033")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9e0ea")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _aplicar_formato_basico_excel(worksheet):
    worksheet.freeze_panes = "A2"
    for cell in worksheet[1]:
        cell.font = Font(bold=True)


def _aplicar_formato_columnas(worksheet, money_columns=None, date_columns=None):
    money_columns = money_columns or set()
    date_columns = date_columns or set()
    for column_cells in worksheet.columns:
        column_letter = column_cells[0].column_letter
        max_length = max(
            len(str(cell.value)) if cell.value not in (None, "") else 0
            for cell in column_cells
        )
        worksheet.column_dimensions[column_letter].width = min(max(max_length + 2, 12), 42)
        for cell in column_cells[1:]:
            if cell.column in money_columns:
                cell.number_format = MONEDA_FORMAT
            if cell.column in date_columns:
                cell.number_format = FECHA_FORMAT


def _workbook_bytes(workbook):
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _carton_ganador(partida, cartones):
    id_ganador = getattr(partida, "idjugadorganador_id", None)
    if id_ganador is None and getattr(partida, "idjugadorganador", None):
        id_ganador = partida.idjugadorganador.pk
    if id_ganador is None:
        return None
    for carton in cartones:
        id_jugador = getattr(carton, "idjugador_id", None)
        if id_jugador is None and getattr(carton, "idjugador", None):
            id_jugador = carton.idjugador.pk
        if id_jugador == id_ganador:
            return carton
    return None


def _alias_ganador(partida):
    jugador = getattr(partida, "idjugadorganador", None)
    if jugador is None:
        return None
    return getattr(jugador, "aliasjugador", None) or str(jugador)


def _nombre_jugador(jugador):
    if jugador is None:
        return "Sin jugador"
    return getattr(jugador, "aliasjugador", None) or str(jugador)


def _formatear_bola(numero):
    if numero in (None, "", 0, "0"):
        return None
    try:
        return formatear_bola_bingo(int(numero))
    except (TypeError, ValueError):
        return str(numero)


def _premio_bingo(bingo):
    partes = []
    if bingo.premiomayor not in (None, ""):
        partes.append(_formatear_moneda(bingo.premiomayor))
    if bingo.descripcionpremiomayor:
        partes.append(str(bingo.descripcionpremiomayor))
    return " - ".join(partes) or "-"


def _formatear_fecha(value):
    if value in (None, ""):
        return "-"
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%d/%m/%Y %H:%M")


def _fecha_para_excel(value):
    if value in (None, ""):
        return None
    if timezone.is_aware(value):
        return timezone.localtime(value).replace(tzinfo=None)
    return value


def _formatear_moneda(value):
    return f"${_decimal(value):.2f}"


def _decimal(value):
    if value in (None, ""):
        return Decimal("0.00")
    return Decimal(str(value))


def _estado_normalizado(value):
    return str(value or "").strip().lower()


def _cantidad_estados(counter, estados):
    return sum(counter.get(estado, 0) for estado in estados)


def _si_no(value):
    return "Sí" if value else "No"
