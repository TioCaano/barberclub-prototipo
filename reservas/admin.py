from django.contrib import admin

from .models import Barbero, Cuenta, Notificacion, Pago, Reserva, Servicio, Sucursal

admin.site.register([Cuenta, Sucursal, Barbero, Servicio, Notificacion])


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "barbero", "fecha", "hora", "estado")
    list_filter = ("estado", "barbero__sucursal")


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("reserva", "monto", "estado", "creado")
