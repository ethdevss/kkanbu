import uuid
import hashlib
from urllib.parse import urlencode
import jwt

import requests


class OrderManager:
    server_url = "https://api.upbit.com"

    @classmethod
    def send_order(cls, market_code, side, ord_type, access_key, secret_key, volume=None, price=None):
        query = {
            'market': market_code,
            'side': side, # bid: 매수, ask: 매도
            'ord_type': ord_type
        }

        if volume:
            query['volume'] = volume

        if price:
            query['price'] = price

        query_string = urlencode(query).encode()

        m = hashlib.sha512()
        m.update(query_string)
        query_hash = m.hexdigest()

        payload = {
            'access_key': access_key,
            'nonce': str(uuid.uuid4()),
            'query_hash': query_hash,
            'query_hash_alg': 'SHA512',
        }

        jwt_token = jwt.encode(payload, secret_key).decode('utf-8')
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}

        res = requests.post(cls.server_url + "/v1/orders", params=query, headers=headers)
        return res

    @classmethod
    def get_current_prices(cls, market_codes):
        query = {
            'markets': ', '.join(market_codes)
        }

        res = requests.get(cls.server_url + "/v1/ticker", params=query)
        return res.json()

    @classmethod
    def get_accounts(cls, access_key, secret_key):
        payload = {
            'access_key': access_key,
            'nonce': str(uuid.uuid4()),
        }

        jwt_token = jwt.encode(payload, secret_key).decode('utf-8')
        authorize_token = 'Bearer {}'.format(jwt_token)
        headers = {"Authorization": authorize_token}

        res = requests.get(cls.server_url + "/v1/accounts", headers=headers)
        return res.json()

    @classmethod
    def get_orderbook(cls, market_code):
        querystring = {"markets": market_code}
        response = requests.request("GET", cls.server_url + "/v1/orderbook", params=querystring)
        return response.text
