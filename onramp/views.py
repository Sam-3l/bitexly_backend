import json
import time
import hmac
import hashlib
from base64 import b64encode
import requests
import logging
import time
from functools import lru_cache

from django.core.cache import cache
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from users.transaction_helpers import create_transaction_record, should_save_transaction, update_transaction_status, find_transaction
from django.utils import timezone
from users.models import Transaction

# Setup logger
logger = logging.getLogger(__name__)

# Onramp API Configuration
ONRAMP_API_BASE_URL = "https://api.onramp.money"
ONRAMP_API_KEY = settings.ONRAMP_API_KEY
ONRAMP_API_SECRET = settings.ONRAMP_API_SECRET


def generate_onramp_headers(body):
    """
    Generate required headers for Onramp API requests.
    """
    payload = {
        "timestamp": int(time.time() * 1000),
        "body": body
    }

    payload_encoded = b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(
        ONRAMP_API_SECRET.encode(),
        payload_encoded.encode(),
        hashlib.sha512
    ).hexdigest()

    return {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "X-ONRAMP-SIGNATURE": signature,
        "X-ONRAMP-APIKEY": ONRAMP_API_KEY,
        "X-ONRAMP-PAYLOAD": payload_encoded,
    }


@lru_cache(maxsize=1)
def get_onramp_config_mappings():
    """
    Fetch and cache the configuration mappings from Onramp API.
    This includes fiatSymbolMapping, coinSymbolMapping, and chainMapping.
    Cache expires on server restart.
    """
    try:
        body = {}
        headers = generate_onramp_headers(body)
        url = f"{ONRAMP_API_BASE_URL}/onramp/api/v2/common/transaction/allConfigMapping"
        response = requests.post(url, headers=headers, json=body, timeout=30)
        
        if response.status_code == 200:
            data = response.json().get("data", {})
            logger.info("Successfully fetched Onramp config mappings")
            return data
        else:
            logger.error(f"Failed to fetch config mappings: {response.status_code}")
            return {}
    except Exception as e:
        logger.error(f"Error fetching config mappings: {str(e)}")
        return {}

def parse_coin_network(coin_code):
    """
    Parse coin code to extract actual coin and network.
    Handles special format: USDT_TRC20, USDT_ERC20, etc.
    
    Returns:
        tuple: (actual_coin_code, network) e.g., ("usdt", "trc20")
    """
    if "_" in coin_code:
        parts = coin_code.split("_")
        actual_coin = parts[0].lower()
        network = parts[1].lower() if len(parts) > 1 else None
        if network == "tron":
            network = "trc20"
        return (actual_coin, network)
    
    # No underscore, use the get_available_network function
    return (coin_code.lower(), None)


def get_fiat_type(currency_code):
    """
    Get the fiatType numeric code for a given currency code.
    Handles inconsistencies in casing or unexpected data types.
    """
    config = get_onramp_config_mappings()
    fiat_mapping = config.get("fiatSymbolMapping", {})

    # Try uppercase, lowercase, or fallback to empty dict
    fiat_info = fiat_mapping.get(currency_code.upper()) or \
                fiat_mapping.get(currency_code.lower()) or {}

    # If the mapping is an int instead of dict, wrap it properly
    if isinstance(fiat_info, int):
        fiat_type = fiat_info
    else:
        fiat_type = fiat_info.get("fiatType")

    if fiat_type is None:
        logger.warning(
            f"Fiat type not found for {currency_code}. Available: "
            f"{list(fiat_mapping.keys())[:20]}"
        )

    return fiat_type


def get_coin_code(currency_code):
    """
    Validate if a coin is supported and get its details.
    """
    config = get_onramp_config_mappings()
    coin_mapping = config.get("coinSymbolMapping", {})
    
    currency_lower = currency_code.lower()
    coin_info = coin_mapping.get(currency_lower, {})
    
    if not coin_info:
        logger.warning(f"Coin not found for {currency_code}. Available: {list(coin_mapping.keys())[:20]}")
        
    return coin_info

