from django.urls import path
from . import views

urlpatterns = [
    path('quote/', views.get_moonpay_quote, name='moonpay_quote'),
    path('payment-methods/', views.get_moonpay_payment_methods, name='moonpay_payment_methods'),
    path('generate-url/', views.generate_moonpay_url, name='moonpay_generate_url'),
]