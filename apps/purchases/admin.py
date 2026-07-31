from django.contrib import admin

from .models import Purchase, PurchaseItem


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("id", "supplier", "supplier_invoice_no", "purchase_date", "total_amount", "created_by")
    list_filter = ("purchase_date",)
    search_fields = ("supplier__name", "supplier_invoice_no")
    autocomplete_fields = ("supplier",)
    date_hierarchy = "purchase_date"
    readonly_fields = ("created_by", "created_at")
    inlines = [PurchaseItemInline]
