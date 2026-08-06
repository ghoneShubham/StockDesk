from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from apps.masters.models import Customer, Product

from .models import Sale, SaleItem


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ("customer", "sale_date", "discount", "tax", "payment_status")
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select"}),
            "sale_date": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "discount": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "id": "id_header_discount"}
            ),
            "tax": forms.NumberInput(
                attrs={"class": "form-control", "step": "0.01", "min": "0", "id": "id_tax"}
            ),
            "payment_status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.order_by("name")
        self.fields["customer"].required = False
        self.fields["customer"].empty_label = "Walk-in customer"
        self.fields["sale_date"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
        self.fields["sale_date"].initial = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        self.fields["discount"].initial = Decimal("0.00")
        self.fields["tax"].initial = Decimal("0.00")
        self.fields["payment_status"].initial = Sale.PaymentStatus.PAID
        self.fields["discount"].label = "Invoice discount"
        self.fields["tax"].label = "Tax"

    def clean_discount(self):
        value = self.cleaned_data.get("discount")
        if value is None:
            return Decimal("0.00")
        if value < 0:
            raise forms.ValidationError("Discount cannot be negative.")
        return value

    def clean_tax(self):
        value = self.cleaned_data.get("tax")
        if value is None:
            return Decimal("0.00")
        if value < 0:
            raise forms.ValidationError("Tax cannot be negative.")
        return value


class SaleItemForm(forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ("product", "qty", "rate", "discount")
        widgets = {
            "product": forms.Select(attrs={"class": "form-select sale-product"}),
            "qty": forms.NumberInput(
                attrs={"class": "form-control sale-qty", "step": "0.01", "min": "0.01"}
            ),
            "rate": forms.NumberInput(
                attrs={"class": "form-control sale-rate", "step": "0.01", "min": "0"}
            ),
            "discount": forms.NumberInput(
                attrs={"class": "form-control sale-discount", "step": "0.01", "min": "0"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = (
            Product.objects.filter(is_active=True, sellable=True)
            .select_related("category")
            .order_by("name")
        )
        self.fields["product"].required = False
        self.fields["qty"].required = False
        self.fields["rate"].required = False
        self.fields["discount"].required = False
        self.fields["discount"].initial = Decimal("0.00")

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        qty = cleaned.get("qty")
        rate = cleaned.get("rate")
        discount = cleaned.get("discount")

        if not product and qty in (None, "") and rate in (None, "") and discount in (None, "", Decimal("0")):
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

        if discount is None:
            cleaned["discount"] = Decimal("0.00")
            discount = cleaned["discount"]
        elif discount < 0:
            self.add_error("discount", "Discount cannot be negative.")

        if product and qty is not None and rate is not None and discount is not None and discount >= 0:
            line_gross = (qty * rate).quantize(Decimal("0.01"))
            if discount > line_gross:
                self.add_error("discount", "Discount cannot exceed the line amount.")

        if product and rate is None:
            cleaned["rate"] = product.sale_price
        return cleaned


class BaseSaleItemFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        lines = []
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or form.cleaned_data.get("DELETE"):
                continue
            product = form.cleaned_data.get("product")
            qty = form.cleaned_data.get("qty")
            rate = form.cleaned_data.get("rate")
            discount = form.cleaned_data.get("discount")
            if not product and qty is None and rate is None:
                continue
            if product:
                lines.append(
                    {
                        "product": product,
                        "qty": qty,
                        "rate": rate,
                        "discount": discount or Decimal("0.00"),
                    }
                )

        if not lines:
            raise forms.ValidationError("Add at least one sale line with product, qty, and rate.")

        self.cleaned_lines = lines


SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    form=SaleItemForm,
    formset=BaseSaleItemFormSet,
    extra=5,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


def lines_from_formset(formset) -> list[dict]:
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
        discount = form.cleaned_data.get("discount") or Decimal("0.00")
        if product and qty is not None and rate is not None:
            out.append({"product": product, "qty": qty, "rate": rate, "discount": discount})
    return out
