from django.contrib import admin

from .models import InvoiceSequence, Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("invoice_no", "customer", "sale_date", "total_amount", "amount_paid", "payment_status", "created_by")
    list_filter = ("payment_status", "sale_date")
    search_fields = ("invoice_no", "customer__name", "customer__phone")
    autocomplete_fields = ("customer",)
    date_hierarchy = "sale_date"
    readonly_fields = ("invoice_no", "created_by", "created_at", "pdf")
    inlines = [SaleItemInline]


@admin.register(InvoiceSequence)
class InvoiceSequenceAdmin(admin.ModelAdmin):
    list_display = ("financial_year", "last_number")
    readonly_fields = ("financial_year", "last_number")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
