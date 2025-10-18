import json
import time
import hmac
import hashlib
from base64 import b64encode
import requests
import logging
from functools import lru_cache

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
@permission_classes([IsAuthenticated])
def get_onramp_quote(request):
    """
    Get quote for BUY/SELL transactions using the standard quotes API.
    Fetches fiat type mappings dynamically from the API.
    """
    try:
        data = request.data
        action = data.get("action", "").upper()
        source_currency = data.get("sourceCurrencyCode", "").upper()
        destination_currency = data.get("destinationCurrencyCode", "").upper()
        source_amount = data.get("sourceAmount")
        resp = get_available_network(destination_currency) if action == "BUY" else get_available_network(source_currency)
        network = resp.get("network")

        if not all([action, source_currency, destination_currency, source_amount]):
            return Response(
                {"success": False, "message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine transaction type
        txn_type = "BUY" if action == "BUY" else "SELL"

        # Prepare the request body based on transaction type
        if txn_type == "BUY":
            # For BUY: fiat -> crypto
            fiat_type = get_fiat_type(source_currency)
            if fiat_type is None:
                # Fetch available currencies for better error message
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

            # Validate crypto currency
            coin_info = get_coin_code(destination_currency)
            if not coin_info:
                config = get_onramp_config_mappings()
                available_coins = list(config.get("coinSymbolMapping", {}).keys())
                
                return Response(
                    {
                        "success": False,
                        "message": f"Unsupported cryptocurrency: {destination_currency}",
                        "supportedCoins": available_coins[:50]  # Limit to first 50
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            quote_body = {
                "coinCode": destination_currency.lower(),  # e.g., "usdt"
                "network": network.lower(),  # e.g., "bep20"
                "fiatAmount": float(source_amount),
                "fiatType": fiat_type,
                "type": 1  # 1 for ONRAMP (buy)
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
            coin_info = get_coin_code(source_currency)
            if not coin_info:
                config = get_onramp_config_mappings()
                available_coins = list(config.get("coinSymbolMapping", {}).keys())
                
                return Response(
                    {
                        "success": False,
                        "message": f"Unsupported cryptocurrency: {source_currency}",
                        "supportedCoins": available_coins[:50]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            quote_body = {
                "coinCode": source_currency.lower(),  # e.g., "usdt"
                "network": network.lower(),
                "quantity": float(source_amount),  # Amount of crypto to sell
                "fiatType": fiat_type,
                "type": 2  # 2 for OFFRAMP (sell)
            }

        # Use the quotes endpoint
        quote_url = f"{ONRAMP_API_BASE_URL}/onramp/api/v2/common/transaction/quotes"
        headers = generate_onramp_headers(quote_body)

        # Log the request for debugging
        logger.info(f"Onramp Quote Request to {quote_url}: {quote_body}")

        quote_response = requests.post(quote_url, headers=headers, json=quote_body, timeout=30)
        quote_json = quote_response.json()

        # Log the response for debugging
        logger.info(f"Onramp Quote Response: {quote_json}")

        if quote_json.get("status") != 1:
            return Response(
                {
                    "success": False,
                    "message": "Quote request failed.",
                    "details": quote_json.get("error", "Unknown error"),
                    "apiResponse": quote_json,
                    "requestBody": quote_body
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        quote_data = quote_json.get("data", {})

        # Standardize the response for your frontend
        if txn_type == "BUY":
            standardized_quote = {
                "sourceCurrency": source_currency,
                "destinationCurrency": destination_currency.upper(),
                "sourceAmount": source_amount,
                "estimatedAmount": quote_data.get("quantity"),
                "rate": quote_data.get("rate"),
                "fees": {
                    "onrampFee": quote_data.get("onrampFee", 0),
                    "clientFee": quote_data.get("clientFee", 0),
                    "gatewayFee": quote_data.get("gatewayFee", 0),
                    "gasFee": quote_data.get("gasFee", 0),
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
                "sourceCurrency": source_currency.upper(),
                "destinationCurrency": destination_currency,
                "sourceAmount": source_amount,
                "estimatedAmount": quote_data.get("fiatAmount"),
                "rate": quote_data.get("rate"),
                "fees": {
                    "onrampFee": quote_data.get("onrampFee", 0),
                    "clientFee": quote_data.get("clientFee", 0),
                    "gatewayFee": quote_data.get("gatewayFee", 0),
                    "tdsFee": quote_data.get("tdsFee", 0),
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
@permission_classes([IsAuthenticated])
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


# ------------------------------------------------------------------
# ✅ GENERATE ONRAMP/OFFRAMP URL (PUBLIC API WITH AUTO FIAT TYPE)
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_onramp_url(request):
    """
    Generate widget link for BUY/SELL flow using OnRamp public API.
    Automatically determines fiatType from the source/destination currency.
    """
    try:
        data = request.data
        action = data.get("action", "").upper()
        source_currency = data.get("sourceCurrencyCode", "").upper()
        destination_currency = data.get("destinationCurrencyCode", "").upper()
        source_amount = data.get("sourceAmount")
        resp = get_available_network(destination_currency) if action == "BUY" else get_available_network(source_currency)
        network = resp.get("network")

        if not all([action, source_currency, destination_currency, source_amount]):
            return Response(
                {"success": False, "message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine flow type: 1 -> onramp (BUY), 2 -> offramp (SELL)
        flow_type = 1 if action == "BUY" else 2

        # Automatically get fiatType from mapping
        fiat_currency = source_currency if flow_type == 1 else destination_currency
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

        # Determine crypto code
        coin_code = destination_currency.lower() if flow_type == 1 else source_currency.lower()

        # Prepare request body for public API
        body = {
            "coinCode": coin_code,
            "network": network.lower(),
            "fiatAmount": source_amount,
            "fiatType": fiat_type,
            "type": flow_type
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

        return Response(
            {
                "success": True,
                "widgetUrl": transaction_data.get("link"),
                "paymentUrl": transaction_data.get("link"),
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