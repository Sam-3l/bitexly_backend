from django.urls import path
from . import views

urlpatterns = [
    # Quote endpoint - Get price quotes for buy/sell
    path('quote/', views.get_moonpay_quote, name='moonpay_quote'),
    
    # Generate widget URL for buy/sell transactions
    path('generate-url/', views.generate_moonpay_url, name='moonpay_generate_url'),
    
    # Get all supported payment methods, currencies, and chains
    path('payment-methods/', views.get_moonpay_payment_methods, name='moonpay_payment_methods'),
    
    # Get all supported currencies
    path('currencies/', views.get_moonpay_currencies_endpoint, name='moonpay_currencies'),
    
    # Get currency limits (min/max amounts)
    path('limits/', views.get_currency_limits, name='moonpay_limits'),
    
    # Get transaction status by ID
    path('transaction/<str:transaction_id>/', views.get_transaction_status, name='moonpay_transaction_status'),
    
    # Get user's IP address information (for location-based restrictions)
    path('ip-info/', views.get_ip_address_info, name='moonpay_ip_info'),

    path('webhook/', views.moonpay_webhook, name='moonpay_webhook'),
]
