from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import random
import uuid
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User
from decimal import Decimal


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

    def create_superuser(self, email, password=None, **extra_fields):
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


# class Users(AbstractBaseUser, PermissionsMixin):
#       USER_TYPE_CHOICES = (
#         ('admin', 'Admin'),
#         # ('driver', 'Driver'),
#         ('trader', 'Trader'),
#     )
#       email = models.EmailField(max_length=255, unique=True)
#       username = models.CharField(max_length=150,blank=True,null=True)
#       first_name = models.CharField(max_length=150, blank=True)
#       last_name = models.CharField(max_length=150, blank=True)
#       password = models.CharField(max_length=128)
#       profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
#       user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default="")
#       username = models.CharField(max_length=150,blank=True,null=True)  
#       is_active = models.BooleanField(default=True)
#       is_staff = models.BooleanField(default=False)  # Required for admin access
#       is_superuser = models.BooleanField(default=False)
#       is_email_verified = models.BooleanField(default=False)
#       unverified_email = models.EmailField(null=True, blank=True, unique=True)
#       email_otp = models.CharField(max_length=4, blank=True, null=True)
#       otp_created_at = models.DateTimeField(blank=True, null=True)
#       reset_otp = models.CharField(max_length=4, blank=True, null=True)
#       reset_otp_expiry = models.DateTimeField(null=True, blank=True)
#       pin_hash = models.CharField(max_length=128, blank=True, null=True) 
#       referral_code = models.CharField(max_length=10, unique=True, blank=True, null=True)
#       referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals')
#       pin_hash = models.CharField(max_length=128, blank=True, null=True) 
#       phone_number = models.PositiveIntegerField(null=True, blank=True )

      
#       def set_pin(self, raw_pin):
#           self.pin_hash = make_password(raw_pin)
  
#       def check_pin(self, raw_pin):
#           return check_password(raw_pin, self.pin_hash)
      
#       def save(self, *args, **kwargs):
#         if not self.referral_code:
#             self.referral_code = str(uuid.uuid4()).replace('-', '')[:10].upper()
#         super().save(*args, **kwargs)
  
#       objects = UserManager()
  
#       USERNAME_FIELD = 'email'
#       REQUIRED_FIELDS = ['username']
  
#       def __str__(self):
#           return self.email
      

class Users(AbstractBaseUser, PermissionsMixin):
    USER_TYPE_CHOICES = (
        ('admin', 'Admin'),
        ('trader', 'Trader'),
    )

    email = models.EmailField(max_length=255, unique=True)
    username = models.CharField(max_length=150, blank=True, null=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    password = models.CharField(max_length=128)
    profile_picture = models.ImageField(upload_to='profile_pics/', null=True, blank=True)

    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default="trader")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    unverified_email = models.EmailField(null=True, blank=True, unique=True)
    email_otp = models.CharField(max_length=4, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)

    reset_otp = models.CharField(max_length=4, blank=True, null=True)
    reset_otp_expiry = models.DateTimeField(null=True, blank=True)

    pin_hash = models.CharField(max_length=128, blank=True, null=True)

    referral_code = models.CharField(max_length=10, unique=True, blank=True, null=True)
    referred_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='referrals'
    )

    phone_number = models.CharField(max_length=20, null=True, blank=True)
    country = models.CharField(max_length=20, null=True, blank=True)

    def set_pin(self, raw_pin):
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin):
        return check_password(raw_pin, self.pin_hash)

    def save(self, *args, **kwargs):
        if not self.referral_code:
            code = str(uuid.uuid4()).replace('-', '')[:10].upper()
            while Users.objects.filter(referral_code=code).exists():
                code = str(uuid.uuid4()).replace('-', '')[:10].upper()
            self.referral_code = code
        super().save(*args, **kwargs)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # no extra required fields for createsuperuser

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


