"""RF-08: envía recordatorios a reservas confirmadas que comienzan entre 2 y 24 horas más.
Pensado para ejecutarse cada hora (cron / tarea programada del proveedor cloud)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from reservas.models import Reserva
from reservas.servicios.notificaciones import NotificacionFactory


def enviar_recordatorios(ahora=None):
    ahora = ahora or timezone.now()
    enviados = 0
    candidatas = Reserva.objects.filter(estado=Reserva.Estado.CONFIRMADA).select_related("cliente__cuenta", "barbero")
    for r in candidatas:
        faltan = r.inicio - ahora
        if timedelta(hours=2) <= faltan <= timedelta(hours=24) and not r.notificaciones.filter(tipo="RECORDATORIO").exists():
            cuenta = r.cliente.cuenta
            NotificacionFactory.crear(cuenta.canal_preferido, cuenta.telefono).enviar(
                r, f"Recordatorio: tu hora con {r.barbero.nombre} es el {r.fecha:%d-%m} a las {r.hora:%H:%M}.",
                tipo="RECORDATORIO")
            enviados += 1
    return enviados


class Command(BaseCommand):
    help = "Envía recordatorios automáticos (RF-08)"

    def handle(self, *args, **opts):
        self.stdout.write(f"Recordatorios enviados: {enviar_recordatorios()}")
