from django.contrib import admin

from .models import Barbero, Cuenta, Notificacion, Pago, Reserva, Servicio, Sucursal

admin.site.register([Cuenta, Sucursal, Barbero, Servicio])


@admin.register(Notificacion)
class NotificacionAdmin(admin.ModelAdmin):
    list_display = ("reserva", "tipo", "canal", "destinatario", "mensaje", "enviada_en")


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "barbero", "fecha", "hora", "tipo_corte_preferido", "estado")
    list_filter = ("estado", "barbero__sucursal")


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("reserva", "monto", "estado", "creado")
