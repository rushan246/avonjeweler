import hashlib
import hmac
import json
from decimal import Decimal
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Address, Cart, CartItem, Category, CustomerProfile, MetalRate, Order, Payment, Product, ProductImage, StoreSettings, Wishlist
from .pricing import cart_totals, product_price


class StoreBaseTest(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Rings", slug="rings")
        self.product = Product.objects.create(
            name="Sol Ring",
            slug="sol-ring",
            sku="AV-TEST-001",
            category=self.category,
            description="A considered gold ring.",
            metal="Gold",
            purity="22K",
            fixed_price=Decimal("1000.00"),
            tax_rate=Decimal("3.00"),
            inventory=8,
            is_active=True,
        )
        self.user = User.objects.create_user(username="customer", email="customer@example.com", password="LongSecurePass123!")
        self.address = Address.objects.create(
            user=self.user,
            full_name="A Customer",
            phone="9876543210",
            line1="1 Market Road",
            city="Mumbai",
            state="Maharashtra",
            postal_code="400001",
        )
        CustomerProfile.objects.create(user=self.user, phone="+919876543210", phone_verified=True)


class PricingTests(StoreBaseTest):
    def test_fixed_price_includes_discount_and_tax_using_decimal_math(self):
        self.product.discount_percent = Decimal("10.00")
        self.product.save()
        result = product_price(self.product)
        self.assertEqual(result["unit_price"], Decimal("900.00"))
        self.assertEqual(result["tax"], Decimal("27.00"))
        self.assertEqual(result["total"], Decimal("927.00"))

    def test_weight_based_price_uses_latest_matching_metal_rate(self):
        self.product.price_type = Product.PriceType.WEIGHT
        self.product.weight_g = Decimal("2.500")
        self.product.making_charge = Decimal("125.00")
        self.product.save()
        MetalRate.objects.create(metal="Gold", purity="22K", price_per_gram=Decimal("6000.00"), effective_at=timezone.now())
        result = product_price(self.product)
        self.assertEqual(result["base"], Decimal("15125.00"))
        self.assertEqual(result["total"], Decimal("15578.75"))

    def test_store_tax_setting_applies_to_products_without_an_override(self):
        self.product.tax_rate = None
        self.product.save()
        store_settings = StoreSettings.get_default()
        store_settings.tax_rate = Decimal("5.00")
        store_settings.save()
        result = product_price(self.product)
        self.assertEqual(result["tax_rate"], Decimal("5.00"))
        self.assertEqual(result["tax"], Decimal("50.00"))

    def test_cart_total_adds_shipping_and_tax(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        result = cart_totals([item])
        self.assertEqual(result["subtotal"], Decimal("2000.00"))
        self.assertEqual(result["tax"], Decimal("60.00"))
        self.assertEqual(result["total"], Decimal("2159.00"))


class StorefrontTests(StoreBaseTest):
    def test_catalog_search_and_detail_render(self):
        response = self.client.get(reverse("home"), {"q": "Sol"})
        self.assertContains(response, "Sol Ring")
        self.assertContains(response, "AVON")
        response = self.client.get(reverse("product_detail", kwargs={"slug": self.product.slug}))
        self.assertContains(response, "22K")

    def test_registration_and_authenticated_cart(self):
        response = self.client.post(
            reverse("register"),
            {
                "first_name": "New",
                "last_name": "Customer",
                "username": "newcustomer",
                "email": "new@example.com",
                "password1": "A-secure-test-password-482!",
                "password2": "A-secure-test-password-482!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="newcustomer").exists())
        self.assertEqual(self.client.get(reverse("cart")).status_code, 200)

    def test_account_and_checkout_pages_render_profile_and_cod_controls(self):
        self.client.force_login(self.user)
        profile_response = self.client.get(reverse("profile"))
        self.assertContains(profile_response, "Profile details")
        self.assertContains(profile_response, "Saved addresses")
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product)
        with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=""):
            checkout_response = self.client.get(reverse("checkout"))
        self.assertContains(checkout_response, "Cash on delivery")
        self.assertContains(checkout_response, "Online payment is unavailable")

    @patch("store.views.send_verification")
    @patch("store.views.check_verification", return_value=True)
    def test_customer_can_verify_phone_from_profile(self, check_phone, send_phone):
        self.client.force_login(self.user)
        profile = self.user.customer_profile
        profile.phone_verified = False
        profile.save(update_fields=["phone_verified"])
        response = self.client.post(reverse("send_phone_otp"))
        self.assertEqual(response.status_code, 302)
        send_phone.assert_called_once_with("+919876543210")
        profile.refresh_from_db()
        self.assertIsNotNone(profile.verification_sent_at)
        response = self.client.post(reverse("verify_phone_otp"), {"code": "123456"})
        self.assertEqual(response.status_code, 302)
        check_phone.assert_called_once_with("+919876543210", "123456")
        profile.refresh_from_db()
        self.assertTrue(profile.phone_verified)

    def test_customer_can_update_profile_and_add_a_delivery_address(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile"),
            {"save_profile": "1", "first_name": "Updated", "last_name": "Customer", "phone": "+919876543210"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertTrue(self.user.customer_profile.phone_verified)
        response = self.client.post(
            reverse("profile"),
            {
                "save_address": "1",
                "full_name": "Updated Customer",
                "phone": "9876543210",
                "line1": "2 Lake Road",
                "line2": "",
                "city": "Pune",
                "state": "Maharashtra",
                "postal_code": "411001",
                "country": "India",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Address.objects.filter(user=self.user, city="Pune").exists())

    def test_changing_profile_phone_requires_verification_again(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("profile"),
            {"save_profile": "1", "first_name": "A", "last_name": "Customer", "phone": "+919876543211"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.customer_profile.refresh_from_db()
        self.assertFalse(self.user.customer_profile.phone_verified)

    def test_customer_cannot_view_another_customers_order(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=self.product)
        order = Order.objects.create(
            user=self.user,
            address=self.address,
            subtotal=Decimal("1000.00"),
            tax=Decimal("30.00"),
            total=Decimal("1129.00"),
        )
        Payment.objects.create(order=order, razorpay_order_id="order_test_123", amount_paise=112900)
        second = User.objects.create_user(username="another", password="AnotherSecure123!")
        self.client.force_login(second)
        response = self.client.get(reverse("order_detail", kwargs={"order_id": order.pk}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(item.quantity, 1)


class AdminWorkflowTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(username="catalog-admin", email="admin@example.com", password="AdminSecurePass123!")
        self.category = Category.objects.create(name="Necklaces", slug="necklaces")
        self.client.force_login(self.staff)

    def test_staff_can_update_store_tax_setting(self):
        StoreSettings.get_default()
        response = self.client.post(
            reverse("admin:store_storesettings_change", args=[1]),
            {"tax_rate": "5.00", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StoreSettings.get_default().tax_rate, Decimal("5.00"))

    def test_staff_can_add_product_and_publish_it_to_catalogue(self):
        response = self.client.post(
            reverse("admin:store_product_add"),
            {
                "name": "Admin-created Heirloom Pendant",
                "slug": "admin-created-heirloom-pendant",
                "sku": "AV-ADMIN-001",
                "category": self.category.pk,
                "description": "A pendant created through the protected store dashboard.",
                "metal": "Gold",
                "purity": "22K",
                "price_type": Product.PriceType.FIXED,
                "fixed_price": "12500.00",
                "weight_g": "2.000",
                "making_charge": "0.00",
                "tax_rate": "3.00",
                "discount_percent": "0.00",
                "inventory": "4",
                "is_active": "on",
                "images-TOTAL_FORMS": "1",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "1000",
                "images-0-position": "0",
            },
        )
        if response.status_code != 302:
            self.fail(
                f"Admin product submission failed: {response.context['adminform'].form.errors}; "
                f"inline errors: {[formset.formset.errors for formset in response.context['inline_admin_formsets']]}"
            )
        product = Product.objects.get(sku="AV-ADMIN-001")
        self.assertTrue(product.is_active)
        self.assertContains(self.client.get(reverse("home")), product.name)


@override_settings(
    RAZORPAY_KEY_ID="rzp_test_key",
    RAZORPAY_KEY_SECRET="test_secret",
    DEFAULT_FROM_EMAIL="orders@avonjeweler.example",
    ORDER_NOTIFICATION_EMAIL="admin@example.com",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class CheckoutTests(StoreBaseTest):
    @patch("store.views.razorpay_client")
    def test_checkout_creates_gateway_order_and_reserves_inventory(self, client_factory):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        gateway = Mock()
        gateway.order.create.return_value = {"id": "order_razorpay_123", "amount": 215900}
        client_factory.return_value = gateway
        response = self.client.post(reverse("checkout"), {"place_order": "1", "address_id": self.address.pk})
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.total, Decimal("2159.00"))
        self.assertEqual(order.payment.razorpay_order_id, "order_razorpay_123")
        self.product.refresh_from_db()
        self.assertEqual(self.product.inventory, 6)
        self.assertFalse(cart.items.exists())
        self.assertEqual(gateway.order.create.call_args.args[0]["amount"], 215900)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["admin@example.com"])
        self.assertIn("AV-TEST-001", mail.outbox[0].body)

    def test_cash_on_delivery_places_order_and_notifies_admin(self):
        self.client.force_login(self.user)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2)
        response = self.client.post(
            reverse("checkout"),
            {"place_order": "1", "address_id": self.address.pk, "payment_method": "cod"},
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        self.assertEqual(order.payment.provider, "cod")
        self.assertEqual(order.payment.status, Payment.Status.PENDING)
        self.assertIsNone(order.payment.razorpay_order_id)
        self.assertEqual(mail.outbox[0].to, ["admin@example.com"])
        self.assertIn("Cash on delivery", mail.outbox[0].subject)

    def test_checkout_requires_verified_phone(self):
        self.client.force_login(self.user)
        self.user.customer_profile.phone_verified = False
        self.user.customer_profile.save(update_fields=["phone_verified"])
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=self.product)
        response = self.client.post(
            reverse("checkout"),
            {"place_order": "1", "address_id": self.address.pk, "payment_method": "cod"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Order.objects.exists())

    def test_checkout_does_not_create_fake_payment_if_credentials_are_missing(self):
        with override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET=""):
            self.client.force_login(self.user)
            cart = Cart.objects.create(user=self.user)
            CartItem.objects.create(cart=cart, product=self.product)
            response = self.client.post(reverse("checkout"), {"place_order": "1", "address_id": self.address.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    @patch("store.views.razorpay_client")
    def test_payment_verification_requires_verified_captured_gateway_payment(self, client_factory):
        cart = Cart.objects.create(user=self.user)
        order = Order.objects.create(
            user=self.user,
            address=self.address,
            subtotal=Decimal("1000.00"),
            tax=Decimal("30.00"),
            total=Decimal("1129.00"),
        )
        payment_record = Payment.objects.create(order=order, razorpay_order_id="order_razorpay_123", amount_paise=112900)
        self.client.force_login(self.user)
        gateway = Mock()
        gateway.payment.fetch.return_value = {
            "order_id": "order_razorpay_123",
            "amount": 112900,
            "currency": "INR",
            "status": "captured",
        }
        client_factory.return_value = gateway
        response = self.client.post(
            reverse("verify_payment"),
            {
                "razorpay_order_id": "order_razorpay_123",
                "razorpay_payment_id": "pay_verified_123",
                "razorpay_signature": "valid-signature",
            },
        )
        self.assertEqual(response.status_code, 200)
        payment_record.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(payment_record.status, Payment.Status.CAPTURED)
        self.assertTrue(payment_record.signature_verified)
        self.assertEqual(order.status, Order.Status.PROCESSING)
        gateway.utility.verify_payment_signature.assert_called_once()

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-test")
    def test_webhook_requires_and_checks_hmac_signature(self):
        order = Order.objects.create(
            user=self.user,
            address=self.address,
            subtotal=Decimal("1000.00"),
            tax=Decimal("30.00"),
            total=Decimal("1129.00"),
        )
        payment_record = Payment.objects.create(order=order, razorpay_order_id="order_webhook_123", amount_paise=112900)
        payload = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_webhook_123",
                            "order_id": "order_webhook_123",
                            "amount": 112900,
                            "currency": "INR",
                        }
                    }
                },
            }
        ).encode()
        signature = hmac.new(b"webhook-test", payload, hashlib.sha256).hexdigest()
        response = self.client.post(reverse("razorpay_webhook"), data=payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)
        payment_record.refresh_from_db()
        order.refresh_from_db()
        self.assertTrue(payment_record.signature_verified)
        self.assertEqual(payment_record.razorpay_payment_id, "pay_webhook_123")
        self.assertEqual(order.status, Order.Status.PROCESSING)
        rejected = self.client.post(reverse("razorpay_webhook"), data=payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="wrong")
        self.assertEqual(rejected.status_code, 400)
