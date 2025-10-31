import json
import time
import hmac
import hashlib
from base64 import b64encode
import requests
import logging
from functools import lru_cache

from django.core.cache import cache
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

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
            if actual_coin == "BTC":
                network = "bitcoin"
            elif not network:
                resp = get_available_network(actual_coin)
                network = resp.get("network")
            fiat_currency = source_currency
        else:
            # source is crypto
            actual_coin, network = parse_coin_network(source_currency)
            # Force BTC to always use BTC network
            if actual_coin == "BTC":
                network = "bitcoin"
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

        transaction_data = result.get("data", {})
        url_hash = transaction_data.get("urlHash")

        # Store transaction for tracking
        transaction_key = f"txn_onramp_{url_hash}" if url_hash else f"txn_onramp_{int(time.time())}_{flow_type}"
        transaction_record = {
            'transaction_id': transaction_key,
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

        from django.core.cache import cache
        cache.set(transaction_key, transaction_record, timeout=86400)

        return Response(
            {
                "success": True,
                "widgetUrl": transaction_data.get("link"),
                "paymentUrl": transaction_data.get("link"),
                "transactionId": transaction_key,
                "urlHash": url_hash,
                "data": transaction_data
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Generate URL Error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    
@api_view(['POST'])
@permission_classes([])
def onramp_webhook(request):
    """
    Handle OnRamp webhook notifications.
    """
    try:
        data = request.data
        logger.info(f"OnRamp webhook received: {json.dumps(data, indent=2)}")
        
        url_hash = data.get('urlHash') or data.get('transactionHash')
        status = data.get('status', '').upper()
        
        status_mapping = {
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
        
        mapped_status = status_mapping.get(status, 'PENDING')
        
        if url_hash:
            transaction_key = f"txn_onramp_{url_hash}"
            transaction_record = cache.get(transaction_key)
            
            if transaction_record:
                transaction_record['status'] = mapped_status
                transaction_record['updated_at'] = int(time.time() * 1000)
                transaction_record['webhook_data'] = data
                transaction_record['provider_status'] = status
                
                cache.set(transaction_key, transaction_record, timeout=86400)
                logger.info(f"✅ Updated OnRamp transaction {transaction_key} to {mapped_status}")
            else:
                logger.warning(f"⚠️ Transaction not found for urlHash: {url_hash}")
        else:
            logger.warning("⚠️ No urlHash in OnRamp webhook payload")
        
        return Response({"success": True, "message": "Webhook processed"}, status=200)
        
    except Exception as e:
        logger.error(f"OnRamp webhook error: {str(e)}", exc_info=True)
        return Response({"success": False, "error": str(e)}, status=400)
    
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