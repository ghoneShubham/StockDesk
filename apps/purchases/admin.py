from django.contrib import admin

from .models import Purchase, PurchaseItem, PurchaseSequence


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


@admin.register(PurchaseSequence)
class PurchaseSequenceAdmin(admin.ModelAdmin):
    list_display = ("financial_year", "last_number")
    readonly_fields = ("financial_year", "last_number")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
