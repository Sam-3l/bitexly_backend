import requests
import logging
import time

from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from users.transaction_helpers import create_transaction_record, should_save_transaction
from users.models import Transaction

# Setup logger
logger = logging.getLogger(__name__)

# LetsExchange API Configuration
LETSEXCHANGE_API_BASE_URL = "https://api.letsexchange.io/api"
LETSEXCHANGE_API_KEY = getattr(settings, 'LETSEXCHANGE_API_KEY', None)
LETSEXCHANGE_AFFILIATE_ID = getattr(settings, 'LETSEXCHANGE_AFFILIATE_ID', None)


# ============================================================================
# 🔄 COIN & NETWORK MAPPING FOR LETSEXCHANGE
# ============================================================================
def parse_coin_and_network_letsexchange(coin_code):
    """
    Parse Changelly-style coin codes into LetsExchange format (coin + network).
    
    LetsExchange uses format like: coin="BTC", network_from="BTC", network_to="TRC20"
    Changelly format: USDTRX, USDTSOL, ETHBSC, etc.
    
    Returns: (coin, network)
    """
    coin_upper = coin_code.upper()
    
    # Multi-chain coins with network suffix patterns
    multi_chain_coins = {
        'USDT': ['TRX', 'ETH', 'BSC', 'POLYGON', 'SOL', 'AVAX', 'ARBITRUM', 'OPTIMISM', 'BASE', 'TON', 'NEAR'],
        'USDC': ['TRX', 'ETH', 'BSC', 'POLYGON', 'SOL', 'AVAX', 'ARBITRUM', 'OPTIMISM', 'BASE'],
        'DAI': ['ETH', 'BSC', 'POLYGON', 'AVAX', 'ARBITRUM', 'OPTIMISM'],
        'BUSD': ['BSC', 'ETH'],
        'WBTC': ['ETH', 'BSC', 'POLYGON', 'AVAX', 'ARBITRUM'],
        'WETH': ['ETH', 'BSC', 'POLYGON', 'ARBITRUM', 'OPTIMISM'],
        'ETH': ['ETH', 'BSC', 'POLYGON', 'ARBITRUM', 'OPTIMISM', 'BASE'],
        'BTC': ['BTC', 'BSC', 'POLYGON'],
        'BNB': ['BSC', 'ETH'],
        'SHIB': ['ETH', 'BSC'],
        'LINK': ['ETH', 'BSC', 'POLYGON', 'ARBITRUM'],
        'UNI': ['ETH', 'BSC', 'POLYGON', 'ARBITRUM'],
        'MATIC': ['POLYGON', 'ETH', 'BSC'],
    }
    
    # Network name mappings (LetsExchange specific)
    network_mappings = {
        'TRX': 'TRC20',
        'BSC': 'BEP20',
        'POLYGON': 'POLYGON',
        'ETH': 'ETH',
        'SOL': 'SOL',
        'AVAX': 'AVAXC',
        'ARBITRUM': 'ARBITRUM',
        'OPTIMISM': 'OPTIMISM',
        'BASE': 'BASE',
        'TON': 'TON',
        'NEAR': 'NEAR',
        'BTC': 'BTC',
    }
    
    # Try to match multi-chain tokens with overlap detection
    for base_coin, networks in multi_chain_coins.items():
        for network in networks:
            # Standard concatenation
            if coin_upper == f"{base_coin}{network}":
                mapped_network = network_mappings.get(network, network)
                logger.info(f"✅ LetsExchange: {coin_upper} -> coin={base_coin}, network={mapped_network}")
                return (base_coin, mapped_network)
            
            # Check for character overlap
            if len(base_coin) > 0 and len(network) > 0:
                if base_coin[-1] == network[0]:
                    overlapped = base_coin + network[1:]
                    if coin_upper == overlapped:
                        mapped_network = network_mappings.get(network, network)
                        logger.info(f"✅ LetsExchange: {coin_upper} -> coin={base_coin}, network={mapped_network} (overlapping)")
                        return (base_coin, mapped_network)
    
    # Native coins
    native_coins = {
        'BTC': 'BTC',
        'ETH': 'ETH',
        'LTC': 'LTC',
        'BCH': 'BCH',
        'DOGE': 'DOGE',
        'XRP': 'XRP',
        'ADA': 'ADA',
        'DOT': 'DOT',
        'TRX': 'TRC20',
        'BNB': 'BEP20',
        'SOL': 'SOL',
        'MATIC': 'POLYGON',
        'AVAX': 'AVAXC',
        'XMR': 'XMR',
        'ATOM': 'ATOM',
        'XLM': 'XLM',
        'NEAR': 'NEAR',
        'FTM': 'FTM',
        'ALGO': 'ALGO',
        'VET': 'VET',
        'ICP': 'ICP',
        'FIL': 'FIL',
        'HBAR': 'HBAR',
        'APT': 'APT',
        'SUI': 'SUI',
        'TON': 'TON',
        'OP': 'OPTIMISM',
        'ARB': 'ARBITRUM',
        'DASH': 'DASH',
        'ZEC': 'ZEC',
        'ETC': 'ETC',
    }
    
    if coin_upper in native_coins:
        network = native_coins[coin_upper]
        logger.info(f"✅ LetsExchange native: {coin_upper} -> coin={coin_upper}, network={network}")
        return (coin_upper, network)
    
    # Default fallback
    logger.warning(f"⚠️ LetsExchange: Unknown coin '{coin_code}', using as-is")
    return (coin_upper, coin_upper)


