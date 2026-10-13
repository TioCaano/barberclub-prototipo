"""Modelos del dominio BarberClub (prototipo UA3).

Corresponden a las clases del diagrama de clases de la Evaluación 2:
Cuenta, Sucursal, Barbero, Servicio, Reserva, Pago y Notificacion.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class Cuenta(models.Model):
    """RF-10: cada usuario tiene una cuenta con rol. La contraseña la guarda
    django.contrib.auth como hash PBKDF2 (RNF-Autenticación)."""

    class Rol(models.TextChoices):
        CLIENTE = "CLIENTE", "Cliente"
        BARBERO = "BARBERO", "Barbero"
        ADMIN = "ADMIN", "Administrador"

    class Canal(models.TextChoices):
        WHATSAPP = "WHATSAPP", "WhatsApp"
        SMS = "SMS", "SMS"

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cuenta")
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.CLIENTE)
    telefono = models.CharField(max_length=15, blank=True)
    canal_preferido = models.CharField(max_length=10, choices=Canal.choices, default=Canal.WHATSAPP)

    def __str__(self):
        return f"{self.usuario.username} ({self.rol})"


class Sucursal(models.Model):
    nombre = models.CharField(max_length=60)
    comuna = models.CharField(max_length=60)
    horario_apertura = models.TimeField()
    horario_cierre = models.TimeField()

    class Meta:
        verbose_name_plural = "sucursales"

    def __str__(self):
        return self.nombre


class Barbero(models.Model):
    nombre = models.CharField(max_length=80)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT, related_name="barberos")
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.nombre} - {self.sucursal}"


class Servicio(models.Model):
    nombre = models.CharField(max_length=60)
    precio = models.PositiveIntegerField(help_text="Precio en CLP")

    def __str__(self):
        return f"{self.nombre} (${self.precio:,})".replace(",", ".")


class Reserva(models.Model):
    """Ciclo de vida según el diagrama de estados de la Evaluación 2."""

    class Estado(models.TextChoices):
        PENDIENTE_PAGO = "PENDIENTE_PAGO", "Pendiente de pago"
        CONFIRMADA = "CONFIRMADA", "Confirmada"
        CANCELADA = "CANCELADA", "Cancelada"
        PAGO_RECHAZADO = "PAGO_RECHAZADO", "Pago rechazado"
        COMPLETADA = "COMPLETADA", "Completada"
        NO_SHOW = "NO_SHOW", "No-show"

    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reservas")
    barbero = models.ForeignKey(Barbero, on_delete=models.PROTECT, related_name="reservas")
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT)
    fecha = models.DateField()
    hora = models.TimeField()
    tipo_corte_preferido = models.CharField(max_length=100, blank=True)  # RF-09 (opcional)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE_PAGO)
    creada = models.DateTimeField(auto_now_add=True)

    ESTADOS_QUE_BLOQUEAN = [Estado.PENDIENTE_PAGO, Estado.CONFIRMADA]

    class Meta:
        ordering = ["fecha", "hora"]
        constraints = [
            models.UniqueConstraint(
                fields=["barbero", "fecha", "hora"],
                condition=models.Q(estado__in=["PENDIENTE_PAGO", "CONFIRMADA"]),
                name="un_bloque_activo_por_barbero",
            )
        ]

    @property
    def inicio(self):
        return timezone.make_aware(datetime.combine(self.fecha, self.hora))

    def __str__(self):
        return f"Reserva #{self.pk} {self.barbero.nombre} {self.fecha} {self.hora:%H:%M} [{self.estado}]"


class Pago(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        REEMBOLSADO = "REEMBOLSADO", "Reembolsado"

    reserva = models.OneToOneField(Reserva, on_delete=models.CASCADE, related_name="pago")
    monto = models.PositiveIntegerField()
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    token = models.CharField(max_length=64, unique=True)
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Pago {self.token[:8]} ${self.monto} [{self.estado}]"


class Notificacion(models.Model):
    """Registro de cada notificación enviada (evidencia de RF-08)."""

    reserva = models.ForeignKey(Reserva, on_delete=models.CASCADE, related_name="notificaciones")
    canal = models.CharField(max_length=10)
    destinatario = models.CharField(max_length=30)
    mensaje = models.TextField()
    tipo = models.CharField(max_length=20, default="CONFIRMACION")
    enviada_en = models.DateTimeField(auto_now_add=True)
