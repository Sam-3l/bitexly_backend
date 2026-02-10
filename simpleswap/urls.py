from django.urls import path
from . import views

app_name = 'simpleswap'

urlpatterns = [
    # Currencies
    path('currencies/', views.get_simpleswap_currencies, name='get-currencies'),
    path('pairs/', views.get_exchange_pairs, name='get-pairs'),
    
    # Rate/Quote
    path('rate/', views.get_simpleswap_rate, name='get-rate'),
    
    # Exchange
    path('create-transaction/', views.create_swap_transaction, name='create-transaction'),
    path('exchange/<str:public_id>/', views.get_transaction_status, name='get-exchange-status'),
]