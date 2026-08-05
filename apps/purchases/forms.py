from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from apps.masters.models import Product, Supplier

from .models import Purchase, PurchaseItem


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ("supplier", "supplier_invoice_no", "purchase_date")
        widgets = {
            "supplier": forms.Select(attrs={"class": "form-select"}),
            "supplier_invoice_no": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Supplier invoice / bill no."}
            ),
            "purchase_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True).order_by("name")
        self.fields["purchase_date"].initial = timezone.localdate()


class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ("product", "qty", "rate")
        widgets = {
            "product": forms.Select(attrs={"class": "form-select purchase-product"}),
            "qty": forms.NumberInput(
                attrs={"class": "form-control purchase-qty", "step": "0.01", "min": "0.01"}
            ),
            "rate": forms.NumberInput(
                attrs={"class": "form-control purchase-rate", "step": "0.01", "min": "0"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = (
            Product.objects.filter(is_active=True).select_related("category").order_by("name")
        )
        self.fields["product"].required = False
        self.fields["qty"].required = False
        self.fields["rate"].required = False

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        qty = cleaned.get("qty")
        rate = cleaned.get("rate")

        # Empty row (all blank) is allowed — formset will drop it.
        if not product and qty in (None, "") and rate in (None, ""):
            return cleaned

        if not product:
            self.add_error("product", "Select a product.")
        if qty is None:
            self.add_error("qty", "Enter quantity.")
        elif qty <= 0:
            self.add_error("qty", "Quantity must be greater than zero.")
        if rate is None:
            self.add_error("rate", "Enter rate.")
        elif rate < 0:
            self.add_error("rate", "Rate cannot be negative.")

        if product and rate is None:
            cleaned["rate"] = product.purchase_price
        return cleaned


class BasePurchaseItemFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        lines = []
        seen_products = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            qty = form.cleaned_data.get("qty")
            rate = form.cleaned_data.get("rate")
            if not product and qty is None and rate is None:
                continue
            if product and product.pk in seen_products:
                form.add_error("product", "This product is already on another line.")
                continue
            if product:
                seen_products.add(product.pk)
                lines.append({"product": product, "qty": qty, "rate": rate})

        if not lines:
            raise forms.ValidationError("Add at least one purchase line with product, qty, and rate.")

        self.cleaned_lines = lines


PurchaseItemFormSet = inlineformset_factory(
    Purchase,
    PurchaseItem,
    form=PurchaseItemForm,
    formset=BasePurchaseItemFormSet,
    extra=4,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


def lines_from_formset(formset) -> list[dict]:
    """Normalize validated formset rows for the purchase service."""
    lines = getattr(formset, "cleaned_lines", None)
    if lines is not None:
        return lines

    out = []
    for form in formset.forms:
        if not form.cleaned_data or form.cleaned_data.get("DELETE"):
            continue
        product = form.cleaned_data.get("product")
        qty = form.cleaned_data.get("qty")
        rate = form.cleaned_data.get("rate")
        if product and qty is not None and rate is not None:
            out.append({"product": product, "qty": qty, "rate": rate})
    return out
