from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from reservas import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.disponibilidad, name="disponibilidad"),
    path("agendar/", views.agendar, name="agendar"),
    path("pago/<int:reserva_id>/", views.pago, name="pago"),
    path("pago/retorno/", views.retorno_pago, name="retorno_pago"),
    path("webpay-simulado/<str:token>/", views.webpay_simulado, name="webpay_simulado"),
    path("mis-reservas/", views.mis_reservas, name="mis_reservas"),
    path("reservas/<int:reserva_id>/cancelar/", views.cancelar, name="cancelar"),
]