class Transaction(models.Model):
    """
    Comprehensive transaction model for tracking all crypto buy/sell/swap operations.
    Supports multiple providers: Meld, OnRamp, MoonPay, FinchPay, Changelly
    """
    
    # Provider Choices
    PROVIDER_CHOICES = [
        ('MELD', 'Meld'),
        ('ONRAMP', 'OnRamp'),
        ('MOONPAY', 'MoonPay'),
        ('FINCHPAY', 'FinchPay'),
        ('CHANGELLY', 'Changelly'),
    ]
    
    # Transaction Type Choices
    TYPE_CHOICES = [
        ('BUY', 'Buy Crypto'),
        ('SELL', 'Sell Crypto'),
        ('SWAP', 'Swap Crypto'),
    ]
    
    # Status Choices
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
        ('EXPIRED', 'Expired'),
    ]
    
    # ============================================================================
    # CORE FIELDS
    # ============================================================================
    user = models.ForeignKey(
        Users, 
        on_delete=models.CASCADE, 
        related_name='crypto_transactions',
        help_text="User who initiated the transaction"
    )
    
    provider = models.CharField(
        max_length=20, 
        choices=PROVIDER_CHOICES,
        help_text="Payment/Exchange provider used"
    )
    
    transaction_type = models.CharField(
        max_length=10, 
        choices=TYPE_CHOICES,
        help_text="Type of transaction: BUY, SELL, or SWAP"
    )
    
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='PENDING',
        db_index=True,
        help_text="Current status of the transaction"
    )
    
    # ============================================================================
    # TRANSACTION IDENTIFIERS
    # ============================================================================
    transaction_id = models.CharField(
        max_length=255, 
        unique=True,
        db_index=True,
        help_text="Our internal transaction ID"
    )
    
    provider_transaction_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        db_index=True,
        help_text="Provider's transaction ID (e.g., urlHash, externalId)"
    )
    
    provider_reference_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Provider's reference ID (e.g., OnRamp referenceId)"
    )
    
    # ============================================================================
    # CURRENCY & AMOUNTS
    # ============================================================================
    source_currency = models.CharField(
        max_length=20,
        help_text="Source currency code (e.g., USD, BTC)"
    )
    
    source_amount = models.DecimalField(
        max_digits=20, 
        decimal_places=8,
        help_text="Amount of source currency"
    )
    
    destination_currency = models.CharField(
        max_length=20,
        help_text="Destination currency code (e.g., USDT, EUR)"
    )
    
    destination_amount = models.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        null=True, 
        blank=True,
        help_text="Amount of destination currency received/expected"
    )
    
    # ============================================================================
    # PRICING & FEES
    # ============================================================================
    exchange_rate = models.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        null=True, 
        blank=True,
        help_text="Exchange rate at time of transaction"
    )
    
    total_fees = models.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        default=Decimal('0.00000000'),
        help_text="Total fees charged (all fees combined)"
    )
    
    network_fee = models.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        default=Decimal('0.00000000'),
        help_text="Blockchain network/gas fee"
    )
    
    service_fee = models.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        default=Decimal('0.00000000'),
        help_text="Provider service fee"
    )
    
    # ============================================================================
    # PROFIT TRACKING (for future features)
    # ============================================================================
    profit_loss = models.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        null=True, 
        blank=True,
        help_text="Calculated profit/loss (for future portfolio tracking)"
    )
    
    profit_percentage = models.DecimalField(
        max_digits=10, 
        decimal_places=4, 
        null=True, 
        blank=True,
        help_text="Profit/loss percentage (for future portfolio tracking)"
    )
    
    # ============================================================================
    # BLOCKCHAIN & NETWORK DETAILS
    # ============================================================================
    network = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        help_text="Blockchain network (e.g., TRC20, ERC20, BEP20)"
    )
    
    wallet_address = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Destination wallet address"
    )
    
    transaction_hash = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Blockchain transaction hash (if available)"
    )
    
    # ============================================================================
    # PAYMENT METHOD
    # ============================================================================
    payment_method = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Payment method used (e.g., card, bank_transfer, SEPA)"
    )
    
    # ============================================================================
    # ADDITIONAL METADATA
    # ============================================================================
    provider_data = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Raw data from provider (webhooks, API responses)"
    )
    
    widget_url = models.URLField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text="URL of the payment/swap widget (if applicable)"
    )
    
    failure_reason = models.TextField(
        blank=True, 
        null=True,
        help_text="Reason for failure (if status is FAILED)"
    )
    
    # ============================================================================
    # TIMESTAMPS
    # ============================================================================
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When transaction was created"
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update time"
    )
    
    completed_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="When transaction was completed"
    )
    
    # ============================================================================
    # META & METHODS
    # ============================================================================
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['transaction_id']),
            models.Index(fields=['provider_transaction_id']),
            models.Index(fields=['status', '-created_at']),
        ]
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
    
    def __str__(self):
        return f"{self.transaction_type} - {self.source_currency} to {self.destination_currency} ({self.status})"
    
    def get_display_status(self):
        """Get user-friendly status message"""
        status_messages = {
            'PENDING': 'Transaction is being processed',
            'PROCESSING': 'Transaction in progress',
            'COMPLETED': 'Transaction completed successfully',
            'FAILED': 'Transaction failed',
            'CANCELLED': 'Transaction was cancelled',
            'EXPIRED': 'Transaction expired',
        }
        return status_messages.get(self.status, 'Unknown status')
    
    def is_profitable(self):
        """Check if transaction resulted in profit (for future use)"""
        if self.profit_loss:
            return self.profit_loss > 0
        return None
    
    @property
    def total_cost(self):
        """Calculate total cost including fees"""
        return self.source_amount + self.total_fees
    
    @property
    def net_amount(self):
        """Calculate net amount after fees"""
        if self.destination_amount:
            return self.destination_amount - self.total_fees
        return None


