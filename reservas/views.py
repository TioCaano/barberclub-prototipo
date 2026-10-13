from datetime import date, datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Barbero, Pago, Reserva, Servicio, Sucursal
from .servicios.gestor_reservas import GestorReservas, ReservaError
from .servicios.notificaciones import NotificacionFactory
from .servicios.pagos import obtener_pasarela

gestor = GestorReservas.obtener_instancia()


def _entero_opcional(valor):
    if valor in (None, ""):
        return None
    if not valor.isdigit():
        raise ValueError(valor)
    return int(valor)


@login_required
def disponibilidad(request):
    """RF-01: consulta de disponibilidad en las 4 sucursales (paso 2 de 4)."""
    sucursales = Sucursal.objects.all()
    # D6 (OWASP A05/A10): toda entrada se valida; un valor inválido responde 400, nunca error 500.
    try:
        fecha_obj = date.fromisoformat(request.GET.get("fecha") or date.today().isoformat())
        id_sucursal = _entero_opcional(request.GET.get("sucursal"))
        id_barbero = _entero_opcional(request.GET.get("barbero"))
    except ValueError:
        return HttpResponseBadRequest("Parámetros de búsqueda inválidos.")
    fecha = fecha_obj.isoformat()
    barberos = Barbero.objects.select_related("sucursal")
    if id_sucursal:
        barberos = barberos.filter(sucursal_id=id_sucursal)
    if id_barbero:
        barberos = barberos.filter(pk=id_barbero)
    resultados = [(b, gestor.bloques_disponibles(b, fecha_obj)) for b in barberos]
    return render(request, "reservas/disponibilidad.html", {
        "sucursales": sucursales, "todos_barberos": Barbero.objects.all(), "resultados": resultados,
        "fecha": fecha, "filtro_sucursal": request.GET.get("sucursal", ""),
        "filtro_barbero": request.GET.get("barbero", ""),
    })


@login_required
def agendar(request):
    """RF-02, RF-03, RF-09: confirmar bloque y servicio (paso 3 de 4)."""
    if request.method == "GET":
        try:
            barbero = get_object_or_404(Barbero, pk=_entero_opcional(request.GET.get("barbero")))
        except ValueError:
            return HttpResponseBadRequest("Barbero inválido.")
        return render(request, "reservas/agendar.html", {
            "barbero": barbero, "fecha": request.GET.get("fecha"), "hora": request.GET.get("hora"),
            "servicios": Servicio.objects.all(),
        })
    try:
        barbero = get_object_or_404(Barbero, pk=_entero_opcional(request.POST.get("barbero")))
        servicio = get_object_or_404(Servicio, pk=_entero_opcional(request.POST.get("servicio")))
        fecha = date.fromisoformat(request.POST.get("fecha", ""))
        hora = datetime.strptime(request.POST.get("hora", ""), "%H:%M").time()
    except ValueError:
        return HttpResponseBadRequest("Datos de reserva inválidos.")
    try:
        reserva = gestor.crear_reserva(
            request.user, barbero, servicio, fecha, hora, request.POST.get("tipo_corte_preferido", "").strip()
        )
    except ReservaError as e:
        messages.error(request, str(e))
        return redirect(f"{reverse('disponibilidad')}?fecha={fecha.isoformat()}")
    return redirect("pago", reserva_id=reserva.pk)


@login_required
def pago(request, reserva_id):
    """RF-11: cobro del anticipo del 30% (paso 4 de 4)."""
    reserva = get_object_or_404(Reserva, pk=reserva_id, cliente=request.user)
    anticipo = gestor.calcular_anticipo(reserva)
    if request.method == "POST":
        if reserva.estado != Reserva.Estado.PENDIENTE_PAGO:
            return HttpResponseBadRequest("La reserva no está pendiente de pago.")
        # D5 (OWASP A04/A08): el monto se calcula en el servidor; se ignora lo que envíe el navegador.
        monto = anticipo
        pasarela = obtener_pasarela()
        token, url = pasarela.iniciar_pago(reserva.pk, monto, request.build_absolute_uri(reverse("retorno_pago")))
        Pago.objects.update_or_create(reserva=reserva, defaults={"monto": monto, "token": token,
                                                                  "estado": Pago.Estado.PENDIENTE})
        return redirect(url)
    return render(request, "reservas/pago.html", {"reserva": reserva, "anticipo": anticipo})


def webpay_simulado(request, token):
    """Página que simula el formulario externo de Webpay (fuera del sistema)."""
    sdk = obtener_pasarela().sdk
    trx = sdk.transaccion(token)
    if trx is None:
        return HttpResponseBadRequest("Transacción inexistente")
    if request.method == "POST":
        url = sdk.simular_resultado(token, request.POST.get("accion") == "aprobar")
        return redirect(f"{url}?token_ws={token}")
    return render(request, "reservas/webpay_simulado.html", {"token": token, "trx": trx})


@login_required
def retorno_pago(request):
    token = request.GET.get("token_ws", "")
    pago_obj = get_object_or_404(Pago, token=token, reserva__cliente=request.user)
    reserva = pago_obj.reserva
    aprobado, monto = obtener_pasarela().confirmar_pago(token)
    # D5: además se verifica que la pasarela haya autorizado exactamente el anticipo esperado.
    if aprobado and monto != gestor.calcular_anticipo(reserva):
        aprobado = False
    if aprobado:
        pago_obj.estado = Pago.Estado.APROBADO
        pago_obj.save(update_fields=["estado"])
        gestor.confirmar(reserva)
        cuenta = request.user.cuenta
        NotificacionFactory.crear(cuenta.canal_preferido, cuenta.telefono).enviar(
            reserva, f"Tu hora con {reserva.barbero.nombre} el {reserva.fecha:%d-%m} a las "
                     f"{reserva.hora:%H:%M} quedó CONFIRMADA. Anticipo pagado: ${pago_obj.monto}.")
        messages.success(request, "¡Pago aprobado! Tu reserva quedó confirmada.")
    else:
        pago_obj.estado = Pago.Estado.RECHAZADO
        pago_obj.save(update_fields=["estado"])
        gestor.liberar(reserva)
        messages.error(request, "El pago fue rechazado. El bloque se liberó; puedes intentarlo nuevamente.")
    return redirect("mis_reservas")


@login_required
def mis_reservas(request):
    reservas = Reserva.objects.filter(cliente=request.user).select_related("barbero__sucursal", "servicio")
    return render(request, "reservas/mis_reservas.html", {"reservas": reservas})


@login_required
@require_POST
def cancelar(request, reserva_id):
    """RF-04 y RF-12: cancelar con 2 h de antelación y reembolso automático."""
    # D4 (OWASP A01): solo el dueño de la reserva puede cancelarla; si no, 404.
    reserva = get_object_or_404(Reserva, pk=reserva_id, cliente=request.user)
    try:
        gestor.cancelar(reserva, obtener_pasarela())
        messages.success(request, "Reserva cancelada. Si pagaste anticipo, fue reembolsado.")
    except ReservaError as e:
        messages.error(request, str(e))
    return redirect("mis_reservas")