def get_available_network(coin_code):
    """
    Returns the best network for a given coin_code.
    Fetches all_config internally and handles edge cases gracefully.
    
    Returns:
        dict: {
            "success": bool,
            "coin": str,
            "network": str or None,
            "message": str
        }
    """
    try:
        coin_code_clean = coin_code.strip().lower()
        
        # Use cached Onramp config instead of fetching from localhost
        config = get_onramp_config_mappings()
        coin_mapping = config.get("coinSymbolMapping", {})
        chain_mapping = config.get("chainSymbolMapping", {})
        
        if not coin_mapping or not chain_mapping:
            return {
                "success": False,
                "coin": coin_code_clean,
                "network": None,
                "message": "Coin or chain mappings are missing in config."
            }
        
        # Standardize keys for matching
        coin_mapping_std = {str(k).strip().lower(): v for k, v in coin_mapping.items()}
        chain_mapping_std = {str(k).strip().lower(): v for k, v in chain_mapping.items()}

        if coin_code_clean not in coin_mapping_std:
            return {
                "success": False,
                "coin": coin_code_clean,
                "network": None,
                "message": f"Coin '{coin_code}' not found in mappings."
            }
        
        # Preferred networks
        preferred_networks = ["bep20", "erc20", "trc20", "matic20"]
        
        for net in preferred_networks:
            if net in chain_mapping_std:
                return {
                    "success": True,
                    "coin": coin_code_clean,
                    "network": net,
                    "message": "Preferred network found."
                }
        
        # If none of the preferred networks exist, pick the first available
        fallback_network = next(iter(chain_mapping_std), None)
        if fallback_network:
            return {
                "success": True,
                "coin": coin_code_clean,
                "network": fallback_network,
                "message": "No preferred network found, using fallback."
            }
        
        # No networks available at all
        return {
            "success": False,
            "coin": coin_code_clean,
            "network": None,
            "message": "No networks available."
        }
    
    except Exception as e:
        return {
            "success": False,
            "coin": coin_code_clean,
            "network": None,
            "message": f"Unexpected error: {str(e)}"
        }


