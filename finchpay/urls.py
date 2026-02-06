from django.urls import path
from . import views

urlpatterns = [
    # Core transaction endpoints
    path('quote/', views.get_finchpay_quote, name='finchpay_quote'),
    path('generate-url/', views.generate_finchpay_url, name='finchpay_generate_url'),
    path('transaction-status/', views.get_finchpay_transaction_status, name='finchpay_transaction_status'),
    path('webhook/', views.finchpay_webhook, name='finchpay_webhook'),    
    path('currencies/', views.get_finchpay_currencies, name='finchpay_currencies'),
    path('limits/', views.get_finchpay_limits, name='finchpay_limits'),
    path('payment-methods/', views.get_finchpay_payment_methods, name='finchpay_payment_methods'),
]
