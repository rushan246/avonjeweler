import razorpay
from django.conf import settings


class PaymentConfigurationError(Exception):
    pass


def razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise PaymentConfigurationError("Razorpay credentials are not configured. Add the test keys to your .env file.")
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
