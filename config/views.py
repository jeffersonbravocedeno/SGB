from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse

from apps.bingos.models import Bingo, Carton
from apps.common.decorators import admin_required
from apps.common.views import safe_count
from apps.finanzas.models import Aportesemanal, Prestamo
from apps.jugadores.models import Jugador
from apps.socios.models import Socio


@admin_required
def home(request):
    quick_links = [
        {
            "title": "Socios",
            "description": "Socios, cuentas bancarias y actividad financiera.",
            "url": reverse("socios:lista"),
            "code": "SO",
        },
        {
            "title": "Jugadores",
            "description": "Cuentas de jugadores vinculadas al sistema.",
            "url": reverse("jugadores:lista"),
            "code": "JU",
        },
        {
            "title": "Bingos",
            "description": "Bingos, partidas, cartones y sesiones.",
            "url": reverse("bingos:lista"),
            "code": "BI",
        },
        {
            "title": "Finanzas",
            "description": "Prestamos, pagos, ahorros y aportes.",
            "url": reverse("finanzas:dashboard"),
            "code": "FI",
        },
        {
            "title": "Configuracion",
            "description": "Catalogos, metodos de pago y plataformas.",
            "url": reverse("configuracion:dashboard"),
            "code": "CO",
        },
    ]
    summary_cards = [
        {"label": "Total de socios", "value": safe_count(Socio)},
        {"label": "Total de jugadores", "value": safe_count(Jugador)},
        {"label": "Total de bingos", "value": safe_count(Bingo)},
        {"label": "Total de préstamos", "value": safe_count(Prestamo)},
        {"label": "Total de cartones", "value": safe_count(Carton)},
        {"label": "Total de aportes semanales", "value": safe_count(Aportesemanal)},
    ]
    return render(
        request,
        "home.html",
        {
            "quick_links": quick_links,
            "summary_cards": summary_cards,
        },
    )


def health(request):
    return HttpResponse("SIAB OK", content_type="text/plain")
