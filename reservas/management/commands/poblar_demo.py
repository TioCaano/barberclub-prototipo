"""Carga datos de demostración: 4 sucursales, barberos, servicios y usuarios."""
from datetime import time

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from reservas.models import Barbero, Cuenta, Servicio, Sucursal

SUCURSALES = [("BarberClub Providencia", "Providencia"), ("BarberClub Ñuñoa", "Ñuñoa"),
              ("BarberClub Santiago Centro", "Santiago"), ("BarberClub Las Condes", "Las Condes")]
BARBEROS = [["Matías Rojas", "Felipe Soto", "Javier Muñoz", "Tomás Díaz"],
            ["Ignacio Vera", "Diego Fuentes", "Benjamín Castro", "Nicolás Reyes"],
            ["Sebastián Mora", "Vicente Lagos", "Cristóbal Pino", "Álvaro Núñez"],
            ["Martín Silva", "Lucas Ortega", "Joaquín Torres"]]


class Command(BaseCommand):
    help = "Pobla la base con datos de demostración"

    def handle(self, *args, **opts):
        for i, (nombre, comuna) in enumerate(SUCURSALES):
            s, _ = Sucursal.objects.get_or_create(nombre=nombre, defaults={
                "comuna": comuna, "horario_apertura": time(10), "horario_cierre": time(20)})
            for b in BARBEROS[i]:
                Barbero.objects.get_or_create(nombre=b, sucursal=s)
        for n, p in [("Corte clásico", 10000), ("Corte + barba", 15000), ("Perfilado de barba", 7000), ("Coloración", 25000)]:
            Servicio.objects.get_or_create(nombre=n, defaults={"precio": p})
        usuarios = [("cliente1", Cuenta.Rol.CLIENTE, "+56911111111"), ("cliente2", Cuenta.Rol.CLIENTE, "+56922222222"),
                    ("barbero1", Cuenta.Rol.BARBERO, "+56933333333"), ("admin", Cuenta.Rol.ADMIN, "+56944444444")]
        for username, rol, tel in usuarios:
            if not User.objects.filter(username=username).exists():
                u = User.objects.create_user(username, password="BarberClub2026!", is_staff=(rol == Cuenta.Rol.ADMIN),
                                             is_superuser=(rol == Cuenta.Rol.ADMIN))
                Cuenta.objects.create(usuario=u, rol=rol, telefono=tel)
        b1 = Barbero.objects.get(nombre="Matías Rojas")
        b1.usuario = User.objects.get(username="barbero1"); b1.save()
        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados (15 barberos, 4 sucursales)."))
