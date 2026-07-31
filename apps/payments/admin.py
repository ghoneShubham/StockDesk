from django.contrib import admin

from .models import PaymentEvent, PaymentLink


@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = ("razorpay_payment_link_id", "sale", "amount", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("razorpay_payment_link_id", "sale__invoice_no")
    autocomplete_fields = ("sale",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("razorpay_event_id", "event_type", "sale", "amount", "processed_at", "created_at")
    list_filter = ("event_type",)
    search_fields = ("razorpay_event_id", "sale__invoice_no")
    readonly_fields = ("razorpay_event_id", "event_type", "payload", "processed_at", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
