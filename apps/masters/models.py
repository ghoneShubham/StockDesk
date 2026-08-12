from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


def product_image_upload_to(instance, filename):
    return f"products/{instance.sku}/{filename}"


class Category(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    class Unit(models.TextChoices):
        PIECE = "pc", "Piece"
        KG = "kg", "Kilogram"
        GRAM = "g", "Gram"
        LITRE = "l", "Litre"
        MILLILITRE = "ml", "Millilitre"
        BOX = "box", "Box"
        DOZEN = "dz", "Dozen"

    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    unit = models.CharField(max_length=8, choices=Unit.choices, default=Unit.PIECE)
    hsn_code = models.CharField(max_length=16, blank=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2)
    reorder_level = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to=product_image_upload_to, blank=True, null=True)
    sellable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(purchase_price__gte=Decimal("0")),
                name="product_purchase_price_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(sale_price__gte=Decimal("0")),
                name="product_sale_price_gte_0",
            ),
            models.CheckConstraint(
                condition=models.Q(reorder_level__gte=0),
                name="product_reorder_level_gte_0",
            ),
        ]
        indexes = [
            models.Index(fields=["is_active", "sellable"]),
            models.Index(fields=["is_active", "name"]),
            models.Index(fields=["sku"]),
        ]
        permissions = [
            ("view_purchase_price", "Can view product purchase price"),
            ("change_sale_price", "Can change product sale price"),
        ]

    def __str__(self):
        return f"{self.sku} — {self.name}"


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"]),
        ]

    def __str__(self):
        return self.name


class Customer(TimeStampedModel):
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"
