from django import template
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

register = template.Library()


@register.filter
def attr(obj, name):
    value = getattr(obj, name, "")
    return value() if callable(value) else value


@register.filter
def money2(value):
    try:
        number = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"${number:,.2f}"


@register.filter
def number2(value):
    try:
        number = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return f"{number:,.2f}"
