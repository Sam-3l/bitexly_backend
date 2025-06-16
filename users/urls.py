from django.urls import path
from .views import *

urlpatterns = [
    path('signup/partner/', SignupView.as_view(), name='partner-signup'),
    path('signin/partner/', SigninView.as_view(), name="partner-signin"),
    path('verify-otp/partner/', VerifyOTPView.as_view(), name="verifyotp"),
    path('forgot-password/partner/', PasswordResetView.as_view(), name="forgot password"),
    # path('reset-password-otp/partner/', ResetPasswordWithOTPView.as_view(), name="reset password"),
    path('change-password/partner/', ChangePasswordView.as_view(), name="Change Password"),
    path('admin/create-driver/', DriverCreateView.as_view(), name="create driver"),
    path('admin/approve-withdrawals/', ApproveWithdrawalView.as_view(), name="admin approve withdrawal"),
    path('driver-login/', DriverLoginView.as_view(), name="driver login"),
    path('setpin/partner/', SetPinView.as_view(), name="set pin"),
    path('delivery/initiateconfirm/', CreateDeliveryConfirmationView.as_view(), name="Initiate delivery"),
    path('deliery/confirm/', ConfirmDeliveryOTPView.as_view(), name="confirm delivery"),
    path('profile/update/partner/', UpdateProfileView.as_view(), name='update-profile'),
    path('retrieve-pin/partner/', RetrieveWithdrawalPinView.as_view(), name='retrieve-withdrawal-pin'),
    # path('request-reset-pin/partner/', RequestPinResetView.as_view(), name='request-reset-pin'),
    # path('reset-pin/partner/', ResetPinWithOTPView.as_view(), name='reset-pin-with-otp'),
    # path('investments/partner/', PartnerInvestmentsView.as_view(), name='partner-investment'),
    path('investments/partner/overview/', PartnerInvestmentOverview.as_view(), name='partner-investment-all-data'),
    path('transactionhistory/partner/', UserTransactionHistoryView.as_view(), name='transaction-history'),
    path('alltransactionHistory/admin/', AllTransactionsView.as_view(), name="all-transactions"),
    path('notifications/partner/', NotificationListView.as_view(), name="get-notified"),
    path('notification/read/', NotificationMarkAsReadView.as_view(), name="mark-read-notification"),
    path('getDetails/', PartnerDetailsView.as_view(), name="partner-details")
]