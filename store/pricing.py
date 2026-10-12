from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import MetalRate, Product, StoreSettings

CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def product_price(product: Product):
    if product.price_type == Product.PriceType.FIXED:
        base = product.fixed_price
    else:
        rate = (
            MetalRate.objects.filter(metal__iexact=product.metal, purity__iexact=product.purity, effective_at__lte=timezone.now())
            .order_by("-effective_at")
            .first()
        )
        if rate is None:
            raise ValidationError(f"No current metal rate is configured for {product.metal} {product.purity}.")
        base = rate.price_per_gram * product.weight_g + product.making_charge
    discounted = money(base * (Decimal("1") - product.discount_percent / Decimal("100")))
    tax_rate = product.tax_rate if product.tax_rate is not None else StoreSettings.get_default().tax_rate
    tax = money(discounted * tax_rate / Decimal("100"))
    return {"base": money(base), "unit_price": discounted, "tax": tax, "tax_rate": tax_rate, "total": money(discounted + tax)}


def cart_totals(items, coupon=None):
    subtotal = Decimal("0.00")
    tax = Decimal("0.00")
    for item in items:
        pricing = product_price(item.product)
        subtotal += pricing["unit_price"] * item.quantity
        tax += pricing["tax"] * item.quantity
    subtotal, tax = money(subtotal), money(tax)
    discount = Decimal("0.00")
    if coupon:
        if not coupon.is_valid(subtotal):
            raise ValidationError("This coupon is expired, unavailable, or does not meet the minimum order.")
        discount = money(subtotal * coupon.discount_percent / Decimal("100") + coupon.discount_amount)
        discount = min(discount, subtotal)
    tax_after_coupon = money(tax * (subtotal - discount) / subtotal) if subtotal else Decimal("0.00")
    shipping = Decimal("0.00") if subtotal >= Decimal("5000.00") else Decimal("99.00")
    return {
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax_after_coupon,
        "shipping_fee": shipping,
        "total": money(subtotal - discount + tax_after_coupon + shipping),
    }
