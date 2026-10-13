# BarberClub — Prototipo UA3 (Grupo 3, TI3V43)

Prototipo ejecutable del módulo crítico **Agendamiento + bloqueo de horario + anticipo del 30%**
(RF-01, RF-02, RF-03, RF-04, RF-08, RF-09, RF-10, RF-11, RF-12 de la Evaluación 2).

## Cómo ejecutarlo
```bash
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py poblar_demo        # 4 sucursales, 15 barberos, usuarios de prueba
python manage.py runserver          # http://127.0.0.1:8000
```
Usuarios de prueba (contraseña `BarberClub2026!`): `cliente1`, `cliente2`, `barbero1`, `admin` (panel en /admin).

## Pruebas
```bash
python manage.py test reservas -v 2          # 22 casos (CP-01 a CP-22)
python manage.py enviar_recordatorios        # RF-08, pensado para ejecutarse cada hora
python manage.py check --deploy              # revisión de configuración de seguridad
```

## Patrones de diseño
| Patrón | Archivo | Clase |
|---|---|---|
| Singleton | `reservas/servicios/gestor_reservas.py` | `GestorReservas` |
| Adapter | `reservas/servicios/pagos.py` | `PasarelaPago`, `WebpayAdapter`, `SimuladorTransbankSDK` |
| Factory Method | `reservas/servicios/notificaciones.py` | `NotificacionFactory`, `NotificacionWhatsApp`, `NotificacionSMS` |

La pasarela Webpay está **simulada** (`SimuladorTransbankSDK`) con la misma forma de respuesta que el ambiente
de integración de Webpay Plus; para producción se reemplaza el SDK dentro de `WebpayAdapter`.
