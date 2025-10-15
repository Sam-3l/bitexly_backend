import requests
from requests.auth import HTTPBasicAuth
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings

MELD_BASE_URL = "https://api.meld.io"

# Split the API key into username and password
API_KEY, API_SECRET = settings.MELD_API_KEY.split(":")


def meld_request(method, endpoint, data=None, params=None):
    """
    Helper function to make authenticated requests to Meld.io.
    Handles GET/POST methods and returns proper DRF Response.
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
        response.raise_for_status()
        return Response(response.json(), status=response.status_code)

    except requests.exceptions.HTTPError as err:
        # Forward Meld error response if available
        try:
            return Response(response.json(), status=response.status_code)
        except Exception:
            return Response({"detail": str(err)}, status=response.status_code)
    except requests.exceptions.RequestException as err:
        return Response({"error": str(err)}, status=status.HTTP_502_BAD_GATEWAY)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_crypto_currencies(request):
    """Fetch available cryptocurrencies from Meld.io"""
    return meld_request("GET", "/service-providers/properties/crypto-currencies")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fiat_currencies(request):
    """Fetch available fiat currencies from Meld.io"""
    return meld_request("GET", "/service-providers/properties/fiat-currencies")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_payment_methods(request):
    """Fetch payment methods based on provider/currency"""
    return meld_request("GET", "/service-providers/properties/payment-methods", params=request.query_params)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def get_crypto_quote(request):
    """Create a crypto quote (estimate)"""
    return meld_request("POST", "/payments/crypto/quote", data=request.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_session_widget(request):
    """Create a crypto payment widget session"""
    return meld_request("POST", "/crypto/session/widget", data=request.data)