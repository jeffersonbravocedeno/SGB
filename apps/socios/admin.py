from django.contrib import admin

from .models import Cuentabancaria, Socio


admin.site.register(Socio)
admin.site.register(Cuentabancaria)
