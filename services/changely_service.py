import base64
import binascii
import json
import logging
from typing import List

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from requests import post, Response

logging.basicConfig(level=logging.INFO)


class ApiException(Exception):
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


class ApiService:
    def __init__(self, url: str, private_key: str, x_api_key: str):
        self.url = url
        self.private_key = private_key
        self.x_api_key = x_api_key

    def _request(self, method: str, params: dict or list = None) -> Response or List[dict]:
        params = params if params else {}
        message = {
            'jsonrpc': '2.0',
            'id': 'test',
            'method': method,
            'params': params
        }
        response = post(self.url, headers=self._get_headers(body=message), json=message)
        if response.ok:
            response_body = response.json()
            logging.info(f'{method} response: {response_body} (request: {params})')
            if response_body.get('error'):
                error = response_body['error']
                raise ApiException(error['code'], error['message'])
            return response_body['result']
        raise ApiException(response.status_code, response.text)

    def _sign_request(self, body: dict) -> bytes:
        decoded_private_key = binascii.unhexlify(self.private_key)
        private_key = RSA.import_key(decoded_private_key)
        message = json.dumps(body).encode('utf-8')
        h = SHA256.new(message)
        signature = pkcs1_15.new(private_key).sign(h)
        return base64.b64encode(signature)

    def _get_headers(self, body: dict) -> dict:
        signature = self._sign_request(body)
        return {
            'content-type': 'application/json',
            'X-Api-Key': self.x_api_key,
            'X-Api-Signature': signature,
        }

    def get_pairs_params(self, currency_from: str, currency_to: str):
        return self._request('getPairsParams', params=[{'from': currency_from, 'to': currency_to}])
