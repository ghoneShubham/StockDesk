from decimal import Decimal

from django import forms

from apps.masters.models import Product

from .models import Adjustment


class AdjustmentForm(forms.ModelForm):
    class Meta:
        model = Adjustment
        fields = ("product", "qty_delta", "reason", "notes")
        widgets = {
            "product": forms.Select(attrs={"class": "form-select"}),
            "qty_delta": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "placeholder": "Use negative for damage/theft",
                }
            ),
            "reason": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "Optional notes"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = (
            Product.objects.filter(is_active=True).select_related("category").order_by("name")
        )
        self.fields["qty_delta"].help_text = (
            "Positive increases stock (opening / count up). Negative decreases (damage, theft, count down)."
        )
        self.fields["notes"].required = False

    def clean_qty_delta(self):
        value = self.cleaned_data.get("qty_delta")
        if value is None:
            raise forms.ValidationError("Enter a quantity change.")
        value = Decimal(str(value)).quantize(Decimal("0.01"))
        if value == 0:
            raise forms.ValidationError("Quantity change cannot be zero.")
        return value

    def clean_reason(self):
        reason = self.cleaned_data.get("reason")
        if not reason:
            raise forms.ValidationError("Reason is required.")
        return reason
