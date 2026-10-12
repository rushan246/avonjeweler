from django import template
from django.core.exceptions import ValidationError

from store.pricing import product_price

register = template.Library()


@register.simple_tag
def price_for(product):
    try:
        return product_price(product)
    except ValidationError:
        return None


@register.filter
def inr(value):
    return f"₹{value:,.2f}"
