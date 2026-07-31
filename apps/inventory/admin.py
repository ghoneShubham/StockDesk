from django.contrib import admin

from .models import Adjustment, StockMovement


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "product",
        "movement_type",
        "qty_delta",
        "reference_type",
        "reference_id",
        "created_by",
    )
    list_filter = ("movement_type", "reference_type")
    search_fields = ("product__sku", "product__name", "reason")
    autocomplete_fields = ("product",)
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)

    def has_change_permission(self, request, obj=None):
        # Stock movements are an immutable ledger — never editable, even by admins.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Adjustment)
class AdjustmentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "product", "qty_delta", "reason", "created_by")
    list_filter = ("reason",)
    search_fields = ("product__sku", "product__name", "notes")
    autocomplete_fields = ("product",)
    date_hierarchy = "created_at"
    readonly_fields = ("stock_movement", "created_by", "created_at")
