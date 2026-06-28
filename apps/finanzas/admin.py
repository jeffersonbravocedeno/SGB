from django.contrib import admin

from .models import Ahorro, Aportesemanal, Pago, Prestamo


admin.site.register(Prestamo)
admin.site.register(Pago)
admin.site.register(Ahorro)
admin.site.register(Aportesemanal)
