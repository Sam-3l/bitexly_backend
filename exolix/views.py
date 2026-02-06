import requests
import logging
import time
from functools import lru_cache

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

# Exolix API Configuration
EXOLIX_API_BASE_URL = "https://exolix.com/api/v2"
EXOLIX_API_KEY = getattr(settings, 'EXOLIX_API_KEY', None)


def get_auth_headers():
    """
    Get authorization headers if API key is configured.
    """
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    if EXOLIX_API_KEY:
        # Add Bearer prefix if not already present
        if EXOLIX_API_KEY.startswith('Bearer '):
            headers["Authorization"] = EXOLIX_API_KEY
        else:
            headers["Authorization"] = f"Bearer {EXOLIX_API_KEY}"
    
    return headers


# ------------------------------------------------------------------
# ✅ GET CURRENCIES - List all available currencies
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_exolix_currencies(request):
    """
    Fetch all supported currencies from Exolix.
    
    Query params:
    - page: Current page (optional)
    - size: Size per page (optional)
    - search: Search by currency code or name (optional)
    - withNetworks: Show currency with networks (true/false, default false)
    """
    try:
        # Get query parameters
        page = request.query_params.get("page", 1)
        size = request.query_params.get("size", 100)
        search = request.query_params.get("search", "")
        with_networks = request.query_params.get("withNetworks", "false")
        
        url = f"{EXOLIX_API_BASE_URL}/currencies"
        params = {
            "page": page,
            "size": size,
            "withNetworks": with_networks
        }
        
        if search:
            params["search"] = search
        
        response = requests.get(url, params=params, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch currencies", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        data = response.json()
        
        return Response(
            {
                "success": True,
                "data": data.get("data", []),
                "count": data.get("count", 0)
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Exolix get currencies error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET CURRENCY NETWORKS - Get networks for a specific currency
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_currency_networks(request, currency_code):
    """
    Get all networks for a specific currency.
    
    Path params:
    - currency_code: The currency code (e.g., ETH, BTC, USDT)
    """
    try:
        url = f"{EXOLIX_API_BASE_URL}/currencies/{currency_code.lower()}/networks"
        
        response = requests.get(url, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": f"Failed to fetch networks for {currency_code}", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        networks = response.json()
        
        return Response(
            {"success": True, "networks": networks},
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Exolix get currency networks error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET ALL NETWORKS - List all available networks
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_all_networks(request):
    """
    Fetch all available networks from Exolix.
    
    Query params:
    - page: Current page (optional)
    - size: Size per page (optional)
    - search: Search by network name (optional)
    """
    try:
        page = request.query_params.get("page", 1)
        size = request.query_params.get("size", 100)
        search = request.query_params.get("search", "")
        
        url = f"{EXOLIX_API_BASE_URL}/currencies/networks"
        params = {
            "page": page,
            "size": size,
        }
        
        if search:
            params["search"] = search
        
        response = requests.get(url, params=params, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch networks", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        data = response.json()
        
        return Response(
            {
                "success": True,
                "data": data.get("data", []),
                "count": data.get("count", 0)
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Exolix get all networks error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET RATE/QUOTE - Get exchange rate and amount estimate
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def get_exolix_rate(request):
    """
    Get exchange rate and amount estimate from Exolix.
    
    Request body:
    {
        "coinFrom": "ETH",
        "networkFrom": "ETH",  // optional
        "coinTo": "USDT",
        "networkTo": "ETH",  // optional
        "amount": "0.5",
        "withdrawalAmount": "500",  // optional - amount to receive
        "rateType": "float"  // "float" or "fixed", default "float"
    }
    """
    try:
        data = request.data
        
        coin_from = data.get("coinFrom", "").upper()
        network_from = data.get("networkFrom", "")
        coin_to = data.get("coinTo", "").upper()
        network_to = data.get("networkTo", "")
        amount = data.get("amount")
        withdrawal_amount = data.get("withdrawalAmount")
        rate_type = data.get("rateType", "float")
        
        # Validate required fields
        if not all([coin_from, coin_to]) or not (amount or withdrawal_amount):
            return Response(
                {"success": False, "message": "coinFrom, coinTo, and amount (or withdrawalAmount) are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        url = f"{EXOLIX_API_BASE_URL}/rate"
        params = {
            "coinFrom": coin_from,
            "coinTo": coin_to,
            "rateType": rate_type
        }
        
        if network_from:
            params["networkFrom"] = network_from
        if network_to:
            params["networkTo"] = network_to
        if amount:
            params["amount"] = str(amount)
        if withdrawal_amount:
            params["withdrawalAmount"] = str(withdrawal_amount)
        
        logger.info(f"Exolix Rate Request: {params}")
        
        response = requests.get(url, params=params, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            error_data = response.json()
            return Response(
                {"success": False, "message": "Failed to get rate", "details": error_data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        rate_data = response.json()
        
        logger.info(f"Exolix Rate Response: {rate_data}")
        
        # Standardize response similar to other providers
        standardized_quote = {
            "sourceCurrency": coin_from,
            "destinationCurrency": coin_to,
            "sourceAmount": rate_data.get("fromAmount"),
            "estimatedAmount": rate_data.get("toAmount"),
            "rate": rate_data.get("rate"),
            "minAmount": rate_data.get("minAmount"),
            "maxAmount": rate_data.get("maxAmount"),
            "withdrawMin": rate_data.get("withdrawMin"),
            "message": rate_data.get("message"),
            "rateType": rate_type,
            "networkFrom": network_from or None,
            "networkTo": network_to or None,
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
        logger.error(f"Exolix rate error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ CREATE SWAP TRANSACTION - Create a new swap transaction
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def create_swap_transaction(request):
    """
    Create a swap transaction on Exolix.
    
    Request body:
    {
        "coinFrom": "ETH",
        "networkFrom": "ETH",
        "coinTo": "USDT",
        "networkTo": "ETH",
        "amount": "0.5",
        "withdrawalAmount": "500",  // optional
        "withdrawalAddress": "0x...",
        "withdrawalExtraId": "",  // optional, for currencies that require memo/tag
        "refundAddress": "0x...",  // optional
        "refundExtraId": "",  // optional
        "rateType": "float",  // "float" or "fixed"
        "slippage": 1  // optional, percentage
    }
    """
    try:
        data = request.data
        
        coin_from = data.get("coinFrom", "").upper()
        network_from = data.get("networkFrom")
        coin_to = data.get("coinTo", "").upper()
        network_to = data.get("networkTo")
        amount = data.get("amount")
        withdrawal_amount = data.get("withdrawalAmount")
        withdrawal_address = data.get("withdrawalAddress")
        withdrawal_extra_id = data.get("withdrawalExtraId", "")
        refund_address = data.get("refundAddress")
        refund_extra_id = data.get("refundExtraId", "")
        rate_type = data.get("rateType", "float")
        slippage = data.get("slippage")
        
        # Validate required fields
        if not all([coin_from, network_from, coin_to, network_to, withdrawal_address]) or not (amount or withdrawal_amount):
            return Response(
                {"success": False, "message": "coinFrom, networkFrom, coinTo, networkTo, withdrawalAddress, and amount are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        # If slippage is provided, refundAddress is required
        if slippage and not refund_address:
            return Response(
                {"success": False, "message": "refundAddress is required when slippage is provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        url = f"{EXOLIX_API_BASE_URL}/transactions"
        
        body = {
            "coinFrom": coin_from,
            "networkFrom": network_from,
            "coinTo": coin_to,
            "networkTo": network_to,
            "withdrawalAddress": withdrawal_address,
            "withdrawalExtraId": withdrawal_extra_id,
            "rateType": rate_type
        }
        
        if amount:
            body["amount"] = float(amount)
        if withdrawal_amount:
            body["withdrawalAmount"] = float(withdrawal_amount)
        if refund_address:
            body["refundAddress"] = refund_address
        if refund_extra_id:
            body["refundExtraId"] = refund_extra_id
        if slippage:
            body["slippage"] = float(slippage)
        
        logger.info(f"Exolix Create Transaction Request: {body}")
        
        response = requests.post(url, json=body, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200 and response.status_code != 201:
            error_data = response.json()
            return Response(
                {"success": False, "message": "Failed to create transaction", "details": error_data},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        result = response.json()
        
        logger.info(f"Exolix Create Transaction Response: {result}")
        
        exolix_txn_id = result.get("id")
        
        # ✅ CREATE DATABASE RECORD (if authenticated)
        db_transaction = None
        if should_save_transaction(request):
            db_transaction = create_transaction_record(
                user=request.user,
                provider='EXOLIX',
                transaction_type='SWAP',
                source_currency=coin_from,
                source_amount=result.get("amount"),
                destination_currency=coin_to,
                destination_amount=result.get("amountTo"),
                wallet_address=withdrawal_address,
                provider_transaction_id=exolix_txn_id,
                provider_data={
                    'depositAddress': result.get('depositAddress'),
                    'depositExtraId': result.get('depositExtraId'),
                    'withdrawalAddress': result.get('withdrawalAddress'),
                    'withdrawalExtraId': result.get('withdrawalExtraId'),
                    'refundAddress': result.get('refundAddress'),
                    'refundExtraId': result.get('refundExtraId'),
                    'rate': result.get('rate'),
                    'rateType': result.get('rateType'),
                    'networkFrom': network_from,
                    'networkTo': network_to,
                    'exolix_result': result
                }
            )
        
        # ✅ STORE IN CACHE FOR TRACKING
        timestamp = int(time.time() * 1000)
        transaction_key = f"txn_exolix_{exolix_txn_id}"
        
        transaction_record = {
            'transaction_id': transaction_key,
            'db_id': db_transaction.id if db_transaction else None,
            'provider': 'EXOLIX',
            'status': 'PENDING',
            'created_at': timestamp,
            'exolix_txn_id': exolix_txn_id,
            'source_currency': coin_from,
            'destination_currency': coin_to,
            'amount': result.get("amount"),
            'estimated_amount': result.get("amountTo"),
            'deposit_address': result.get('depositAddress'),
            'deposit_extra_id': result.get('depositExtraId'),
            'withdrawal_address': result.get('withdrawalAddress'),
            'withdrawal_extra_id': result.get('withdrawalExtraId'),
            'rate': result.get('rate'),
            'rate_type': result.get('rateType'),
        }
        
        cache.set(transaction_key, transaction_record, timeout=86400)
        
        # Also store by Exolix ID for easy lookup
        cache.set(f"exolix_id_{exolix_txn_id}", transaction_key, timeout=86400)
        
        # ✅ Enhance response with our transaction ID
        enhanced_result = result.copy()
        if db_transaction:
            enhanced_result['ourTransactionId'] = db_transaction.transaction_id
            enhanced_result['transactionId'] = db_transaction.transaction_id
        
        logger.info(f"✅ Created Exolix transaction: {exolix_txn_id} (DB: {db_transaction.id if db_transaction else 'none'})")
        
        return Response(
            {
                "success": True,
                "transaction": enhanced_result
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Exolix create transaction error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET TRANSACTION STATUS - Check status of a transaction
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_transaction_status(request, transaction_id):
    """
    Get the status of an Exolix transaction.
    
    Path params:
    - transaction_id: The Exolix transaction ID
    """
    try:
        url = f"{EXOLIX_API_BASE_URL}/transactions/{transaction_id}"
        
        response = requests.get(url, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch transaction", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        result = response.json()
        
        exolix_status = result.get('status', '').lower()
        
        # Map Exolix status to our internal status
        status_mapping = {
            'wait': 'PENDING',
            'confirmation': 'PENDING',
            'confirmed': 'PENDING',
            'exchanging': 'PENDING',
            'sending': 'PENDING',
            'success': 'COMPLETED',
            'overdue': 'FAILED',
            'refund': 'FAILED',
            'refunded': 'FAILED',
        }
        
        mapped_status = status_mapping.get(exolix_status, 'PENDING')
        
        # ✅ UPDATE CACHE
        transaction_key = cache.get(f"exolix_id_{transaction_id}")
        if not transaction_key:
            transaction_key = f"txn_exolix_{transaction_id}"
        
        transaction_record = cache.get(transaction_key)
        
        if transaction_record:
            # Update cache record
            transaction_record['status'] = mapped_status
            transaction_record['updated_at'] = int(time.time() * 1000)
            transaction_record['last_status_check'] = result
            transaction_record['exolix_status'] = exolix_status
            
            # Add hash information if available
            if result.get('hashIn', {}).get('hash'):
                transaction_record['hash_in'] = result['hashIn']['hash']
            if result.get('hashOut', {}).get('hash'):
                transaction_record['hash_out'] = result['hashOut']['hash']
            
            cache.set(transaction_key, transaction_record, timeout=86400)
            
            # ✅ UPDATE DATABASE
            db_id = transaction_record.get('db_id')
            if db_id:
                try:
                    txn = Transaction.objects.get(id=db_id)
                    
                    # Only update if status actually changed
                    if txn.status != mapped_status:
                        txn.status = mapped_status
                        
                        # Update provider_data with latest status
                        if not txn.provider_data:
                            txn.provider_data = {}
                        txn.provider_data['latest_status'] = result
                        txn.provider_data['exolix_status'] = exolix_status
                        txn.provider_data['last_checked'] = timezone.now().isoformat()
                        
                        # Add hash if available
                        if result.get('hashOut', {}).get('hash'):
                            txn.transaction_hash = result['hashOut']['hash']
                            txn.provider_data['hashOut'] = result.get('hashOut')
                        if result.get('hashIn', {}).get('hash'):
                            txn.provider_data['hashIn'] = result.get('hashIn')
                        
                        # Set completed timestamp
                        if mapped_status == 'COMPLETED' and not txn.completed_at:
                            txn.completed_at = timezone.now()
                        
                        txn.save()
                        
                        logger.info(f"✅ Updated Exolix DB transaction {db_id}: {exolix_status} -> {mapped_status}")
                    else:
                        logger.debug(f"🔄 Exolix transaction {db_id} status unchanged: {mapped_status}")
                    
                except Transaction.DoesNotExist:
                    logger.error(f"❌ DB transaction {db_id} not found for Exolix ID {transaction_id}")
            else:
                logger.debug(f"⚠️ No DB record for Exolix transaction {transaction_id} (non-authenticated user)")
        else:
            logger.warning(f"⚠️ No cached transaction found for Exolix ID: {transaction_id}")
        
        return Response(
            {
                "success": True,
                "transaction": result,
                "mappedStatus": mapped_status
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Exolix get transaction status error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET TRANSACTION HISTORY - List all transactions (requires API key)
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_transaction_history(request):
    """
    Get transaction history from Exolix.
    Note: Requires API key to be configured for authorization.
    
    Query params:
    - page: Current page (optional)
    - size: Size per page (optional)
    - search: Search by transaction id (optional)
    - sort: Sort by field (optional)
    - order: Order (asc|desc) (optional)
    - dateFrom: Filter from date (optional)
    - dateTo: Filter to date (optional)
    - statuses: Filter by status (optional)
    """
    try:
        if not EXOLIX_API_KEY:
            return Response(
                {"success": False, "message": "API key not configured. This endpoint requires authorization."},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Build query params
        params = {}
        
        if request.query_params.get("page"):
            params["page"] = request.query_params.get("page")
        if request.query_params.get("size"):
            params["size"] = request.query_params.get("size")
        if request.query_params.get("search"):
            params["search"] = request.query_params.get("search")
        if request.query_params.get("sort"):
            params["sort"] = request.query_params.get("sort")
        if request.query_params.get("order"):
            params["order"] = request.query_params.get("order")
        if request.query_params.get("dateFrom"):
            params["dateFrom"] = request.query_params.get("dateFrom")
        if request.query_params.get("dateTo"):
            params["dateTo"] = request.query_params.get("dateTo")
        if request.query_params.get("statuses"):
            params["statuses"] = request.query_params.get("statuses")
        
        url = f"{EXOLIX_API_BASE_URL}/transactions"
        
        response = requests.get(url, params=params, headers=get_auth_headers(), timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch transaction history", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        data = response.json()
        
        return Response(
            {
                "success": True,
                "data": data.get("data", []),
                "count": data.get("count", 0)
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Exolix get transaction history error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )