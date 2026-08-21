from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path(
        "sales/<int:pk>/send-link/",
        views.SendPaymentLinkView.as_view(),
        name="send_payment_link",
    ),
    path("reconcile/", views.PaymentReconcileReportView.as_view(), name="reconcile"),
]