# ------------------------------------------------------------------
# ✅ QUOTE ENDPOINT (STANDARD API - DYNAMIC MAPPING)
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def get_onramp_quote(request):
    """
    Get quote for BUY/SELL transactions using the standard quotes API.
    Supports both regular coins and network-specific coins (e.g., USDT_TRC20)
    """
    try:
        data = request.data
        action = data.get("action", "").upper()
        source_currency = data.get("sourceCurrencyCode", "").upper()
        destination_currency = data.get("destinationCurrencyCode", "").upper()
        source_amount = data.get("sourceAmount")

        if not all([action, source_currency, destination_currency, source_amount]):
            return Response(
                {"success": False, "message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine transaction type
        txn_type = "BUY" if action == "BUY" else "SELL"

        # Parse coin and network
        if txn_type == "BUY":
            # destination is crypto
            actual_coin, network = parse_coin_network(destination_currency)
            if not network:
                resp = get_available_network(actual_coin)
                network = resp.get("network")
        else:
            # source is crypto
            actual_coin, network = parse_coin_network(source_currency)
            if not network:
                resp = get_available_network(actual_coin)
                network = resp.get("network")

        # Prepare the request body based on transaction type
        if txn_type == "BUY":
            # For BUY: fiat -> crypto
            fiat_type = get_fiat_type(source_currency)
            if fiat_type is None:
                config = get_onramp_config_mappings()
                available_fiats = list(config.get("fiatSymbolMapping", {}).keys())
                
                return Response(
                    {
                        "success": False,
                        "message": f"Unsupported fiat currency: {source_currency}",
                        "supportedCurrencies": available_fiats
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate crypto currency (use actual coin without network suffix)
            coin_info = get_coin_code(actual_coin)
            if not coin_info:
                config = get_onramp_config_mappings()
                available_coins = list(config.get("coinSymbolMapping", {}).keys())
                
                return Response(
                    {
                        "success": False,
                        "message": f"Unsupported cryptocurrency: {actual_coin}",
                        "supportedCoins": available_coins[:50]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            quote_body = {
                "coinCode": actual_coin,
                "network": network.lower(),
                "fiatAmount": float(source_amount),
                "fiatType": fiat_type,
                "type": 1
            }
        else:
            # For SELL: crypto -> fiat
            fiat_type = get_fiat_type(destination_currency)
            if fiat_type is None:
                config = get_onramp_config_mappings()
                available_fiats = list(config.get("fiatSymbolMapping", {}).keys())
                
                return Response(
                    {
                        "success": False,
                        "message": f"Unsupported fiat currency: {destination_currency}",
                        "supportedCurrencies": available_fiats
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate crypto currency
            coin_info = get_coin_code(actual_coin)
            if not coin_info:
                config = get_onramp_config_mappings()
                available_coins = list(config.get("coinSymbolMapping", {}).keys())
                
                return Response(
                    {
                        "success": False,
                        "message": f"Unsupported cryptocurrency: {actual_coin}",
                        "supportedCoins": available_coins[:50]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            quote_body = {
                "coinCode": actual_coin,
                "network": network.lower(),
                "quantity": float(source_amount),
                "fiatType": fiat_type,
                "type": 2
            }

        # Use the quotes endpoint
        quote_url = f"{ONRAMP_API_BASE_URL}/onramp/api/v2/common/transaction/quotes"
        headers = generate_onramp_headers(quote_body)

        logger.info(f"Onramp Quote Request to {quote_url}: {quote_body}")

        quote_response = requests.post(quote_url, headers=headers, json=quote_body, timeout=30)
        quote_json = quote_response.json()

        logger.info(f"Onramp Quote Response: {quote_json}")

        # FIXED: Better error handling with min/max extraction
        if quote_json.get("status") != 1:
            error_message = quote_json.get("error", "Unknown error")
            
            # Extract min/max amounts from error message
            min_amount = None
            max_amount = None
            
            # Parse minimum amount
            if "minimum" in error_message.lower():
                import re
                min_match = re.search(r'minimum.*?(\d+\.?\d*)', error_message, re.IGNORECASE)
                if min_match:
                    min_amount = float(min_match.group(1))
            
            # Parse maximum amount
            if "maximum" in error_message.lower():
                import re
                max_match = re.search(r'maximum.*?(\d+\.?\d*)', error_message, re.IGNORECASE)
                if max_match:
                    max_amount = float(max_match.group(1))
            
            return Response(
                {
                    "success": False,
                    "message": error_message,
                    "details": error_message,
                    "minAmount": min_amount,
                    "maxAmount": max_amount,
                    "apiResponse": quote_json,
                    "requestBody": quote_body
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        quote_data = quote_json.get("data", {})

        # Standardize the response (use original currency codes with network suffix)
        if txn_type == "BUY":
            standardized_quote = {
                "sourceCurrency": source_currency,
                "destinationCurrency": destination_currency,  # Keep original e.g., USDT_TRC20
                "sourceAmount": source_amount,
                "estimatedAmount": quote_data.get("quantity"),
                "cryptoAmount": quote_data.get("quantity"),  # ADDED: For frontend compatibility
                "rate": quote_data.get("rate"),
                "exchangeRate": quote_data.get("rate"),  # ADDED: For frontend compatibility
                "fees": {
                    "onrampFee": quote_data.get("onrampFee", 0),
                    "clientFee": quote_data.get("clientFee", 0),
                    "gatewayFee": quote_data.get("gatewayFee", 0),
                    "gasFee": quote_data.get("gasFee", 0),
                    "transactionFee": quote_data.get("clientFee", 0),  # ADDED: For frontend
                    "networkFee": quote_data.get("gasFee", 0),  # ADDED: For frontend
                },
                "totalFees": sum([
                    quote_data.get("onrampFee", 0),
                    quote_data.get("clientFee", 0),
                    quote_data.get("gatewayFee", 0),
                    quote_data.get("gasFee", 0)
                ]),
                "txnType": txn_type,
                "network": network,
            }
        else:
            standardized_quote = {
                "sourceCurrency": source_currency,  # Keep original e.g., USDT_TRC20
                "destinationCurrency": destination_currency,
                "sourceAmount": source_amount,
                "estimatedAmount": quote_data.get("fiatAmount"),
                "fiatAmount": quote_data.get("fiatAmount"),  # ADDED: For frontend compatibility
                "rate": quote_data.get("rate"),
                "exchangeRate": quote_data.get("rate"),  # ADDED: For frontend compatibility
                "fees": {
                    "onrampFee": quote_data.get("onrampFee", 0),
                    "clientFee": quote_data.get("clientFee", 0),
                    "gatewayFee": quote_data.get("gatewayFee", 0),
                    "tdsFee": quote_data.get("tdsFee", 0),
                    "transactionFee": quote_data.get("clientFee", 0),  # ADDED: For frontend
                    "networkFee": quote_data.get("gasFee", 0),  # ADDED: For frontend
                },
                "totalFees": sum([
                    quote_data.get("onrampFee", 0),
                    quote_data.get("clientFee", 0),
                    quote_data.get("gatewayFee", 0),
                    quote_data.get("tdsFee", 0)
                ]),
                "txnType": txn_type,
                "network": network,
            }

        return Response({"success": True, "quote": standardized_quote}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Onramp Quote Error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ PAYMENT METHODS (ALL CONFIG MAPPINGS)
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([])
def get_onramp_payment_methods(request):
    """
    Fetch all supported fiat currencies, coins, and chains from Onramp.
    """
    try:
        body = {}
        headers = generate_onramp_headers(body)
        url = f"{ONRAMP_API_BASE_URL}/onramp/api/v2/common/transaction/allConfigMapping"
        response = requests.post(url, headers=headers, json=body, timeout=30)
        return Response(response.json(), status=response.status_code)

    except requests.exceptions.RequestException as e:
        return Response(
            {"success": False, "message": f"Request to Onramp API failed: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except Exception as e:
        return Response(
            {"success": False, "message": f"Unexpected error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["GET"])
@permission_classes([])
def get_onramp_payment_methods_by_currency(request):
    """
    Get payment methods for a specific currency from OnRamp.
    Uses the PUBLIC fetchPaymentMethodType endpoint.
    Query params: fiatCurrency
    """
    try:
        fiat_currency = request.GET.get('fiatCurrency', '').upper()
        
        if not fiat_currency:
            return Response(
                {"success": False, "message": "fiatCurrency is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # First, get the fiatType for this currency from our cached config
        config = get_onramp_config_mappings()
        fiat_mapping = config.get("fiatSymbolMapping", {})
        fiat_info = fiat_mapping.get(fiat_currency.upper()) or fiat_mapping.get(fiat_currency.lower())
        
        if isinstance(fiat_info, int):
            fiat_type = fiat_info
        else:
            fiat_type = fiat_info.get("fiatType") if fiat_info else None
        
        if fiat_type is None:
            return Response(
                {
                    "success": False, 
                    "message": f"Currency {fiat_currency} not supported",
                    "supportedCurrencies": list(fiat_mapping.keys())
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Now fetch payment methods from the PUBLIC endpoint (no auth needed)
        payment_methods_url = "https://api.onramp.money/onramp/api/v2/common/public/fetchPaymentMethodType"
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json;charset=UTF-8'
        }
        
        payment_response = requests.get(payment_methods_url, headers=headers, timeout=30)
        payment_data = payment_response.json()
        
        if payment_data.get("status") != 1:
            return Response(
                {"success": False, "message": "Failed to fetch payment methods from OnRamp"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # Extract payment methods for this specific fiatType
        all_payment_methods = payment_data.get("data", {})
        methods_for_currency = all_payment_methods.get(str(fiat_type), {})
        
        return Response(
            {
                "success": True,
                "data": {
                    "fiatType": fiat_type,
                    "currency": fiat_currency,
                    "paymentMethods": methods_for_currency
                }
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"OnRamp payment methods by currency error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# ------------------------------------------------------------------
# ✅ GENERATE ONRAMP/OFFRAMP URL (PUBLIC API WITH AUTO FIAT TYPE)
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([])
def generate_onramp_url(request):
    """
    Generate widget link for BUY/SELL flow using OnRamp public API.
    Supports network-specific coins (e.g., USDT_TRC20)
    """
    try:
        data = request.data
        action = data.get("action", "").upper()
        source_currency = data.get("sourceCurrencyCode", "").upper()
        destination_currency = data.get("destinationCurrencyCode", "").upper()
        source_amount = data.get("sourceAmount")

        if not all([action, source_currency, destination_currency, source_amount]):
            return Response(
                {"success": False, "message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine flow type: 1 -> onramp (BUY), 2 -> offramp (SELL)
        flow_type = 1 if action == "BUY" else 2

        # Parse coin and network
        if flow_type == 1:
            # destination is crypto
            actual_coin, network = parse_coin_network(destination_currency)
            # Force BTC to always use BTC network
            if actual_coin == "btc":
                network = "btc"
            elif not network:
                resp = get_available_network(actual_coin)
                network = resp.get("network")
            fiat_currency = source_currency
        else:
            # source is crypto
            actual_coin, network = parse_coin_network(source_currency)
            # Force BTC to always use BTC network
            if actual_coin == "btc":
                network = "btc"
            elif not network:
                resp = get_available_network(actual_coin)
                network = resp.get("network")
            fiat_currency = destination_currency

        # Get fiatType from mapping
        fiat_type = get_fiat_type(fiat_currency)
        if fiat_type is None:
            return Response(
                {
                    "success": False,
                    "message": f"Unsupported fiat currency: {fiat_currency}",
                    "supportedCurrencies": list(get_onramp_config_mappings().get("fiatSymbolMapping", {}).keys())
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Prepare request body for public API
        if flow_type == 1:
            # BUY: fiatAmount is the source (what user pays)
            body = {
                "coinCode": actual_coin,
                "network": network.lower(),
                "fiatAmount": float(source_amount),
                "fiatType": fiat_type,
                "flowType": flow_type
            }
        else:
            # SELL: quantity is the crypto amount being sold
            body = {
                "coinCode": actual_coin,
                "network": network.lower(),
                "fiatAmount": float(source_amount),
                "fiatType": fiat_type,
                "flowType": flow_type
            }

        # Generate headers using existing helper
        headers = generate_onramp_headers(body)
        url = f"{ONRAMP_API_BASE_URL}/onramp/api/v2/common/transaction/generateLink"
        logger.info(f"Generate URL Request to {url}: {body}")

        response = requests.post(url, headers=headers, json=body, timeout=30)
        result = response.json()
        logger.info(f"Generate URL Response: {result}")

        if result.get("status") != 1:
            return Response(
                {
                    "success": False,
                    "message": "Failed to create transaction.",
                    "details": result.get("error", "Unknown error"),
                    "apiResponse": result,
                    "requestBody": body
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if result.get("status") == 1:
            transaction_data = result.get("data", {})
            url_hash = transaction_data.get("urlHash")
            
            # ✅ CHECK IF USER IS AUTHENTICATED
            db_transaction = None
            if should_save_transaction(request):
                # ✅ CREATE DATABASE RECORD
                db_transaction = create_transaction_record(
                    user=request.user,
                    provider='ONRAMP',
                    transaction_type='BUY' if flow_type == 1 else 'SELL',
                    source_currency=source_currency,
                    source_amount=source_amount,
                    destination_currency=destination_currency,
                    network=network,
                    widget_url=transaction_data.get('link'),
                    provider_transaction_id=url_hash,
                    provider_data={
                        'flow_type': flow_type,
                        'fiat_type': fiat_type,
                        'response': transaction_data
                    }
                )
            
            # ✅ STORE IN CACHE (for webhooks - works for both auth and non-auth)
            transaction_key = f"txn_onramp_{url_hash}"
            transaction_record = {
                'transaction_id': transaction_key,
                'db_id': db_transaction.id if db_transaction else None,  # Link to DB
                'provider': 'ONRAMP',
                'status': 'PENDING',
                'url_hash': url_hash,
                'widget_url': transaction_data.get('link'),
                'created_at': int(time.time() * 1000),
                'flow_type': 'BUY' if flow_type == 1 else 'SELL',
                'source_currency': source_currency,
                'destination_currency': destination_currency,
                'amount': source_amount,
                'network': network,
            }
            
            cache.set(transaction_key, transaction_record, timeout=86400)
            
            return Response({
                "success": True,
                "widgetUrl": transaction_data.get("link"),
                "transactionId": db_transaction.transaction_id if db_transaction else transaction_key,
                "urlHash": url_hash,
            })

    except Exception as e:
        logger.error(f"Generate URL Error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    

def verify_onramp_webhook_signature(request):
    """
    Verify OnRamp webhook authenticity using HMAC-SHA512.
    
    According to OnRamp docs:
    1. Request body is JSON-stringified and base64-encoded to generate X-ONRAMP-PAYLOAD
    2. This encoded payload is signed using HMAC-SHA512 with API_SECRET
    3. The signature is sent in X-ONRAMP-SIGNATURE header
    """
    try:
        # Get headers (handle both lowercase and uppercase)
        received_signature = (
            request.headers.get('x-onramp-signature') or 
            request.headers.get('X-ONRAMP-SIGNATURE') or
            request.META.get('HTTP_X_ONRAMP_SIGNATURE')
        )
        received_payload = (
            request.headers.get('x-onramp-payload') or 
            request.headers.get('X-ONRAMP-PAYLOAD') or
            request.META.get('HTTP_X_ONRAMP_PAYLOAD')
        )
        
        if not received_signature or not received_payload:
            logger.error("❌ Missing OnRamp signature or payload headers")
            logger.error(f"Headers: {dict(request.headers)}")
            return False
        
        # Get raw request body
        body = request.body.decode('utf-8')
        
        # Generate expected payload (base64 encode the JSON body)
        # IMPORTANT: Use compact JSON (no spaces) like OnRamp does
        expected_payload = b64encode(body.encode()).decode()
        
        # Generate expected signature using HMAC-SHA512
        expected_signature = hmac.new(
            ONRAMP_API_SECRET.encode(),
            expected_payload.encode(),
            hashlib.sha512
        ).hexdigest()
        
        # Verify both payload and signature match
        payload_match = expected_payload == received_payload
        signature_match = expected_signature == received_signature
        
        if not payload_match:
            logger.error(f"❌ Payload mismatch")
            logger.error(f"Expected: {expected_payload[:100]}...")
            logger.error(f"Received: {received_payload[:100]}...")
        
        if not signature_match:
            logger.error(f"❌ Signature mismatch")
            logger.error(f"Expected: {expected_signature[:40]}...")
            logger.error(f"Received: {received_signature[:40]}...")
        
        return payload_match and signature_match
        
    except Exception as e:
        logger.error(f"❌ Webhook verification error: {str(e)}", exc_info=True)
        return False


@api_view(['POST'])
@permission_classes([AllowAny])  # We verify manually with signature
def onramp_webhook(request):
    """
    Handle OnRamp webhook notifications for both ONRAMP (BUY) and OFFRAMP (SELL).
    
    OnRamp Payload Structure:
    {
        "referenceId": 23,  // Transaction ID (NOT urlHash!)
        "eventType": "ONRAMP" | "OFFRAMP",
        "status": "FAILED" | "FIAT_DEPOSIT_RECEIVED" | "TRADE_COMPLETED" | "ON_CHAIN_COMPLETED" etc,
        "metadata": {
            "eventId": 22,
            "eventCreatedAt": "2023-11-17T13:33:14.000Z",
            "failure_reasons": "Transaction timed out"  // Only for failed transactions
        }
    }
    
    ONRAMP Events (BUY):
    - FIAT_DEPOSIT_RECEIVED -> 2, 10 (deposit secured)
    - TRADE_COMPLETED -> 3, 12
    - ON_CHAIN_INITIATED -> 14 (withdrawal initiated)
    - ON_CHAIN_COMPLETED -> 4, 15, 5, 16 (withdrawal complete)
    - FAILED -> -1, -2, -3, -4
    
    OFFRAMP Events (SELL):
    - ON_CHAIN_DEPOSIT_RECEIVED -> 2, 10, 11 (deposit found, selling crypto)
    - TRADE_COMPLETED -> 4, 12 (crypto sold)
    - FIAT_TRANSFER_INITIATED -> 13
    - FIAT_TRANSFER_COMPLETED -> 14, 19, 40, 15, 20, 41
    - FAILED -> -1, -2, -4
    """
    try:
        # Step 1: Verify webhook signature
        if not verify_onramp_webhook_signature(request):
            logger.error("❌ OnRamp webhook signature verification failed!")
            return Response(
                {"status": 0, "error": "Invalid signature"}, 
                status=401
            )
        
        # Step 2: Parse webhook data
        data = request.data
        logger.info(f"✅ OnRamp webhook received (verified): {json.dumps(data, indent=2)}")
        
        # Extract webhook fields
        reference_id = data.get('referenceId')  # This is the transaction ID
        event_type = data.get('eventType', '').upper()  # ONRAMP or OFFRAMP
        status_value = data.get('status', '').upper()
        metadata = data.get('metadata', {})
        
        # Extract metadata
        event_id = metadata.get('eventId')
        event_created_at = metadata.get('eventCreatedAt')
        failure_reasons = metadata.get('failure_reasons', '')
        
        # Step 3: Check for duplicate events using eventId
        if event_id:
            duplicate_key = f"onramp_event_{event_id}"
            if cache.get(duplicate_key):
                logger.info(f"⚠️ Duplicate webhook event {event_id}, skipping")
                return Response({"success": True, "message": "Duplicate event"}, status=200)
            
            # Mark this event as processed (cache for 7 days)
            cache.set(duplicate_key, True, timeout=604800)
        
        # Step 4: Map OnRamp status to our internal status
        # OnRamp sends both text statuses and numeric codes
        status_mapping = {
            # Completed statuses
            'ON_CHAIN_COMPLETED': 'COMPLETED',
            'FIAT_TRANSFER_COMPLETED': 'COMPLETED',
            '4': 'COMPLETED',
            '5': 'COMPLETED',
            '15': 'COMPLETED',
            '16': 'COMPLETED',
            '14': 'COMPLETED',
            '19': 'COMPLETED',
            '20': 'COMPLETED',
            '40': 'COMPLETED',
            '41': 'COMPLETED',
            
            # Pending/Processing statuses
            'FIAT_DEPOSIT_RECEIVED': 'PENDING',
            'TRADE_COMPLETED': 'PENDING',
            'ON_CHAIN_INITIATED': 'PENDING',
            'ON_CHAIN_DEPOSIT_RECEIVED': 'PENDING',
            'FIAT_TRANSFER_INITIATED': 'PENDING',
            '2': 'PENDING',
            '3': 'PENDING',
            '10': 'PENDING',
            '11': 'PENDING',
            '12': 'PENDING',
            '13': 'PENDING',
            
            # Failed statuses
            'FAILED': 'FAILED',
            '-1': 'FAILED',
            '-2': 'FAILED',
            '-3': 'FAILED',
            '-4': 'FAILED',
        }
        
        mapped_status = status_mapping.get(str(status_value), 'PENDING')
        
        # Step 5: Find and update the transaction
        if reference_id:
            # OnRamp sends referenceId which is their internal transaction ID
            # We need to find our transaction by this reference
            
            # Try multiple possible transaction key formats
            possible_keys = [
                f"txn_onramp_{reference_id}",
                f"onramp_txn_{reference_id}",
            ]
            
            transaction_record = None
            transaction_key = None
            
            # Try to find the transaction
            for key in possible_keys:
                transaction_record = cache.get(key)
                if transaction_record:
                    transaction_key = key
                    break
            
            # If not found by referenceId, try searching all onramp transactions
            if not transaction_record:
                logger.warning(f"⚠️ Transaction not found by referenceId: {reference_id}")
                logger.info(f"🔍 Searching for pending OnRamp transactions...")
                
                # Get all cache keys (this is inefficient but necessary for debugging)
                # In production, you should maintain a separate index
                all_keys = cache.keys('txn_onramp_*')
                
                for key in all_keys:
                    txn = cache.get(key)
                    if txn and txn.get('provider') == 'ONRAMP' and txn.get('status') == 'PENDING':
                        # Found a pending OnRamp transaction
                        transaction_record = txn
                        transaction_key = key
                        logger.info(f"✅ Found pending transaction: {key}")
                        break
            
            if transaction_record:
                # Update the transaction
                transaction_record['status'] = mapped_status
                transaction_record['updated_at'] = int(time.time() * 1000)
                transaction_record['webhook_data'] = data
                transaction_record['provider_status'] = status_value
                transaction_record['onramp_reference_id'] = reference_id
                transaction_record['event_type'] = event_type
                
                if failure_reasons:
                    transaction_record['failure_reason'] = failure_reasons
                
                if event_id:
                    transaction_record['last_event_id'] = event_id
                
                if event_created_at:
                    transaction_record['last_event_time'] = event_created_at
                
                # Save updated transaction
                cache.set(transaction_key, transaction_record, timeout=86400)

                # UPDATE DATABASE
                db_id = transaction_record.get('db_id')
                if db_id:
                    try:
                        txn = Transaction.objects.get(id=db_id)
                        txn.status = mapped_status
                        txn.provider_reference_id = reference_id
                        
                        # Update provider_data with webhook info
                        if not txn.provider_data:
                            txn.provider_data = {}
                        txn.provider_data['webhook_data'] = data
                        txn.provider_data['last_event_id'] = event_id
                        txn.provider_data['event_type'] = event_type
                        
                        if mapped_status == 'COMPLETED':
                            txn.completed_at = timezone.now()
                        
                        if failure_reasons:
                            txn.failure_reason = failure_reasons
                        
                        txn.save()
                        
                        logger.info(f"✅ Updated DB transaction {db_id} to {mapped_status}")
                        
                    except Transaction.DoesNotExist:
                        logger.error(f"❌ DB transaction {db_id} not found")
                
                logger.info(
                    f"✅ Updated OnRamp transaction {transaction_key}\n"
                    f"   Status: {mapped_status}\n"
                    f"   Event: {status_value}\n"
                    f"   Type: {event_type}\n"
                    f"   Reference: {reference_id}"
                )
            else:
                logger.warning(
                    f"⚠️ No transaction found for OnRamp webhook\n"
                    f"   Reference ID: {reference_id}\n"
                    f"   Event Type: {event_type}\n"
                    f"   Status: {status_value}"
                )
        else:
            logger.error("❌ No referenceId in OnRamp webhook payload")
        
        # Step 6: Always return 200 OK to acknowledge receipt
        # OnRamp will retry up to 5 times if not 200
        return Response(
            {"success": True, "message": "Webhook processed"}, 
            status=200
        )
        
    except Exception as e:
        logger.error(f"❌ OnRamp webhook error: {str(e)}", exc_info=True)
        # Still return 200 to prevent retries for code errors
        return Response(
            {"success": True, "message": "Webhook received but error in processing"}, 
            status=200
        )


# ============================================================================
# API endpoint to manually set OnRamp webhook URL (run once)
# ============================================================================
@api_view(["POST"])
@permission_classes([])
def setup_onramp_webhook_url(request):
    """
    One-time API endpoint to register webhook URL with OnRamp.
    """
    import requests
    import time
    import json
    import hmac
    import hashlib
    from base64 import b64encode
    from django.conf import settings

    webhook_url = "https://api.mintcoins.pro/onramp/webhook/"

    body = {"webhookUrl": webhook_url}

    payload = {
        "timestamp": int(time.time() * 1000),
        "body": body
    }

    payload_encoded = b64encode(json.dumps(payload).encode()).decode()

    signature = hmac.new(
        settings.ONRAMP_API_SECRET.encode(),
        payload_encoded.encode(),
        hashlib.sha512
    ).hexdigest()

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json;charset=UTF-8",
        "X-ONRAMP-SIGNATURE": signature,
        "X-ONRAMP-APIKEY": settings.ONRAMP_API_KEY,
        "X-ONRAMP-PAYLOAD": payload_encoded,
    }

    url = "https://api.onramp.money/onramp/api/v1/merchant/setWebhookUrl"

    try:
        response = requests.post(url, headers=headers, json=body, timeout=30)

        return Response(
            {
                "status_code": response.status_code,
                "response": response.json()
            },
            status=status.HTTP_200_OK if response.ok else status.HTTP_400_BAD_REQUEST
        )

    except requests.RequestException as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
@api_view(['POST'])
@permission_classes([])
def get_onramp_transaction_status(request):
    """
    Get OnRamp transaction status by urlHash.
    """
    try:
        url_hash = request.data.get('urlHash')
        
        if not url_hash:
            return Response(
                {"success": False, "message": "urlHash is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        body = {"urlHash": url_hash}
        headers = generate_onramp_headers(body)
        url = f"{ONRAMP_API_BASE_URL}/onramp/api/v2/common/transaction/getTransactionStatus"
        
        logger.info(f"Checking OnRamp status for: {url_hash}")
        
        response = requests.post(url, headers=headers, json=body, timeout=30)
        result = response.json()
        
        logger.info(f"OnRamp status response: {result}")
        
        if result.get("status") != 1:
            return Response(
                {
                    "success": False,
                    "message": "Failed to get transaction status",
                    "details": result.get("error", "Unknown error")
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        txn_data = result.get("data", {})
        
        return Response(
            {
                "success": True,
                "status": txn_data.get("status"),
                "transactionData": txn_data
            },
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"OnRamp status check error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )