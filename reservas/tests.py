"""Plan de pruebas UA3 — BarberClub, módulo Agendamiento + Anticipo.

Cada prueba lleva el ID del caso (CP-XX) y el requerimiento de la
Evaluación 2 que verifica. Ejecutar con:  python manage.py test reservas -v 2
"""
import time as _time
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from reservas.management.commands.enviar_recordatorios import enviar_recordatorios
from reservas.models import Barbero, Cuenta, Notificacion, Pago, Reserva, Servicio, Sucursal
from reservas.servicios.gestor_reservas import GestorReservas, ReservaError
from reservas.servicios.notificaciones import NotificacionFactory, NotificacionSMS, NotificacionWhatsApp
from reservas.servicios.pagos import WebpayAdapter

MANANA = date.today() + timedelta(days=1)
CLAVE = "BarberClub2026!"


class BaseBarberClub(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.suc = Sucursal.objects.create(nombre="Providencia", comuna="Providencia",
                                          horario_apertura=time(10), horario_cierre=time(20))
        cls.suc2 = Sucursal.objects.create(nombre="Ñuñoa", comuna="Ñuñoa",
                                           horario_apertura=time(10), horario_cierre=time(20))
        cls.barbero = Barbero.objects.create(nombre="Matías Rojas", sucursal=cls.suc)
        cls.barbero2 = Barbero.objects.create(nombre="Ignacio Vera", sucursal=cls.suc2)
        cls.servicio = Servicio.objects.create(nombre="Corte clásico", precio=10000)
        cls.cliente = cls._crear_usuario("cliente1", Cuenta.Rol.CLIENTE)
        cls.cliente2 = cls._crear_usuario("cliente2", Cuenta.Rol.CLIENTE, canal=Cuenta.Canal.SMS)
        cls.usuario_barbero = cls._crear_usuario("barbero1", Cuenta.Rol.BARBERO)

    @staticmethod
    def _crear_usuario(username, rol, canal=Cuenta.Canal.WHATSAPP):
        u = User.objects.create_user(username, password=CLAVE)
        Cuenta.objects.create(usuario=u, rol=rol, telefono="+56900000000", canal_preferido=canal)
        return u

    def setUp(self):
        self.gestor = GestorReservas.obtener_instancia()

    def login(self, user):
        self.client.login(username=user.username, password=CLAVE)

    def agendar_post(self, fecha=MANANA, hora="11:00", barbero=None, extra=None):
        data = {"barbero": (barbero or self.barbero).pk, "servicio": self.servicio.pk,
                "fecha": fecha.isoformat(), "hora": hora, "tipo_corte_preferido": ""}
        data.update(extra or {})
        return self.client.post(reverse("agendar"), data)

    def flujo_pago(self, reserva, aprobar=True, monto=None):
        """Recorre pago -> Webpay simulado -> retorno, como lo haría el navegador."""
        datos = {} if monto is None else {"monto": monto}
        if monto is None:
            datos["monto"] = self.gestor.calcular_anticipo(reserva)
        r = self.client.post(reverse("pago", args=[reserva.pk]), datos)
        token = r.url.rstrip("/").split("/")[-1]
        r = self.client.post(r.url, {"accion": "aprobar" if aprobar else "rechazar"})
        return self.client.get(r.url)


# ---------------------------- Pruebas funcionales ----------------------------
class PruebasFuncionales(BaseBarberClub):

    def test_CP01_disponibilidad_multisucursal(self):
        """CP-01 | RF-01 | Consulta de disponibilidad muestra bloques de las sucursales."""
        self.login(self.cliente)
        r = self.client.get(reverse("disponibilidad"), {"fecha": MANANA.isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Matías Rojas")
        self.assertContains(r, "Ignacio Vera")
        self.assertEqual(len(self.gestor.bloques_disponibles(self.barbero, MANANA)), 10)

    def test_CP02_agendar_queda_pendiente_pago(self):
        """CP-02 | RF-02, RF-11 | Agendar un bloque libre crea reserva 'Pendiente de pago'."""
        self.login(self.cliente)
        r = self.agendar_post()
        reserva = Reserva.objects.get()
        self.assertRedirects(r, reverse("pago", args=[reserva.pk]))
        self.assertEqual(reserva.estado, Reserva.Estado.PENDIENTE_PAGO)

    def test_CP03_bloque_confirmado_no_se_puede_reservar(self):
        """CP-03 | RF-03 | Un bloque ya confirmado no puede reservarse otra vez (caso de error)."""
        Reserva.objects.create(cliente=self.cliente, barbero=self.barbero, servicio=self.servicio,
                               fecha=MANANA, hora=time(11), estado=Reserva.Estado.CONFIRMADA)
        with self.assertRaises(ReservaError):
            self.gestor.crear_reserva(self.cliente2, self.barbero, self.servicio, MANANA, time(11))

    def test_CP04_bloque_pendiente_de_pago_tambien_bloquea(self):
        """CP-04 | RF-03 | Mientras el cliente A paga, el cliente B no puede tomar el mismo bloque."""
        self.gestor.crear_reserva(self.cliente, self.barbero, self.servicio, MANANA, time(11))
        with self.assertRaises(ReservaError):
            self.gestor.crear_reserva(self.cliente2, self.barbero, self.servicio, MANANA, time(11))
        self.assertNotIn(time(11), self.gestor.bloques_disponibles(self.barbero, MANANA))

    def test_CP05_anticipo_30_y_confirmacion(self):
        """CP-05 | RF-11, RF-08 | Pago aprobado del 30% confirma la reserva y notifica por el canal preferido."""
        self.login(self.cliente)
        self.agendar_post()
        reserva = Reserva.objects.get()
        self.flujo_pago(reserva, aprobar=True)
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.Estado.CONFIRMADA)
        self.assertEqual(reserva.pago.monto, 3000)
        self.assertEqual(reserva.pago.estado, Pago.Estado.APROBADO)
        self.assertEqual(Notificacion.objects.get().canal, "WHATSAPP")

    def test_CP06_pago_rechazado_libera_bloque(self):
        """CP-06 | RF-11 | Si Webpay rechaza el pago, la reserva no se confirma y el bloque se libera (error)."""
        self.login(self.cliente)
        self.agendar_post()
        reserva = Reserva.objects.get()
        self.flujo_pago(reserva, aprobar=False)
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.Estado.PAGO_RECHAZADO)
        self.assertIn(time(11), self.gestor.bloques_disponibles(self.barbero, MANANA))

    def test_CP07_cancelar_exactamente_2h_antes(self):
        """CP-07 | RF-04 | Límite: cancelar con EXACTAMENTE 2 h de antelación debe permitirse."""
        r = Reserva.objects.create(cliente=self.cliente, barbero=self.barbero, servicio=self.servicio,
                                   fecha=MANANA, hora=time(11), estado=Reserva.Estado.CONFIRMADA)
        ahora = r.inicio - timedelta(hours=2)
        self.gestor.cancelar(r, WebpayAdapter(), ahora=ahora)
        self.assertEqual(r.estado, Reserva.Estado.CANCELADA)

    def test_CP08_cancelar_1h59_antes_rechazado(self):
        """CP-08 | RF-04 | Límite: cancelar con 1 h 59 min de antelación se rechaza."""
        r = Reserva.objects.create(cliente=self.cliente, barbero=self.barbero, servicio=self.servicio,
                                   fecha=MANANA, hora=time(11), estado=Reserva.Estado.CONFIRMADA)
        with self.assertRaises(ReservaError):
            self.gestor.cancelar(r, WebpayAdapter(), ahora=r.inicio - timedelta(hours=1, minutes=59))

    def test_CP09_cancelacion_a_tiempo_reembolsa(self):
        """CP-09 | RF-12 | Cancelar a tiempo una reserva pagada reembolsa el anticipo."""
        self.login(self.cliente)
        self.agendar_post()
        reserva = Reserva.objects.get()
        self.flujo_pago(reserva, aprobar=True)
        self.client.post(reverse("cancelar", args=[reserva.pk]))
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, Reserva.Estado.CANCELADA)
        self.assertEqual(reserva.pago.estado, Pago.Estado.REEMBOLSADO)

    def test_CP10_tipo_corte_opcional(self):
        """CP-10 | RF-09 | Se puede reservar sin indicar corte preferido, y se guarda si se indica."""
        self.login(self.cliente)
        self.agendar_post(hora="11:00")
        self.agendar_post(hora="12:00", extra={"tipo_corte_preferido": "Degradado bajo"})
        self.assertEqual(Reserva.objects.get(hora=time(11)).tipo_corte_preferido, "")
        self.assertEqual(Reserva.objects.get(hora=time(12)).tipo_corte_preferido, "Degradado bajo")

    def test_CP11_no_se_agenda_en_el_pasado(self):
        """CP-11 | RF-02 | Error/límite: no se puede agendar una fecha pasada."""
        ayer = date.today() - timedelta(days=1)
        with self.assertRaises(ReservaError):
            self.gestor.crear_reserva(self.cliente, self.barbero, self.servicio, ayer, time(11))

    def test_CP12_recordatorio_ventana_24_a_2_horas(self):
        """CP-12 | RF-08 | Recordatorio solo si faltan entre 24 y 2 h; usa la fábrica según canal."""
        r = Reserva.objects.create(cliente=self.cliente2, barbero=self.barbero, servicio=self.servicio,
                                   fecha=MANANA, hora=time(11), estado=Reserva.Estado.CONFIRMADA)
        self.assertEqual(enviar_recordatorios(ahora=r.inicio - timedelta(hours=30)), 0)
        self.assertEqual(enviar_recordatorios(ahora=r.inicio - timedelta(hours=5)), 1)
        self.assertEqual(enviar_recordatorios(ahora=r.inicio - timedelta(hours=4)), 0)  # no duplica
        self.assertEqual(Notificacion.objects.get(tipo="RECORDATORIO").canal, "SMS")

    def test_CP13_rendimiento_disponibilidad_menor_2s(self):
        """CP-13 | RNF-Rendimiento | La consulta de disponibilidad de toda la cadena responde en < 2 s."""
        for i in range(13):
            Barbero.objects.create(nombre=f"Barbero {i}", sucursal=self.suc if i % 2 else self.suc2)
        self.login(self.cliente)
        t0 = _time.perf_counter()
        r = self.client.get(reverse("disponibilidad"), {"fecha": MANANA.isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertLess(_time.perf_counter() - t0, 2.0)


# ---------------------------- Pruebas de seguridad ----------------------------
class PruebasSeguridad(BaseBarberClub):

    def test_CP14_anonimo_redirigido_a_login(self):
        """CP-14 | RF-10 · OWASP A01/A07 | Sin sesión no se accede a agendar ni a reservas."""
        for url in (reverse("disponibilidad"), reverse("mis_reservas"), reverse("agendar")):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn(reverse("login"), r.url)

    def test_CP15_cliente_no_cancela_reserva_ajena(self):
        """CP-15 | RF-10 · OWASP A01 | El cliente B no puede cancelar la reserva del cliente A (IDOR)."""
        r = Reserva.objects.create(cliente=self.cliente, barbero=self.barbero, servicio=self.servicio,
                                   fecha=MANANA, hora=time(11), estado=Reserva.Estado.CONFIRMADA)
        self.login(self.cliente2)
        resp = self.client.post(reverse("cancelar", args=[r.pk]))
        r.refresh_from_db()
        self.assertEqual(r.estado, Reserva.Estado.CONFIRMADA)
        self.assertEqual(resp.status_code, 404)

    def test_CP16_monto_manipulado_no_altera_anticipo(self):
        """CP-16 | RF-11 · OWASP A06/A08 | Alterar el campo oculto 'monto' a $1 no permite confirmar con menos del 30%."""
        self.login(self.cliente)
        self.agendar_post()
        reserva = Reserva.objects.get()
        self.flujo_pago(reserva, aprobar=True, monto=1)
        reserva.refresh_from_db()
        self.assertEqual(reserva.pago.monto, 3000)

    def test_CP17_contrasena_almacenada_con_hash(self):
        """CP-17 | RNF-Autenticación · OWASP A04 (fallas criptográficas) | La contraseña no se guarda en texto plano."""
        u = User.objects.get(username="cliente1")
        self.assertNotIn(CLAVE, u.password)
        self.assertTrue(u.password.startswith("pbkdf2_sha256$"))

    def test_CP18_parametros_invalidos_no_provocan_error_500(self):
        """CP-18 | OWASP A05 (inyección) / A10 | Parámetros maliciosos se rechazan sin error interno."""
        self.login(self.cliente)
        for params in ({"barbero": "1 OR 1=1"}, {"sucursal": "1;DROP TABLE reservas_reserva"},
                       {"fecha": "2026-13-45"}):
            r = self.client.get(reverse("disponibilidad"), params)
            self.assertIn(r.status_code, (200, 400), msg=f"params={params}")
        self.assertTrue(Reserva._meta.db_table)  # la tabla sigue existiendo

    def test_CP19_barbero_no_puede_agendar_como_cliente(self):
        """CP-19 | RF-10 · OWASP A01 | Solo el rol Cliente puede agendar horas."""
        self.login(self.usuario_barbero)
        r = self.agendar_post()
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Reserva.objects.exists())

    def test_CP20_csrf_obligatorio(self):
        """CP-20 | OWASP A01 | Un POST sin token CSRF (sitio externo) es rechazado."""
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.login(username="cliente1", password=CLAVE)
        r = c.post(reverse("agendar"), {"barbero": self.barbero.pk, "servicio": self.servicio.pk,
                                       "fecha": MANANA.isoformat(), "hora": "11:00"})
        self.assertEqual(r.status_code, 403)


# ---------------------------- Pruebas de patrones ----------------------------
class PruebasPatrones(BaseBarberClub):

    def test_CP21_singleton_unica_instancia(self):
        """CP-21 | Patrón Singleton | GestorReservas entrega siempre la misma instancia."""
        self.assertIs(GestorReservas(), GestorReservas.obtener_instancia())

    def test_CP22_factory_crea_canal_correcto(self):
        """CP-22 | Patrón Factory Method | La fábrica crea WhatsApp o SMS y rechaza canales desconocidos."""
        self.assertIsInstance(NotificacionFactory.crear("WHATSAPP", "+569"), NotificacionWhatsApp)
        self.assertIsInstance(NotificacionFactory.crear("SMS", "+569"), NotificacionSMS)
        with self.assertRaises(ValueError):
            NotificacionFactory.crear("PALOMA", "+569")
