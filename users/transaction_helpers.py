import logging
import hashlib
import time
from decimal import Decimal
from django.utils import timezone
from .models import Transaction
from django.core.cache import cache

logger = logging.getLogger(__name__)


# ============================================================================
# TRANSACTION CREATION HELPER
# ============================================================================
def create_transaction_record(
    user,
    provider,
    transaction_type,
    source_currency,
    source_amount,
    destination_currency,
    destination_amount=None,
    exchange_rate=None,
    total_fees=None,
    network_fee=None,
    service_fee=None,
    network=None,
    wallet_address=None,
    payment_method=None,
    widget_url=None,
    provider_transaction_id=None,
    provider_reference_id=None,
    transaction_hash=None,
    provider_data=None,
):
    """
    Create a new transaction record in the database.
    
    Args:
        user: User instance (must be authenticated)
        provider: Provider name (MELD, ONRAMP, MOONPAY, FINCHPAY, CHANGELLY)
        transaction_type: Type (BUY, SELL, SWAP)
        source_currency: Source currency code
        source_amount: Source amount
        destination_currency: Destination currency code
        destination_amount: Destination amount (optional)
        exchange_rate: Exchange rate (optional)
        total_fees: Total fees (optional)
        network_fee: Network/gas fee (optional)
        service_fee: Service fee (optional)
        network: Blockchain network (optional)
        wallet_address: Destination wallet (optional)
        payment_method: Payment method (optional)
        widget_url: Widget URL (optional)
        provider_transaction_id: Provider's transaction ID (optional)
        provider_reference_id: Provider's reference ID (optional)
        transaction_hash: Blockchain hash (optional)
        provider_data: Additional data as dict (optional)
    
    Returns:
        Transaction instance
    """
    try:
        # Generate unique internal transaction ID
        timestamp = int(time.time() * 1000)
        unique_string = f"{user.id}_{provider}_{timestamp}_{source_currency}_{destination_currency}"
        transaction_id = f"txn_{provider.lower()}_{hashlib.md5(unique_string.encode()).hexdigest()[:16]}"
        
        # Convert to Decimal if needed
        if source_amount and not isinstance(source_amount, Decimal):
            source_amount = Decimal(str(source_amount))
        
        if destination_amount and not isinstance(destination_amount, Decimal):
            destination_amount = Decimal(str(destination_amount))
        
        if exchange_rate and not isinstance(exchange_rate, Decimal):
            exchange_rate = Decimal(str(exchange_rate))
        
        if total_fees and not isinstance(total_fees, Decimal):
            total_fees = Decimal(str(total_fees))
        elif total_fees is None:
            total_fees = Decimal('0.00000000')
        
        if network_fee and not isinstance(network_fee, Decimal):
            network_fee = Decimal(str(network_fee))
        elif network_fee is None:
            network_fee = Decimal('0.00000000')
        
        if service_fee and not isinstance(service_fee, Decimal):
            service_fee = Decimal(str(service_fee))
        elif service_fee is None:
            service_fee = Decimal('0.00000000')
        
        # Create transaction
        transaction = Transaction.objects.create(
            user=user,
            provider=provider.upper(),
            transaction_type=transaction_type.upper(),
            transaction_id=transaction_id,
            provider_transaction_id=provider_transaction_id,
            provider_reference_id=provider_reference_id,
            source_currency=source_currency.upper(),
            source_amount=source_amount,
            destination_currency=destination_currency.upper(),
            destination_amount=destination_amount,
            exchange_rate=exchange_rate,
            total_fees=total_fees,
            network_fee=network_fee,
            service_fee=service_fee,
            network=network,
            wallet_address=wallet_address,
            transaction_hash=transaction_hash,
            payment_method=payment_method,
            widget_url=widget_url,
            provider_data=provider_data or {},
            status='PENDING',  # Always start as PENDING
        )
        
        logger.info(f"✅ Created transaction record: {transaction_id} for user {user.email}")
        
        # Also store in cache for webhook lookups
        cache_key = f"db_txn_{transaction_id}"
        cache.set(cache_key, transaction.id, timeout=86400)  # 24 hours
        
        return transaction
    
    except Exception as e:
        logger.error(f"❌ Failed to create transaction record: {str(e)}", exc_info=True)
        return None


