from django.conf import settings
from django.db.models import Sum

from .models import Cart

def store_settings(request):
    if request.user.is_authenticated:
        cart_count = Cart.objects.filter(user=request.user).aggregate(count=Sum("items__quantity"))["count"] or 0
    else:
        cart_count = 0
    return {
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "store_name": "AVON JEWELER",
        "cart_count": cart_count,
    }