# ============================================================================
# TRANSACTION STATISTICS MODEL (for caching stats)
# ============================================================================
class TransactionStats(models.Model):
    """
    Cached transaction statistics per user.
    Updated periodically or on transaction completion.
    """
    user = models.OneToOneField(
        Users, 
        on_delete=models.CASCADE, 
        related_name='transaction_stats'
    )
    
    # Total counts
    total_transactions = models.IntegerField(default=0)
    completed_transactions = models.IntegerField(default=0)
    failed_transactions = models.IntegerField(default=0)
    pending_transactions = models.IntegerField(default=0)
    
    # Transaction types
    total_buys = models.IntegerField(default=0)
    total_sells = models.IntegerField(default=0)
    total_swaps = models.IntegerField(default=0)
    
    # Volume (in USD equivalent for now)
    total_volume_usd = models.DecimalField(
        max_digits=20, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    
    total_fees_paid = models.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        default=Decimal('0.00000000')
    )
    
    # Profit tracking (for future)
    total_profit_loss = models.DecimalField(
        max_digits=20, 
        decimal_places=8, 
        default=Decimal('0.00000000')
    )
    
    # Timestamps
    last_transaction_date = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Transaction Statistics'
        verbose_name_plural = 'Transaction Statistics'
    
    def __str__(self):
        return f"Stats for {self.user.email}"
    
    def update_stats(self):
        """
        Recalculate statistics from actual transactions.
        Call this after each transaction completion or periodically.
        """
        from django.db.models import Count, Sum, Q
        from decimal import Decimal
        
        user_txns = Transaction.objects.filter(user=self.user)
        
        # Count totals
        self.total_transactions = user_txns.count()
        self.completed_transactions = user_txns.filter(status='COMPLETED').count()
        self.failed_transactions = user_txns.filter(status='FAILED').count()
        self.pending_transactions = user_txns.filter(
            status__in=['PENDING', 'PROCESSING']
        ).count()
        
        # Count by type
        self.total_buys = user_txns.filter(transaction_type='BUY').count()
        self.total_sells = user_txns.filter(transaction_type='SELL').count()
        self.total_swaps = user_txns.filter(transaction_type='SWAP').count()
        
        # Calculate total fees (only completed transactions)
        fees_sum = user_txns.filter(status='COMPLETED').aggregate(
            total=Sum('total_fees')
        )['total']
        self.total_fees_paid = fees_sum or Decimal('0.00000000')
        
        # Get last transaction date
        last_txn = user_txns.order_by('-created_at').first()
        if last_txn:
            self.last_transaction_date = last_txn.created_at
        
        self.save()