def get_auth_headers():
    """Get authorization headers for LetsExchange API."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    if LETSEXCHANGE_API_KEY:
        if LETSEXCHANGE_API_KEY.startswith('Bearer '):
            headers["Authorization"] = LETSEXCHANGE_API_KEY
        else:
            headers["Authorization"] = f"Bearer {LETSEXCHANGE_API_KEY}"
    
    return headers


# ------------------------------------------------------------------
# ✅ GET COINS LIST (V2 recommended)
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_letsexchange_coins(request):
    """
    Fetch all supported coins from LetsExchange (API v2).
    Returns aggregated list with networks for each coin.
    """
    try:
        url = f"{LETSEXCHANGE_API_BASE_URL}/v2/coins"
        
        response = requests.get(url, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch coins from LetsExchange", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        coins = response.json()
        
        return Response(
            {
                "success": True,
                "coins": coins,
                "count": len(coins) if isinstance(coins, list) else 0
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"LetsExchange get coins error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET RATE/QUOTE
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def get_letsexchange_rate(request):
    """
    Get exchange rate from LetsExchange.
    
    Request body:
    {
        "coinFrom": "BTC",
        "coinTo": "USDT",
        "amount": 0.01,
        "float": true
    }
    """
    try:
        data = request.data
        
        coin_from_raw = data.get("coinFrom", "")
        coin_to_raw = data.get("coinTo", "")
        amount = data.get("amount")
        is_float = data.get("float", True)
        
        # Validate
        if not all([coin_from_raw, coin_to_raw, amount]):
            return Response(
                {"success": False, "message": "coinFrom, coinTo, and amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Parse coins and networks
        coin_from, network_from = parse_coin_and_network_letsexchange(coin_from_raw)
        coin_to, network_to = parse_coin_and_network_letsexchange(coin_to_raw)
        
        logger.info(f"📤 LetsExchange Rate: {coin_from_raw} -> coin={coin_from}, network={network_from}")
        logger.info(f"📤 LetsExchange Rate: {coin_to_raw} -> coin={coin_to}, network={network_to}")
        
        url = f"{LETSEXCHANGE_API_BASE_URL}/v1/info"
        
        body = {
            "from": coin_from,
            "to": coin_to,
            "network_from": network_from,
            "network_to": network_to,
            "amount": float(amount),
            "float": is_float
        }
        
        # Add affiliate ID if configured
        if LETSEXCHANGE_AFFILIATE_ID:
            body["affiliate_id"] = LETSEXCHANGE_AFFILIATE_ID
        
        response = requests.post(url, json=body, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            error_data = response.json()
            return Response(
                {"success": False, "message": "Failed to get rate from LetsExchange", "details": error_data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        rate_data = response.json()
        
        # Standardize response
        standardized_quote = {
            "sourceCurrency": coin_from_raw,
            "destinationCurrency": coin_to_raw,
            "sourceAmount": str(amount),
            "estimatedAmount": rate_data.get("amount"),
            "rate": rate_data.get("rate"),
            "minAmount": rate_data.get("min_amount"),
            "maxAmount": rate_data.get("max_amount"),
            "withdrawalFee": rate_data.get("withdrawal_fee"),
            "rateId": rate_data.get("rate_id"),
            "rateIdExpiredAt": rate_data.get("rate_id_expired_at"),
            "networkFrom": network_from,
            "networkTo": network_to,
        }
        
        return Response(
            {
                "success": True,
                "quote": standardized_quote,
                "rawData": rate_data
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"LetsExchange rate error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ CREATE TRANSACTION
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def create_swap_transaction(request):
    """
    Create swap transaction on LetsExchange.
    
    Request body:
    {
        "coinFrom": "BTC",
        "coinTo": "USDT",
        "amount": 0.01,
        "withdrawalAddress": "TR7NHqjeKQxGTCi8...",
        "withdrawalExtraId": "",  // optional
        "float": true,
        "rateId": ""  // required for fixed rate
    }
    """
    try:
        data = request.data
        
        coin_from_raw = data.get("coinFrom", "")
        coin_to_raw = data.get("coinTo", "")
        amount = data.get("amount")
        withdrawal_address = data.get("withdrawalAddress")
        withdrawal_extra_id = data.get("withdrawalExtraId", "")
        return_address = data.get("returnAddress", "")
        return_extra_id = data.get("returnExtraId", "")
        is_float = data.get("float", True)
        rate_id = data.get("rateId")
        
        # Validate
        if not all([coin_from_raw, coin_to_raw, amount, withdrawal_address]):
            return Response(
                {"success": False, "message": "coinFrom, coinTo, amount, and withdrawalAddress are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # For fixed rate, rate_id is required
        if not is_float and not rate_id:
            return Response(
                {"success": False, "message": "rateId is required for fixed rate transactions"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Parse coins and networks
        coin_from, network_from = parse_coin_and_network_letsexchange(coin_from_raw)
        coin_to, network_to = parse_coin_and_network_letsexchange(coin_to_raw)
        
        logger.info(f"📤 LetsExchange Create: {coin_from_raw} -> coin={coin_from}, network={network_from}")
        logger.info(f"📤 LetsExchange Create: {coin_to_raw} -> coin={coin_to}, network={network_to}")
        
        url = f"{LETSEXCHANGE_API_BASE_URL}/v1/transaction"
        
        body = {
            "float": is_float,
            "coin_from": coin_from,
            "coin_to": coin_to,
            "network_from": network_from,
            "network_to": network_to,
            "deposit_amount": float(amount),
            "withdrawal": withdrawal_address,
            "withdrawal_extra_id": withdrawal_extra_id,
        }
        
        # Add affiliate ID if configured
        if LETSEXCHANGE_AFFILIATE_ID:
            body["affiliate_id"] = LETSEXCHANGE_AFFILIATE_ID
        
        # Add optional fields
        if return_address:
            body["return"] = return_address
        if return_extra_id:
            body["return_extra_id"] = return_extra_id
        if rate_id:
            body["rate_id"] = rate_id
        
        response = requests.post(url, json=body, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            error_data = response.json()
            return Response(
                {"success": False, "message": "Failed to create transaction", "details": error_data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        result = response.json()
        
        letsexchange_txn_id = result.get("transaction_id")
        
        # ✅ CREATE DATABASE RECORD
        db_transaction = None
        if should_save_transaction(request):
            db_transaction = create_transaction_record(
                user=request.user,
                provider='LETSEXCHANGE',
                transaction_type='SWAP',
                source_currency=coin_from_raw,
                source_amount=result.get("deposit_amount"),
                destination_currency=coin_to_raw,
                destination_amount=result.get("withdrawal_amount"),
                wallet_address=withdrawal_address,
                provider_transaction_id=letsexchange_txn_id,
                provider_data={
                    'depositAddress': result.get('deposit'),
                    'depositExtraId': result.get('deposit_extra_id'),
                    'withdrawalAddress': result.get('withdrawal'),
                    'withdrawalExtraId': result.get('withdrawal_extra_id'),
                    'rate': result.get('rate'),
                    'isFloat': result.get('is_float'),
                    'coinFrom': coin_from,
                    'networkFrom': network_from,
                    'coinTo': coin_to,
                    'networkTo': network_to,
                    'letsexchange_result': result
                }
            )
        
        # ✅ STORE IN CACHE
        timestamp = int(time.time() * 1000)
        transaction_key = f"txn_letsexchange_{letsexchange_txn_id}"
        
        transaction_record = {
            'transaction_id': transaction_key,
            'db_id': db_transaction.id if db_transaction else None,
            'provider': 'LETSEXCHANGE',
            'status': 'PENDING',
            'created_at': timestamp,
            'letsexchange_txn_id': letsexchange_txn_id,
            'source_currency': coin_from_raw,
            'destination_currency': coin_to_raw,
            'amount': result.get("deposit_amount"),
            'estimated_amount': result.get("withdrawal_amount"),
            'deposit_address': result.get('deposit'),
            'deposit_extra_id': result.get('deposit_extra_id'),
            'withdrawal_address': result.get('withdrawal'),
            'withdrawal_extra_id': result.get('withdrawal_extra_id'),
            'rate': result.get('rate'),
        }
        
        cache.set(transaction_key, transaction_record, timeout=86400)
        cache.set(f"letsexchange_id_{letsexchange_txn_id}", transaction_key, timeout=86400)
        
        # Enhance response
        enhanced_result = result.copy()
        if db_transaction:
            enhanced_result['ourTransactionId'] = db_transaction.transaction_id
            enhanced_result['transactionId'] = db_transaction.transaction_id
        
        logger.info(f"✅ Created LetsExchange transaction: {letsexchange_txn_id}")
        
        return Response(
            {
                "success": True,
                "transaction": enhanced_result
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"LetsExchange create transaction error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET TRANSACTION STATUS
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_transaction_status(request, transaction_id):
    """
    Get transaction status from LetsExchange.
    
    Path params:
    - transaction_id: LetsExchange transaction ID
    """
    try:
        url = f"{LETSEXCHANGE_API_BASE_URL}/v1/transaction/{transaction_id}"
        
        response = requests.get(url, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch transaction", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        result = response.json()
        
        letsexchange_status = result.get('status', '').lower()
        
        # Map LetsExchange status to internal status
        status_mapping = {
            'wait': 'PENDING',
            'confirmation': 'PENDING',
            'confirmed': 'PENDING',
            'exchanging': 'PENDING',
            'sending': 'PENDING',
            'sending_confirmation': 'PENDING',
            'success': 'COMPLETED',
            'aml_check_failed': 'FAILED',
            'overdue': 'FAILED',
            'error': 'FAILED',
            'refund': 'FAILED',
        }
        
        mapped_status = status_mapping.get(letsexchange_status, 'PENDING')
        
        # ✅ UPDATE CACHE
        transaction_key = cache.get(f"letsexchange_id_{transaction_id}")
        if not transaction_key:
            transaction_key = f"txn_letsexchange_{transaction_id}"
        
        transaction_record = cache.get(transaction_key)
        
        if transaction_record:
            transaction_record['status'] = mapped_status
            transaction_record['updated_at'] = int(time.time() * 1000)
            transaction_record['last_status_check'] = result
            transaction_record['letsexchange_status'] = letsexchange_status
            
            if result.get('hash_in'):
                transaction_record['hash_in'] = result['hash_in']
            if result.get('hash_out'):
                transaction_record['hash_out'] = result['hash_out']
            
            cache.set(transaction_key, transaction_record, timeout=86400)
            
            # ✅ UPDATE DATABASE
            db_id = transaction_record.get('db_id')
            if db_id:
                try:
                    txn = Transaction.objects.get(id=db_id)
                    
                    if txn.status != mapped_status:
                        txn.status = mapped_status
                        
                        if not txn.provider_data:
                            txn.provider_data = {}
                        txn.provider_data['latest_status'] = result
                        txn.provider_data['letsexchange_status'] = letsexchange_status
                        txn.provider_data['last_checked'] = timezone.now().isoformat()
                        
                        if result.get('hash_out'):
                            txn.transaction_hash = result['hash_out']
                        
                        if mapped_status == 'COMPLETED' and not txn.completed_at:
                            txn.completed_at = timezone.now()
                        
                        txn.save()
                        logger.info(f"✅ Updated LetsExchange DB transaction {db_id}: {letsexchange_status} -> {mapped_status}")
                    
                except Transaction.DoesNotExist:
                    logger.error(f"❌ DB transaction {db_id} not found for LetsExchange ID {transaction_id}")
        
        return Response(
            {
                "success": True,
                "transaction": result,
                "mappedStatus": mapped_status
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"LetsExchange get transaction status error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )