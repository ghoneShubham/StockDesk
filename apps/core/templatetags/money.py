"""Indian-style comma formatting for money display (e.g. 2,88,48,772.13)."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def format_inr(value) -> str:
    if value is None or value == "":
        return "0.00"
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)

    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    whole_str, frac = f"{amount:.2f}".split(".")

    if len(whole_str) <= 3:
        return f"{sign}{whole_str}.{frac}"

    last3 = whole_str[-3:]
    rest = whole_str[:-3]
    groups = []
    while rest:
        groups.append(rest[-2:])
        rest = rest[:-2]
    groups.reverse()
    return f"{sign}{','.join(groups)},{last3}.{frac}"


@register.filter(name="inr")
def inr(value):
    """Format a number with Indian grouping + 2 decimal places."""
    return format_inr(value)
