from django.urls import path
from . import views

urlpatterns = [
    # Currency and network endpoints
    path('currencies/', views.get_exolix_currencies, name='exolix_currencies'),
    path('currencies/<str:currency_code>/networks/', views.get_currency_networks, name='exolix_currency_networks'),
    path('networks/', views.get_all_networks, name='exolix_all_networks'),
    
    # Rate/Quote endpoint - Get exchange rate and estimate
    path('rate/', views.get_exolix_rate, name='exolix_rate'),
    
    # Transaction endpoints
    path('create-transaction/', views.create_swap_transaction, name='exolix_create_transaction'),
    path('transaction/<str:transaction_id>/', views.get_transaction_status, name='exolix_transaction_status'),
    path('transactions/', views.get_transaction_history, name='exolix_transaction_history'),
]