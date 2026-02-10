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

# SimpleSwap API Configuration
SIMPLESWAP_API_BASE_URL = "https://api.simpleswap.io/v3"
SIMPLESWAP_API_KEY = getattr(settings, 'SIMPLESWAP_API_KEY', None)


# ============================================================================
# 🔄 COIN & NETWORK MAPPING FOR SIMPLESWAP
# ============================================================================
def parse_coin_and_network_simpleswap(coin_code):
    """
    Parse Changelly-style coin codes into SimpleSwap format (ticker:network).
    
    SimpleSwap uses format like: "btc:btc", "usdt:trc20", "eth:bsc"
    Changelly format: USDTRX, USDTSOL, ETHBSC, etc.
    
    Returns: (ticker, network) in lowercase.
    """
    coin_upper = coin_code.upper()
    
    # Multi-chain coins
    multi_chain_coins = {
        'USDT': ['TRX', 'ETH', 'BSC', 'POLYGON', 'SOL', 'AVAX', 'ARBITRUM', 'OPTIMISM', 'BASE', 'TON'],
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
    
    # Network name mappings (SimpleSwap format)
    network_mappings = {
        'TRX': 'trc20',
        'BSC': 'bsc',
        'POLYGON': 'polygon',
        'ETH': 'eth',
        'SOL': 'sol',
        'AVAX': 'avax',
        'ARBITRUM': 'arbitrum',
        'OPTIMISM': 'optimism',
        'BASE': 'base',
        'TON': 'ton',
        'BTC': 'btc',
    }
    
    # Try to match multi-chain tokens
    for base_coin, networks in multi_chain_coins.items():
        for network in networks:
            # Standard concatenation
            if coin_upper == f"{base_coin}{network}":
                ticker = base_coin.lower()
                network_code = network_mappings.get(network, network.lower())
                logger.info(f"✅ SimpleSwap: {coin_upper} -> ticker={ticker}, network={network_code}")
                return (ticker, network_code)
            
            # Overlap detection
            if len(base_coin) > 0 and len(network) > 0:
                if base_coin[-1] == network[0]:
                    overlapped = base_coin + network[1:]
                    if coin_upper == overlapped:
                        ticker = base_coin.lower()
                        network_code = network_mappings.get(network, network.lower())
                        logger.info(f"✅ SimpleSwap: {coin_upper} -> ticker={ticker}, network={network_code} (overlapping)")
                        return (ticker, network_code)
    
    # Native coins
    native_coins = {
        'BTC': 'btc',
        'ETH': 'eth',
        'LTC': 'ltc',
        'BCH': 'bch',
        'DOGE': 'doge',
        'XRP': 'xrp',
        'ADA': 'ada',
        'DOT': 'dot',
        'TRX': 'trc20',
        'BNB': 'bsc',
        'SOL': 'sol',
        'MATIC': 'polygon',
        'AVAX': 'avax',
        'XMR': 'xmr',
        'ATOM': 'atom',
        'XLM': 'xlm',
        'NEAR': 'near',
        'FTM': 'ftm',
        'ALGO': 'algo',
        'VET': 'vet',
        'ICP': 'icp',
        'FIL': 'fil',
        'HBAR': 'hbar',
        'APT': 'apt',
        'SUI': 'sui',
        'TON': 'ton',
        'DASH': 'dash',
        'ZEC': 'zec',
        'ETC': 'etc',
    }
    
    if coin_upper in native_coins:
        ticker = coin_upper.lower()
        network = native_coins[coin_upper]
        logger.info(f"✅ SimpleSwap native: {coin_upper} -> ticker={ticker}, network={network}")
        return (ticker, network)
    
    # Default fallback
    logger.warning(f"⚠️ SimpleSwap: Unknown coin '{coin_code}', using as-is")
    ticker = coin_upper.lower()
    return (ticker, ticker)


def get_auth_headers():
    """Get authorization headers for SimpleSwap API."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    if SIMPLESWAP_API_KEY:
        headers["api-key"] = SIMPLESWAP_API_KEY
    
    return headers


# ------------------------------------------------------------------
# ✅ GET CURRENCIES
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_simpleswap_currencies(request):
    """
    Fetch all supported currencies from SimpleSwap.
    """
    try:
        url = f"{SIMPLESWAP_API_BASE_URL}/currencies"
        
        response = requests.get(url, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch currencies from SimpleSwap", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        data = response.json()
        currencies = data.get("result", [])
        
        return Response(
            {
                "success": True,
                "currencies": currencies,
                "count": len(currencies) if isinstance(currencies, list) else 0
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"SimpleSwap get currencies error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET EXCHANGE PAIRS
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_exchange_pairs(request):
    """
    Get all available exchange pairs.
    
    Query params:
    - fixed: true/false (default: false for floating rate)
    """
    try:
        fixed = request.query_params.get("fixed", "false").lower() == "true"
        
        url = f"{SIMPLESWAP_API_BASE_URL}/pairs"
        params = {"fixed": str(fixed).lower()}
        
        response = requests.get(url, params=params, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch pairs", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        data = response.json()
        
        return Response(
            {
                "success": True,
                "pairs": data.get("result", {}),
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"SimpleSwap get pairs error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET RATE/ESTIMATE
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def get_simpleswap_rate(request):
    """
    Get exchange estimate from SimpleSwap.
    
    Request body:
    {
        "coinFrom": "BTC",
        "coinTo": "USDT",
        "amount": 0.01,
        "fixed": false
    }
    """
    try:
        data = request.data
        
        coin_from_raw = data.get("coinFrom", "")
        coin_to_raw = data.get("coinTo", "")
        amount = data.get("amount")
        fixed = data.get("fixed", False)
        
        # Validate
        if not all([coin_from_raw, coin_to_raw, amount]):
            return Response(
                {"success": False, "message": "coinFrom, coinTo, and amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Parse coins and networks
        ticker_from, network_from = parse_coin_and_network_simpleswap(coin_from_raw)
        ticker_to, network_to = parse_coin_and_network_simpleswap(coin_to_raw)
        
        logger.info(f"📤 SimpleSwap Rate: {coin_from_raw} -> ticker={ticker_from}, network={network_from}")
        logger.info(f"📤 SimpleSwap Rate: {coin_to_raw} -> ticker={ticker_to}, network={network_to}")
        
        url = f"{SIMPLESWAP_API_BASE_URL}/estimates"
        
        params = {
            "fixed": str(fixed).lower(),
            "tickerFrom": ticker_from,
            "tickerTo": ticker_to,
            "networkFrom": network_from,
            "networkTo": network_to,
            "amount": str(amount),
            "reverse": "false"
        }
        
        response = requests.get(url, params=params, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            error_data = response.json()
            return Response(
                {"success": False, "message": "Failed to get estimate from SimpleSwap", "details": error_data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        rate_data = response.json().get("result", {})
        
        # Get range info (min/max)
        range_url = f"{SIMPLESWAP_API_BASE_URL}/ranges"
        range_params = {
            "fixed": str(fixed).lower(),
            "tickerFrom": ticker_from,
            "tickerTo": ticker_to,
            "networkFrom": network_from,
            "networkTo": network_to,
            "reverse": "false"
        }
        
        range_response = requests.get(range_url, params=range_params, headers=get_auth_headers(), timeout=30)
        range_data = range_response.json().get("result", {}) if range_response.status_code == 200 else {}
        
        # Standardize response
        standardized_quote = {
            "sourceCurrency": coin_from_raw,
            "destinationCurrency": coin_to_raw,
            "sourceAmount": str(amount),
            "estimatedAmount": rate_data.get("estimatedAmount"),
            "rate": None,  # SimpleSwap doesn't provide explicit rate
            "minAmount": range_data.get("min"),
            "maxAmount": range_data.get("max"),
            "rateId": rate_data.get("rateId"),
            "validUntil": rate_data.get("validUntil"),
            "tickerFrom": ticker_from,
            "networkFrom": network_from,
            "tickerTo": ticker_to,
            "networkTo": network_to,
        }
        
        # Calculate rate
        if rate_data.get("estimatedAmount") and amount:
            calc_rate = float(rate_data.get("estimatedAmount")) / float(amount)
            standardized_quote["rate"] = str(calc_rate)
        
        return Response(
            {
                "success": True,
                "quote": standardized_quote,
                "rawData": rate_data
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"SimpleSwap rate error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ CREATE EXCHANGE
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def create_swap_transaction(request):
    """
    Create exchange on SimpleSwap.
    
    Request body:
    {
        "coinFrom": "BTC",
        "coinTo": "USDT",
        "amount": 0.01,
        "withdrawalAddress": "TR7NHqje...",
        "withdrawalExtraId": "",
        "fixed": false,
        "rateId": ""  // required for fixed rate
    }
    """
    try:
        data = request.data
        
        coin_from_raw = data.get("coinFrom", "")
        coin_to_raw = data.get("coinTo", "")
        amount = data.get("amount")
        address_to = data.get("withdrawalAddress")
        extra_id_to = data.get("withdrawalExtraId", "")
        user_refund_address = data.get("userRefundAddress", "")
        user_refund_extra_id = data.get("userRefundExtraId", "")
        fixed = data.get("fixed", False)
        rate_id = data.get("rateId")
        
        # Validate
        if not all([coin_from_raw, coin_to_raw, amount, address_to]):
            return Response(
                {"success": False, "message": "coinFrom, coinTo, amount, and withdrawalAddress are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # Parse coins and networks
        ticker_from, network_from = parse_coin_and_network_simpleswap(coin_from_raw)
        ticker_to, network_to = parse_coin_and_network_simpleswap(coin_to_raw)
        
        logger.info(f"📤 SimpleSwap Create: {coin_from_raw} -> ticker={ticker_from}, network={network_from}")
        logger.info(f"📤 SimpleSwap Create: {coin_to_raw} -> ticker={ticker_to}, network={network_to}")
        
        url = f"{SIMPLESWAP_API_BASE_URL}/exchanges"
        
        body = {
            "fixed": fixed,
            "tickerFrom": ticker_from,
            "tickerTo": ticker_to,
            "amount": str(amount),
            "networkFrom": network_from,
            "networkTo": network_to,
            "reverse": False,
            "addressTo": address_to,
        }
        
        # Optional fields
        if extra_id_to:
            body["extraIdTo"] = extra_id_to
        if user_refund_address:
            body["userRefundAddress"] = user_refund_address
        if user_refund_extra_id:
            body["userRefundExtraId"] = user_refund_extra_id
        if rate_id:
            body["rateId"] = rate_id
        
        response = requests.post(url, json=body, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            error_data = response.json()
            return Response(
                {"success": False, "message": "Failed to create exchange", "details": error_data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        result = response.json().get("result", {})
        
        simpleswap_txn_id = result.get("publicId")
        
        # ✅ CREATE DATABASE RECORD
        db_transaction = None
        if should_save_transaction(request):
            db_transaction = create_transaction_record(
                user=request.user,
                provider='SIMPLESWAP',
                transaction_type='SWAP',
                source_currency=coin_from_raw,
                source_amount=result.get("amountFrom"),
                destination_currency=coin_to_raw,
                destination_amount=result.get("amountTo"),
                wallet_address=address_to,
                provider_transaction_id=simpleswap_txn_id,
                provider_data={
                    'depositAddress': result.get('addressFrom'),
                    'depositExtraId': result.get('extraIdFrom'),
                    'withdrawalAddress': result.get('addressTo'),
                    'withdrawalExtraId': result.get('extraIdTo'),
                    'tickerFrom': ticker_from,
                    'networkFrom': network_from,
                    'tickerTo': ticker_to,
                    'networkTo': network_to,
                    'simpleswap_result': result
                }
            )
        
        # ✅ STORE IN CACHE
        timestamp = int(time.time() * 1000)
        transaction_key = f"txn_simpleswap_{simpleswap_txn_id}"
        
        transaction_record = {
            'transaction_id': transaction_key,
            'db_id': db_transaction.id if db_transaction else None,
            'provider': 'SIMPLESWAP',
            'status': 'PENDING',
            'created_at': timestamp,
            'simpleswap_txn_id': simpleswap_txn_id,
            'source_currency': coin_from_raw,
            'destination_currency': coin_to_raw,
            'amount': result.get("amountFrom"),
            'estimated_amount': result.get("amountTo"),
            'deposit_address': result.get('addressFrom'),
            'deposit_extra_id': result.get('extraIdFrom'),
            'withdrawal_address': result.get('addressTo'),
            'withdrawal_extra_id': result.get('extraIdTo'),
        }
        
        cache.set(transaction_key, transaction_record, timeout=86400)
        cache.set(f"simpleswap_id_{simpleswap_txn_id}", transaction_key, timeout=86400)
        
        # Enhance response
        enhanced_result = result.copy()
        if db_transaction:
            enhanced_result['ourTransactionId'] = db_transaction.transaction_id
            enhanced_result['transactionId'] = db_transaction.transaction_id
        
        logger.info(f"✅ Created SimpleSwap exchange: {simpleswap_txn_id}")
        
        return Response(
            {
                "success": True,
                "transaction": enhanced_result
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"SimpleSwap create exchange error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET EXCHANGE STATUS
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_transaction_status(request, public_id):
    """
    Get exchange status from SimpleSwap.
    
    Path params:
    - public_id: SimpleSwap public transaction ID
    """
    try:
        url = f"{SIMPLESWAP_API_BASE_URL}/exchanges/{public_id}"
        
        response = requests.get(url, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch exchange", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        result = response.json().get("result", {})
        
        simpleswap_status = result.get('status', '').lower()
        
        # Map SimpleSwap status to internal status
        status_mapping = {
            'waiting': 'PENDING',
            'confirming': 'PENDING',
            'exchanging': 'PENDING',
            'sending': 'PENDING',
            'finished': 'COMPLETED',
            'failed': 'FAILED',
            'refunded': 'FAILED',
            'expired': 'FAILED',
        }
        
        mapped_status = status_mapping.get(simpleswap_status, 'PENDING')
        
        # ✅ UPDATE CACHE
        transaction_key = cache.get(f"simpleswap_id_{public_id}")
        if not transaction_key:
            transaction_key = f"txn_simpleswap_{public_id}"
        
        transaction_record = cache.get(transaction_key)
        
        if transaction_record:
            transaction_record['status'] = mapped_status
            transaction_record['updated_at'] = int(time.time() * 1000)
            transaction_record['last_status_check'] = result
            transaction_record['simpleswap_status'] = simpleswap_status
            
            if result.get('txFrom'):
                transaction_record['hash_in'] = result['txFrom']
            if result.get('txTo'):
                transaction_record['hash_out'] = result['txTo']
            
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
                        txn.provider_data['simpleswap_status'] = simpleswap_status
                        txn.provider_data['last_checked'] = timezone.now().isoformat()
                        
                        if result.get('txTo'):
                            txn.transaction_hash = result['txTo']
                        
                        if mapped_status == 'COMPLETED' and not txn.completed_at:
                            txn.completed_at = timezone.now()
                        
                        txn.save()
                        logger.info(f"✅ Updated SimpleSwap DB transaction {db_id}: {simpleswap_status} -> {mapped_status}")
                    
                except Transaction.DoesNotExist:
                    logger.error(f"❌ DB transaction {db_id} not found for SimpleSwap ID {public_id}")
        
        return Response(
            {
                "success": True,
                "transaction": result,
                "mappedStatus": mapped_status
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"SimpleSwap get exchange status error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )