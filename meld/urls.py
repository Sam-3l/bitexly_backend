from django.urls import path
from . import views

urlpatterns = [
    path('crypto-currencies/', views.get_crypto_currencies, name='crypto-currencies'),
    path('fiat-currencies/', views.get_fiat_currencies, name='fiat-currencies'),
    path('payment-methods/', views.get_payment_methods, name='payment-methods'),
    path('crypto-quote/', views.get_crypto_quote, name='crypto-quote'),
    path('session-widget/', views.create_session_widget, name='session-widget'),
    path('webhook/', views.meld_webhook, name='meld_webhook'),
    path('transaction-status/', views.get_transaction_status, name='transaction-status'),
]
