from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Users, EmailOTP, Transaction
from drf_yasg.utils import swagger_auto_schema
from .serializers import SignUpSerializer, CompleteRegistrationSerializer, TransactionSerializer, ResetPasswordOTPSerializer, ProfileSerializer
from bitexly.utils import send_email
from drf_yasg import openapi
from rest_framework.parsers import MultiPartParser, FormParser,JSONParser
from .utils import generate_otp, get_tokens_for_user, set_user_pin
from .permisssion import IsTrader
import os
from django.conf import settings
import requests
import hmac
import hashlib
import json


MELD_API_KEY = settings.MELD_CRYPTO_API_KEY
MELD_WEBHOOK_SECRET = settings.MELD_WEBHOOK_SECRET
MELD_BASE = "https://api.meld.io/payments/crypto"


def get_headers():
    return {
        "Authorization": f"Bearer {MELD_API_KEY}",
        "Content-Type": "application/json",
    }
# Create your views here.


# Partners SignUp   
class SignupView(APIView):
    @swagger_auto_schema(request_body=SignUpSerializer, responses={201: openapi.Response(
            description="OTP sent to your email!",
            schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                'message': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
            })
        )}
    )
    def post(self, request):
        resend = request.data.get('resend', False)
        serializer = SignUpSerializer(data=request.data)

        if resend:
            otp_code = generate_otp()
            EmailOTP.objects.create(user=serializer.email, otp=otp_code)
            # send_reg_otp_email(user, otp_code)
            send_email(serializer,"Your OTP Code", "Use the code below to verify your account.", code=otp_code)
            return Response({'detail': 'OTP resent to your email.'}, status=status.HTTP_200_OK)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        existing_user = Users.objects.filter(email=email).first()

        if existing_user:
            if existing_user.is_email_verified:
                return Response({'detail': 'Email already verified.'}, status=status.HTTP_400_BAD_REQUEST)
           
            user = existing_user
        else:
            user = serializer.save() 

        otp = generate_otp()
        EmailOTP.objects.create(user=user, otp=otp)
        send_email(user,"Your OTP Code","Use the code below to verify your email.", code=otp)

        return Response({'detail': 'OTP sent to your email.', 'otp': otp}, status=status.HTTP_200_OK)

    @swagger_auto_schema(request_body=CompleteRegistrationSerializer, responses={201: openapi.Response(
            description="Registration Completed, Signin to access your account!.",
            schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                'message': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
            })
        )}
    )
    def patch(self, request):
        serializer = CompleteRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            # send_email(request.user,"Welcome to foodhybrid!","Your account has successfully been created with foodhybrid, Kindly Signin to access your account!.",)
            return Response({'detail': 'Registeration Completed, Signin to access your account!.'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class VerifyOTPView(APIView):
    @swagger_auto_schema(  
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING),
                'otp': openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=['email', 'otp']
        ),
        responses={201: openapi.Response(
            description="Email verified successfully. Go ahead and complete your signup process!",
            schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                'message': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
            })
        )}
    )
    def post(self, request):
        email = request.data.get('email')
        otp_input = request.data.get('otp')

        user = Users.objects.filter(email=email).first()
        if not user:
            return Response({'detail': 'Invalid email, Please sign up'}, status=status.HTTP_400_BAD_REQUEST)

        otp_record = EmailOTP.objects.filter(user=user, otp=otp_input).first()
        print(otp_input, user)
        if otp_record:
            user.is_email_verified = True
            user.save()
            EmailOTP.objects.filter(user=user).delete()

            return Response({'detail': 'Email verified successfully. Go ahead and complete your signup process!'}, status=status.HTTP_200_OK)
        
        return Response({'detail': 'Invalid or expired OTP.'}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetView(APIView):
        @swagger_auto_schema(
        request_body=ResetPasswordOTPSerializer,
        responses={201: openapi.Response(
            description="Reset OTP has been sent!",
            schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                'message': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
            })
        )}
    )
        def post(self, request):
            resend = request.data.get('resend', False)
            serializer = ResetPasswordOTPSerializer(data=request.data)
            if resend:
                email = request.data.get('email')
                if not email:
                    return Response({"email": "This field is required to resend OTP."}, status=400)
                try:
                    user = Users.objects.get(email=email)
                except Users.DoesNotExist:
                    return Response({"email": "User not found."}, status=400)

                otp_code = generate_otp()
                EmailOTP.objects.create(user=user, otp=otp_code)
                # send_reset_otp_email(user, otp_code)
                send_email(user,"Your OTP Code", "Use the code below to reset your password.", code=otp_code)
                return Response({"detail": "OTP resent to your email."}, status=200)
            if serializer.is_valid():
                user = serializer.validated_data['user']
                otp = request.data.get('otp')
                new_password = request.data.get('new_password')
                if not otp and not new_password:
                    # Stage 1: Send OTP
                    otp_code = generate_otp()
                    EmailOTP.objects.create(user=user, otp=otp_code)
                    send_email(user,"Your OTP Code", "Use the code below to reset your password", code=otp_code)  # Your email utility
                    return Response({"detail": "OTP sent to your email.", "otp": otp_code}, status=status.HTTP_200_OK)
                elif otp and not new_password:
                    # Stage 2: Verify OTP only
                    return Response({"detail": "OTP is valid. You can now reset your password."}, status=status.HTTP_200_OK)
                elif otp and new_password:
                    # Stage 3: Reset password
                    serializer.save()
                    return Response({"detail": "Password has been reset successfully."}, status=status.HTTP_200_OK)
            print(serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# authenticated user reset password
class ChangePasswordView(APIView):
    permission_classes = [IsTrader]
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'old password': openapi.Schema(type=openapi.TYPE_STRING),
                'new password': openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=['old password', 'new password']
        ),
        responses={201: openapi.Response(
            description="Password changed successfully!",
            schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                'message': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
            })
        )}
    )

    def post(self, request):
        user = request.user
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not old_password or not new_password:
            return Response({
                "status": "error",
                "message": "Old and new password are required."
            }, status=400)

        if not user.check_password(old_password):
            return Response({
                "status": "error",
                "message": "Old password is incorrect."
            }, status=400)

        user.set_password(new_password)
        user.save()
        
        send_email(user,"Password Changed!", "Your password has been reset!")

        return Response({
            "status": "success",
            "message": "Password changed successfully."
        }, status=200)
    

