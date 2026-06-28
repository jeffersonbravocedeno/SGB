from django.contrib import admin

from .models import Bingo, Carton, Partidabingo, Sesionjuego


admin.site.register(Bingo)
admin.site.register(Partidabingo)
admin.site.register(Carton)
admin.site.register(Sesionjuego)
