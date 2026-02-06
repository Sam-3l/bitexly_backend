import json
import time
import hmac
import hashlib
import uuid
import logging
from urllib.parse import urlencode
from functools import lru_cache

import requests
from django.core.cache import cache
from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

# ✅ ADD THESE IMPORTS
from users.transaction_helpers import create_transaction_record, should_save_transaction
from users.models import Transaction

# Setup logger
logger = logging.getLogger(__name__)

# FinchPay Configuration
FINCHPAY_API_KEY = settings.FINCHPAY_API_KEY
FINCHPAY_SECRET_KEY = settings.FINCHPAY_SECRET_KEY
FINCHPAY_API_BASE_URL = "https://api.finchpay.io"
FINCHPAY_WIDGET_BASE_URL = "https://widget.finchpay.io"


def get_finchpay_headers():
    """
    Generate headers for FinchPay API requests.
    FinchPay uses simple x-api-key authentication.
    """
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-api-key": FINCHPAY_API_KEY
    }


def generate_wallet_signature(email, wallet_address, wallet_extra, secret_key):
    """
    Generate HMAC-SHA256 signature for wallet address prefilling.
    Formula: HMAC-SHA256(email + wallet_address + wallet_extra, secret_key)
    """
    payload = f"{email}{wallet_address}{wallet_extra}"
    signature = hmac.new(
        secret_key.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature


def parse_coin_network(coin_code):
    """
    Parse coin code to extract actual coin and network.
    Handles format: USDT_TRC20, USDT_ERC20, BTC, etc.
    """
    coin_code = coin_code.upper()
    
    if "_" in coin_code:
        parts = coin_code.split("_", 1)
        network = parts[1]

        if network == "TRON":
            network = "TRC20"

        return parts[0], network
    
    return (coin_code, None)


@lru_cache(maxsize=1)
def get_finchpay_currencies_cached():
    """
    Fetch and cache currencies from FinchPay API.
    """
    try:
        headers = get_finchpay_headers()
        url = f"{FINCHPAY_API_BASE_URL}/v1/currencies"
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to fetch FinchPay currencies: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Error fetching FinchPay currencies: {str(e)}")
        return []


@api_view(["GET"])
@permission_classes([])
def get_finchpay_currencies(request):
    """
    Fetch all supported currencies from FinchPay API.
    """
    try:
        currencies_data = get_finchpay_currencies_cached()
        
        if not currencies_data:
            return Response(
                {"success": False, "message": "Failed to fetch currencies from FinchPay"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Organize data
        fiat_currencies = []
        crypto_currencies = {}
        payment_methods_by_currency = {}
        
        for currency in currencies_data:
            if currency.get("is_fiat"):
                fiat_currencies.append(currency["ticker"])
                if currency.get("payment_methods"):
                    payment_methods_by_currency[currency["ticker"]] = currency["payment_methods"]
            else:
                ticker = currency["ticker"]
                network = currency.get("network", "")
                
                if ticker not in crypto_currencies:
                    crypto_currencies[ticker] = []
                if network and network not in crypto_currencies[ticker]:
                    crypto_currencies[ticker].append(network)
        
        return Response(
            {
                "success": True,
                "data": {
                    "fiatCurrencies": sorted(fiat_currencies),
                    "cryptocurrencies": crypto_currencies,
                    "paymentMethodsByCurrency": payment_methods_by_currency,
                    "raw": currencies_data
                }
            },
            status=status.HTTP_200_OK
        )
            
    except Exception as e:
        logger.error(f"FinchPay currencies error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([])
def get_finchpay_limits(request):
    """
    Get min/max limits for a specific currency pair from FinchPay API.
    """
    try:
        from_currency = request.GET.get('from_currency', '').upper()
        to_currency = request.GET.get('to_currency', '').upper()
        to_network = request.GET.get('to_network', '')
        payment_method = request.GET.get('payment_method', '')
        
        if not from_currency or not to_currency:
            return Response(
                {"success": False, "message": "from_currency and to_currency are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        headers = get_finchpay_headers()
        url = f"{FINCHPAY_API_BASE_URL}/v2/currencies/limits"
        
        params = {
            "from_currency": from_currency,
            "to_currency": to_currency
        }
        
        if to_network:
            params["to_network"] = to_network
        if payment_method:
            params["payment_method"] = payment_method
        
        logger.info(f"Fetching limits from FinchPay: {url} with params: {params}")
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            return Response(
                {"success": True, "data": response.json()},
                status=status.HTTP_200_OK
            )
        else:
            error_data = response.json() if response.text else {}
            logger.error(f"FinchPay limits API error: {response.status_code} - {response.text}")
            return Response(
                {
                    "success": False,
                    "message": error_data.get("message", "Failed to fetch limits from FinchPay"),
                    "details": response.text
                },
                status=response.status_code
            )
            
    except Exception as e:
        logger.error(f"FinchPay limits error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([])
def get_finchpay_quote(request):
    """
    Get REAL exchange rate quote from FinchPay API.
    """
    try:
        data = request.data
        action = data.get("action", "").upper()
        source_currency = data.get("sourceCurrencyCode", "").upper()
        destination_currency = data.get("destinationCurrencyCode", "").upper()
        source_amount = data.get("sourceAmount")
        payment_method = data.get("paymentMethod", "card")

        if not all([action, source_currency, destination_currency, source_amount]):
            return Response(
                {"success": False, "message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if action != "BUY":
            return Response(
                {
                    "success": False,
                    "message": "FinchPay API currently only supports BUY (fiat to crypto) quotes."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # BUY: fiat -> crypto
        from_currency = source_currency
        coin, network = parse_coin_network(destination_currency)
        to_currency = coin
        to_network = network

        # Build API request
        headers = get_finchpay_headers()
        url = f"{FINCHPAY_API_BASE_URL}/v1/estimates"
        
        params = {
            "from_amount": float(source_amount),
            "from_currency": from_currency,
            "to_currency": to_currency,
            "payment_method": payment_method
        }
        
        if to_network:
            params["to_network"] = to_network
        
        logger.info(f"FinchPay estimate request: {url} with params: {params}")
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code != 200:
            error_data = response.json() if response.text else {}
            logger.error(f"FinchPay estimate API error: {response.status_code} - {response.text}")
            
            error_message = error_data.get("message", "Failed to get quote from FinchPay")
            min_amount = None
            max_amount = None
            
            if "minimum" in error_message.lower() or "min" in error_message.lower():
                import re
                min_match = re.search(r'(\d+\.?\d*)', error_message)
                if min_match:
                    min_amount = float(min_match.group(1))
            
            if "maximum" in error_message.lower() or "max" in error_message.lower():
                import re
                max_match = re.search(r'(\d+\.?\d*)', error_message)
                if max_match:
                    max_amount = float(max_match.group(1))
            
            return Response(
                {
                    "success": False,
                    "message": error_message,
                    "details": error_message,
                    "minAmount": min_amount,
                    "maxAmount": max_amount,
                    "apiResponse": error_data
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        estimate_data = response.json()
        logger.info(f"FinchPay estimate response: {estimate_data}")
        
        # Standardize response
        standardized_quote = {
            "sourceCurrency": source_currency,
            "destinationCurrency": destination_currency,
            "sourceAmount": source_amount,
            "estimatedAmount": estimate_data.get("to_amount"),
            "cryptoAmount": estimate_data.get("to_amount"),
            "rate": estimate_data.get("exchange_rate"),
            "exchangeRate": estimate_data.get("exchange_rate"),
            "fees": {
                "serviceFee": float(estimate_data.get("service_fee_amount", 0)),
                "networkFee": float(estimate_data.get("network_fee_amount", 0)),
                "transactionFee": float(estimate_data.get("service_fee_amount", 0)),
                "serviceFeeCurrency": estimate_data.get("service_fee_currency"),
                "networkFeeCurrency": estimate_data.get("network_fee_currency")
            },
            "totalFees": float(estimate_data.get("service_fee_amount", 0)) + float(estimate_data.get("network_fee_amount", 0)),
            "txnType": "BUY",
            "network": estimate_data.get("to_network") or to_network,
            "paymentMethod": estimate_data.get("payment_method"),
            "fromAmount": estimate_data.get("from_amount"),
            "fromCurrency": estimate_data.get("from_currency"),
            "convertedAmount": estimate_data.get("converted_amount"),
            "convertedAmountCurrency": estimate_data.get("converted_amount_currency")
        }

        return Response(
            {
                "success": True,
                "quote": standardized_quote,
                "rawEstimate": estimate_data
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"FinchPay quote error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================================
# ✅ UPDATED: generate_finchpay_url - Now saves to database for auth users
# ============================================================================
@api_view(["POST"])
@permission_classes([])
def generate_finchpay_url(request):
    """
    Generate FinchPay widget URL with pre-filled parameters.
    """
    try:
        data = request.data
        action = data.get("action", "").upper()
        source_currency = data.get("sourceCurrencyCode", "").upper()
        destination_currency = data.get("destinationCurrencyCode", "").upper()
        source_amount = data.get("sourceAmount")
        wallet_address = data.get("walletAddress")
        wallet_extra = data.get("walletExtra", "")
        email = data.get("email", "")

        if not all([action, source_currency, destination_currency, source_amount]):
            return Response(
                {"success": False, "message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if action not in ["BUY", "SELL"]:
            return Response(
                {"success": False, "message": "Action must be BUY or SELL"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if action == "SELL":
            return Response(
                {
                    "success": False,
                    "message": "FinchPay SELL (crypto to fiat) is not supported through the API at this time."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parse crypto coin and network for BUY
        coin, network = parse_coin_network(destination_currency)
        fiat_currency = source_currency

        # Generate external_id for tracking
        external_id = str(uuid.uuid4())

        # Build widget URL parameters
        params = {
            "partner_key": FINCHPAY_API_KEY,
            "a": float(source_amount),
            "p": fiat_currency,
            "c": coin,
            "external_id": external_id
        }

        if network:
            params["n"] = network

        # Add wallet address with signature if provided
        if wallet_address:
            signature = generate_wallet_signature(
                email=email,
                wallet_address=wallet_address,
                wallet_extra=wallet_extra,
                secret_key=FINCHPAY_SECRET_KEY
            )
            
            params["wallet_address"] = wallet_address
            params["sign"] = signature
            
            if wallet_extra:
                params["wallet_extra"] = wallet_extra
            
            if email:
                params["email"] = email

        # Build the complete widget URL
        widget_url = f"{FINCHPAY_WIDGET_BASE_URL}/payment_method?{urlencode(params)}"

        # CREATE DATABASE RECORD (if authenticated)
        db_transaction = None
        if should_save_transaction(request):
            db_transaction = create_transaction_record(
                user=request.user,
                provider='FINCHPAY',
                transaction_type=action.upper(),
                source_currency=source_currency,
                source_amount=source_amount,
                destination_currency=destination_currency,
                network=network,
                wallet_address=wallet_address,
                widget_url=widget_url,
                provider_transaction_id=external_id,
                provider_data={
                    'coin': coin,
                    'email': email,
                }
            )

        # STORE IN CACHE
        transaction_key = f"txn_finchpay_{external_id}"
        transaction_record = {
            'transaction_id': transaction_key,
            'db_id': db_transaction.id if db_transaction else None,  # ✅ Link to DB
            'external_id': external_id,
            'provider': 'FINCHPAY',
            'status': 'PENDING',
            'widget_url': widget_url,
            'created_at': int(time.time() * 1000),
            'flow_type': action,
            'source_currency': source_currency,
            'destination_currency': destination_currency,
            'amount': source_amount,
            'coin': coin,
            'network': network,
            'wallet_address': wallet_address,
            'email': email
        }

        cache.set(transaction_key, transaction_record, timeout=86400)

        logger.info(f"✅ Generated FinchPay widget URL for external_id: {external_id}")

        return Response(
            {
                "success": True,
                "widgetUrl": widget_url,
                "paymentUrl": widget_url,
                "transactionId": db_transaction.transaction_id if db_transaction else transaction_key,
                "externalId": external_id,
                "data": {
                    "widgetUrl": widget_url,
                    "externalId": external_id,
                    "coin": coin,
                    "network": network,
                    "fiatAmount": float(source_amount),
                    "fiatCurrency": fiat_currency
                }
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"FinchPay generate URL error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([])
def get_finchpay_transaction_status(request):
    """
    Get FinchPay transaction status from API by external_id or transaction_id.
    """
    try:
        external_id = request.data.get('externalId') or request.data.get('external_id')
        transaction_id = request.data.get('transactionId') or request.data.get('transaction_id')
        
        if not external_id and not transaction_id:
            return Response(
                {"success": False, "message": "externalId or transactionId is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        headers = get_finchpay_headers()
        
        if external_id:
            url = f"{FINCHPAY_API_BASE_URL}/v1/transaction/external/{external_id}"
            logger.info(f"Checking FinchPay transaction by external_id: {external_id}")
        else:
            url = f"{FINCHPAY_API_BASE_URL}/v1/transaction/{transaction_id}"
            logger.info(f"Checking FinchPay transaction by id: {transaction_id}")
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            transaction_data = response.json()
            
            status_mapping = {
                'CREATED': 'PENDING',
                'PROCESSING': 'PENDING',
                'SENDING': 'PENDING',
                'HOLD': 'PENDING',
                'COMPLETE': 'COMPLETED',
                'COMPLETED': 'COMPLETED',
                'REFUNDED': 'FAILED',
                'ERROR': 'FAILED',
                'EXPIRED': 'FAILED',
                'REJECTED_BY_ANTI_FRAUD': 'FAILED'
            }
            
            finchpay_status = transaction_data.get('status', '').upper()
            mapped_status = status_mapping.get(finchpay_status, 'PENDING')
            
            # Update cached transaction if exists
            if external_id:
                transaction_key = f"txn_finchpay_{external_id}"
                cached_record = cache.get(transaction_key)
                
                if cached_record:
                    cached_record['status'] = mapped_status
                    cached_record['updated_at'] = int(time.time() * 1000)
                    cached_record['api_data'] = transaction_data
                    cached_record['provider_status'] = finchpay_status
                    cache.set(transaction_key, cached_record, timeout=86400)
            
            logger.info(f"✅ FinchPay transaction status: {mapped_status} (original: {finchpay_status})")
            
            return Response(
                {
                    "success": True,
                    "status": mapped_status,
                    "transactionData": transaction_data
                },
                status=status.HTTP_200_OK
            )
        elif response.status_code == 404:
            return Response(
                {
                    "success": False,
                    "message": "Transaction not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        else:
            error_data = response.json() if response.text else {}
            logger.error(f"FinchPay status API error: {response.status_code} - {response.text}")
            return Response(
                {
                    "success": False,
                    "message": error_data.get("message", "Failed to get transaction status"),
                    "details": response.text
                },
                status=response.status_code
            )
        
    except Exception as e:
        logger.error(f"FinchPay status check error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# ============================================================================
# Finchpay_webhook - Now updates database for auth users
# ============================================================================
@api_view(['POST'])
@permission_classes([])
def finchpay_webhook(request):
    """
    Handle FinchPay webhook notifications.
    """
    try:
        # Get the raw body for signature verification
        raw_body = request.body.decode('utf-8')
        
        # Get signature from header
        received_signature = request.headers.get('x-signature', '')
        
        if not received_signature:
            logger.warning("⚠️ No x-signature header in FinchPay webhook")
            return Response(
                {"success": False, "message": "Missing x-signature header"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Verify signature using HMAC-SHA256
        computed_signature = hmac.new(
            FINCHPAY_SECRET_KEY.encode(),
            raw_body.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if received_signature != computed_signature:
            logger.warning(f"❌ Invalid FinchPay webhook signature")
            return Response(
                {"success": False, "message": "Invalid signature"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Parse webhook data
        data = request.data
        logger.info(f"📩 FinchPay webhook received: {json.dumps(data, indent=2)}")
        
        # Extract transaction details
        finchpay_transaction_id = data.get('id')
        webhook_status = data.get('status', '').upper()
        external_id = data.get('external_id')
        
        # Status mapping
        status_mapping = {
            'CREATED': 'PENDING',
            'PROCESSING': 'PENDING',
            'SENDING': 'PENDING',
            'HOLD': 'PENDING',
            'COMPLETE': 'COMPLETED',
            'COMPLETED': 'COMPLETED',
            'REFUNDED': 'FAILED',
            'ERROR': 'FAILED',
            'EXPIRED': 'FAILED',
            'REJECTED_BY_ANTI_FRAUD': 'FAILED'
        }
        
        mapped_status = status_mapping.get(webhook_status, 'PENDING')
        
        # Update cached transaction if we have external_id
        if external_id:
            transaction_key = f"txn_finchpay_{external_id}"
            transaction_record = cache.get(transaction_key)
            
            if transaction_record:
                transaction_record['status'] = mapped_status
                transaction_record['updated_at'] = int(time.time() * 1000)
                transaction_record['webhook_data'] = data
                transaction_record['provider_status'] = webhook_status
                transaction_record['finchpay_transaction_id'] = finchpay_transaction_id
                transaction_record['transaction_hash'] = data.get('transaction_hash')
                transaction_record['payment_method'] = data.get('payment_method')
                transaction_record['partner_profit_amount'] = data.get('partner_profit_amount')
                transaction_record['partner_profit_currency'] = data.get('partner_profit_currency')
                transaction_record['amount_from'] = data.get('amount_from')
                transaction_record['amount_to'] = data.get('amount_to')
                transaction_record['asset_from'] = data.get('asset_from')
                transaction_record['asset_to'] = data.get('asset_to')
                transaction_record['asset_network_to'] = data.get('asset_network_to')
                transaction_record['event_time'] = data.get('event_time')
                transaction_record['side'] = data.get('side')
                
                cache.set(transaction_key, transaction_record, timeout=86400)
                
                # ✅ UPDATE DATABASE (NEW)
                db_id = transaction_record.get('db_id')
                if db_id:
                    try:
                        txn = Transaction.objects.get(id=db_id)
                        txn.status = mapped_status
                        txn.transaction_hash = data.get('transaction_hash')
                        txn.payment_method = data.get('payment_method')
                        
                        # Update provider_data with webhook info
                        if not txn.provider_data:
                            txn.provider_data = {}
                        txn.provider_data['webhook_data'] = data
                        txn.provider_data['finchpay_transaction_id'] = finchpay_transaction_id
                        txn.provider_data['partner_profit'] = {
                            'amount': data.get('partner_profit_amount'),
                            'currency': data.get('partner_profit_currency')
                        }
                        
                        if mapped_status == 'COMPLETED':
                            txn.completed_at = timezone.now()
                        
                        txn.save()
                        
                        logger.info(f"✅ Updated DB transaction {db_id} to {mapped_status}")
                        
                    except Transaction.DoesNotExist:
                        logger.error(f"❌ DB transaction {db_id} not found")
                
                logger.info(f"✅ Updated FinchPay transaction {transaction_key} to {mapped_status}")
            else:
                logger.warning(f"⚠️ Transaction not found in cache for external_id: {external_id}")
        else:
            logger.warning("⚠️ No external_id in FinchPay webhook payload")
        
        return Response(
            {"success": True, "message": "Webhook processed successfully"},
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"❌ FinchPay webhook error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Webhook processing failed", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([])
def get_finchpay_payment_methods(request):
    """
    Return supported payment methods.
    """
    try:
        payment_methods = {
            "card": "Credit/Debit Cards",
            "sepa": "SEPA Bank Transfer",
            "google_pay": "Google Pay",
            "apple_pay": "Apple Pay",
            "bank_link": "Bank Link",
            "pix": "PIX (Brazil)",
            "picpay": "PicPay (Brazil)",
            "boleto": "Boleto (Brazil)",
            "oxxo": "OXXO (Mexico)",
            "spei": "SPEI (Mexico)",
            "dana": "DANA (Indonesia)",
            "ovo": "OVO (Indonesia)",
            "mandiri_va": "Mandiri VA (Indonesia)",
            "bri_va": "BRI VA (Indonesia)",
            "vietqr": "VietQR (Vietnam)",
            "vnpay": "VNPay (Vietnam)",
            "skrill": "Skrill",
            "neteller": "Neteller",
            "paysafe_card": "Paysafe Card"
        }
        
        return Response(
            {
                "success": True,
                "data": {
                    "paymentMethods": payment_methods
                }
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"FinchPay payment methods error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )