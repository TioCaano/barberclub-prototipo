"""Patrón SINGLETON — GestorReservas.

Única instancia que centraliza la validación de disponibilidad y el bloqueo
de bloques horarios para las 4 sucursales (RF-01, RF-02, RF-03, RF-04, RF-12).
"""
import threading
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from reservas.models import Pago, Reserva

DURACION_BLOQUE = timedelta(hours=1)
ANTELACION_CANCELACION = timedelta(hours=2)
PORCENTAJE_ANTICIPO = 0.30
EXPIRACION_PAGO = timedelta(minutes=15)


class ReservaError(Exception):
    """Error de regla de negocio en el agendamiento."""


class GestorReservas:
    _instancia = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instancia is None:
            with cls._lock:
                if cls._instancia is None:
                    cls._instancia = super().__new__(cls)
        return cls._instancia

    @classmethod
    def obtener_instancia(cls):
        return cls()

    # ---------- RF-01: disponibilidad ----------
    def bloques_del_dia(self, barbero, fecha):
        suc = barbero.sucursal
        actual = datetime.combine(fecha, suc.horario_apertura)
        fin = datetime.combine(fecha, suc.horario_cierre)
        bloques = []
        while actual + DURACION_BLOQUE <= fin:
            bloques.append(actual.time())
            actual += DURACION_BLOQUE
        return bloques

    def _expirar_pendientes(self, barbero, fecha):
        """Libera reservas cuyo pago quedó abandonado más de 15 minutos."""
        limite = timezone.now() - EXPIRACION_PAGO
        Reserva.objects.filter(barbero=barbero, fecha=fecha, estado=Reserva.Estado.PENDIENTE_PAGO,
                               creada__lt=limite).update(estado=Reserva.Estado.PAGO_RECHAZADO)

    def bloques_ocupados(self, barbero, fecha):
        # D1: un bloque en PENDIENTE_PAGO también está tomado mientras el cliente paga.
        self._expirar_pendientes(barbero, fecha)
        return set(
            Reserva.objects.filter(
                barbero=barbero, fecha=fecha, estado__in=Reserva.ESTADOS_QUE_BLOQUEAN
            ).values_list("hora", flat=True)
        )

    def bloques_disponibles(self, barbero, fecha):
        ocupados = self.bloques_ocupados(barbero, fecha)
        return [b for b in self.bloques_del_dia(barbero, fecha) if b not in ocupados]

    # ---------- RF-02 / RF-03: agendar con bloqueo ----------
    def crear_reserva(self, cliente, barbero, servicio, fecha, hora, tipo_corte_preferido=""):
        if hora not in self.bloques_del_dia(barbero, fecha):
            raise ReservaError("El bloque no corresponde al horario de la sucursal.")
        # D3: no se permiten reservas en fechas u horas que ya pasaron.
        if timezone.make_aware(datetime.combine(fecha, hora)) <= timezone.now():
            raise ReservaError("No se puede agendar una hora que ya pasó.")
        try:
            with transaction.atomic():
                # Bloqueo de la fila del barbero: serializa reservas simultáneas (RF-03).
                type(barbero).objects.select_for_update().get(pk=barbero.pk)
                if hora in self.bloques_ocupados(barbero, fecha):
                    raise ReservaError("El bloque ya fue reservado por otro cliente.")
                return Reserva.objects.create(
                    cliente=cliente,
                    barbero=barbero,
                    servicio=servicio,
                    fecha=fecha,
                    hora=hora,
                    tipo_corte_preferido=tipo_corte_preferido or "",
                )
        except IntegrityError:
            # Segunda barrera: restricción única en la base de datos.
            raise ReservaError("El bloque ya fue reservado por otro cliente.")

    def calcular_anticipo(self, reserva):
        return round(reserva.servicio.precio * PORCENTAJE_ANTICIPO)

    # ---------- RF-11: resultado del pago ----------
    def confirmar(self, reserva):
        reserva.estado = Reserva.Estado.CONFIRMADA
        reserva.save(update_fields=["estado"])

    def liberar(self, reserva):
        reserva.estado = Reserva.Estado.PAGO_RECHAZADO
        reserva.save(update_fields=["estado"])

    # ---------- RF-04 / RF-12: cancelación con reembolso ----------
    def cancelar(self, reserva, pasarela, ahora=None):
        ahora = ahora or timezone.now()
        if reserva.estado not in (Reserva.Estado.CONFIRMADA, Reserva.Estado.PENDIENTE_PAGO):
            raise ReservaError("La reserva no se puede cancelar en su estado actual.")
        # D2: "al menos 2 horas" incluye exactamente 2 h (>=, no >).
        if reserva.inicio - ahora < ANTELACION_CANCELACION:
            raise ReservaError("Solo se puede cancelar con al menos 2 horas de antelación.")
        reembolsable = True
        with transaction.atomic():
            reserva.estado = Reserva.Estado.CANCELADA
            reserva.save(update_fields=["estado"])
            pago = getattr(reserva, "pago", None)
            if reembolsable and pago and pago.estado == Pago.Estado.APROBADO:
                if pasarela.reembolsar(pago.token, pago.monto):
                    pago.estado = Pago.Estado.REEMBOLSADO
                    pago.save(update_fields=["estado"])
        return reserva
