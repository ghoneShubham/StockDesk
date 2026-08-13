from datetime import timedelta

from django import forms
from django.utils import timezone


class DateRangeForm(forms.Form):
    date_from = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    date_to = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def __init__(self, *args, default_days: int = 30, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["date_from"].initial = today - timedelta(days=default_days - 1)
        self.fields["date_to"].initial = today

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("Start date must be on or before end date.")
        return cleaned
