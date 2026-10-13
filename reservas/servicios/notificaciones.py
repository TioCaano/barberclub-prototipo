"""Patrón FACTORY METHOD — NotificacionFactory (RF-08).

Crea la notificación concreta (WhatsApp o SMS) según el canal preferido del
cliente. En el prototipo el envío se registra en la tabla Notificacion y en el
log (no se conecta a un proveedor real de mensajería).
"""
import logging
from abc import ABC, abstractmethod

from reservas.models import Notificacion as NotificacionRegistro

log = logging.getLogger("barberclub.notificaciones")


class Notificacion(ABC):
    canal = None

    def __init__(self, destinatario):
        self.destinatario = destinatario

    @abstractmethod
    def formatear(self, mensaje):
        ...

    def enviar(self, reserva, mensaje, tipo="CONFIRMACION"):
        texto = self.formatear(mensaje)
        log.info("[%s] -> %s: %s", self.canal, self.destinatario, texto)
        return NotificacionRegistro.objects.create(
            reserva=reserva, canal=self.canal, destinatario=self.destinatario, mensaje=texto, tipo=tipo
        )


class NotificacionWhatsApp(Notificacion):
    canal = "WHATSAPP"

    def formatear(self, mensaje):
        return f"💈 BarberClub: {mensaje}"


class NotificacionSMS(Notificacion):
    canal = "SMS"

    def formatear(self, mensaje):
        return f"BarberClub: {mensaje}"[:160]


class NotificacionFactory:
    _canales = {"WHATSAPP": NotificacionWhatsApp, "SMS": NotificacionSMS}

    @classmethod
    def crear(cls, canal, destinatario):
        try:
            return cls._canales[canal](destinatario)
        except KeyError:
            raise ValueError(f"Canal de notificación no soportado: {canal}")