# parners and admin signin
class SigninView(APIView): 
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'username': openapi.Schema(type=openapi.TYPE_STRING),
                'password': openapi.Schema(type=openapi.TYPE_STRING),
                'user_type': openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=['username', 'password', 'user_type']
        ),
        responses={201: openapi.Response(
            description="Sign In successful!",
            schema=openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                'message': openapi.Schema(type=openapi.TYPE_STRING),
                'status': openapi.Schema(type=openapi.TYPE_INTEGER),
            })
        )}
    )
    def post(self, request):
        login_input = request.data.get('username')  # Can be username or email
        password = request.data.get('password')
        expected_user_type = request.data.get('user_type')

        if not login_input or not password or not expected_user_type:
            return Response({'detail': 'Username/email, password and user type required.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Find user by email or username
        user = Users.objects.filter(email=login_input).first() or Users.objects.filter(username=login_input).first()

        if user and user.check_password(password):
            if not user.is_email_verified:
                return Response({'detail': 'Email not verified.'}, status=status.HTTP_403_FORBIDDEN)
            
            if user.user_type != expected_user_type:
               return Response({'detail': f'User is not of type {expected_user_type}.'},
                               status=status.HTTP_403_FORBIDDEN)
            tokens = get_tokens_for_user(user)
            return Response({
                'detail': 'Login successful.',
                'tokens': tokens
            })
        else:
            return Response({'detail': 'Invalid credentials.'}, status=status.HTTP_401_UNAUTHORIZED)
  
class SetPinView(APIView):
    permission_classes = [IsTrader]

    def post(self, request):
        user = request.user
        if user.user_type != 'trader':
            return Response({'detail': 'Only trader can set a PIN.'}, status=status.HTTP_403_FORBIDDEN)

        pin_set = bool(user.pin_hash and user.pin_hash.strip() != "")
        if pin_set:
             email = request.user.email
             otp = request.data.get('otp')
             new_pin = request.data.get('pin')
                 # Step 1: Send OTP
             if email and not otp:
                 raw_otp = generate_otp()
                 request.session['otp'] = raw_otp
                 request.session['email'] = email
                 request.session.modified = True
                 # Send OTP via email here in real use
                 send_email(user,"Your OTP Code", "Use the code below to set your pin", code=raw_otp)
                 return Response({'detail': f'OTP sent to {email}', 'otp': raw_otp})
                 # Step 2: Verify OTP
             if not otp:
                 return Response({'detail': 'OTP is required.'}, status=status.HTTP_400_BAD_REQUEST)
             if otp != request.session.get('otp'):
                 return Response({'detail': 'Invalid OTP.'}, status=status.HTTP_403_FORBIDDEN)
             if not new_pin:
                 return Response({"detail": 'Enter a new pin'}, status=status.HTTP_400_BAD_REQUEST)
                 # Step 3: Reset PIN
             user = request.user
             user.pin_hash = set_user_pin(new_pin)
             user.save()
                 # Step 4: Clear session
             request.session.pop('otp', None)
             request.session.pop('email', None)
             return Response({'detail': 'Your withdrawal PIN has been successfully reset.'}, status=status.HTTP_200_OK)
     
        pin = request.data.get('transaction_pin')
        if not pin or len(pin) < 4 or not pin.isdigit():
           return Response({'detail': 'PIN must be at least 4 digits.'}, status=status.HTTP_400_BAD_REQUEST)

        encrypted_pin = set_user_pin(pin)
        user.pin_hash = encrypted_pin
        user.save()
    
        return Response({'detail': 'PIN set successfully.'})


class UpdateProfileView(APIView):
    permission_classes = [IsTrader]
    parser_classes = [MultiPartParser, FormParser, JSONParser]  # for handling file uploads

    def patch(self, request):
        user = request.user

        # Update basic fields
        username = request.data.get('username')
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        # email = request.data.get('email')
        profile_picture = request.data.get('profile_picture')  # optional

        # Update fields only if they are present
        if username:
            user.username = username
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if profile_picture:
          if profile_picture.content_type not in ['image/jpeg', 'image/png']:
              return Response({'detail': 'Only JPEG or PNG images are allowed.'}, status=400)
          if profile_picture.size > 2 * 1024 * 1024:
              return Response({'detail': 'Max file size is 2MB.'}, status=400)
          if user.profile_picture and hasattr(user.profile_picture, 'path'):
              if os.path.isfile(user.profile_picture.path):
                  user.profile_picture.delete(save=False)
          user.profile_picture = profile_picture

        user.save()
        return Response({'detail': 'Profile updated successfully.'}, status=status.HTTP_200_OK)



class DetailsView(APIView):
    permission_classes = [IsTrader]

    def get(self, request):
        user = request.user
        serializer = ProfileSerializer(user)
        has_pin = bool(user.pin_hash and user.pin_hash.strip())
        return Response({"user_details":serializer.data, "has_pin" : has_pin})
# class TransactionPagination(PageNumberPagination):
#     page_size = 10

# class UserTransactionHistoryView(APIView):
#     permission_classes = [IsPartner]

#     def get(self, request):
#         user = request.user
        
#         # Filters
#         transaction_type = request.query_params.get('transaction_type')
#         status = request.query_params.get('status')
#         date_from = request.query_params.get('date_from')
#         date_to = request.query_params.get('date_to')

#         # Base queryset
#         transactions = Transaction.objects.filter(user=user).order_by('-created_at')

#         # Apply filters
#         if transaction_type:
#             transactions = transactions.filter(transaction_type=transaction_type)

#         if status:
#             transactions = transactions.filter(status=status)

#         if date_from:
#             transactions = transactions.filter(created_at__date__gte=date_from)

#         if date_to:
#             transactions = transactions.filter(created_at__date__lte=date_to)

#         # PAGINATION
#         paginator = TransactionPagination()
#         paginated_transactions = paginator.paginate_queryset(transactions, request)

#         serializer = TransactionSerializer(paginated_transactions, many=True)

#         # SUMMARY PART
#         total_funds = Transaction.objects.filter(user=user, transaction_type='fund', status='completed').aggregate(total=Sum('amount'))['total'] or 0
#         total_withdrawals = Transaction.objects.filter(user=user, transaction_type='withdraw', status='completed').aggregate(total=Sum('amount'))['total'] or 0
#         total_investments = Transaction.objects.filter(user=user, transaction_type='investment', status='completed').aggregate(total=Sum('amount'))['total'] or 0
#         total_roi_earned = Transaction.objects.filter(user=user, transaction_type='roi', status='completed').aggregate(total=Sum('amount'))['total'] or 0

        
#         # wallet = getattr(user, 'wallet', None)
#         # available_balance = wallet.balance if wallet else 0

#         summary = {
#             # 'total_funds': total_funds,
#             # 'total_withdrawals': total_withdrawals,
#             # 'total_investments': total_investments,
#             # 'total_roi_earned': total_roi_earned,
#             # 'available_balance':available_balance
#         }

#         return paginator.get_paginated_response({
#             'summary': summary,
#             'transactions': serializer.data
#         })
    

# class AllTransactionsPagination(PageNumberPagination):
#     page_size = 20

# class AllTransactionsView(APIView):
#     permission_classes = [IsAdmin]

#     def get(self, request):
#         user = request.user

#         transactions = Transaction.objects.all() if user.is_superuser else Transaction.objects.filter(user=user)

#         # Admin-only filters
#         if user.is_superuser:
#             user_id = request.query_params.get('user_id')
#             transaction_type = request.query_params.get('transaction_type')
#             status_filter = request.query_params.get('status')
#             from_date = request.query_params.get('from_date')
#             to_date = request.query_params.get('to_date')
#             search = request.query_params.get('search')
#             sort_by = request.query_params.get('sort_by')  # <-- NEW

#             if user_id:
#                 transactions = transactions.filter(user__id=user_id)
#             if transaction_type:
#                 transactions = transactions.filter(transaction_type=transaction_type)
#             if status_filter:
#                 transactions = transactions.filter(status=status_filter)
#             if from_date:
#                 try:
#                     from_date_obj = datetime.strptime(from_date, "%Y-%m-%d")
#                     transactions = transactions.filter(created_at__date__gte=from_date_obj)
#                 except ValueError:
#                     return Response({"detail": "Invalid from_date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
#             if to_date:
#                 try:
#                     to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
#                     transactions = transactions.filter(created_at__date__lte=to_date_obj)
#                 except ValueError:
#                     return Response({"detail": "Invalid to_date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
#             if search:
#                 transactions = transactions.filter(
#                     Q(order_id__icontains=search) |
#                     Q(amount__icontains=search)
#                 )

#             # Handle Sorting
#             if sort_by == 'newest':
#                 transactions = transactions.order_by('-created_at')
#             elif sort_by == 'oldest':
#                 transactions = transactions.order_by('created_at')
#             elif sort_by == 'amount_high':
#                 transactions = transactions.order_by('-amount')
#             elif sort_by == 'amount_low':
#                 transactions = transactions.order_by('amount')
#             else:
#                 transactions = transactions.order_by('-created_at')  # Default

#         else:
#             transactions = transactions.order_by('-created_at')  # Normal users, default newest first

#         # Pagination
#         paginator = AllTransactionsPagination()
#         paginated_transactions = paginator.paginate_queryset(transactions, request)

#         serializer = TransactionSerializer(paginated_transactions, many=True)

#         return paginator.get_paginated_response(serializer.data)

# class NotificationListView(APIView):
#     permission_classes = [IsPartner]

#     def get(self, request):
#         notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
#         serializer = NotificationSerializer(notifications, many=True)
#         return Response(serializer.data)

# class NotificationMarkAsReadView(APIView):
#     permission_classes = [IsPartner]

#     def post(self, request, pk):
#         try:
#             notification = Notification.objects.get(pk=pk, user=request.user)
#             notification.is_read = True
#             notification.save()
#             return Response({"detail": "Notification marked as read."})
#         except Notification.DoesNotExist:
#             return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)
        
# class ApproveWithdrawalView(APIView):
#     permission_classes = [IsAdmin]  # or a custom IsStaff permission

#     def post(self, request, transaction_id):
#         action = request.data.get('action')  # 'approve' or 'reject'
#         note = request.data.get('note')

#         try:
#             tx = Transaction.objects.get(reference=transaction_id, transaction_type='withdraw', status='pending')
#         except Transaction.DoesNotExist:
#             return Response({'detail': 'Withdrawal not found or already processed.'}, status=404)

#         if action == 'approve':
#             tx.status = 'approved'
#             tx.save()
#             # Trigger payment webhook or internal payout function here
#             # e.g. send_to_payment_provider(tx)
#             Notification.objects.create(
#                 user=tx.user,
#                 title="Withdrawal Approved",
#                 message=f"Your withdrawal of {tx.amount} was approved.",
#                 event_type="withdraw",
#             )

#         elif action == 'reject':
#             tx.status = 'rejected'
#             tx.admin_note = note
#             tx.save()

#             # Refund the wallet
#             tx.user.wallet.balance += tx.amount
#             tx.user.wallet.save()

#             Notification.objects.create(
#                 user=tx.user,
#                 title="Withdrawal Rejected",
#                 message=f"Your withdrawal of {tx.amount} was rejected. Reason: {note}",
#                 event_type="withdraw",
#             )
#         else:
#             return Response({'detail': 'Invalid action.'}, status=400)

#         return Response({'detail': f'Withdrawal {action}ed successfully.'})


class CreateQuoteView(APIView):
    permission_classes = [IsTrader]

    def post(self, request):
        try:
            payload = {
                "sourceAmount": str(request.data.get("source_amount")),
                "sourceCurrencyCode": request.data.get("source_currency"),
                "destinationCurrencyCode": request.data.get("destination_currency"),
                "countryCode": request.data.get("country_code", "NG"),  # fallback
            }
            response = requests.post(f"{MELD_BASE}/quote", headers=get_headers(), json=payload)
            return Response(response.json(), status=response.status_code)
        except Exception as e:
            return Response({"detail": str(e)}, status=500)


class CreatePaymentView(APIView):
    permission_classes = [IsTrader]

    def post(self, request):
        try:
            payload = {
                "quoteId": request.data.get("quote_id"),
                "callbackUrl": request.data.get("callback_url"),  # e.g. https://yourapp.com/api/meld/webhook/
            }
            response = requests.post(f"{MELD_BASE}/payment", headers=get_headers(), json=payload)
            return Response(response.json(), status=response.status_code)
        except Exception as e:
            return Response({"detail": str(e)}, status=500)


# class MeldWebhookView(APIView):
#     permission_classes = [IsTrader]  # You can restrict this if needed

#     def post(self, request):
#         # Validate signature
#         raw_body = request.body
#         received_signature = request.headers.get("X-Meld-Signature")

#         computed_signature = hmac.new(
#             key=MELD_WEBHOOK_SECRET.encode(),
#             msg=raw_body,
#             digestmod=hashlib.sha256,
#         ).hexdigest()

#         if not hmac.compare_digest(received_signature, computed_signature):
#             return Response({"detail": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

#         data = request.data
#         event_type = data.get("event")
#         payment_id = data.get("data", {}).get("paymentId")
#         status_ = data.get("data", {}).get("status")

#         # TODO: update DB, notify React Native app
#         print(f"[MELD Webhook] Event: {event_type}, Payment ID: {payment_id}, Status: {status_}")

#         return Response({"detail": "Webhook received"}, status=200)
    
class UserTransactionHistory(APIView):
    permission_classes = [IsTrader]

    def get(self, request):
        transactions = (
            Transaction.objects.filter(user=request.user)
            .order_by('-created_at')
        )
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)
    
# views.py
class OnrampWebhookView(APIView):
    permission_classes = [IsTrader]

    def post(self, request):
        data = request.data
        # Example mapping – modify based on Onramp format
        tx_id = data.get("transactionId")
        user_id = data.get("metadata", {}).get("user_id")  # optional if attached
        user = Users.objects.get(id=user_id)

        Transaction.objects.update_or_create(
            transaction_id=tx_id,
            defaults={
                "user": user,
                "platform": "onramp",
                "type": data.get("type", "buy"),
                "crypto_code": data.get("coinCode"),
                "fiat_code": data.get("fiatCode"),
                "crypto_amount": data.get("cryptoAmount", 0),
                "fiat_amount": data.get("fiatAmount", 0),
                "status": data.get("status"),
                "created_at": data.get("timestamp"),
            },
        )
        return Response({"detail": "onramp webhook received"}, status=200)


class MeldWebhookView(APIView):
    permission_classes = [IsTrader]

    def post(self, request):
        data = request.data
        tx_id = data.get("data", {}).get("paymentId")
        external_id = data.get("data", {}).get("externalTransactionId")
        user = Users.objects.get(id=external_id)

        Transaction.objects.update_or_create(
            transaction_id=tx_id,
            defaults={
                "user": user,
                "platform": "meld",
                "type": data.get("data", {}).get("type", "buy"),
                "crypto_code": data.get("data", {}).get("destinationCurrencyCode"),
                "fiat_code": data.get("data", {}).get("sourceCurrencyCode"),
                "crypto_amount": data.get("data", {}).get("destinationAmount", 0),
                "fiat_amount": data.get("data", {}).get("sourceAmount", 0),
                "status": data.get("data", {}).get("status"),
                "created_at": data.get("data", {}).get("createdAt"),
            },
        )
        return Response({"detail": "meld webhook received"}, status=200)
