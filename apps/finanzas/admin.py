from django.contrib import admin

from .models import Ahorro, Aportesemanal, PagoPrestamo, Prestamo


admin.site.register(Prestamo)
admin.site.register(Ahorro)
admin.site.register(Aportesemanal)


@admin.register(PagoPrestamo)
class PagoPrestamoAdmin(admin.ModelAdmin):
    list_display = (
        "idpagoprestamo",
        "idprestamo",
        "montopagado",
        "fechapago",
        "estado",
        "idmetodopago",
    )
    search_fields = (
        "numeroreferencia",
        "observacion",
    )
    list_filter = (
        "estado",
        "fechapago",
        "idmetodopago",
    )
    readonly_fields = tuple(field.name for field in PagoPrestamo._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
