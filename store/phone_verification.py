import base64
import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class PhoneVerificationError(Exception):
    pass


def _twilio_request(resource, data):
    if not all((settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_VERIFY_SERVICE_SID)):
        raise PhoneVerificationError("Phone verification is not configured yet. Please contact the store.")

    service_sid = quote(settings.TWILIO_VERIFY_SERVICE_SID, safe="")
    url = f"https://verify.twilio.com/v2/Services/{service_sid}/{resource}"
    credentials = f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()
    authorization = base64.b64encode(credentials).decode("ascii")
    request = Request(
        url,
        data=urlencode(data).encode("utf-8"),
        headers={"Authorization": f"Basic {authorization}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("Twilio Verify request failed with HTTP status %s.", exc.code)
        if resource == "VerificationCheck" and exc.code == 404:
            return {"status": "invalid"}
        raise PhoneVerificationError("Twilio could not complete phone verification. Check the SMS service configuration.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise PhoneVerificationError("Twilio could not be reached. Please try again shortly.") from exc


def send_verification(phone):
    result = _twilio_request("Verifications", {"To": phone, "Channel": "sms"})
    if result.get("status") != "pending":
        raise PhoneVerificationError("Twilio did not start phone verification. Please try again.")


def check_verification(phone, code):
    result = _twilio_request("VerificationCheck", {"To": phone, "Code": code})
    return result.get("status") == "approved"
