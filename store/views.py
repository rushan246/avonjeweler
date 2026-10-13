import hashlib
import hmac
import json
import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import AddressForm, CustomerProfileForm, RegistrationForm
from .models import Address, Cart, CartItem, Category, Coupon, CustomerProfile, Order, OrderItem, Payment, Product, ShippingInformation, Wishlist
from .payment_gateway import PaymentConfigurationError, razorpay_client
from .phone_verification import PhoneVerificationError, check_verification, send_verification
from .pricing import cart_totals, money, product_price

logger = logging.getLogger(__name__)


def home(request):
    products = Product.objects.filter(is_active=True, inventory__gt=0).select_related("category").prefetch_related("images")
    query = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "")
    metal = request.GET.get("metal", "")
    sort = request.GET.get("sort", "")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(sku__icontains=query))
    if category_slug:
        products = products.filter(category__slug=category_slug)
    if metal:
        products = products.filter(metal__iexact=metal)
    if sort in {"price-low", "price-high"}:
        def sort_key(product):
            try:
                return product_price(product)["total"]
            except ValidationError:
                return Decimal("0.00")

        products = sorted(products, key=sort_key, reverse=(sort == "price-high"))
    context = {
        "products": products,
        "categories": Category.objects.filter(is_active=True),
        "query": query,
        "selected_category": category_slug,
        "selected_metal": metal,
        "metals": Product.objects.filter(is_active=True).values_list("metal", flat=True).distinct(),
        "sort": sort,
    }
    return render(request, "store/home.html", context)


def product_detail(request, slug):
    product = get_object_or_404(Product.objects.filter(is_active=True).select_related("category").prefetch_related("images"), slug=slug)
    try:
        price = product_price(product)
    except ValidationError as exc:
        price = None
        pricing_error = exc.messages[0]
    else:
        pricing_error = ""
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"{reverse('login')}?next={request.path}")
        try:
            quantity = int(request.POST.get("quantity", "1"))
        except ValueError:
            quantity = 0
        if quantity < 1 or quantity > 20:
            messages.error(request, "Choose a quantity between 1 and 20.")
        elif quantity > product.inventory:
            messages.error(request, "There isn't enough stock available for that quantity.")
        else:
            cart, _ = Cart.objects.get_or_create(user=request.user)
            item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": quantity})
            if not created:
                if item.quantity + quantity > product.inventory:
                    messages.error(request, "That quantity exceeds the available stock.")
                    return redirect("product_detail", slug=slug)
                item.quantity += quantity
                item.save(update_fields=["quantity"])
            messages.success(request, f"{product.name} was added to your bag.")
            return redirect("cart")
        return redirect("product_detail", slug=slug)
    is_wishlisted = request.user.is_authenticated and Wishlist.objects.filter(user=request.user, products=product).exists()
    return render(request, "store/product_detail.html", {"product": product, "price": price, "pricing_error": pricing_error, "is_wishlisted": is_wishlisted})


class StoreLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = AuthenticationForm
    redirect_authenticated_user = True


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome to AVON JEWELER. Your account is ready.")
        return redirect("home")
    return render(request, "registration/register.html", {"form": form})


@login_required
def cart(request):
    cart_obj, _ = Cart.objects.get_or_create(user=request.user)
    items = list(cart_obj.items.select_related("product").prefetch_related("product__images"))
    try:
        totals = cart_totals(items)
        price_errors = {}
    except ValidationError as exc:
        totals = None
        price_errors = {"cart": exc.messages[0]}
    for item in items:
        try:
            item.pricing = product_price(item.product)
            item.line_total = money(item.pricing["total"] * item.quantity)
        except ValidationError as exc:
            item.pricing = None
            item.line_total = None
            price_errors[item.pk] = exc.messages[0]
    return render(request, "store/cart.html", {"items": items, "totals": totals, "price_errors": price_errors})


@login_required
@require_POST
def update_cart_item(request, item_id):
    item = get_object_or_404(CartItem.objects.select_related("product"), pk=item_id, cart__user=request.user)
    try:
        quantity = int(request.POST.get("quantity", "0"))
    except ValueError:
        quantity = 0
    if quantity == 0:
        item.delete()
        messages.info(request, "Item removed from your bag.")
    elif 1 <= quantity <= min(20, item.product.inventory):
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        messages.success(request, "Your bag has been updated.")
    else:
        messages.error(request, "Choose a quantity within the available stock.")
    return redirect("cart")


@login_required
@require_POST
def toggle_wishlist(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    if wishlist.products.filter(pk=product.pk).exists():
        wishlist.products.remove(product)
        messages.info(request, "Removed from your wishlist.")
    else:
        wishlist.products.add(product)
        messages.success(request, "Saved to your wishlist.")
    if request.POST.get("next") == "detail":
        return redirect("product_detail", slug=product.slug)
    return redirect("home")


@login_required
def wishlist(request):
    wishlist_obj, _ = Wishlist.objects.get_or_create(user=request.user)
    products = wishlist_obj.products.filter(is_active=True).select_related("category").prefetch_related("images")
    return render(request, "store/wishlist.html", {"products": products})


@login_required
def checkout(request):
    cart_obj, _ = Cart.objects.get_or_create(user=request.user)
    items = list(cart_obj.items.select_related("product"))
    if not items:
        messages.info(request, "Your bag is empty.")
        return redirect("cart")
    addresses = Address.objects.filter(user=request.user)
    address_form = AddressForm()
    if request.method == "POST" and "save_address" in request.POST:
        address_form = AddressForm(request.POST)
        if address_form.is_valid():
            address = address_form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "Delivery address saved.")
            return redirect("checkout")
    coupon = None
    coupon_code = request.session.get("coupon_code", "")
    if coupon_code:
        coupon = Coupon.objects.filter(code__iexact=coupon_code).first()
    try:
        totals = cart_totals(items, coupon)
        price_error = ""
    except ValidationError as exc:
        totals = None
        price_error = exc.messages[0]
    if request.method == "POST" and "apply_coupon" in request.POST:
        code = request.POST.get("coupon_code", "").strip().upper()
        try:
            candidate = Coupon.objects.get(code__iexact=code)
            cart_totals(items, candidate)
        except (Coupon.DoesNotExist, ValidationError) as exc:
            messages.error(request, exc.messages[0] if isinstance(exc, ValidationError) else "That coupon code is not valid.")
        else:
            request.session["coupon_code"] = candidate.code
            messages.success(request, "Your discount has been applied.")
        return redirect("checkout")
    if request.method == "POST" and "remove_coupon" in request.POST:
        request.session.pop("coupon_code", None)
        return redirect("checkout")
    if request.method == "POST" and "place_order" in request.POST:
        profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
        if not profile.phone_verified:
            messages.error(request, "Verify your phone number in your account before placing an order.")
            return redirect("profile")
        address = Address.objects.filter(user=request.user, pk=request.POST.get("address_id")).first()
        payment_method = request.POST.get("payment_method", "razorpay")
        if not address:
            messages.error(request, "Select a valid delivery address.")
        elif payment_method not in ("razorpay", "cod"):
            messages.error(request, "Select a valid payment method.")
        elif price_error:
            messages.error(request, price_error)
        elif payment_method == "razorpay" and not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
            messages.error(request, "Razorpay is not configured. Choose cash on delivery or contact the store.")
        else:
            try:
                with transaction.atomic():
                    locked_items = list(CartItem.objects.select_for_update().filter(cart=cart_obj).select_related("product"))
                    if not locked_items:
                        raise ValidationError("Your bag is empty.")
                    if coupon:
                        coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
                    for line in locked_items:
                        product = Product.objects.select_for_update().get(pk=line.product_id)
                        if not product.is_active or product.inventory < line.quantity:
                            raise ValidationError(f"{product.name} no longer has enough stock.")
                        line.product = product
                    totals = cart_totals(locked_items, coupon)
                    for line in locked_items:
                        product = line.product
                        if product.price_type == Product.PriceType.WEIGHT:
                            product_price(product)
                    order = Order.objects.create(
                        user=request.user,
                        address=address,
                        coupon=coupon,
                        status=Order.Status.PROCESSING if payment_method == "cod" else Order.Status.PENDING,
                        coupon_code=coupon.code if coupon else "",
                        subtotal=totals["subtotal"],
                        discount=totals["discount"],
                        tax=totals["tax"],
                        shipping_fee=totals["shipping_fee"],
                        total=totals["total"],
                    )
                    for line in locked_items:
                        product = line.product
                        pricing = product_price(product)
                        line_total = money(pricing["total"] * line.quantity)
                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            product_name=product.name,
                            sku=product.sku,
                            metal=product.metal,
                            purity=product.purity,
                            weight_g=product.weight_g,
                            quantity=line.quantity,
                            unit_price=pricing["unit_price"],
                            making_charge=product.making_charge,
                            tax_rate=pricing["tax_rate"],
                            discount_percent=product.discount_percent,
                            line_total=line_total,
                        )
                        product.inventory -= line.quantity
                        product.save(update_fields=["inventory", "updated_at"])
                    if coupon:
                        coupon.uses += 1
                        coupon.save(update_fields=["uses"])
                    if payment_method == "cod":
                        Payment.objects.create(
                            order=order,
                            provider="cod",
                            status=Payment.Status.PENDING,
                            amount_paise=int(totals["total"] * 100),
                        )
                    else:
                        gateway_order = razorpay_client().order.create(
                            {
                                "amount": int(totals["total"] * 100),
                                "currency": "INR",
                                "receipt": f"avon-{order.pk}",
                                "notes": {"order_id": str(order.pk), "customer_id": str(request.user.pk)},
                            }
                        )
                        Payment.objects.create(order=order, razorpay_order_id=gateway_order["id"], amount_paise=gateway_order["amount"])
                    ShippingInformation.objects.create(order=order)
                    cart_obj.items.all().delete()
                    request.session.pop("coupon_code", None)
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
            except PaymentConfigurationError as exc:
                messages.error(request, str(exc))
                return render(request, "store/checkout.html", _checkout_context(request, items, addresses, address_form, totals, price_error, coupon))
            except Exception:
                logger.exception("Unable to place order for customer %s", request.user.pk)
                messages.error(request, "We couldn't place your order. Please try again or contact support.")
            else:
                _send_order_admin_notification(order)
                if payment_method == "cod":
                    messages.success(request, "Your cash-on-delivery order has been placed.")
                    return redirect("order_detail", order_id=order.pk)
                return redirect("payment", order_id=order.pk)
    return render(request, "store/checkout.html", _checkout_context(request, items, addresses, address_form, totals, price_error, coupon))


