"""Registro de intentos de inicio de sesión fallidos (OWASP A09, ISO 27001 A.8.15)."""
import logging

from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

log = logging.getLogger("barberclub.seguridad")


@receiver(user_login_failed)
def registrar_login_fallido(sender, credentials, request=None, **kwargs):
    ip = request.META.get("REMOTE_ADDR") if request else "-"
    log.warning("Login fallido usuario=%s ip=%s", credentials.get("username"), ip)
