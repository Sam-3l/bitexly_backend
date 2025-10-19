import hmac
import hashlib
import json
import requests
import logging
from urllib.parse import urlencode
from functools import lru_cache

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

# Setup logger
logger = logging.getLogger(__name__)

# MoonPay API Configuration
MOONPAY_API_BASE_URL = "https://api.moonpay.com"
MOONPAY_WIDGET_BASE_URL = "https://buy.moonpay.com"
MOONPAY_PUBLISHABLE_KEY = settings.MOONPAY_PUBLISHABLE_KEY
MOONPAY_SECRET_KEY = settings.MOONPAY_SECRET_KEY


def generate_moonpay_signature(url):
    """
    Generate signature for MoonPay URL using secret key.
    Used to secure widget URLs.
    """
    signature = hmac.new(
        MOONPAY_SECRET_KEY.encode(),
        url.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature


@lru_cache(maxsize=1)
def get_moonpay_currencies():
    """
    Fetch and cache all supported currencies from MoonPay.
    Returns dict with 'crypto' and 'fiat' currencies.
    """
    try:
        url = f"{MOONPAY_API_BASE_URL}/v3/currencies"
        params = {"apiKey": MOONPAY_PUBLISHABLE_KEY}
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            all_currencies = response.json()
            
            # Separate crypto and fiat currencies
            crypto_currencies = [c for c in all_currencies if c.get('type') == 'crypto']
            fiat_currencies = list(set([c.get('code', '').upper() for c in all_currencies if c.get('type') == 'fiat']))
            
            logger.info(f"Successfully fetched {len(crypto_currencies)} crypto and {len(fiat_currencies)} fiat currencies")
            return {
                "crypto": crypto_currencies,
                "fiat": fiat_currencies,
                "all": all_currencies
            }
        else:
            logger.error(f"Failed to fetch currencies: {response.status_code}")
            return {"crypto": [], "fiat": [], "all": []}
            
    except Exception as e:
        logger.error(f"Error fetching currencies: {str(e)}")
        return {"crypto": [], "fiat": [], "all": []}


def get_currency_info(currency_code):
    """
    Get detailed information about a specific currency.
    """
    currencies_data = get_moonpay_currencies()
    all_currencies = currencies_data.get("all", [])
    
    currency_code_lower = currency_code.lower()
    
    for currency in all_currencies:
        if currency.get('code', '').lower() == currency_code_lower:
            return currency
    
    return None


def validate_currency_support(currency_code, transaction_type="buy"):
    """
    Validate if a currency is supported for buy or sell.
    
    Args:
        currency_code: Currency code to validate
        transaction_type: "buy" or "sell"
    
    Returns:
        tuple: (is_valid, currency_info, error_message)
    """
    currency_info = get_currency_info(currency_code)
    
    if not currency_info:
        currencies_data = get_moonpay_currencies()
        available = [c.get('code') for c in currencies_data.get('all', [])][:50]
        return False, None, f"Currency {currency_code} not found. Available: {available}"
    
    # Check if currency supports the transaction type
    if transaction_type == "sell":
        if currency_info.get('type') == 'crypto' and not currency_info.get('isSellSupported', False):
            return False, currency_info, f"{currency_code} does not support selling"
    
    return True, currency_info, None


# ------------------------------------------------------------------
# ✅ GET QUOTE ENDPOINT
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def get_moonpay_quote(request):
    """
    Get quote for BUY/SELL transactions from MoonPay.
    
    Expected request body:
    {
        "action": "BUY" or "SELL",
        "sourceCurrencyCode": "USD" or "BTC",
        "destinationCurrencyCode": "BTC" or "USD",
        "sourceAmount": 100,
        "paymentMethod": "credit_debit_card" (optional)
    }
    """
    try:
        data = request.data
        action = data.get("action", "").upper()
        source_currency = data.get("sourceCurrencyCode", "").upper()
        destination_currency = data.get("destinationCurrencyCode", "").upper()
        source_amount = data.get("sourceAmount")
        payment_method = data.get("paymentMethod", "credit_debit_card")

        # Validate required fields
        if not all([action, source_currency, destination_currency, source_amount]):
            return Response(
                {"success": False, "message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine transaction type
        if action == "BUY":
            # BUY: fiat -> crypto
            crypto_code = destination_currency.lower()
            base_currency_code = source_currency.lower()
            quote_endpoint = "buy_quote"
            
            # Validate crypto currency
            is_valid, currency_info, error_msg = validate_currency_support(crypto_code, "buy")
            if not is_valid:
                return Response(
                    {"success": False, "message": error_msg},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
        else:
            # SELL: crypto -> fiat
            crypto_code = source_currency.lower()
            base_currency_code = destination_currency.lower()
            quote_endpoint = "sell_quote"
            
            # Validate crypto currency supports selling
            is_valid, currency_info, error_msg = validate_currency_support(crypto_code, "sell")
            if not is_valid:
                return Response(
                    {"success": False, "message": error_msg},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Build quote URL
        quote_url = f"{MOONPAY_API_BASE_URL}/v3/currencies/{crypto_code}/{quote_endpoint}"
        
        # Prepare query parameters
        params = {
            "apiKey": MOONPAY_PUBLISHABLE_KEY,
            "baseCurrencyCode": base_currency_code,
            "paymentMethod": payment_method,
        }
        
        # Add amount parameter based on action
        if action == "BUY":
            params["baseCurrencyAmount"] = float(source_amount)
        else:
            params["baseCurrencyAmount"] = float(source_amount)

        # Log the request
        logger.info(f"MoonPay Quote Request to {quote_url}: {params}")

        # Make API request
        response = requests.get(quote_url, params=params, timeout=30)
        quote_data = response.json()

        # Log the response
        logger.info(f"MoonPay Quote Response: {quote_data}")

        # Handle errors
        if response.status_code != 200:
            return Response(
                {
                    "success": False,
                    "message": "Quote request failed.",
                    "details": quote_data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Standardize the response
        if action == "BUY":
            standardized_quote = {
                "sourceCurrency": source_currency,
                "destinationCurrency": destination_currency,
                "sourceAmount": source_amount,
                "estimatedAmount": quote_data.get("quoteCurrencyAmount"),
                "totalAmount": quote_data.get("totalAmount"),
                "rate": quote_data.get("quoteCurrencyPrice"),
                "fees": {
                    "moonpayFee": quote_data.get("feeAmount", 0),
                    "networkFee": quote_data.get("networkFeeAmount", 0),
                    "extraFee": quote_data.get("extraFeeAmount", 0),
                },
                "totalFees": quote_data.get("feeAmount", 0) + quote_data.get("networkFeeAmount", 0) + quote_data.get("extraFeeAmount", 0),
                "txnType": "BUY",
                "paymentMethod": payment_method,
            }
        else:
            standardized_quote = {
                "sourceCurrency": source_currency,
                "destinationCurrency": destination_currency,
                "sourceAmount": source_amount,
                "estimatedAmount": quote_data.get("quoteCurrencyAmount"),
                "totalAmount": quote_data.get("quoteCurrencyAmount"),
                "rate": quote_data.get("quoteCurrencyPrice"),
                "fees": {
                    "moonpayFee": quote_data.get("feeAmount", 0),
                    "networkFee": quote_data.get("networkFeeAmount", 0),
                    "extraFee": quote_data.get("extraFeeAmount", 0),
                },
                "totalFees": quote_data.get("feeAmount", 0) + quote_data.get("networkFeeAmount", 0),
                "txnType": "SELL",
                "paymentMethod": payment_method,
            }

        return Response(
            {"success": True, "quote": standardized_quote},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"MoonPay Quote Error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET PAYMENT METHODS (Similar to OnRamp's structure)
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_moonpay_payment_methods(request):
    """
    Fetch all supported payment methods, currencies, and country info from MoonPay.
    Returns structured data similar to OnRamp's payment methods format.
    """
    try:
        currencies_data = get_moonpay_currencies()
        
        # Build payment methods structure
        crypto_currencies = currencies_data.get("crypto", [])
        fiat_currencies = currencies_data.get("fiat", [])
        
        # Build a mapping similar to OnRamp's format
        coin_symbol_mapping = {}
        for crypto in crypto_currencies:
            code = crypto.get('code', '').lower()
            coin_symbol_mapping[code] = {
                "coinCode": code,
                "name": crypto.get('name', ''),
                "type": crypto.get('type', 'crypto'),
                "isSellSupported": crypto.get('isSellSupported', False),
                "isSuspended": crypto.get('isSuspended', False),
                "minBuyAmount": crypto.get('minBuyAmount'),
                "maxBuyAmount": crypto.get('maxBuyAmount'),
                "minSellAmount": crypto.get('minSellAmount'),
                "maxSellAmount": crypto.get('maxSellAmount'),
            }
        
        fiat_symbol_mapping = {}
        for fiat in fiat_currencies:
            fiat_symbol_mapping[fiat] = {
                "fiatCode": fiat,
                "symbol": fiat,
            }
        
        # Get available payment methods from IP info
        try:
            ip_url = f"{MOONPAY_API_BASE_URL}/v4/ip_address"
            ip_params = {"apiKey": MOONPAY_PUBLISHABLE_KEY}
            ip_response = requests.get(ip_url, params=ip_params, timeout=30)
            ip_data = ip_response.json() if ip_response.status_code == 200 else {}
            
            payment_methods_list = ip_data.get('alpha3', '') 
        except Exception as e:
            logger.warning(f"Could not fetch IP info: {str(e)}")
            payment_methods_list = []
        
        return Response(
            {
                "success": True,
                "data": {
                    "coinSymbolMapping": coin_symbol_mapping,
                    "fiatSymbolMapping": fiat_symbol_mapping,
                    "cryptoCurrencies": crypto_currencies,
                    "fiatCurrencies": fiat_currencies,
                    "paymentMethods": payment_methods_list,
                }
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Error fetching payment methods: {str(e)}")
        return Response(
            {"success": False, "message": "Failed to fetch payment methods", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET SUPPORTED CURRENCIES
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_moonpay_currencies_endpoint(request):
    """
    Fetch all supported currencies from MoonPay.
    Returns crypto currencies and fiat currencies separately.
    """
    try:
        currencies_data = get_moonpay_currencies()
        
        return Response(
            {
                "success": True,
                "data": {
                    "cryptoCurrencies": currencies_data.get("crypto", []),
                    "fiatCurrencies": currencies_data.get("fiat", []),
                }
            },
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Error fetching currencies: {str(e)}")
        return Response(
            {"success": False, "message": "Failed to fetch currencies", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET CURRENCY LIMITS
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_currency_limits(request):
    """
    Get min/max limits for a specific currency.
    
    Query params:
        currencyCode: Currency code (e.g., 'btc', 'eth')
        baseCurrencyCode: Base currency code (e.g., 'usd', 'eur')
        paymentMethod: Payment method (optional)
    """
    try:
        currency_code = request.query_params.get("currencyCode", "").lower()
        base_currency_code = request.query_params.get("baseCurrencyCode", "usd").lower()
        payment_method = request.query_params.get("paymentMethod", "credit_debit_card")

        if not currency_code:
            return Response(
                {"success": False, "message": "currencyCode is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url = f"{MOONPAY_API_BASE_URL}/v3/currencies/{currency_code}/limits"
        params = {
            "apiKey": MOONPAY_PUBLISHABLE_KEY,
            "baseCurrencyCode": base_currency_code,
            "paymentMethod": payment_method,
        }

        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch limits", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        limits_data = response.json()
        
        return Response(
            {"success": True, "limits": limits_data},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Error fetching limits: {str(e)}")
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GENERATE WIDGET URL
# ------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_moonpay_url(request):
    """
    Generate a signed MoonPay widget URL for BUY or SELL.
    
    Expected request body:
    {
        "action": "BUY" or "SELL",
        "sourceCurrencyCode": "USD" or "BTC",
        "destinationCurrencyCode": "BTC" or "USD",
        "sourceAmount": 100,
        "walletAddress": "0x..." (optional for BUY),
        "externalCustomerId": "user123" (optional),
        "redirectURL": "https://yourapp.com/success" (optional)
    }
    """
    try:
        data = request.data
        action = data.get("action", "").upper()
        source_currency = data.get("sourceCurrencyCode", "").upper()
        destination_currency = data.get("destinationCurrencyCode", "").upper()
        source_amount = data.get("sourceAmount")
        wallet_address = data.get("walletAddress")
        external_customer_id = data.get("externalCustomerId")
        redirect_url = data.get("redirectURL")

        if not all([action, source_currency, destination_currency, source_amount]):
            return Response(
                {"success": False, "message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build widget parameters
        widget_params = {
            "apiKey": MOONPAY_PUBLISHABLE_KEY,
        }

        if action == "BUY":
            # BUY: fiat -> crypto
            crypto_code = destination_currency.lower()
            
            # Validate currency
            is_valid, currency_info, error_msg = validate_currency_support(crypto_code, "buy")
            if not is_valid:
                return Response(
                    {"success": False, "message": error_msg},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            widget_params.update({
                "currencyCode": crypto_code,
                "baseCurrencyCode": source_currency.lower(),
                "baseCurrencyAmount": str(source_amount),
            })
            
            if wallet_address:
                widget_params["walletAddress"] = wallet_address
                
        else:
            # SELL: crypto -> fiat
            crypto_code = source_currency.lower()
            
            # Validate currency supports selling
            is_valid, currency_info, error_msg = validate_currency_support(crypto_code, "sell")
            if not is_valid:
                return Response(
                    {"success": False, "message": error_msg},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            
            widget_params.update({
                "baseCurrencyCode": crypto_code,
                "baseCurrencyAmount": str(source_amount),
                "quoteCurrencyCode": destination_currency.lower(),
            })

        # Add optional parameters
        if external_customer_id:
            widget_params["externalCustomerId"] = external_customer_id
        
        if redirect_url:
            widget_params["redirectURL"] = redirect_url

        # Build the unsigned URL
        query_string = urlencode(widget_params)
        
        if action == "BUY":
            unsigned_url = f"{MOONPAY_WIDGET_BASE_URL}?{query_string}"
        else:
            # For SELL, use the sell widget URL
            unsigned_url = f"https://sell.moonpay.com?{query_string}"

        # Generate signature
        signature = generate_moonpay_signature(f"?{query_string}")
        
        # Add signature to URL
        signed_url = f"{unsigned_url}&signature={signature}"

        logger.info(f"Generated MoonPay URL for {action}: {signed_url}")

        return Response(
            {
                "success": True,
                "widgetUrl": signed_url,
                "paymentUrl": signed_url,
                "action": action,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Generate URL Error: {str(e)}", exc_info=True)
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET TRANSACTION STATUS (Using Transaction ID)
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_transaction_status(request, transaction_id):
    """
    Get the status of a MoonPay transaction.
    
    URL params:
        transaction_id: MoonPay transaction ID
    """
    try:
        url = f"{MOONPAY_API_BASE_URL}/v1/transactions/{transaction_id}"
        params = {"apiKey": MOONPAY_PUBLISHABLE_KEY}

        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch transaction", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transaction_data = response.json()
        
        return Response(
            {"success": True, "transaction": transaction_data},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Error fetching transaction: {str(e)}")
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ------------------------------------------------------------------
# ✅ GET IP ADDRESS INFO (User's location/country)
# ------------------------------------------------------------------
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_ip_address_info(request):
    """
    Get information about the user's IP address (country, state, etc.)
    Useful for determining available payment methods and currencies.
    """
    try:
        url = f"{MOONPAY_API_BASE_URL}/v4/ip_address"
        params = {"apiKey": MOONPAY_PUBLISHABLE_KEY}

        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            return Response(
                {"success": False, "message": "Failed to fetch IP info", "details": response.json()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ip_data = response.json()
        
        return Response(
            {"success": True, "ipInfo": ip_data},
            status=status.HTTP_200_OK
        )

    except Exception as e:
        logger.error(f"Error fetching IP info: {str(e)}")
        return Response(
            {"success": False, "message": "Internal server error", "details": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )