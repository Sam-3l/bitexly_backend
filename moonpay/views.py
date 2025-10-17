import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings

MOONPAY_BASE_URL = settings.MOONPAY_BASE_URL
MOONPAY_API_KEY = settings.MOONPAY_API_KEY

def moonpay_request(method, endpoint, data=None, params=None):
    """Helper function to make authenticated requests to MoonPay"""
    url = f"{MOONPAY_BASE_URL}{endpoint}"
    
    headers = {
        "Content-Type": "application/json",
    }

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=data,
            params=params,
            timeout=20
        )

        try:
            res_data = response.json()
        except ValueError:
            res_data = {"error": "Invalid JSON response from MoonPay"}

        if not response.ok:
            return Response(
                {
                    "success": False,
                    "status_code": response.status_code,
                    "message": res_data.get("message", "MoonPay request failed"),
                    "details": res_data,
                },
                status=response.status_code,
            )

        return Response(
            {
                "success": True,
                "data": res_data,
            },
            status=response.status_code,
        )

    except requests.exceptions.Timeout:
        return Response(
            {"success": False, "error": "MoonPay API timeout"},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        return Response(
            {"success": False, "error": "Network error while connecting to MoonPay"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except requests.exceptions.RequestException as err:
        return Response(
            {"success": False, "error": str(err)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_moonpay_quote(request):
    """
    Get quote from MoonPay for BUY or SELL
    Expected payload:
    {
        "action": "BUY" or "SELL",
        "sourceAmount": 100,
        "sourceCurrencyCode": "NGN" or "BTC",
        "destinationCurrencyCode": "BTC" or "NGN",
        "countryCode": "NG"
    }
    """
    data = request.data
    action = data.get("action", "BUY").upper()
    source_amount = data.get("sourceAmount")
    source_currency = data.get("sourceCurrencyCode", "").lower()
    dest_currency = data.get("destinationCurrencyCode", "").lower()
    
    params = {
        "apiKey": MOONPAY_API_KEY,
    }
    
    if action == "BUY":
        params["baseCurrencyCode"] = source_currency
        params["baseCurrencyAmount"] = source_amount
        params["quoteCurrencyCode"] = dest_currency
        endpoint = f"/v3/currencies/{dest_currency}/buy_quote"
    else:  # SELL
        params["baseCurrencyCode"] = source_currency
        params["baseCurrencyAmount"] = source_amount
        params["quoteCurrencyCode"] = dest_currency
        endpoint = f"/v3/currencies/{source_currency}/sell_quote"
    
    response = moonpay_request("GET", endpoint, params=params)
    
    # Transform response to match Meld structure
    if response.status_code == 200:
        moonpay_data = response.data.get("data", {})
        
        dest_amount = moonpay_data.get("quoteCurrencyAmount") or moonpay_data.get("cryptoAmount") or moonpay_data.get("fiatAmount")
        exchange_rate = moonpay_data.get("exchangeRate")
        
        # Calculate rate if not provided
        if not exchange_rate and dest_amount and source_amount:
            if action == "BUY":
                exchange_rate = float(source_amount) / float(dest_amount) if float(dest_amount) > 0 else 0
            else:
                exchange_rate = float(dest_amount) / float(source_amount) if float(source_amount) > 0 else 0
        
        transformed = {
            "success": True,
            "data": {
                "quote": {
                    "serviceProvider": "MOONPAY",
                    "provider": "MoonPay",
                    "destinationAmount": dest_amount,
                    "destinationAmountWithoutFees": dest_amount,
                    "exchangeRate": exchange_rate,
                    "totalFee": moonpay_data.get("totalFee") or moonpay_data.get("feeAmount"),
                    "transactionFee": moonpay_data.get("transactionFee"),
                    "networkFee": moonpay_data.get("networkFeeAmount"),
                    "minimumAmount": moonpay_data.get("baseCurrency", {}).get("minBuyAmount") if action == "BUY" else moonpay_data.get("baseCurrency", {}).get("minSellAmount", 0.001),
                }
            }
        }
        return Response(transformed, status=status.HTTP_200_OK)
    
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_moonpay_payment_methods(request):
    """Get available payment methods from MoonPay"""
    currency = request.query_params.get("fiatCurrencies", "usd").lower()
    
    params = {
        "apiKey": MOONPAY_API_KEY,
    }
    
    endpoint = f"/v3/currencies/{currency}/payment_methods"
    return moonpay_request("GET", endpoint, params=params)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_moonpay_url(request):
    """
    Generate MoonPay widget URL
    Expected payload for BUY:
    {
        "walletAddress": "...",
        "sourceCurrencyCode": "NGN",
        "destinationCurrencyCode": "BTC",
        "sourceAmount": 800000
    }
    
    Expected payload for SELL:
    {
        "sourceCurrencyCode": "BTC",
        "destinationCurrencyCode": "NGN",
        "sourceAmount": 0.01
    }
    """
    data = request.data
    action = data.get("action", "BUY").upper()
    
    params = {
        "apiKey": MOONPAY_API_KEY,
    }
    
    if action == "BUY":
        params["currencyCode"] = data.get("destinationCurrencyCode", "").lower()
        params["walletAddress"] = data.get("walletAddress")
        params["baseCurrencyCode"] = data.get("sourceCurrencyCode", "").lower()
        params["baseCurrencyAmount"] = data.get("sourceAmount")
        params["enabledPaymentMethods"] = "credit_debit_card,sepa_bank_transfer,gbp_bank_transfer"
        
        base_url = "https://buy.moonpay.com"
    else:  # SELL
        params["currencyCode"] = data.get("sourceCurrencyCode", "").lower()
        params["baseCurrencyCode"] = data.get("destinationCurrencyCode", "").lower()
        params["baseCurrencyAmount"] = data.get("sourceAmount")
        params["refundWalletAddress"] = data.get("walletAddress", "")
        
        base_url = "https://sell.moonpay.com"
    
    # Build URL with query params
    from urllib.parse import urlencode
    url = f"{base_url}?{urlencode(params)}"
    
    return Response({
        "success": True,
        "widgetUrl": url
    }, status=status.HTTP_200_OK)