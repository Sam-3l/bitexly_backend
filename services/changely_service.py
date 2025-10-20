import json
import hmac
import hashlib
import requests
from django.conf import settings

#   The private key is: 308204bc020100300d06092a864886f70d0101010500048204a6308204a20201000282010100af3a673384e54824b03785089a553be5c5413441d9b9ed52af1a1c37f9e78e4d28947ce7d551e70ae1cb12f2f70fca543bdc385881c78b405760296bf6998d0d82744c01a8daa6865e3451b996d723631f185d660e749c995117f5e91a953e1e75720e38817bb9ccd0e0887d1cad3597c76e9eaf9d45d8c0fb62dca68b1ec38b205bc37a4cd709af697e410e170d19ff26deba2a3c7cbfdfed1dda5ad47c37b41da176bc2969ad1e5b6326a2a80437915fc232f30c28a427ab3dd6b2decfc159dc67c1c6b85735e2b20deb486b0d690290219b1e976ded5c0808e1b1d0a2497843c30736efb5f9cf1fe3f42290700ab2d7a72a1b2c6104f273f16fefcda684b3020301000102820100091e667179687f251da07e055116bf6bb924a8060741143719d2a78648348324c3c85a69ac21bb7ec6fa4ceda4eac6f2343d4517620592db11d0f8c6dc09e89bbbdeb677dda4274755ceae3414c3f45cfba8c66f81b012d82daeac06e9f1bb4e55794e812547dd86e995cdb4891200787a11e923257195929162772e198e4bc9b308cfc04e49dd2e5a52c315fd405b785768709e6603ee836bdbd32f1a4fca34271e71ba781d90255e031c1669cca7e2780e16b26a81003c87a5a576ca2a52b7955f87ce480e002f7972c6a4c533cfd9838bee3c67be92d81082f1bfa2a29fa55638ecc536428dbbb07fcd5c84c56415a4bc32da01e5194462660ede48e548f902818100ea4fb238d00efb046f7076d6249a2e8acf3fee24aa47dcf0c592b992cf549f77660460aa6104175911ffbc18a0046b0ad502919be57ba25697afbd552584e6264be14c2bf9c0a1ce5cc5fe6de72534dfb53f9f1791953394824509144c94a15804217af1dd8702e4a6abd1ff4495db45f79c13dec51ccee851b79c67e2c431cb02818100bf72a7f8dc95f49ae0261452de7e6cd8d2838282a702f7c667bda44bc13b38e98fbf8d1ff19a859996aaae2b2935879be6d87e9613641a82884d1fd3863dd77e2b71fdd1b3585f0cbde6264f6fb5885e7ff2ed6711084efe2dc0f9695b33344ecc0d9029abc74dd1df87a28203d637c12f054cf0df487a3c2678a226d7967bb902818025c3065405a4046c68915575999c8797b362f83c4c7d1c6c694b064154ccac8e8f90710bc46ae660627836963963bce49803bbf7c5fa30e587b8b8e8ba0d3b123cf468544601f791cc7dd44d5e0d2f0246b1a43026344785cda0d69fc0dfcb48e6118740e794d4b088f3f3fa11d19cef1fc2b5a91757573935c243a0b27930150281802d36f100cf68030b08e1356f94e89ae0626778cd4e905ee056e3ed078f2d637595e3917af7de9caaf7707c0de97fa0f56b01ba73cb449b163506b1fb8cfad208144ea9b97af7e60ae65692b9b4125590abfb3da257dd747a8767c9ffddf02bec6838d3d163a680748eac43ef1ce4dcea1d26cd531e08ca05a6b85ae37d8b26d10281806a8c4add427ebc181be1f97e410562851d65ae76b94d751f2fb6d8e9ee84275eef92f1bb2c42ffd486e562bdf47011f9cecd3f6e46ddd70e095d794b6253d251bade11ef789d88979cd51bd05bb027b4cfcae9bf1b6073c1dc055ad33c7defc95716dc62f6d19957c192c7a71eee47fd43ab139b89585449401ec46f79903808
#     The public key is: MIIBCgKCAQEArzpnM4TlSCSwN4UImlU75cVBNEHZue1SrxocN/nnjk0olHzn1VHnCuHLEvL3D8pUO9w4WIHHi0BXYClr9pmNDYJ0TAGo2qaGXjRRuZbXI2MfGF1mDnScmVEX9ekalT4edXIOOIF7uczQ4Ih9HK01l8dunq+dRdjA+2Lcposew4sgW8N6TNcJr2l+QQ4XDRn/Jt66Kjx8v9/tHdpa1Hw3tB2hdrwpaa0eW2MmoqgEN5FfwjLzDCikJ6s91rLez8FZ3GfBxrhXNeKyDetIaw1pApAhmx6Xbe1cCAjhsdCiSXhDwwc277X5zx/j9CKQcAqy16cqGyxhBPJz8W/vzaaEswIDAQAB
#     SHA256 hash of your public key in Base64 format is: iHhiaXLglwUb33XL8FhqCfEs+Hq2KX65mhJs+5mB/sk=
API_URL = "https://api.changelly.com/v2"
API_KEY = "iHhiaXLglwUb33XL8FhqCfEs+Hq2KX65mhJs+5mB/sk="
# API_SECRET = "az0xu2gihjl1hbwm"
# API_SECRET = "308204bc020100300d06092a864886f70d0101010500048204a6308204a20201000282010100af3a673384e54824b03785089a553be5c5413441d9b9ed52af1a1c37f9e78e4d28947ce7d551e70ae1cb12f2f70fca543bdc385881c78b405760296bf6998d0d82744c01a8daa6865e3451b996d723631f185d660e749c995117f5e91a953e1e75720e38817bb9ccd0e0887d1cad3597c76e9eaf9d45d8c0fb62dca68b1ec38b205bc37a4cd709af697e410e170d19ff26deba2a3c7cbfdfed1dda5ad47c37b41da176bc2969ad1e5b6326a2a80437915fc232f30c28a427ab3dd6b2decfc159dc67c1c6b85735e2b20deb486b0d690290219b1e976ded5c0808e1b1d0a2497843c30736efb5f9cf1fe3f42290700ab2d7a72a1b2c6104f273f16fefcda684b3020301000102820100091e667179687f251da07e055116bf6bb924a8060741143719d2a78648348324c3c85a69ac21bb7ec6fa4ceda4eac6f2343d4517620592db11d0f8c6dc09e89bbbdeb677dda4274755ceae3414c3f45cfba8c66f81b012d82daeac06e9f1bb4e55794e812547dd86e995cdb4891200787a11e923257195929162772e198e4bc9b308cfc04e49dd2e5a52c315fd405b785768709e6603ee836bdbd32f1a4fca34271e71ba781d90255e031c1669cca7e2780e16b26a81003c87a5a576ca2a52b7955f87ce480e002f7972c6a4c533cfd9838bee3c67be92d81082f1bfa2a29fa55638ecc536428dbbb07fcd5c84c56415a4bc32da01e5194462660ede48e548f902818100ea4fb238d00efb046f7076d6249a2e8acf3fee24aa47dcf0c592b992cf549f77660460aa6104175911ffbc18a0046b0ad502919be57ba25697afbd552584e6264be14c2bf9c0a1ce5cc5fe6de72534dfb53f9f1791953394824509144c94a15804217af1dd8702e4a6abd1ff4495db45f79c13dec51ccee851b79c67e2c431cb02818100bf72a7f8dc95f49ae0261452de7e6cd8d2838282a702f7c667bda44bc13b38e98fbf8d1ff19a859996aaae2b2935879be6d87e9613641a82884d1fd3863dd77e2b71fdd1b3585f0cbde6264f6fb5885e7ff2ed6711084efe2dc0f9695b33344ecc0d9029abc74dd1df87a28203d637c12f054cf0df487a3c2678a226d7967bb902818025c3065405a4046c68915575999c8797b362f83c4c7d1c6c694b064154ccac8e8f90710bc46ae660627836963963bce49803bbf7c5fa30e587b8b8e8ba0d3b123cf468544601f791cc7dd44d5e0d2f0246b1a43026344785cda0d69fc0dfcb48e6118740e794d4b088f3f3fa11d19cef1fc2b5a91757573935c243a0b27930150281802d36f100cf68030b08e1356f94e89ae0626778cd4e905ee056e3ed078f2d637595e3917af7de9caaf7707c0de97fa0f56b01ba73cb449b163506b1fb8cfad208144ea9b97af7e60ae65692b9b4125590abfb3da257dd747a8767c9ffddf02bec6838d3d163a680748eac43ef1ce4dcea1d26cd531e08ca05a6b85ae37d8b26d10281806a8c4add427ebc181be1f97e410562851d65ae76b94d751f2fb6d8e9ee84275eef92f1bb2c42ffd486e562bdf47011f9cecd3f6e46ddd70e095d794b6253d251bade11ef789d88979cd51bd05bb027b4cfcae9bf1b6073c1dc055ad33c7defc95716dc62f6d19957c192c7a71eee47fd43ab139b89585449401ec46f79903808"
# API_SECRET = "308204bc020100300d06092a864886f70d0101010500048204a6308204a20201000282010100af3a673384e54824b03785089a553be5c5413441d9b9ed52af1a1c37f9e78e4d28947ce7d551e70ae1cb12f2f70fca543bdc385881c78b405760296bf6998d0d82744c01a8daa6865e3451b996d723631f185d660e749c995117f5e91a953e1e75720e38817bb9ccd0e0887d1cad3597c76e9eaf9d45d8c0fb62dca68b1ec38b205bc37a4cd709af697e410e170d19ff26deba2a3c7cbfdfed1dda5ad47c37b41da176bc2969ad1e5b6326a2a80437915fc232f30c28a427ab3dd6b2decfc159dc67c1c6b85735e2b20deb486b0d690290219b1e976ded5c0808e1b1d0a2497843c30736efb5f9cf1fe3f42290700ab2d7a72a1b2c6104f273f16fefcda684b3020301000102820100091e667179687f251da07e055116bf6bb924a8060741143719d2a78648348324c3c85a69ac21bb7ec6fa4ceda4eac6f2343d4517620592db11d0f8c6dc09e89bbbdeb677dda4274755ceae3414c3f45cfba8c66f81b012d82daeac06e9f1bb4e55794e812547dd86e995cdb4891200787a11e923257195929162772e198e4bc9b308cfc04e49dd2e5a52c315fd405b785768709e6603ee836bdbd32f1a4fca34271e71ba781d90255e031c1669cca7e2780e16b26a81003c87a5a576ca2a52b7955f87ce480e002f7972c6a4c533cfd9838bee3c67be92d81082f1bfa2a29fa55638ecc536428dbbb07fcd5c84c56415a4bc32da01e5194462660ede48e548f902818100ea4fb238d00efb046f7076d6249a2e8acf3fee24aa47dcf0c592b992cf549f77660460aa6104175911ffbc18a0046b0ad502919be57ba25697afbd552584e6264be14c2bf9c0a1ce5cc5fe6de72534dfb53f9f1791953394824509144c94a15804217af1dd8702e4a6abd1ff4495db45f79c13dec51ccee851b79c67e2c431cb02818100bf72a7f8dc95f49ae0261452de7e6cd8d2838282a702f7c667bda44bc13b38e98fbf8d1ff19a859996aaae2b2935879be6d87e9613641a82884d1fd3863dd77e2b71fdd1b3585f0cbde6264f6fb5885e7ff2ed6711084efe2dc0f9695b33344ecc0d9029abc74dd1df87a28203d637c12f054cf0df487a3c2678a226d7967bb902818025c3065405a4046c68915575999c8797b362f83c4c7d1c6c694b064154ccac8e8f90710bc46ae660627836963963bce49803bbf7c5fa30e587b8b8e8ba0d3b123cf468544601f791cc7dd44d5e0d2f0246b1a43026344785cda0d69fc0dfcb48e6118740e794d4b088f3f3fa11d19cef1fc2b5a91757573935c243a0b27930150281802d36f100cf68030b08e1356f94e89ae0626778cd4e905ee056e3ed078f2d637595e3917af7de9caaf7707c0de97fa0f56b01ba73cb449b163506b1fb8cfad208144ea9b97af7e60ae65692b9b4125590abfb3da257dd747a8767c9ffddf02bec6838d3d163a680748eac43ef1ce4dcea1d26cd531e08ca05a6b85ae37d8b26d10281806a8c4add427ebc181be1f97e410562851d65ae76b94d751f2fb6d8e9ee84275eef92f1bb2c42ffd486e562bdf47011f9cecd3f6e46ddd70e095d794b6253d251bade11ef789d88979cd51bd05bb027b4cfcae9bf1b6073c1dc055ad33c7defc95716dc62f6d19957c192c7a71eee47fd43ab139b89585449401ec46f79903808"

# def sign_request(message: dict):
#     # Compact JSON: separators=(',', ':')
#     msg_json = json.dumps(message, separators=(',', ':'))
    
#     signature = hmac.new(
#         API_SECRET.encode(),
#         msg_json.encode(),
#         hashlib.sha512
#     ).hexdigest()
    
#     return signature, msg_json



# def changelly_request(method, params=None):
#     params = params or {}
#     message = {
#         "jsonrpc": "2.0",
#         "id": "test",
#         "method": method,
#         "params": params
#     }
#     signature, msg_obj = sign_request(message)

#     headers = {
#         "api-key": API_KEY,
#         "sign": signature,
#         "Content-Type": "application/json"
#     }

#     # ✅ FIX: use json= instead of data=
#     response = requests.post(API_URL, headers=headers, data=msg_obj)

#     try:
#         return response.json()
#     except Exception:
#         # Debug output
#         print({"message": message, "signature": signature, "msg_obj": msg_obj})
#         print("Changelly RAW RESPONSE:", (response))
#         return {"error": response, "status_code": response.status_code}

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

    def _request(self, method: str, params: dict or list = None) -> Response or List[dict]: # type: ignore
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
    #   "from": "eth",
    #   "to": "xrp",
    #   "address": "<<valid xrp address>>",
    #   "extraId": "<<valid xrp extraId>>",
    #   "amountFrom": "0.0339"

    def get_pairs_params(self, currency_from: str, currency_to: str):
        return self._request('getPairsParams', params=[{'from': currency_from, 'to': currency_to}])

    def get_convert(self, currency_from: str, currency_to: str, amount: int):
        return self._request('getExchangeAmount', params=[{'from': currency_from, 'to': currency_to, 'amountFrom': amount}])
    
    def validate_address(self, currency_from: str, address: str):
        print({'currency': currency_from, 'address': address})
        return self._request('validateAddress', params={"currency": currency_from,
     "address": address,
     })
    
    def create_transaction(self, currency_from: str, currency_to: str, amount: int, address: str):
        return self._request('createTransaction', params={'from': currency_from, 'to': currency_to, 'amountFrom': amount, 'address': address})
    
    def verify_transaction(self, transact_id: str):
        return self._request('getStatus',{"id": transact_id})
    
    def get_currencies(self):
        return self._request('getCurrenciesFull',{})
    
    def get_min_amount(self, currency_from: str, currency_to: str):
        return self._request('getMinAmount', params={'from': currency_from, 'to': currency_to})
 

api = ApiService(
        url='https://api.changelly.com/v2/',
        private_key='308204bc020100300d06092a864886f70d0101010500048204a6308204a20201000282010100af3a673384e54824b03785089a553be5c5413441d9b9ed52af1a1c37f9e78e4d28947ce7d551e70ae1cb12f2f70fca543bdc385881c78b405760296bf6998d0d82744c01a8daa6865e3451b996d723631f185d660e749c995117f5e91a953e1e75720e38817bb9ccd0e0887d1cad3597c76e9eaf9d45d8c0fb62dca68b1ec38b205bc37a4cd709af697e410e170d19ff26deba2a3c7cbfdfed1dda5ad47c37b41da176bc2969ad1e5b6326a2a80437915fc232f30c28a427ab3dd6b2decfc159dc67c1c6b85735e2b20deb486b0d690290219b1e976ded5c0808e1b1d0a2497843c30736efb5f9cf1fe3f42290700ab2d7a72a1b2c6104f273f16fefcda684b3020301000102820100091e667179687f251da07e055116bf6bb924a8060741143719d2a78648348324c3c85a69ac21bb7ec6fa4ceda4eac6f2343d4517620592db11d0f8c6dc09e89bbbdeb677dda4274755ceae3414c3f45cfba8c66f81b012d82daeac06e9f1bb4e55794e812547dd86e995cdb4891200787a11e923257195929162772e198e4bc9b308cfc04e49dd2e5a52c315fd405b785768709e6603ee836bdbd32f1a4fca34271e71ba781d90255e031c1669cca7e2780e16b26a81003c87a5a576ca2a52b7955f87ce480e002f7972c6a4c533cfd9838bee3c67be92d81082f1bfa2a29fa55638ecc536428dbbb07fcd5c84c56415a4bc32da01e5194462660ede48e548f902818100ea4fb238d00efb046f7076d6249a2e8acf3fee24aa47dcf0c592b992cf549f77660460aa6104175911ffbc18a0046b0ad502919be57ba25697afbd552584e6264be14c2bf9c0a1ce5cc5fe6de72534dfb53f9f1791953394824509144c94a15804217af1dd8702e4a6abd1ff4495db45f79c13dec51ccee851b79c67e2c431cb02818100bf72a7f8dc95f49ae0261452de7e6cd8d2838282a702f7c667bda44bc13b38e98fbf8d1ff19a859996aaae2b2935879be6d87e9613641a82884d1fd3863dd77e2b71fdd1b3585f0cbde6264f6fb5885e7ff2ed6711084efe2dc0f9695b33344ecc0d9029abc74dd1df87a28203d637c12f054cf0df487a3c2678a226d7967bb902818025c3065405a4046c68915575999c8797b362f83c4c7d1c6c694b064154ccac8e8f90710bc46ae660627836963963bce49803bbf7c5fa30e587b8b8e8ba0d3b123cf468544601f791cc7dd44d5e0d2f0246b1a43026344785cda0d69fc0dfcb48e6118740e794d4b088f3f3fa11d19cef1fc2b5a91757573935c243a0b27930150281802d36f100cf68030b08e1356f94e89ae0626778cd4e905ee056e3ed078f2d637595e3917af7de9caaf7707c0de97fa0f56b01ba73cb449b163506b1fb8cfad208144ea9b97af7e60ae65692b9b4125590abfb3da257dd747a8767c9ffddf02bec6838d3d163a680748eac43ef1ce4dcea1d26cd531e08ca05a6b85ae37d8b26d10281806a8c4add427ebc181be1f97e410562851d65ae76b94d751f2fb6d8e9ee84275eef92f1bb2c42ffd486e562bdf47011f9cecd3f6e46ddd70e095d794b6253d251bade11ef789d88979cd51bd05bb027b4cfcae9bf1b6073c1dc055ad33c7defc95716dc62f6d19957c192c7a71eee47fd43ab139b89585449401ec46f79903808',
        x_api_key='iHhiaXLglwUb33XL8FhqCfEs+Hq2KX65mhJs+5mB/sk=',
    )

