from django.contrib import admin

from .models import Category, Customer, Product, SkuSequence, Supplier


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "category",
        "unit",
        "purchase_price",
        "sale_price",
        "reorder_level",
        "sellable",
        "is_active",
    )
    list_filter = ("category", "unit", "sellable", "is_active")
    search_fields = ("sku", "name", "hsn_code")
    autocomplete_fields = ("category",)
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            form.base_fields["sku"].required = False
            form.base_fields["sku"].help_text = "Leave blank to auto-generate."
        return form

    def save_model(self, request, obj, form, change):
        if not (obj.sku or "").strip():
            from .services import next_sku

            obj.sku = next_sku()
        super().save_model(request, obj, form, change)


@admin.register(SkuSequence)
class SkuSequenceAdmin(admin.ModelAdmin):
    list_display = ("slug", "last_number")
    readonly_fields = ("slug", "last_number")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "gstin", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "phone", "gstin")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "created_at")
    search_fields = ("name", "phone")
    readonly_fields = ("created_at", "updated_at")
