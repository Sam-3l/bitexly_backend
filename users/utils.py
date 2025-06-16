# utils.py
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
import random
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