# api.get_currencies()
# api.get_pairs_params("lee","azur")
# api.get_convert('lee', 'azur', 0.02)
# api.create_transaction('eth','btc',0.02,'1FfmbHfnpaZjKFvyi1okTjJJusN455paPH')
# api.verify_transaction("4bc9j3q8zkc5js3d")

        # url='https://api.changelly.com/v2/',
        # private_key='308204bc020100300d06092a864886f70d0101010500048204a6308204a20201000282010100af3a673384e54824b03785089a553be5c5413441d9b9ed52af1a1c37f9e78e4d28947ce7d551e70ae1cb12f2f70fca543bdc385881c78b405760296bf6998d0d82744c01a8daa6865e3451b996d723631f185d660e749c995117f5e91a953e1e75720e38817bb9ccd0e0887d1cad3597c76e9eaf9d45d8c0fb62dca68b1ec38b205bc37a4cd709af697e410e170d19ff26deba2a3c7cbfdfed1dda5ad47c37b41da176bc2969ad1e5b6326a2a80437915fc232f30c28a427ab3dd6b2decfc159dc67c1c6b85735e2b20deb486b0d690290219b1e976ded5c0808e1b1d0a2497843c30736efb5f9cf1fe3f42290700ab2d7a72a1b2c6104f273f16fefcda684b3020301000102820100091e667179687f251da07e055116bf6bb924a8060741143719d2a78648348324c3c85a69ac21bb7ec6fa4ceda4eac6f2343d4517620592db11d0f8c6dc09e89bbbdeb677dda4274755ceae3414c3f45cfba8c66f81b012d82daeac06e9f1bb4e55794e812547dd86e995cdb4891200787a11e923257195929162772e198e4bc9b308cfc04e49dd2e5a52c315fd405b785768709e6603ee836bdbd32f1a4fca34271e71ba781d90255e031c1669cca7e2780e16b26a81003c87a5a576ca2a52b7955f87ce480e002f7972c6a4c533cfd9838bee3c67be92d81082f1bfa2a29fa55638ecc536428dbbb07fcd5c84c56415a4bc32da01e5194462660ede48e548f902818100ea4fb238d00efb046f7076d6249a2e8acf3fee24aa47dcf0c592b992cf549f77660460aa6104175911ffbc18a0046b0ad502919be57ba25697afbd552584e6264be14c2bf9c0a1ce5cc5fe6de72534dfb53f9f1791953394824509144c94a15804217af1dd8702e4a6abd1ff4495db45f79c13dec51ccee851b79c67e2c431cb02818100bf72a7f8dc95f49ae0261452de7e6cd8d2838282a702f7c667bda44bc13b38e98fbf8d1ff19a859996aaae2b2935879be6d87e9613641a82884d1fd3863dd77e2b71fdd1b3585f0cbde6264f6fb5885e7ff2ed6711084efe2dc0f9695b33344ecc0d9029abc74dd1df87a28203d637c12f054cf0df487a3c2678a226d7967bb902818025c3065405a4046c68915575999c8797b362f83c4c7d1c6c694b064154ccac8e8f90710bc46ae660627836963963bce49803bbf7c5fa30e587b8b8e8ba0d3b123cf468544601f791cc7dd44d5e0d2f0246b1a43026344785cda0d69fc0dfcb48e6118740e794d4b088f3f3fa11d19cef1fc2b5a91757573935c243a0b27930150281802d36f100cf68030b08e1356f94e89ae0626778cd4e905ee056e3ed078f2d637595e3917af7de9caaf7707c0de97fa0f56b01ba73cb449b163506b1fb8cfad208144ea9b97af7e60ae65692b9b4125590abfb3da257dd747a8767c9ffddf02bec6838d3d163a680748eac43ef1ce4dcea1d26cd531e08ca05a6b85ae37d8b26d10281806a8c4add427ebc181be1f97e410562851d65ae76b94d751f2fb6d8e9ee84275eef92f1bb2c42ffd486e562bdf47011f9cecd3f6e46ddd70e095d794b6253d251bade11ef789d88979cd51bd05bb027b4cfcae9bf1b6073c1dc055ad33c7defc95716dc62f6d19957c192c7a71eee47fd43ab139b89585449401ec46f79903808',
        # x_api_key='iHhiaXLglwUb33XL8FhqCfEs+Hq2KX65mhJs+5mB/sk=',