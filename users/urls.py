from django.urls import path
from .views import *

urlpatterns = [
    path('signup/', SignupView.as_view(), name='partner-signup'),
    path('signin/', SigninView.as_view(), name="partner-signin"),
    path('verify-otp/', VerifyOTPView.as_view(), name="verifyotp"),
    path('forgot-password/', PasswordResetView.as_view(), name="forgot password"),
    path('set-pin/', SetPinView.as_view(), name="reset password"),
    path('change-password/', ChangePasswordView.as_view(), name="Change Password"),
    path('profile/update/', UpdateProfileView.as_view(), name='update-profile'),
    # path('transactionhistory/partner/', UserTransactionHistoryView.as_view(), name='transaction-history'),
    # path('alltransactionHistory/admin/', AllTransactionsView.as_view(), name="all-transactions"),
    # path('notifications/partner/', NotificationListView.as_view(), name="get-notified"),
    # path('notification/read/', NotificationMarkAsReadView.as_view(), name="mark-read-notification"),
    path('getDetails/', DetailsView.as_view(), name="partner-details")
]