import requests
from requests.auth import HTTPBasicAuth
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.http import JsonResponse

MELD_BASE_URL = "https://api.meld.io"

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


@api_view(['POST'])
@permission_classes([])
def create_session_widget(request):
    """Create a crypto payment widget session"""
    return meld_request("POST", "/crypto/session/widget", data=request.data)