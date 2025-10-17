import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings

ONRAMP_BASE_URL = settings.ONRAMP_BASE_URL
ONRAMP_APP_ID = settings.ONRAMP_APP_ID
ONRAMP_API_KEY = settings.ONRAMP_API_KEY

def onramp_request(method, endpoint, data=None, params=None):
    """Helper function to make authenticated requests to OnRamp"""
    url = f"{ONRAMP_BASE_URL}{endpoint}"
    
    headers = {
        "Authorization": f"Bearer {ONRAMP_API_KEY}",
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
            res_data = {"error": "Invalid JSON response from OnRamp"}

        if not response.ok:
            return Response(
                {
                    "success": False,
                    "status_code": response.status_code,
                    "message": res_data.get("message", "OnRamp request failed"),
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
            {"success": False, "error": "OnRamp API timeout"},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        return Response(
            {"success": False, "error": "Network error while connecting to OnRamp"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except requests.exceptions.RequestException as err:
        return Response(
            {"success": False, "error": str(err)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_onramp_quote(request):
    """
    Get quote from OnRamp for BUY or SELL
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
    
    payload = {
        "appId": ONRAMP_APP_ID,
        "amount": data.get("sourceAmount"),
        "type": action.lower(),
        "country": data.get("countryCode"),
    }
    
    if action == "BUY":
        payload["fiatCurrency"] = data.get("sourceCurrencyCode")
        payload["cryptoCurrency"] = data.get("destinationCurrencyCode")
    else:  # SELL
        payload["cryptoCurrency"] = data.get("sourceCurrencyCode")
        payload["fiatCurrency"] = data.get("destinationCurrencyCode")
    
    response = onramp_request("GET", "/v2/quote", params=payload)
    
    # Transform response to match Meld structure
    if response.status_code == 200:
        onramp_data = response.data.get("data", {})
        
        transformed = {
            "success": True,
            "data": {
                "quote": {
                    "serviceProvider": "ONRAMP",
                    "provider": "OnRamp",
                    "destinationAmount": onramp_data.get("cryptoAmount") if action == "BUY" else onramp_data.get("fiatAmount"),
                    "destinationAmountWithoutFees": onramp_data.get("cryptoAmountWithoutFees") if action == "BUY" else onramp_data.get("fiatAmountWithoutFees"),
                    "exchangeRate": onramp_data.get("rate") or onramp_data.get("exchangeRate"),
                    "totalFee": onramp_data.get("totalFee") or onramp_data.get("fee"),
                    "transactionFee": onramp_data.get("transactionFee"),
                    "networkFee": onramp_data.get("networkFee"),
                    "minimumAmount": onramp_data.get("minAmount") or onramp_data.get("minimumAmount"),
                }
            }
        }
        return Response(transformed, status=status.HTTP_200_OK)
    
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_onramp_payment_methods(request):
    """Get available payment methods from OnRamp"""
    return onramp_request("GET", "/v2/payment-methods", params=request.query_params)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_onramp_url(request):
    """
    Generate OnRamp widget URL
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
        "sourceAmount": 0.01,
        "bankDetails": {...}
    }
    """
    data = request.data
    action = data.get("action", "BUY").upper()
    
    params = {
        "appId": ONRAMP_APP_ID,
        "type": action.lower(),
    }
    
    if action == "BUY":
        params["walletAddress"] = data.get("walletAddress")
        params["fiatCurrency"] = data.get("sourceCurrencyCode")
        params["cryptoCurrency"] = data.get("destinationCurrencyCode")
        params["amount"] = data.get("sourceAmount")
    else:  # SELL
        params["cryptoCurrency"] = data.get("sourceCurrencyCode")
        params["fiatCurrency"] = data.get("destinationCurrencyCode")
        params["amount"] = data.get("sourceAmount")
        
        # Add bank details if provided
        bank_details = data.get("bankDetails", {})
        if bank_details.get("accountNumber"):
            params["accountNumber"] = bank_details["accountNumber"]
        if bank_details.get("accountName"):
            params["accountName"] = bank_details["accountName"]
        if bank_details.get("bankName"):
            params["bankName"] = bank_details["bankName"]
    
    # Build URL with query params
    from urllib.parse import urlencode
    url = f"https://onramp.money/app/?{urlencode(params)}"
    
    return Response({
        "success": True,
        "widgetUrl": url
    }, status=status.HTTP_200_OK)