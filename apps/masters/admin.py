from django.contrib import admin

from .models import Category, Customer, Product, Supplier


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