# ============================================================================
# TRANSACTION UPDATE HELPER
# ============================================================================
def update_transaction_status(
    transaction_id=None,
    provider_transaction_id=None,
    status=None,
    destination_amount=None,
    transaction_hash=None,
    failure_reason=None,
    provider_data=None,
):
    """
    Update an existing transaction status (typically called from webhooks).
    
    Args:
        transaction_id: Our internal transaction ID
        provider_transaction_id: Provider's transaction ID (alternative lookup)
        status: New status (PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED, EXPIRED)
        destination_amount: Final destination amount (optional)
        transaction_hash: Blockchain transaction hash (optional)
        failure_reason: Reason for failure (optional)
        provider_data: Additional provider data (optional)
    
    Returns:
        Updated Transaction instance or None
    """
    try:
        # Find transaction
        transaction = None
        
        if transaction_id:
            try:
                transaction = Transaction.objects.get(transaction_id=transaction_id)
            except Transaction.DoesNotExist:
                logger.warning(f"Transaction not found by ID: {transaction_id}")
        
        if not transaction and provider_transaction_id:
            try:
                transaction = Transaction.objects.get(provider_transaction_id=provider_transaction_id)
            except Transaction.DoesNotExist:
                logger.warning(f"Transaction not found by provider ID: {provider_transaction_id}")
        
        if not transaction:
            logger.error(f"Transaction not found for update")
            return None
        
        # Update fields
        if status:
            transaction.status = status.upper()
        
        if destination_amount is not None:
            if not isinstance(destination_amount, Decimal):
                destination_amount = Decimal(str(destination_amount))
            transaction.destination_amount = destination_amount
        
        if transaction_hash:
            transaction.transaction_hash = transaction_hash
        
        if failure_reason:
            transaction.failure_reason = failure_reason
        
        if provider_data:
            # Merge with existing provider_data
            transaction.provider_data.update(provider_data)
        
        # Set completed_at if status is COMPLETED
        if status and status.upper() == 'COMPLETED' and not transaction.completed_at:
            transaction.completed_at = timezone.now()
        
        transaction.save()
        
        logger.info(f"✅ Updated transaction {transaction.transaction_id} to status {transaction.status}")
        
        return transaction
    
    except Exception as e:
        logger.error(f"❌ Failed to update transaction: {str(e)}", exc_info=True)
        return None


# ============================================================================
# FIND TRANSACTION HELPER
# ============================================================================
def find_transaction(
    transaction_id=None,
    provider_transaction_id=None,
    user=None,
):
    """
    Find a transaction by various identifiers.
    
    Args:
        transaction_id: Our internal transaction ID
        provider_transaction_id: Provider's transaction ID
        user: User instance (optional, for additional filtering)
    
    Returns:
        Transaction instance or None
    """
    try:
        filters = {}
        
        if user:
            filters['user'] = user
        
        if transaction_id:
            filters['transaction_id'] = transaction_id
        elif provider_transaction_id:
            filters['provider_transaction_id'] = provider_transaction_id
        else:
            logger.warning("No transaction identifier provided")
            return None
        
        transaction = Transaction.objects.get(**filters)
        return transaction
    
    except Transaction.DoesNotExist:
        logger.warning(f"Transaction not found with filters: {filters}")
        return None
    except Transaction.MultipleObjectsReturned:
        logger.error(f"Multiple transactions found with filters: {filters}")
        return Transaction.objects.filter(**filters).first()
    except Exception as e:
        logger.error(f"Error finding transaction: {str(e)}", exc_info=True)
        return None


