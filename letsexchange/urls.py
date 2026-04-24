from django.urls import path
from . import views

app_name = 'letsexchange'

urlpatterns = [
    # Coins
    path('coins/', views.get_letsexchange_coins, name='get-coins'),
    
    # Rate/Quote
    path('rate/', views.get_letsexchange_rate, name='get-rate'),
    
    # Transaction
    path('create-transaction/', views.create_swap_transaction, name='create-transaction'),
    path('transaction/<str:transaction_id>/', views.get_transaction_status, name='get-transaction-status'),

    # Status polling (frontend calls this every ~10s, mirrors Changelly's confirm-transaction)
    path('confirm-transaction/', views.confirm_transaction, name='confirm-transaction'),
]
