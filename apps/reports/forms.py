from datetime import timedelta

from django import forms
from django.utils import timezone

MONTH_CHOICES = [
    (1, "January"),
    (2, "February"),
    (3, "March"),
    (4, "April"),
    (5, "May"),
    (6, "June"),
    (7, "July"),
    (8, "August"),
    (9, "September"),
    (10, "October"),
    (11, "November"),
    (12, "December"),
]


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


class MonthForm(forms.Form):
    """Calendar month picker for the running-total report."""

    year = forms.IntegerField(
        min_value=2000,
        max_value=2100,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 2000, "max": 2100}),
    )
    month = forms.TypedChoiceField(
        coerce=int,
        choices=MONTH_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        self.fields["year"].initial = today.year
        self.fields["month"].initial = today.month
