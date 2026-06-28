from django.contrib import admin

from .models import Metodopago, Plataformajuego, Regalo, Tiposocio


admin.site.register(Tiposocio)
admin.site.register(Metodopago)
admin.site.register(Plataformajuego)
admin.site.register(Regalo)
