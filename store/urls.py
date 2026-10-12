from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("jewellery/<slug:slug>/", views.product_detail, name="product_detail"),
    path("accounts/login/", views.StoreLoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/register/", views.register, name="register"),
    path("account/", views.profile, name="profile"),
    path("account/phone/send-otp/", views.send_phone_otp, name="send_phone_otp"),
    path("account/phone/verify-otp/", views.verify_phone_otp, name="verify_phone_otp"),
    path("account/addresses/<int:address_id>/delete/", views.delete_address, name="delete_address"),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/<int:product_id>/toggle/", views.toggle_wishlist, name="toggle_wishlist"),
    path("bag/", views.cart, name="cart"),
    path("bag/items/<int:item_id>/", views.update_cart_item, name="update_cart_item"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/payment/<int:order_id>/", views.payment, name="payment"),
    path("checkout/payment/verify/", views.verify_payment, name="verify_payment"),
    path("payments/razorpay/webhook/", views.razorpay_webhook, name="razorpay_webhook"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
]
