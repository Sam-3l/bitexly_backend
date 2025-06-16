from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import random
import uuid
from django.contrib.auth.hashers import make_password, check_password

class UserManager(BaseUserManager):
    def create_user(self, email, password=None,**extra_fields):
        if not email:
            raise ValueError('The Email field is required')
    # if not username:
    #     raise ValueError('The Username field is required')

        email = self.normalize_email(email)
        user = self.model(email=email,**extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('username', username)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('user_type', 'admin')
        extra_fields.setdefault('is_email_verified', True)

        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class Users(AbstractBaseUser, PermissionsMixin):
      USER_TYPE_CHOICES = (
        ('admin', 'Admin'),
        # ('driver', 'Driver'),
        ('trader', 'Trader'),
    )
      email = models.EmailField(max_length=255, unique=True)
      username = models.CharField(max_length=150,blank=True,null=False)
      first_name = models.CharField(max_length=150, blank=True)
      last_name = models.CharField(max_length=150, blank=True)
      password = models.CharField(max_length=128)
      profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
      user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default="")  
      is_active = models.BooleanField(default=True)
      is_staff = models.BooleanField(default=False)  # Required for admin access
      is_superuser = models.BooleanField(default=False)
      is_email_verified = models.BooleanField(default=False)
      unverified_email = models.EmailField(null=True, blank=True, unique=True)
      email_otp = models.CharField(max_length=4, blank=True, null=True)
      otp_created_at = models.DateTimeField(blank=True, null=True)
      reset_otp = models.CharField(max_length=4, blank=True, null=True)
      reset_otp_expiry = models.DateTimeField(null=True, blank=True)
      pin_hash = models.CharField(max_length=128, blank=True, null=True) 

      
      def set_pin(self, raw_pin):
          self.pin_hash = make_password(raw_pin)
  
      def check_pin(self, raw_pin):
          return check_password(raw_pin, self.pin_hash)
  
      objects = UserManager()
  
      USERNAME_FIELD = 'email'
      REQUIRED_FIELDS = ['username']
  
      def __str__(self):
          return self.email
    
class EmailOTP(models.Model):
    user = models.ForeignKey(Users, on_delete=models.CASCADE)
    otp = models.CharField(max_length=4)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.otp}"


class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('fund', 'Funding'),
        ('withdraw', 'Withdrawal'),
        ('investment', 'Investment'),
        ('roi', 'Return On Investment'),
        ('system', 'System Notification'),
    )

    user = models.ForeignKey(Users, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    event_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, default='system')
    is_read = models.BooleanField(default=False)
    from_user = models.CharField(max_length=255, null=True, blank=True)
    to_user = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    available_balance_at_time = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    bank_name = models.CharField(max_length=100, null=True, blank=True)
    account_number = models.CharField(max_length=30, null=True, blank=True)
    account_name = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.title}"