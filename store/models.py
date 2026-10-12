from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class MetalRate(models.Model):
    metal = models.CharField(max_length=40)
    purity = models.CharField(max_length=30)
    price_per_gram = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    effective_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-effective_at"]
        indexes = [models.Index(fields=["metal", "purity", "-effective_at"])]

    def __str__(self):
        return f"{self.metal} {self.purity}: ₹{self.price_per_gram}/g"


class StoreSettings(models.Model):
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("3.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(100)],
    )

    class Meta:
        verbose_name = "store settings"
        verbose_name_plural = "store settings"

    @classmethod
    def get_default(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Store tax settings"


class Product(models.Model):
    class PriceType(models.TextChoices):
        FIXED = "fixed", "Fixed price"
        WEIGHT = "weight", "Weight-based"

    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    sku = models.CharField(max_length=40, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    description = models.TextField()
    metal = models.CharField(max_length=40, default="Gold")
    purity = models.CharField(max_length=30, default="22K")
    price_type = models.CharField(max_length=10, choices=PriceType.choices, default=PriceType.FIXED)
    fixed_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    weight_g = models.DecimalField(max_digits=8, decimal_places=3, default=Decimal("0.000"), validators=[MinValueValidator(Decimal("0.000"))])
    making_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(100)],
        help_text="Leave blank to use the tax rate in Store settings.",
    )
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(100)])
    inventory = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_featured", "-created_at"]
        indexes = [models.Index(fields=["is_active", "category"]), models.Index(fields=["name"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def primary_image(self):
        return self.images.first()


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/%Y/%m/", blank=True)
    image_url = models.URLField(blank=True)
    alt_text = models.CharField(max_length=180, blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.alt_text or f"Image for {self.product}"


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    line1 = models.CharField(max_length=180)
    line2 = models.CharField(max_length=180, blank=True)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    postal_code = models.CharField(max_length=12)
    country = models.CharField(max_length=80, default="India")
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "-id"]

    def __str__(self):
        return f"{self.full_name}, {self.city}"


class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    phone = models.CharField(max_length=16, blank=True)
    phone_verified = models.BooleanField(default=False)
    verification_sent_at = models.DateTimeField(null=True, blank=True)
    verification_attempts = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Profile for {self.user}"


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(20)])

    class Meta:
        constraints = [models.UniqueConstraint(fields=["cart", "product"], name="unique_product_per_cart")]

    def __str__(self):
        return f"{self.quantity} × {self.product}"


class Wishlist(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist")
    products = models.ManyToManyField(Product, related_name="wishlisted_by", blank=True)

    def __str__(self):
        return f"Wishlist for {self.user}"


class Coupon(models.Model):
    code = models.CharField(max_length=40, unique=True)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(100)])
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.00"))])
    minimum_order = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def is_valid(self, subtotal):
        now = timezone.now()
        return (
            self.is_active
            and self.starts_at <= now
            and (self.expires_at is None or self.expires_at >= now)
            and (self.usage_limit is None or self.uses < self.usage_limit)
            and subtotal >= self.minimum_order
        )

    def __str__(self):
        return self.code


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
    address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="orders")
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2)
    coupon_code = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"AV{self.pk:06d}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    product_name = models.CharField(max_length=180)
    sku = models.CharField(max_length=40)
    metal = models.CharField(max_length=40)
    purity = models.CharField(max_length=30)
    weight_g = models.DecimalField(max_digits=8, decimal_places=3)
    quantity = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    making_charge = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"


class Payment(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending collection"
        AUTHORIZED = "authorized", "Authorized"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="payment")
    provider = models.CharField(max_length=20, choices=(("razorpay", "Razorpay"), ("cod", "Cash on delivery")), default="razorpay")
    razorpay_order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.CREATED)
    signature_verified = models.BooleanField(default=False)
    amount_paise = models.PositiveBigIntegerField()
    currency = models.CharField(max_length=3, default="INR")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.provider} payment for {self.order}"


class ShippingInformation(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="shipping")
    courier = models.CharField(max_length=100, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    tracking_url = models.URLField(blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Shipping for {self.order}"
