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
        headers["x-api-key"] = SIMPLESWAP_API_KEY
    
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
        
        # Defensive wrapper: same logic as get_transaction_status.
        # POST /exchanges wraps in {"result":{...}} but handle direct response too.
        _raw_create = response.json()
        result = _raw_create.get("result") if (isinstance(_raw_create, dict) and "result" in _raw_create) else _raw_create

        simpleswap_txn_id = result.get("publicId") or result.get("id")
        
        # ✅ CREATE DATABASE RECORD
        # Always attempt to save; use request.user only when authenticated
        db_transaction = None
        user_for_record = request.user if should_save_transaction(request) else None
        
        if user_for_record:
            db_transaction = create_transaction_record(
                user=user_for_record,
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
        
        # ✅ STORE IN CACHE (always, regardless of auth)
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
        
        # ✅ Enhance response — always include the SimpleSwap public ID + our internal ID if available
        enhanced_result = result.copy()
        # Always expose the simpleswap public ID so the frontend can poll status
        enhanced_result['simpleswapTxnId'] = simpleswap_txn_id
        enhanced_result['publicId'] = simpleswap_txn_id
        # CRITICAL: transactionId MUST be the SimpleSwap publicId for polling to work.
        # confirm_transaction and get_transaction_status both pass this value directly
        # to the SimpleSwap API — sending the cache key prefix breaks status polling.
        enhanced_result['transactionId'] = simpleswap_txn_id
        if db_transaction:
            enhanced_result['ourTransactionId'] = db_transaction.transaction_id
        else:
            # For unauthenticated users, store cache key separately so frontend
            # can reference it, but transactionId stays as the SimpleSwap publicId.
            enhanced_result['ourTransactionId'] = transaction_key
        
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
            # Upstream API failed — return cached status so frontend polling stays alive
            # instead of throwing an error that kills the polling loop.
            fallback_key = cache.get(f"simpleswap_id_{public_id}") or f"txn_simpleswap_{public_id}"
            cached = cache.get(fallback_key) or {}
            logger.warning(f"SimpleSwap status API failed ({response.status_code}) for {public_id}, using cached status")
            return Response(
                {
                    "success": True,
                    "transaction": {"status": cached.get("simpleswap_status", "waiting"), "publicId": public_id},
                    "mappedStatus": cached.get("status", "PENDING"),
                    "fromCache": True,
                },
                status=status.HTTP_200_OK,
            )

        # SimpleSwap v3 GET /exchanges/{id} may return the object directly (no "result" wrapper).
        # Handle both shapes defensively so polling never silently returns empty {}.
        _raw_status = response.json()
        result = _raw_status.get("result") if (isinstance(_raw_status, dict) and "result" in _raw_status) else _raw_status
        
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

# ------------------------------------------------------------------
# ✅ POLL TRANSACTION STATUS (mirrors Changelly's ConfirmTransaction)
# Called by frontend every ~10 seconds to update status display
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def confirm_transaction(request):
    """
    Poll SimpleSwap for the latest exchange status and update DB + cache.
    Frontend should call this endpoint with the publicId (simpleswap exchange ID)
    every ~10 seconds while the transaction is in progress.

    Request body:
    {
        "transaction_id": "<simpleswap publicId>"
    }
    """
    try:
        public_id = request.data.get("transaction_id") or request.data.get("publicId")

        if not public_id:
            return Response(
                {"success": False, "error": "transaction_id (SimpleSwap publicId) is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = f"{SIMPLESWAP_API_BASE_URL}/exchanges/{public_id}"
        response = requests.get(url, headers=get_auth_headers(), timeout=30)

        if response.status_code != 200:
            fallback_key = cache.get(f"simpleswap_id_{public_id}") or f"txn_simpleswap_{public_id}"
            cached = cache.get(fallback_key) or {}
            logger.warning(f"SimpleSwap confirm API failed ({response.status_code}) for {public_id}, using cached status")
            return Response(
                {
                    "success": True,
                    "result": {"status": cached.get("simpleswap_status", "waiting"), "publicId": public_id},
                    "mappedStatus": cached.get("status", "PENDING"),
                    "fromCache": True,
                },
                status=status.HTTP_200_OK,
            )

        # Defensive wrapper: same as get_transaction_status
        _raw = response.json()
        result = _raw.get("result") if (isinstance(_raw, dict) and "result" in _raw) else _raw
        simpleswap_status = result.get("status", "").lower()

        status_mapping = {
            "waiting": "PENDING",
            "confirming": "PENDING",
            "exchanging": "PENDING",
            "sending": "PENDING",
            "finished": "COMPLETED",
            "failed": "FAILED",
            "refunded": "FAILED",
            "expired": "FAILED",
        }
        mapped_status = status_mapping.get(simpleswap_status, "PENDING")

        # ✅ UPDATE CACHE
        transaction_key = cache.get(f"simpleswap_id_{public_id}")
        if not transaction_key:
            transaction_key = f"txn_simpleswap_{public_id}"

        transaction_record = cache.get(transaction_key)
        if transaction_record:
            transaction_record["status"] = mapped_status
            transaction_record["simpleswap_status"] = simpleswap_status
            transaction_record["updated_at"] = int(time.time() * 1000)
            transaction_record["last_status_check"] = result

            if result.get("txFrom"):
                transaction_record["hash_in"] = result["txFrom"]
            if result.get("txTo"):
                transaction_record["hash_out"] = result["txTo"]

            cache.set(transaction_key, transaction_record, timeout=86400)

            # ✅ UPDATE DATABASE
            db_id = transaction_record.get("db_id")
            if db_id:
                try:
                    txn = Transaction.objects.get(id=db_id)
                    if txn.status != mapped_status:
                        txn.status = mapped_status
                        if not txn.provider_data:
                            txn.provider_data = {}
                        txn.provider_data["latest_status"] = result
                        txn.provider_data["simpleswap_status"] = simpleswap_status
                        txn.provider_data["last_checked"] = timezone.now().isoformat()

                        if result.get("txTo"):
                            txn.transaction_hash = result["txTo"]
                            txn.provider_data["txTo"] = result["txTo"]
                        if result.get("txFrom"):
                            txn.provider_data["txFrom"] = result["txFrom"]

                        if mapped_status == "COMPLETED" and not txn.completed_at:
                            txn.completed_at = timezone.now()

                        txn.save()
                        logger.info(f"✅ Updated SimpleSwap DB transaction {db_id}: {simpleswap_status} -> {mapped_status}")
                    else:
                        logger.debug(f"🔄 SimpleSwap transaction {db_id} status unchanged: {mapped_status}")

                except Transaction.DoesNotExist:
                    logger.error(f"❌ DB transaction {db_id} not found for SimpleSwap ID {public_id}")
            else:
                logger.debug(f"⚠️ No DB record for SimpleSwap transaction {public_id} (non-authenticated user)")
        else:
            logger.warning(f"⚠️ No cached transaction found for SimpleSwap ID: {public_id}")

        return Response(
            {
                "success": True,
                "result": result,
                "mappedStatus": mapped_status,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"SimpleSwap confirm transaction error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ SIMPLESWAP WEBHOOK (for server-side push updates from SimpleSwap)
# Register this URL in your SimpleSwap partner dashboard as the callback URL
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def simpleswap_webhook(request):
    """
    Receives real-time status push notifications from SimpleSwap.
    Register this endpoint URL in your SimpleSwap partner dashboard.

    SimpleSwap sends a POST with the exchange object whenever status changes.
    """
    try:
        payload = request.data

        # SimpleSwap sends the exchange object directly (same shape as GET /exchanges/{id})
        public_id = payload.get("publicId") or payload.get("id")
        simpleswap_status = payload.get("status", "").lower()

        if not public_id:
            logger.warning("⚠️ SimpleSwap webhook received payload with no publicId")
            return Response({"success": True}, status=status.HTTP_200_OK)

        logger.info(f"📩 SimpleSwap webhook: {public_id} -> {simpleswap_status}")

        status_mapping = {
            "waiting": "PENDING",
            "confirming": "PENDING",
            "exchanging": "PENDING",
            "sending": "PENDING",
            "finished": "COMPLETED",
            "failed": "FAILED",
            "refunded": "FAILED",
            "expired": "FAILED",
        }
        mapped_status = status_mapping.get(simpleswap_status, "PENDING")

        # ✅ UPDATE CACHE
        transaction_key = cache.get(f"simpleswap_id_{public_id}")
        if not transaction_key:
            transaction_key = f"txn_simpleswap_{public_id}"

        transaction_record = cache.get(transaction_key)
        if transaction_record:
            transaction_record["status"] = mapped_status
            transaction_record["simpleswap_status"] = simpleswap_status
            transaction_record["updated_at"] = int(time.time() * 1000)
            transaction_record["last_webhook_payload"] = payload

            if payload.get("txFrom"):
                transaction_record["hash_in"] = payload["txFrom"]
            if payload.get("txTo"):
                transaction_record["hash_out"] = payload["txTo"]

            cache.set(transaction_key, transaction_record, timeout=86400)

            # ✅ UPDATE DATABASE
            db_id = transaction_record.get("db_id")
            if db_id:
                try:
                    txn = Transaction.objects.get(id=db_id)
                    txn.status = mapped_status

                    if not txn.provider_data:
                        txn.provider_data = {}
                    txn.provider_data["webhook_payload"] = payload
                    txn.provider_data["simpleswap_status"] = simpleswap_status
                    txn.provider_data["last_webhook"] = timezone.now().isoformat()

                    if payload.get("txTo"):
                        txn.transaction_hash = payload["txTo"]
                        txn.provider_data["txTo"] = payload["txTo"]
                    if payload.get("txFrom"):
                        txn.provider_data["txFrom"] = payload["txFrom"]

                    if mapped_status == "COMPLETED" and not txn.completed_at:
                        txn.completed_at = timezone.now()

                    txn.save()
                    logger.info(f"✅ Webhook updated SimpleSwap DB transaction {db_id}: {simpleswap_status} -> {mapped_status}")

                except Transaction.DoesNotExist:
                    logger.error(f"❌ Webhook: DB transaction {db_id} not found for SimpleSwap ID {public_id}")

        # Always return 200 to SimpleSwap so they don't retry
        return Response({"success": True}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"SimpleSwap webhook error: {str(e)}", exc_info=True)
        # Still return 200 to prevent SimpleSwap from spamming retries
        return Response({"success": True}, status=status.HTTP_200_OK)