def _checkout_context(request, items, addresses, address_form, totals, price_error, coupon):
    priced_items = []
    for item in items:
        try:
            pricing = product_price(item.product)
        except ValidationError:
            pricing = None
        priced_items.append({"item": item, "pricing": pricing})
    return {
        "items": priced_items,
        "addresses": addresses,
        "address_form": address_form,
        "totals": totals,
        "price_error": price_error,
        "coupon": coupon,
        "razorpay_configured": bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET),
        "phone_verified": CustomerProfile.objects.filter(user=request.user, phone_verified=True).exists(),
    }


@login_required
def payment(request, order_id):
    order = get_object_or_404(Order.objects.select_related("payment"), pk=order_id, user=request.user)
    payment_record = order.payment
    if payment_record.provider == "cod":
        return redirect("order_detail", order_id=order.pk)
    if payment_record.status == Payment.Status.CAPTURED:
        return redirect("order_detail", order_id=order.pk)
    return render(request, "store/payment.html", {"order": order, "payment": payment_record, "razorpay_key_id": settings.RAZORPAY_KEY_ID})


@login_required
@require_POST
def verify_payment(request):
    payment_id = request.POST.get("razorpay_payment_id", "")
    razorpay_order_id = request.POST.get("razorpay_order_id", "")
    signature = request.POST.get("razorpay_signature", "")
    if not all((payment_id, razorpay_order_id, signature)):
        return JsonResponse({"error": "Missing payment verification details."}, status=400)
    payment_record = get_object_or_404(Payment.objects.select_related("order"), razorpay_order_id=razorpay_order_id, order__user=request.user)
    client = razorpay_client()
    try:
        client.utility.verify_payment_signature(
            {"razorpay_order_id": razorpay_order_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature}
        )
        gateway_payment = client.payment.fetch(payment_id)
    except Exception as exc:
        from razorpay.errors import SignatureVerificationError

        if not isinstance(exc, SignatureVerificationError):
            logger.exception("Unable to verify Razorpay payment for order %s", payment_record.order_id)
            return JsonResponse({"error": "Payment could not be verified. Please retry or contact support."}, status=502)
        logger.warning("Razorpay signature verification failed for order %s", payment_record.order_id)
        return JsonResponse({"error": "Payment signature verification failed."}, status=400)
    if (
        gateway_payment.get("order_id") != payment_record.razorpay_order_id
        or int(gateway_payment.get("amount", -1)) != payment_record.amount_paise
        or gateway_payment.get("currency") != payment_record.currency
    ):
        logger.error("Razorpay payment details do not match local order %s", payment_record.order_id)
        return JsonResponse({"error": "Payment details do not match this order."}, status=400)
    if gateway_payment.get("status") != "captured":
        return JsonResponse({"error": "Payment has not been captured yet.", "status": gateway_payment.get("status", "unknown")}, status=409)
    mark_payment_captured(payment_record, payment_id)
    return JsonResponse({"redirect": reverse("order_detail", kwargs={"order_id": payment_record.order_id})})


def mark_payment_captured(payment_record, payment_id):
    newly_captured = False
    with transaction.atomic():
        locked_payment = Payment.objects.select_for_update().get(pk=payment_record.pk)
        if locked_payment.status == Payment.Status.CAPTURED:
            return
        order = Order.objects.select_for_update().select_related("user").get(pk=locked_payment.order_id)
        locked_payment.razorpay_payment_id = payment_id
        locked_payment.status = Payment.Status.CAPTURED
        locked_payment.signature_verified = True
        locked_payment.save(update_fields=["razorpay_payment_id", "status", "signature_verified", "updated_at"])
        if order.status == Order.Status.PENDING:
            order.status = Order.Status.PROCESSING
            order.save(update_fields=["status", "updated_at"])
        newly_captured = True
    if newly_captured and order.user.email:
        try:
            context = {"order": order}
            subject = f"Your AVON JEWELER order AV{order.pk:06d} is confirmed"
            text_body = render_to_string("emails/order_confirmation.txt", context)
            html_body = render_to_string("emails/order_confirmation.html", context)
            email = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [order.user.email])
            email.attach_alternative(html_body, "text/html")
            email.send(fail_silently=False)
        except Exception:
            logger.exception("Unable to send AVON JEWELER order confirmation for order %s", order.pk)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        logger.error("Razorpay webhook called without a configured webhook secret.")
        return HttpResponse(status=503)
    signature = request.headers.get("X-Razorpay-Signature", "")
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), request.body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        logger.warning("Rejected Razorpay webhook with invalid signature.")
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)
    if event.get("event") == "payment.captured":
        entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        if not order_id or not payment_id:
            return HttpResponse(status=400)
        payment_record = Payment.objects.filter(razorpay_order_id=order_id).first()
        if payment_record:
            if int(entity.get("amount", -1)) != payment_record.amount_paise or entity.get("currency") != payment_record.currency:
                logger.error("Captured webhook does not match payment record %s", payment_record.pk)
                return HttpResponse(status=400)
            mark_payment_captured(payment_record, payment_id)
    elif event.get("event") == "payment.failed":
        entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        if entity.get("order_id"):
            Payment.objects.filter(razorpay_order_id=entity["order_id"], status=Payment.Status.CREATED).update(status=Payment.Status.FAILED)
    return HttpResponse(status=200)


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items").select_related("payment")
    return render(request, "store/orders.html", {"orders": orders})


def _send_order_admin_notification(order):
    recipient = settings.ORDER_NOTIFICATION_EMAIL
    if not recipient:
        logger.error("Order notification email is not configured; order %s was placed without an admin email.", order.pk)
        return
    try:
        subject = f"New {order.payment.get_provider_display()} order AV{order.pk:06d}"
        body = render_to_string("emails/admin_order_notification.txt", {"order": order})
        EmailMultiAlternatives(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient]).send(fail_silently=False)
    except Exception:
        logger.exception("Unable to send admin order notification for order %s", order.pk)


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related("address", "payment", "shipping").prefetch_related("items"),
        pk=order_id,
        user=request.user,
    )
    return render(request, "store/order_detail.html", {"order": order})


@login_required
def profile(request):
    customer_profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    profile_form = CustomerProfileForm(
        initial={
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "phone": customer_profile.phone,
        }
    )
    address_form = AddressForm()
    if request.method == "POST" and "save_profile" in request.POST:
        profile_form = CustomerProfileForm(request.POST)
        if profile_form.is_valid():
            user = request.user
            user.first_name = profile_form.cleaned_data["first_name"]
            user.last_name = profile_form.cleaned_data["last_name"]
            user.save(update_fields=["first_name", "last_name"])
            phone = profile_form.cleaned_data["phone"]
            if phone != customer_profile.phone:
                customer_profile.phone = phone
                customer_profile.phone_verified = False
                customer_profile.verification_sent_at = None
                customer_profile.verification_attempts = 0
                customer_profile.save()
            messages.success(request, "Your account details were saved.")
            return redirect("profile")
    elif request.method == "POST" and "save_address" in request.POST:
        address_form = AddressForm(request.POST)
        if address_form.is_valid():
            address = address_form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "Delivery address saved.")
            return redirect("profile")
    addresses = Address.objects.filter(user=request.user)
    return render(
        request,
        "store/profile.html",
        {
            "addresses": addresses,
            "orders": Order.objects.filter(user=request.user)[:5],
            "customer_profile": customer_profile,
            "profile_form": profile_form,
            "address_form": address_form,
        },
    )


@login_required
@require_POST
def send_phone_otp(request):
    customer_profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    if not customer_profile.phone:
        messages.error(request, "Save your phone number in your account before requesting an OTP.")
        return redirect("profile")
    if customer_profile.phone_verified:
        messages.info(request, "Your phone number is already verified.")
        return redirect("profile")
    now = timezone.now()
    if customer_profile.verification_sent_at and now - customer_profile.verification_sent_at < timedelta(seconds=30):
        messages.error(request, "Please wait 30 seconds before requesting another OTP.")
        return redirect("profile")
    try:
        send_verification(customer_profile.phone)
    except PhoneVerificationError as exc:
        logger.exception("Unable to send phone verification for customer %s", request.user.pk)
        messages.error(request, str(exc))
    else:
        customer_profile.verification_sent_at = now
        customer_profile.verification_attempts = 0
        customer_profile.save(update_fields=["verification_sent_at", "verification_attempts"])
        messages.success(request, "A verification code has been sent by SMS.")
    return redirect("profile")


@login_required
@require_POST
def verify_phone_otp(request):
    customer_profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
    code = request.POST.get("code", "").strip()
    if not re.fullmatch(r"\d{4,10}", code):
        messages.error(request, "Enter the verification code sent to your phone.")
        return redirect("profile")
    if not customer_profile.verification_sent_at:
        messages.error(request, "Request a phone verification code first.")
        return redirect("profile")
    now = timezone.now()
    if now - customer_profile.verification_sent_at > timedelta(minutes=10):
        customer_profile.verification_sent_at = None
        customer_profile.verification_attempts = 0
        customer_profile.save(update_fields=["verification_sent_at", "verification_attempts"])
        messages.error(request, "That verification code has expired. Request a new one.")
        return redirect("profile")
    if customer_profile.verification_attempts >= 5:
        messages.error(request, "Too many incorrect codes. Request a new verification code.")
        return redirect("profile")
    try:
        verified = check_verification(customer_profile.phone, code)
    except PhoneVerificationError as exc:
        logger.exception("Unable to verify phone for customer %s", request.user.pk)
        messages.error(request, str(exc))
        return redirect("profile")
    if verified:
        customer_profile.phone_verified = True
        customer_profile.verification_sent_at = None
        customer_profile.verification_attempts = 0
        customer_profile.save(update_fields=["phone_verified", "verification_sent_at", "verification_attempts"])
        messages.success(request, "Your phone number is verified.")
    else:
        customer_profile.verification_attempts += 1
        customer_profile.save(update_fields=["verification_attempts"])
        messages.error(request, "That code was not accepted. Check it and try again.")
    return redirect("profile")


@login_required
@require_POST
def delete_address(request, address_id):
    address = get_object_or_404(Address, pk=address_id, user=request.user)
    if address.orders.exists():
        messages.error(request, "This address is linked to an order and cannot be deleted.")
    else:
        address.delete()
        messages.success(request, "Address deleted.")
    return redirect("profile")
