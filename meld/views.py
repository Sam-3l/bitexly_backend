import requests
import logging
import time
import hashlib
import json
from requests.auth import HTTPBasicAuth
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.http import JsonResponse
from django.core.cache import cache
from django.utils import timezone

# ✅ ADD THESE IMPORTS
from users.transaction_helpers import create_transaction_record, should_save_transaction
from users.models import Transaction

from onramp.views import generate_onramp_headers, ONRAMP_API_BASE_URL

MELD_BASE_URL = "https://api.meld.io"

# Setup logger
logger = logging.getLogger(__name__)

# Split the API key into username and password
API_KEY, API_SECRET = settings.MELD_API_KEY.split(":")


def meld_request(method, endpoint, data=None, params=None):
    """
    Helper function to make authenticated requests to Meld.io.
    Handles GET/POST methods and gracefully manages errors.
    """
    url = f"{MELD_BASE_URL}{endpoint}"

    try:
        response = requests.request(
            method=method,
            url=url,
            auth=HTTPBasicAuth(API_KEY, API_SECRET),
            json=data,
            params=params,
            timeout=20
        )

        # Try to parse JSON safely
        try:
            res_data = response.json()
        except ValueError:
            res_data = {"error": "Invalid JSON response from Meld.io"}

        # Handle unsuccessful responses explicitly
        if not response.ok:
            # Meld sometimes returns detailed error structures — include them
            return Response(
                {
                    "success": False,
                    "status_code": response.status_code,
                    "message": res_data.get("message", "Meld request failed"),
                    "details": res_data,
                },
                status=response.status_code,
            )

        # Clean success response
        return Response(
            {
                "success": True,
                "data": res_data,
            },
            status=response.status_code,
        )

    except requests.exceptions.Timeout:
        return Response(
            {"success": False, "error": "Meld API timeout"},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    except requests.exceptions.ConnectionError:
        return Response(
            {"success": False, "error": "Network error while connecting to Meld.io"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    except requests.exceptions.RequestException as err:
        return Response(
            {"success": False, "error": str(err)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([])
def get_crypto_currencies(request):
    """Fetch available cryptocurrencies from Meld.io"""
    return meld_request("GET", "/service-providers/properties/crypto-currencies")


@api_view(['GET'])
@permission_classes([])
def get_fiat_currencies(request):
    """Fetch available fiat currencies from Meld.io"""
    return meld_request("GET", "/service-providers/properties/fiat-currencies")


@api_view(['GET'])
@permission_classes([])
def get_payment_methods(request):
    """Fetch payment methods based on provider/currency"""
    return meld_request("GET", "/service-providers/properties/payment-methods", params=request.query_params)


@api_view(['POST'])
@permission_classes([])
def get_crypto_quote(request):
    """
    Create a crypto quote (buy/sell estimate).
    Meld may return provider-specific errors which we catch and surface clearly.
    """
    response = meld_request("POST", "/payments/crypto/quote", data=request.data)

    # Custom handling for known Meld provider errors
    data = response.data if hasattr(response, "data") else {}
    if data.get("data", {}).get("code") in [
        "TRANSACTION_FAILED_GETTING_CRYPTO_QUOTE_FROM_PROVIDER",
        "INVALID_REQUEST_BODY",
    ]:
        return Response(
            {
                "success": False,
                "message": data["data"].get("message", "Failed to retrieve quote"),
                "hint": "Check the currency pair, amount, and provider limits.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return response


# ============================================================================
# UPDATED: create_session_widget - Now saves to database for auth users
# ============================================================================
@api_view(['POST'])
@permission_classes([])
def create_session_widget(request):
    """Create a crypto payment widget session"""
    try:
        data = request.data.copy()
        
        data['skipMeldScreen'] = True

        customer_id = data.get('externalCustomerId')
        session_type = data.get('sessionType', 'BUY')
        session_data = data.get('sessionData', {})
        
        # Make the request to Meld
        response = meld_request("POST", "/crypto/session/widget", data=data)
        
        if response.status_code in [200, 201]:
            response_data = response.data if hasattr(response, 'data') else {}
            
            if response_data.get('success'):
                widget_url = response_data.get('data', {}).get('widgetUrl') or response_data.get('widgetUrl')
                
                # CREATE DATABASE RECORD (if authenticated)
                db_transaction = None
                if should_save_transaction(request):
                    db_transaction = create_transaction_record(
                        user=request.user,
                        provider='MELD',
                        transaction_type=session_type.upper(),
                        source_currency=session_data.get('sourceCurrencyCode'),
                        source_amount=session_data.get('sourceAmount'),
                        destination_currency=session_data.get('destinationCurrencyCode'),
                        widget_url=widget_url,
                        payment_method=session_data.get('paymentMethod'),
                        provider_data={
                            'customer_id': customer_id,
                            'service_provider': session_data.get('serviceProvider'),
                        }
                    )
                
                # CREATE CACHE RECORD (for webhooks)
                timestamp = int(time.time() * 1000)
                unique_string = f"{customer_id}_{timestamp}_{session_type}"
                transaction_key = f"txn_meld_{hashlib.md5(unique_string.encode()).hexdigest()[:12]}"
                
                transaction_record = {
                    'transaction_id': transaction_key,
                    'db_id': db_transaction.id if db_transaction else None,  # Link to DB
                    'customer_id': customer_id,
                    'provider': session_data.get('serviceProvider'),
                    'session_type': session_type,
                    'status': 'PENDING',
                    'widget_url': widget_url,
                    'created_at': timestamp,
                    'source_currency': session_data.get('sourceCurrencyCode'),
                    'destination_currency': session_data.get('destinationCurrencyCode'),
                    'amount': session_data.get('sourceAmount'),
                }
                
                # Store transaction
                cache.set(transaction_key, transaction_record, timeout=86400)
                
                # Store latest transaction for this customer
                cache.set(f"customer_{customer_id}_latest", transaction_key, timeout=86400)
                
                # CRITICAL: Store a list of all transactions for this customer
                customer_txns = cache.get(f"customer_{customer_id}_all") or []
                customer_txns.append(transaction_key)
                cache.set(f"customer_{customer_id}_all", customer_txns, timeout=86400)
                
                # Return transaction ID in response
                response_data['transactionId'] = db_transaction.transaction_id if db_transaction else transaction_key
                
                return Response(response_data, status=response.status_code)
        
        return response
        
    except Exception as e:
        logger.error(f"Session creation error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================================
# UPDATED: meld_webhook - Now updates database for auth users
# ============================================================================
@api_view(['POST'])
@permission_classes([])
def meld_webhook(request):
    """
    Handle webhook notifications from Meld.
    """
    try:
        data = request.data
        logger.info(f"Meld webhook received: {json.dumps(data, indent=2)}")
        
        customer_id = data.get('externalCustomerId') or data.get('customerId')
        status_value = data.get('status', '').upper()
        
        # Try to get cryptoCurrency and fiatCurrency from webhook to match transaction
        crypto_currency = data.get('cryptoCurrencyCode') or data.get('destinationCurrencyCode')
        fiat_currency = data.get('fiatCurrencyCode') or data.get('sourceCurrencyCode')
        amount = data.get('sourceAmount') or data.get('cryptoAmount')
        
        status_mapping = {
            'COMPLETED': 'COMPLETED',
            'SUCCESS': 'COMPLETED',
            'SUCCESSFUL': 'COMPLETED',
            'FAILED': 'FAILED',
            'CANCELLED': 'FAILED',
            'PENDING': 'PENDING',
            'PROCESSING': 'PENDING'
        }
        
        mapped_status = status_mapping.get(status_value, 'PENDING')
        
        if customer_id:
            # Get all transactions for this customer
            customer_txns = cache.get(f"customer_{customer_id}_all") or []
            
            logger.info(f"Found {len(customer_txns)} transactions for customer {customer_id}")
            
            # Find matching transaction (most recent pending one)
            updated = False
            for txn_key in reversed(customer_txns):  # Check newest first
                transaction_record = cache.get(txn_key)
                
                if transaction_record and transaction_record.get('status') == 'PENDING':
                    # This is a pending transaction, update it
                    transaction_record['status'] = mapped_status
                    transaction_record['updated_at'] = int(time.time() * 1000)
                    transaction_record['webhook_data'] = data
                    transaction_record['provider_status'] = status_value
                    
                    cache.set(txn_key, transaction_record, timeout=86400)
                    
                    db_id = transaction_record.get('db_id')
                    if db_id:
                        try:
                            txn = Transaction.objects.get(id=db_id)
                            txn.status = mapped_status
                            
                            # Update provider_data with webhook info
                            if not txn.provider_data:
                                txn.provider_data = {}
                            txn.provider_data['webhook_data'] = data
                            
                            if mapped_status == 'COMPLETED':
                                txn.completed_at = timezone.now()
                            
                            txn.save()
                            
                            logger.info(f"✅ Updated DB transaction {db_id} to {mapped_status}")
                            
                        except Transaction.DoesNotExist:
                            logger.error(f"❌ DB transaction {db_id} not found")
                    
                    logger.info(f"✅ Updated transaction {txn_key} to status {mapped_status}")
                    updated = True
                    break  # Only update the first pending transaction
            
            if not updated:
                logger.warning(f"⚠️ No pending transactions found for customer {customer_id}")
        else:
            logger.warning("⚠️ No customer ID in webhook payload")
        
        return Response({"success": True, "message": "Webhook processed"}, status=200)
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}", exc_info=True)
        return Response({"success": False, "error": str(e)}, status=400)
    
    
@api_view(['GET'])
@permission_classes([])
def get_transaction_status(request):
    """
    Poll for transaction status.
    Combines cached status (from webhooks) with direct API checks.
    """
    try:
        transaction_id = request.query_params.get('transactionId')
        customer_id = request.query_params.get('customerId')
        
        if not (transaction_id or customer_id):
            return Response(
                {"success": False, "message": "transactionId or customerId required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get transaction record
        if not transaction_id and customer_id:
            transaction_id = cache.get(f"customer_{customer_id}_latest")
        
        if not transaction_id:
            return Response({
                "success": True,
                "status": "NOT_FOUND",
                "message": "No transaction found"
            })
        
        transaction_record = cache.get(transaction_id)
        
        if not transaction_record:
            return Response({
                "success": True,
                "status": "NOT_FOUND",
                "message": "Transaction not found"
            })
        
        provider = transaction_record.get('provider', '').upper()
        current_status = transaction_record.get('status', 'PENDING')
        last_webhook_update = transaction_record.get('updated_at')
        current_time = int(time.time() * 1000)
        
        # If status is PENDING and no webhook update in last 2 minutes, check API
        should_check_api = (
            current_status == 'PENDING' and 
            (not last_webhook_update or (current_time - last_webhook_update) > 120000)  # 2 minutes
        )
        
        if should_check_api:
            logger.info(f"Checking {provider} API for transaction {transaction_id}")
            
            if provider == 'ONRAMP':
                try:
                    url_hash = transaction_record.get('url_hash')
                    if url_hash:
                        body = {"urlHash": url_hash}
                        headers = generate_onramp_headers(body)
                        status_url = f"{ONRAMP_API_BASE_URL}/onramp/api/v2/common/transaction/getTransactionStatus"
                        
                        response = requests.post(status_url, headers=headers, json=body, timeout=10)
                        
                        if response.status_code == 200:
                            status_data = response.json()
                            if status_data.get('status') == 1:
                                txn_data = status_data.get('data', {})
                                onramp_status = txn_data.get('status', '').upper()
                                
                                status_map = {
                                    'COMPLETED': 'COMPLETED',
                                    'SUCCESS': 'COMPLETED',
                                    'SUCCESSFUL': 'COMPLETED',
                                    'FAILED': 'FAILED',
                                    'CANCELLED': 'FAILED',
                                    'EXPIRED': 'FAILED',
                                    'PENDING': 'PENDING',
                                    'PROCESSING': 'PENDING',
                                    'INITIATED': 'PENDING'
                                }
                                
                                new_status = status_map.get(onramp_status, 'PENDING')
                                
                                # Update cache if status changed
                                if new_status != current_status:
                                    transaction_record['status'] = new_status
                                    transaction_record['provider_status'] = onramp_status
                                    transaction_record['updated_at'] = current_time
                                    transaction_record['updated_via'] = 'API_POLL'
                                    cache.set(transaction_id, transaction_record, timeout=86400)
                                    current_status = new_status
                                    logger.info(f"✅ Updated {transaction_id} via API: {onramp_status} -> {new_status}")
                except Exception as e:
                    logger.error(f"OnRamp API check failed: {str(e)}")
            
            # For Meld and MoonPay, we rely on webhooks
            # But check if transaction is too old
            age_minutes = (current_time - transaction_record.get('created_at', current_time)) / 60000
            
            if age_minutes > 30 and current_status == 'PENDING':
                current_status = 'TIMEOUT'
                transaction_record['status'] = 'TIMEOUT'
                transaction_record['updated_at'] = current_time
                cache.set(transaction_id, transaction_record, timeout=86400)
                logger.info(f"⏱️ Transaction {transaction_id} timed out after {age_minutes} minutes")
        
        return Response({
            "success": True,
            "status": current_status,
            "transactionId": transaction_id,
            "provider": provider,
            "sessionType": transaction_record.get('session_type'),
            "amount": transaction_record.get('amount'),
            "sourceCurrency": transaction_record.get('source_currency'),
            "destinationCurrency": transaction_record.get('destination_currency'),
            "createdAt": transaction_record.get('created_at'),
            "updatedAt": transaction_record.get('updated_at'),
            "updatedVia": transaction_record.get('updated_via', 'WEBHOOK'),
            "providerStatus": transaction_record.get('provider_status'),
            "message": _get_status_message(current_status)
        })
        
    except Exception as e:
        logger.error(f"Status check error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def _get_status_message(status):
    """Helper to get user-friendly status messages"""
    messages = {
        'PENDING': 'Transaction is being processed',
        'COMPLETED': 'Transaction completed successfully',
        'FAILED': 'Transaction failed',
        'TIMEOUT': 'Transaction timed out - please check with provider',
        'NOT_FOUND': 'Transaction not found'
    }
    return messages.get(status, 'Unknown status')