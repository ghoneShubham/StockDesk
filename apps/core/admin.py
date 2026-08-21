from django.contrib import admin

from .models import AuditLog, EmailOutbox


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "model_name", "object_id")
    list_filter = ("action", "model_name")
    search_fields = ("object_id", "user__username")
    date_hierarchy = "created_at"
    readonly_fields = ("user", "action", "model_name", "object_id", "changes", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EmailOutbox)
class EmailOutboxAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "subject", "attempts", "created_at", "sent_at")
    list_filter = ("status",)
    search_fields = ("subject", "idempotency_key", "to_addresses")
    readonly_fields = (
        "to_addresses",
        "subject",
        "body_text",
        "body_html",
        "status",
        "attempts",
        "max_attempts",
        "last_error",
        "idempotency_key",
        "next_attempt_at",
        "sent_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
