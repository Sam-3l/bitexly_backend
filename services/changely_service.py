import json
import hmac
import hashlib
import requests
from django.conf import settings

API_URL = "https://api.changelly.com/v2"
API_KEY = "DczA8A5tyxtHVg9DQO6u7qLs6ueyg5B7zwoyr6ovJRI="
# API_SECRET = "az0xu2gihjl1hbwm"
API_SECRET = "308204bb020100300d06092a864886f70d0101010500048204a5308204a10201000282010100906a3d15c826b7808792b21b3fa44b9ea3aa2cf907a71acc8aa050d3b21d8e0f10fc4877674f7c48f27420df39ae2399522d300509765f0a1dd9247d99deedbaa62008ff2d3c6cf45e97f41459477d8145e74c61bb1edde0065e262efde279143f2c3f1f2e921badf8de20038e75ba9316770dc740055e8ec5684794b856e9ba90eecc0a69f2231cbdbf438891b62144b38a140161c989ffdd0ef5ffa80b59f4e4bb926f96d55fb07db09f66a6dc5fd415da293a32be37a8a9df88140f70eb3c5303a4fa720c7a4ff97348fa1fd3df417ddc973f029b591e23166b0807d8d8e88a13cf61e79cbdc9c48786fe305979b781759b195e1f5dd707ba197ca7b4363102030100010281ff720b73dc9508a8e1578456cd834a111861272d5cd183a57b8ca8b8811ffd3707aee23702bf1330e86a8fa010a8a707208d44ccd1d82722915aaba0503ab35209942762f3769b16c539ee70a7a12efe6ded9b908b9d6498287cdedcf33f366f67b87bb8b2bc945047931681dc4d24565d7c8add81518d969ed39bb0eb96a7b6eb440da2c9a9d5bbceae683a6882cedd67ff534fb19e4dad003daa78140c6c20a866caced87ab2161c2008a7d5b189385d187cc7a825a79fa05cc04c15d0a71eb07020a1572b12edff285cfe8c11e41085f7b0296e956890ff63d27063c6d36908e565b6634a6c6fdf5fceda365b3746a1aeb76ee1c1936afc5f1e2663d1fd4702818100c5fb201ba5eec74a73aa69e4a3a4fefc135da92560540c0b7fc28e09aa6b9b24706f94b7a697d508102ba12ce54f5a7c9f5be4b0f34bf0f85a6d760b7e25c408c02bb773039c7def8e964ab702283c12a3ec3ab05069aee82e46489b2a1900765455b9f8cb33a005cddf5cc29189dbee890b5666217b0976180224cddf442e9b02818100babc80728088a8e26fcc5d5b3cef860c70d110b7cb6f35d02b7dbc7e180106ae044b4dbde7f511c36292fd20330bf82c386c4676c4a501be0bdac240fc6a426a5f5e7d4ae7afcf1f83f1b1c3fbfb3e333e21291ef3d214e88eaf0171de881a7827442c0db93f0a657141f13974e74c178854985c77c9e2f7e3fad498070f752302818100a71861ac142b68d6a4b2d2f71f4af5cea945a6aa1e1831a64ee954da4194da7731d26b1169b0c223310ab1d8e39d4b00ddbb40543cb3fea88e21cebcba768372e346c2697745d060acd69a2ec5ca519165face39db54a743dd3282bb3b17a8f5360eb88c8c6c810605111d0836afc509196f913757d0b15693c2d36f529e083b0281807aa636e37e02c4923d86084755e5a8b0e124a00b6805fa5d6943639b9a5e8a299fce6a187292e780e26cd2eee438575f8c0ba9d8765e3e9fb99f8c792c910a605d956d4bd69305c298621635387b13a68a8733400e3b0cda9664e1d90da56d653fbd2a063586ef682394814110c49e98d24565f14e087f17fc58926bec2f3deb0281801fef02fbc2095bd625f2b04ace7bef124b7d636f406e170c7688b3af15f643c8d445997e0c6b996382b2df523a630d3c608ef572323de7d3537b2cadfeeab8f498d98b82d6b22c1761f87a3ce9b6bdbe008aa3c22a321f91095c81956c563ee4eea361550977b1f25a6b14c6bb3934a149548d7b7a2c7803fefa6c4bfae203c8"


def sign_request(message: dict):
    # Compact JSON: separators=(',', ':')
    msg_json = json.dumps(message, separators=(',', ':'))
    
    signature = hmac.new(
        API_SECRET.encode(),
        msg_json.encode(),
        hashlib.sha512
    ).hexdigest()
    
    return signature, msg_json



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
        "api-key": API_KEY,
        "sign": signature,
        "Content-Type": "application/json"
    }

    # ✅ FIX: use json= instead of data=
    response = requests.post(API_URL, headers=headers, data=msg_obj)

    try:
        return response.json()
    except Exception:
        # Debug output
        print({"message": message, "signature": signature, "msg_obj": msg_obj})
        print("Changelly RAW RESPONSE:", (response))
        return {"error": response, "status_code": response.status_code}