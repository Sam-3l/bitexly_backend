from django.urls import path
from .views import *
from .transaction_views import (
    TransactionHistoryView,
    TransactionDetailView,
    TransactionStatisticsView,
    QuickStatsView,
    RecentTransactionsView,
    ExportTransactionsView,
)

urlpatterns = [
    path('signup/', SignupView.as_view(), name='partner-signup'),
    path('signin/', SigninView.as_view(), name="partner-signin"),
    path('token/refresh/', RefreshTokenView.as_view(), name="token-refresh"),
    path('verify-otp/', VerifyOTPView.as_view(), name="verifyotp"),
    path('forgot-password/', PasswordResetView.as_view(), name="forgot password"),
    path('set-pin/', SetPinView.as_view(), name="reset password"),
    path('change-password/', ChangePasswordView.as_view(), name="Change Password"),
    path('profile/update/', UpdateProfileView.as_view(), name='update-profile'),
    # path('transactionhistory/partner/', UserTransactionHistoryView.as_view(), name='transaction-history'),
    # path('alltransactionHistory/admin/', AllTransactionsView.as_view(), name="all-transactions"),
    # path('notifications/partner/', NotificationListView.as_view(), name="get-notified"),
    # path('notification/read/', NotificationMarkAsReadView.as_view(), name="mark-read-notification"),
    path('getDetails/', DetailsView.as_view(), name="partner-details"),
    # ============================================================================
    # TRANSACTION HISTORY & STATISTICS
    # ============================================================================
    # Main transaction history with filters
    path('transactions/history/', TransactionHistoryView.as_view(), name='transaction-history'),
    
    # Get specific transaction details
    path('transactions/<str:transaction_id>/', TransactionDetailView.as_view(), name='transaction-detail'),
    
    # Full statistics with breakdowns
    path('transactions/stats/full/', TransactionStatisticsView.as_view(), name='transaction-statistics'),
    
    # Quick stats for dashboard
    path('transactions/stats/quick/', QuickStatsView.as_view(), name='quick-stats'),
    
    # Recent transactions (for dashboard)
    path('transactions/recent/', RecentTransactionsView.as_view(), name='recent-transactions'),
    
    # Export transactions (CSV/JSON)
    path('transactions/export/', ExportTransactionsView.as_view(), name='export-transactions'),
    
    # ============================================================================
    # OLD TRANSACTION ENDPOINTS (Keep for backward compatibility)
    # ============================================================================
    path("transactions/", UserTransactionHistory.as_view(), name="user-transaction"),  # Old endpoint
    path("quote/", CreateQuoteView.as_view(), name="meld-create-quote"),
    path("payment/", CreatePaymentView.as_view(), name="meld-create-payment"),
    path("meldwebhook/", MeldWebhookView.as_view(), name="meld-webhook"),
    path("moonpay/signature/", MeldWebhookView.as_view(), name="meld-webhook"),
    path("onrampwebhook/", OnrampWebhookView.as_view(), name="onramp-webhook"),
    # path("get-onramp-url/", OnrampURLView.as_view(), name="get_onramp_url"),
    path("get-offramp-url/", OfframpURLView.as_view(), name="get_offramp_url"),
    # path("changelly/pairs/", GetPairsParamsView.as_view(), name=""),
    # path("changelly/currencies/", GetCurrenciesView.as_view(), name=""),
    # path("changelly/exchange-amount/", GetExchangeAmountView.as_view(), name=""),
    # path("changelly/create-transaction/", CreateTransactionView.as_view(), name=""), 
    path("api/changelly/exchange-amount/", ChangellyExchangeAmountView.as_view(), name="changelly-exchange-amount"),
    path("api/changelly/validate-wallet/", ValidateWallet.as_view(), name="validate-address"),
    path("api/changelly/create-transaction/", CreateTransaction.as_view(), name="create-transaction"),
    path("api/changelly/confirm-transaction/", ConfirmTransaction.as_view(), name="confirm-transaction"),
    path("api/changelly/get-coins/", GetCoins.as_view(), name="get-coins"),
    path("quotes/onRamp/", QuoteAPIView.as_view(), name="get_quotes"),
]