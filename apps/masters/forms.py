import re
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db.models import Q

from .models import Category, Customer, Product, Supplier

ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Category name"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise ValidationError("Category name is required.")
        qs = Category.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A category with this name already exists.")
        return name


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ("name", "phone", "gstin", "address", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "10-digit phone"}),
            "gstin": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional GSTIN"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise ValidationError("Supplier name is required.")
        return name

    def clean_gstin(self):
        gstin = self.cleaned_data.get("gstin", "").strip().upper()
        if gstin and not GSTIN_RE.match(gstin):
            raise ValidationError("Enter a valid 15-character GSTIN, or leave blank.")
        return gstin


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ("name", "phone", "address")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Unique phone number"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise ValidationError("Customer name is required.")
        return name

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not phone:
            raise ValidationError("Phone is required.")
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 8:
            raise ValidationError("Enter a valid phone number.")
        qs = Customer.objects.filter(phone=phone)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A customer with this phone already exists.")
        return phone


class ProductForm(forms.ModelForm):
    image = forms.ImageField(
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "webp", "gif"])],
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp,image/gif"}
        ),
    )

    class Meta:
        model = Product
        fields = (
            "sku",
            "name",
            "category",
            "unit",
            "hsn_code",
            "purchase_price",
            "sale_price",
            "reorder_level",
            "image",
            "sellable",
            "is_active",
        )
        widgets = {
            "sku": forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "hsn_code": forms.TextInput(attrs={"class": "form-control"}),
            "purchase_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "sale_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "reorder_level": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "sellable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        category_qs = Category.objects.filter(is_active=True)
        if self.instance.pk and self.instance.category_id:
            category_qs = Category.objects.filter(Q(is_active=True) | Q(pk=self.instance.category_id))
        self.fields["category"].queryset = category_qs.order_by("name")

        can_view_purchase = bool(user and user.has_perm("masters.view_purchase_price"))
        can_change_sale = bool(user and user.has_perm("masters.change_sale_price"))

        if not can_view_purchase:
            self.fields.pop("purchase_price", None)

        # Manager may create products (set initial sale price) but cannot edit sale price later.
        if not can_change_sale and self.instance.pk:
            self.fields["sale_price"].disabled = True
            self.fields["sale_price"].help_text = "Only the Owner can change selling price."

        if not self.instance.pk:
            from .services import peek_next_sku

            preview = peek_next_sku()
            self.fields["sku"].required = False
            self.fields["sku"].help_text = f"Leave blank to auto-generate. Next: {preview}."
            self.fields["sku"].widget.attrs["placeholder"] = preview

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip().upper()
        if not sku:
            if self.instance.pk:
                raise ValidationError("SKU is required.")
            return ""
        qs = Product.objects.filter(sku__iexact=sku)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("A product with this SKU already exists.")
        return sku

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.sku:
            from .services import next_sku

            instance.sku = next_sku()
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise ValidationError("Product name is required.")
        return name

    def clean_purchase_price(self):
        price = self.cleaned_data["purchase_price"]
        if price is None or price < Decimal("0"):
            raise ValidationError("Purchase price cannot be negative.")
        return price

    def clean_sale_price(self):
        if self.fields.get("sale_price") and self.fields["sale_price"].disabled and self.instance.pk:
            return self.instance.sale_price
        price = self.cleaned_data.get("sale_price")
        if price is None or price < Decimal("0"):
            raise ValidationError("Sale price cannot be negative.")
        return price

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image
        content_type = getattr(image, "content_type", None)
        if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise ValidationError("Only JPEG, PNG, WebP, or GIF images are allowed.")
        if getattr(image, "size", 0) and image.size > 2 * 1024 * 1024:
            raise ValidationError("Image must be 2 MB or smaller.")
        return image