# ============================================================================
# EXTRACT TRANSACTION DATA FROM QUOTE HELPER
# ============================================================================
def extract_transaction_data_from_quote(quote_data, provider):
    """
    Extract common transaction fields from a quote response.
    Different providers have different response structures.
    
    Args:
        quote_data: Quote data from provider API
        provider: Provider name (MELD, ONRAMP, MOONPAY, FINCHPAY)
    
    Returns:
        dict with extracted fields
    """
    extracted = {}
    
    try:
        if provider.upper() == 'ONRAMP':
            # OnRamp quote structure
            extracted['destination_amount'] = quote_data.get('quantity') or quote_data.get('fiatAmount')
            extracted['exchange_rate'] = quote_data.get('rate')
            extracted['total_fees'] = Decimal(str(quote_data.get('onrampFee', 0))) + \
                                    Decimal(str(quote_data.get('clientFee', 0))) + \
                                    Decimal(str(quote_data.get('gatewayFee', 0))) + \
                                    Decimal(str(quote_data.get('gasFee', 0)))
            extracted['network_fee'] = quote_data.get('gasFee', 0)
            extracted['service_fee'] = quote_data.get('clientFee', 0)
        
        elif provider.upper() == 'MELD':
            # Meld quote structure
            extracted['destination_amount'] = quote_data.get('cryptoAmount') or quote_data.get('fiatAmount')
            extracted['exchange_rate'] = quote_data.get('exchangeRate')
            extracted['total_fees'] = quote_data.get('totalFee', 0)
            extracted['service_fee'] = quote_data.get('serviceFee', 0)
        
        elif provider.upper() == 'MOONPAY':
            # MoonPay quote structure
            extracted['destination_amount'] = quote_data.get('quoteCurrencyAmount')
            extracted['exchange_rate'] = quote_data.get('quoteCurrencyPrice')
            extracted['total_fees'] = Decimal(str(quote_data.get('feeAmount', 0))) + \
                                    Decimal(str(quote_data.get('networkFeeAmount', 0))) + \
                                    Decimal(str(quote_data.get('extraFeeAmount', 0)))
            extracted['network_fee'] = quote_data.get('networkFeeAmount', 0)
            extracted['service_fee'] = quote_data.get('feeAmount', 0)
        
        elif provider.upper() == 'FINCHPAY':
            # FinchPay quote structure
            extracted['destination_amount'] = quote_data.get('to_amount')
            extracted['exchange_rate'] = quote_data.get('exchange_rate')
            extracted['total_fees'] = Decimal(str(quote_data.get('service_fee_amount', 0))) + \
                                    Decimal(str(quote_data.get('network_fee_amount', 0)))
            extracted['network_fee'] = quote_data.get('network_fee_amount', 0)
            extracted['service_fee'] = quote_data.get('service_fee_amount', 0)
        
        elif provider.upper() == 'CHANGELLY':
            # Changelly structure (for swaps)
            extracted['destination_amount'] = quote_data.get('result')
            # Changelly doesn't provide detailed fee breakdown in quotes
            extracted['total_fees'] = Decimal('0.00000000')
    
    except Exception as e:
        logger.error(f"Error extracting quote data for {provider}: {str(e)}")
    
    return extracted


# ============================================================================
# CHECK IF USER IS AUTHENTICATED HELPER
# ============================================================================
def should_save_transaction(request):
    """
    Check if transaction should be saved to database.
    Only save for authenticated users.
    
    Args:
        request: Django request object
    
    Returns:
        bool: True if transaction should be saved
    """
    return request.user and request.user.is_authenticated


# ============================================================================
# GET OR CREATE TRANSACTION STATS HELPER
# ============================================================================
def get_or_update_user_stats(user):
    """
    Get or create user transaction stats and update them.
    
    Args:
        user: User instance
    
    Returns:
        TransactionStats instance
    """
    from .models import TransactionStats
    
    try:
        stats, created = TransactionStats.objects.get_or_create(user=user)
        stats.update_stats()
        return stats
    except Exception as e:
        logger.error(f"Error updating user stats: {str(e)}", exc_info=True)
        return None