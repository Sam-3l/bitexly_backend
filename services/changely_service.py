# import base64
# import binascii
# import hashlib
# import hmac
# import json
# import logging
# from typing import List

# from Crypto.Hash import SHA256
# from Crypto.PublicKey import RSA
# from Crypto.Signature import pkcs1_15
# from requests import post, Response

# logging.basicConfig(level=logging.INFO)


# class ApiException(Exception):
#     def __init__(self, code: int, message: str):
#         self.code = code
#         self.message = message


# class ApiService:
#     def __init__(self, url: str, private_key: str, x_api_key: str):
#         self.url = url
#         self.private_key = private_key
#         self.x_api_key = x_api_key

#     def _request(self, method: str, params: dict or list = None) -> Response or List[dict]:
#         params = params if params else {}
#         message = {
#             'jsonrpc': '2.0',
#             'id': 'test',
#             'method': method,
#             'params': params
#         }
#         response = post(self.url, headers=self._get_headers(body=message), json=message)
#         if response.ok:
#             response_body = response.json()
#             logging.info(f'{method} response: {response_body} (request: {params})')
#             if response_body.get('error'):
#                 error = response_body['error']
#                 raise ApiException(error['code'], error['message'])
#             return response_body['result']
#         raise ApiException(response.status_code, response.text)

#     # def _sign_request(self, body: dict) -> bytes:
#     #     decoded_private_key = binascii.unhexlify(self.private_key)
#     #     private_key = RSA.import_key(decoded_private_key)
#     #     message = json.dumps(body).encode('utf-8')
#     #     h = SHA256.new(message)
#     #     signature = pkcs1_15.new(private_key).sign(h)
#     #     return base64.b64encode(signature)
#     # def _sign_request(self, body):
#     #     message = json.dumps(body)
#     #     signature = hmac.new(
#     #         self.private_key.encode('utf-8'),  # use private key directly
#     #         message.encode('utf-8'),
#     #         hashlib.sha512
#     #     ).hexdigest()
#     #     return signature
#     def _sign_request(self, body: dict) -> str:
#         # Encode private key (hex to binary if needed)
#         decoded_private_key = binascii.unhexlify(self.private_key)
#         private_key = RSA.import_key(decoded_private_key)

#         # Make sure JSON is consistently encoded
#         message = json.dumps(body, separators=(',', ':'), sort_keys=True).encode('utf-8')

#         # Sign with SHA256 + PKCS1 v1.5
#         h = SHA256.new(message)
#         signature = pkcs1_15.new(private_key).sign(h)

#         # Return base64 string
#         return base64.b64encode(signature).decode()

#     def _get_headers(self, body: dict) -> dict:
#         signature = self._sign_request(body)
#         return {
#             'content-type': 'application/json',
#             'X-Api-Key': self.x_api_key,
#             'X-Api-Signature': signature,
#         }
    

#     def get_pairs_params(self, currency_from: str, currency_to: str):
#         return self._request('getPairsParams', params=[{'from': currency_from, 'to': currency_to}])


#     def get_currencies(self):
#         return self._request("getCurrencies")

#     def get_exchange_amount(self, from_currency: str, to_currency: str, amount: str):
#         return self._request("getExchangeAmount", params=[{
#             "from": from_currency,
#             "to": to_currency,
#             "amount": amount
#         }])

#     def create_transaction(self, from_currency: str, to_currency: str, address: str, amount: str):
#         return self._request("createTransaction", params=[{
#             "from": from_currency,
#             "to": to_currency,
#             "address": address,
#             "amount": amount
#         }])


import json
import hmac
import hashlib
import requests
from django.conf import settings

API_URL = "https://api.changelly.com/v2"
API_KEY = "DczA8A5tyxtHVg9DQO6u7qLs6ueyg5B7zwoyr6ovJRI="
API_SECRET = "az0xu2gihjl1hbwm"  # keep secret safe
    # private_key="",
    # x_api_key="",


# def sign_request(message: dict):
#     msg_json = json.dumps(message)
#     signature = hmac.new(
#         API_SECRET.encode(),
#         msg_json.encode(),
#         hashlib.sha512
#     ).hexdigest()
#     return signature, msg_json

def sign_request(message: dict):
    # Compact JSON: separators=(',', ':')
    msg_json = json.dumps(message, separators=(',', ':'))
    
    signature = hmac.new(
        API_SECRET.encode(),
        msg_json.encode(),
        hashlib.sha512
    ).hexdigest()
    
    return signature, msg_json

# def changelly_request(method, params=None):
#     params = params or {}
#     message = {
#         "jsonrpc": "2.0",
#         "id": "test",
#         "method": method,
#         "params": params
#     }
#     signature, msg_json = sign_request(message)

#     headers = {
#         "api-key": API_KEY,
#         "sign": signature,
#         "Content-Type": "application/json"
#     }

#     response = requests.post(API_URL, headers=headers, data=msg_json)
#     return response.json()




def changelly_request(method, params=None):
    params = params or {}
    message = {
        "jsonrpc": "2.0",
        "id": "test",
        "method": method,
        "params": params
    }
    signature, msg_obj = sign_request(message)

    headers = {
        "X-Api-Key": API_KEY,
        "X-Api-Signature": signature,
        "Content-Type": "application/json"
    }

    # ✅ FIX: use json= instead of data=
    response = requests.post(API_URL, headers=headers, data=msg_obj)

    try:
        return response.json()
    except Exception:
        # Debug output
        print("Changelly RAW RESPONSE:", response.text)
        return {"error": response.text, "status_code": response.status_code}