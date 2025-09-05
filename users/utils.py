# utils.py
import hashlib
import json
import time
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
import random
import requests
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.contrib.auth import get_user_model, authenticate
from cryptography.fernet import Fernet, InvalidToken

User = get_user_model()
fernet = Fernet(settings.FERNET_KEY)

def verify_user_pin(input_pin: str, stored_encrypted_pin: str) -> bool:
    try:
        decrypted_pin = retrieve_user_pin(stored_encrypted_pin)
        return input_pin == decrypted_pin
    except ValueError as e:
        # Log or handle failed decryption if needed
        return False

def set_user_pin(plain_pin):
    encrypted_pin = fernet.encrypt(plain_pin.encode()).decode()
    return encrypted_pin


def retrieve_user_pin(pin_hash: str) -> str:
    try:
        print(pin_hash)
        return fernet.decrypt(pin_hash.encode()).decode()
    except InvalidToken:
        raise ValueError("Invalid or corrupt PIN hash (likely not encrypted)")
    except Exception as e:
        raise ValueError(f"Decryption failed: {str(e)}")
def generate_otp():
    return str(random.randint(1000, 9999))

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class SecureActionMixin:
    def validate_pin(self, user, pin):
        if not pin:
            return False, Response({'detail': 'PIN is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not user.pin_hash or not user.check_pin(pin):
            return False, Response({'detail': 'Invalid PIN.'}, status=status.HTTP_403_FORBIDDEN)
        return True, None

import hmac
import base64
from hashlib import sha256
from urllib.parse import urlencode

def sign_url(base_url, params, secret_key):
    query_string = urlencode(params)
    signature = hmac.new(
        key=secret_key.encode("utf-8"),
        msg=query_string.encode("utf-8"),
        digestmod=sha256
    ).digest()
    signature_b64 = base64.b64encode(signature).decode("utf-8")

    return f"{base_url}?{query_string}&signature={signature_b64}"


def quotes():
    try:
        body = {
        'coinId': 54,
        'coinCode': "usdt",  # (if both coinId and coinCode are passed -> coinCode takes precedence)
        'chainId': 3,
        'network': "bep20",  #(if both chainId and network are passed -> network takes precedence)
        'quantity': 2,       # refers to the crypto quantity to be sold 
        'fiatType': 1,       #Fiat Type from config file(1 for INR || 2 for TRY)
        'type': 2            # 1 -> onramp || 2 -> offramp (will be supported soon)
        }
        payload = {
            "timestamp": int(time.time() * 1000),  # to get timestamp in milliseconds
            "body": body
        }
        api_key = 'API_KEY'
        api_secret = 'API_SECRET'

        payload = base64.b64encode(json.dumps(payload).encode()).decode()
        signature = hmac.new(api_secret.encode(), payload.encode(), hashlib.sha512).hexdigest()
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json;charset=UTF-8',
            'X-ONRAMP-SIGNATURE': signature,
            'X-ONRAMP-APIKEY': api_key,
            'X-ONRAMP-PAYLOAD': payload
        }
        url = 'https://api.onramp.money/onramp/api/v2/common/transaction/quotes'
        response = requests.post(url, headers=headers, data=json.dumps(body))
        print(response.json())
    except Exception as e:
        print(str(e))

quotes()