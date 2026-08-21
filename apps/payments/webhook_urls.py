from django.urls import path

from .views import RazorpayWebhookView

urlpatterns = [
    path("", RazorpayWebhookView.as_view(), name="razorpay_webhook"),
]
