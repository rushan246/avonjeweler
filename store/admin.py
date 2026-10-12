from django.contrib import admin

from .models import Address, Cart, CartItem, Category, Coupon, CustomerProfile, MetalRate, Order, OrderItem, Payment, Product, ProductImage, ShippingInformation, StoreSettings, Wishlist


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "image_url", "alt_text", "position")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "metal", "purity", "price_type", "inventory", "is_active", "is_featured")
    list_filter = ("is_active", "is_featured", "category", "metal", "purity", "price_type")
    search_fields = ("name", "sku", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = [ProductImageInline]
    fieldsets = (
        ("Product", {"fields": ("name", "slug", "sku", "category", "description", "is_active", "is_featured", "inventory")}),
        ("Metal & pricing", {"fields": ("metal", "purity", "price_type", "fixed_price", "weight_g", "making_charge", "tax_rate", "discount_percent")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(MetalRate)
class MetalRateAdmin(admin.ModelAdmin):
    list_display = ("metal", "purity", "price_per_gram", "effective_at")
    list_filter = ("metal", "purity")
    ordering = ("-effective_at",)


@admin.register(StoreSettings)
class StoreSettingsAdmin(admin.ModelAdmin):
    list_display = ("tax_rate",)
    fields = ("tax_rate",)

    def has_add_permission(self, request):
        return not StoreSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product", "product_name", "sku", "metal", "purity", "weight_g", "quantity", "unit_price", "making_charge", "tax_rate", "discount_percent", "line_total")


class ShippingInformationInline(admin.StackedInline):
    model = ShippingInformation
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "status", "payment_method", "total", "created_at")
    list_filter = ("status", "payment__provider", "created_at")
    search_fields = ("id", "user__username", "user__email", "items__sku")
    readonly_fields = ("user", "address", "coupon", "coupon_code", "subtotal", "discount", "tax", "shipping_fee", "total", "created_at", "updated_at")
    inlines = [OrderItemInline, ShippingInformationInline]
    list_select_related = ("user", "payment")

    @admin.display(description="Payment method")
    def payment_method(self, obj):
        return obj.payment.get_provider_display()


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "provider", "status", "amount_paise", "signature_verified", "created_at")
    list_filter = ("provider", "status", "signature_verified")
    search_fields = ("razorpay_order_id", "razorpay_payment_id", "order__id")
    readonly_fields = ("order", "provider", "razorpay_order_id", "razorpay_payment_id", "status", "signature_verified", "amount_paise", "currency", "created_at", "updated_at")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_percent", "discount_amount", "uses", "usage_limit", "is_active", "expires_at")
    list_filter = ("is_active",)
    search_fields = ("code",)
    readonly_fields = ("uses",)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "city", "state", "postal_code", "is_default")
    search_fields = ("full_name", "user__username", "user__email", "postal_code")


admin.site.register(Cart)
admin.site.register(CartItem)
admin.site.register(Wishlist)
admin.site.register(CustomerProfile)

admin.site.site_header = "AVON JEWELER | Store administration"
admin.site.site_title = "AVON JEWELER Admin"
admin.site.index_title = "Manage your jewellery store"
