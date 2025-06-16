from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import Users, Driver,OrderDeliveryConfirmation, Notification, EmailOTP
from datetime import timedelta
from django.utils import timezone

class SignUpSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(required=False,allow_blank=True)
    last_name = serializers.CharField(required=False,allow_blank=True) 

    class Meta:
        model = Users
        fields = ['email','first_name', 'last_name']
        extra_kwargs = {
            'email': {'validators': []}
        }

    def validate_email(self, value):
        existing_user = Users.objects.filter(email=value).first()
        if existing_user and existing_user.is_email_verified:
            raise serializers.ValidationError("A user with this email is already verified.")
        return value

    def create(self, validated_data):
        user = Users.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            user_type='partner',
            is_email_verified=False
        )
        print("saved")
        return user
    
class CompleteRegistrationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True, required=False)

    def validate(self, data):
        try:
            user = Users.objects.get(email=data['email'])
        except Users.DoesNotExist:
            raise serializers.ValidationError("User not found.")

        if not user.is_email_verified:
            raise serializers.ValidationError({"error":"Email is not verified yet."})
        
        if user.username and user.has_usable_password():
            raise serializers.ValidationError({"detail": "Registration is already completed."})

        if 'username' in data:
            if Users.objects.filter(username=data['username']).exclude(pk=user.pk).exists():
                raise serializers.ValidationError("Username already taken.")
            
            
        try:
            validate_password(data['password'], user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})

        data['user'] = user
        return data

    def save(self):
        user = self.validated_data['user']
        updated_fields = []

        if 'username' in self.validated_data:
            user.username = self.validated_data['username']
            updated_fields.append('username')

        if 'password' in self.validated_data:
            user.set_password(self.validated_data['password'])
            updated_fields.append('password')

        user.save(update_fields=updated_fields)
        return user
    

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Users
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id','user','title','from_user','to_user','message','event_type','is_read','created_at','available_balance_at_time', 'payment_method', 'bank_name', 'account_number','account_name']
        read_only_fields = ['id', 'created_at', 'user']
    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.event_type not in ['fund', 'withdraw']:
            data.pop('from_user', None)
            data.pop('to_user', None)
        if instance.event_type in ['fund', 'withdraw']:
            data.pop('order_id', None)
        if instance.event_type not in ['fund', 'withdraw', 'roi', 'investment']:
            data.pop('available_balance_at_time', None)
        
        # Hide bank details if not a withdrawal
        if instance.event_type != 'withdraw':
            data.pop('bank_name', None)
            data.pop('account_number', None)
            data.pop('account_name', None)
        return data
class ResetPasswordOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(required=False,allow_blank=True)
    new_password = serializers.CharField(write_only=True, required=False,allow_blank=True)

    def validate(self, data):
        email = data.get('email')
        otp = data.get('otp')
        new_password = data.get('new_password')

        # Step 1: Email is always required
        try:
            user = Users.objects.get(email=email)
        except Users.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})

        data['user'] = user

        # Step 2: If OTP is provided, verify it
        if otp:
            try:
                otp_entry = EmailOTP.objects.filter(user=user, otp=otp).latest('created_at')
            except EmailOTP.DoesNotExist:
                raise serializers.ValidationError({"otp": "Invalid OTP."})

            if timezone.now() - otp_entry.created_at > timedelta(minutes=10):
                raise serializers.ValidationError({"otp": "OTP has expired."})

            data['otp_entry'] = otp_entry

        # Step 3: If new password is provided, ensure OTP is valid and password is strong
        if new_password:
            if not otp:
                raise serializers.ValidationError({"otp": "OTP is required to set a new password."})
            try:
                validate_password(new_password, user=user)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"new_password": list(e.messages)})

        return data

    def save(self):
        user = self.validated_data['user']
        new_password = self.validated_data.get('new_password')
        otp_entry = self.validated_data.get('otp_entry')

        # If password is being reset
        if new_password:
            user.set_password(new_password)
            user.save()

            # Invalidate OTP after use
            if otp_entry:
                otp_entry.delete()

        return user
      
class EmailVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField()
    password = serializers.CharField(write_only=True)


class RequestPasswordResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not Users.objects.filter(email=value).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return value
    
    # def save(self):
    #     email = self.validated_data['email']
    #     user = Users.objects.get(email=email)
