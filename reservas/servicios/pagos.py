"""Patrón ADAPTER — PasarelaPago / WebpayAdapter (RF-11, RF-12).

El resto del sistema solo conoce la interfaz PasarelaPago. WebpayAdapter
traduce esas llamadas a la interfaz del SDK de Transbank (Transaction.create /
commit / refund). En el prototipo se usa SimuladorTransbankSDK, que replica
la forma de respuesta del ambiente de integración de Webpay Plus; para pasar
a producción solo se reemplaza el SDK dentro del adaptador.
"""
import secrets
from abc import ABC, abstractmethod


class PasarelaPago(ABC):
    @abstractmethod
    def iniciar_pago(self, orden, monto, url_retorno):
        """Retorna (token, url_formulario_pago)."""

    @abstractmethod
    def confirmar_pago(self, token):
        """Retorna (aprobado: bool, monto_autorizado: int)."""

    @abstractmethod
    def reembolsar(self, token, monto):
        """Retorna True si la pasarela aceptó el reembolso."""


class SimuladorTransbankSDK:
    """Imita el SDK de Webpay Plus (ambiente de integración). La tarjeta se
    'ingresa' en una página externa simulada: el sistema nunca la recibe."""

    _transacciones = {}

    def create(self, buy_order, session_id, amount, return_url):
        token = secrets.token_hex(16)
        self._transacciones[token] = {
            "buy_order": buy_order, "amount": amount, "status": "INITIALIZED", "return_url": return_url,
        }
        return {"token": token, "url": f"/webpay-simulado/{token}/"}

    def simular_resultado(self, token, aprobado):
        self._transacciones[token]["status"] = "AUTHORIZED" if aprobado else "FAILED"
        return self._transacciones[token]["return_url"]

    def commit(self, token):
        t = self._transacciones.get(token)
        if t is None:
            return {"status": "FAILED", "amount": 0}
        return {"status": t["status"], "amount": t["amount"], "buy_order": t["buy_order"]}

    def refund(self, token, amount):
        t = self._transacciones.get(token)
        if t and t["status"] == "AUTHORIZED":
            t["status"] = "REVERSED"
            return {"type": "REVERSED"}
        return {"type": "NULLIFIED_ERROR"}

    def transaccion(self, token):
        return self._transacciones.get(token)


class WebpayAdapter(PasarelaPago):
    def __init__(self, sdk=None):
        self.sdk = sdk or SimuladorTransbankSDK()

    def iniciar_pago(self, orden, monto, url_retorno):
        r = self.sdk.create(buy_order=str(orden), session_id=str(orden), amount=monto, return_url=url_retorno)
        return r["token"], r["url"]

    def confirmar_pago(self, token):
        r = self.sdk.commit(token)
        return r["status"] == "AUTHORIZED", r.get("amount", 0)

    def reembolsar(self, token, monto):
        return self.sdk.refund(token, monto)["type"] == "REVERSED"


def obtener_pasarela() -> PasarelaPago:
    return WebpayAdapter()
