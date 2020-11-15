"""
import websocket
import json
import arrow
import mongoengine
import logging
import requests
import time

try:
    import thread
except ImportError:
    import _thread as thread

from dataclasses import dataclass
import os, sys, inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from collector.models.candle import Candle

endpoint = "wss://api.upbit.com/websocket/v1"
trade_time = {}
candle_price = {}


@dataclass
class ParsedMarketData:
    code: str
    trade_price: int
    year: int
    month: int
    days: int
    hour: int
    minute: int
    stream_type: str

    @classmethod
    def create(cls, code: str, trade_price: int, year: int, month: int, days: int, hour: int, minute: int, stream_type: str):
        return cls(code=code, trade_price=trade_price, year=year, month=month, days=days, hour=hour, minute=minute, stream_type=stream_type)


class TradeTimeInitializer:
    @classmethod
    def initialize(cls, market_data: ParsedMarketData):
        global trade_time
        trade_time[market_data.code] = {}
        trade_time[market_data.code]['year'] = market_data.year
        trade_time[market_data.code]['month'] = market_data.month
        trade_time[market_data.code]['days'] = market_data.days
        trade_time[market_data.code]['hour'] = market_data.hour
        trade_time[market_data.code]['minute'] = market_data.minute


class TradeTimeUpdater:
    @classmethod
    def update(cls, market_data: ParsedMarketData):
        global trade_time
        trade_time[market_data.code]['year'] = market_data.year
        trade_time[market_data.code]['month'] = market_data.month
        trade_time[market_data.code]['days'] = market_data.days
        trade_time[market_data.code]['hour'] = market_data.hour
        trade_time[market_data.code]['minute'] = market_data.minute


class CandlePriceInitializer:
    @classmethod
    def initialize(cls, market_data: ParsedMarketData):
        global candle_price
        candle_price[market_data.code] = {}
        candle_price[market_data.code]['1m'] = {}
        candle_price[market_data.code]['3m'] = {}
        candle_price[market_data.code]['5m'] = {}
        candle_price[market_data.code]['10m'] = {}
        candle_price[market_data.code]['15m'] = {}
        candle_price[market_data.code]['30m'] = {}
        candle_price[market_data.code]['60m'] = {}
        candle_price[market_data.code]['240m'] = {}

        cls._initialize(market_data, candle_price[market_data.code]['1m'])
        cls._initialize(market_data, candle_price[market_data.code]['3m'])
        cls._initialize(market_data, candle_price[market_data.code]['5m'])
        cls._initialize(market_data, candle_price[market_data.code]['10m'])
        cls._initialize(market_data, candle_price[market_data.code]['15m'])
        cls._initialize(market_data, candle_price[market_data.code]['30m'])
        cls._initialize(market_data, candle_price[market_data.code]['60m'])
        cls._initialize(market_data, candle_price[market_data.code]['240m'])

    @classmethod
    def _initialize(cls, market_data: ParsedMarketData, candle):
        candle['open_price'] = market_data.trade_price
        candle['close_price'] = market_data.trade_price
        candle['high_price'] = market_data.trade_price
        candle['low_price'] = market_data.trade_price


class LowHighPriceUpdater:
    @classmethod
    def update(cls, market_data: ParsedMarketData, minute):
        if candle_price[market_data.code][minute]['low_price'] > market_data.trade_price:
            LowPriceUpdater.update(market_data, minute=minute, low_price=market_data.trade_price)
        if candle_price[market_data.code][minute]['high_price'] < market_data.trade_price:
            HighPriceUpdater.update(market_data, minute=minute, high_price=market_data.trade_price)


class OpenPriceUpdater:
    @classmethod
    def update(cls, market_data, minute, open_price):
        global candle_price
        candle_price[market_data.code][minute]['open_price'] = open_price


class ClosePriceUpdater:
    @classmethod
    def update(cls, market_data, minute, close_price):
        global candle_price
        candle_price[market_data.code][minute]['close_price'] = close_price


class LowPriceUpdater:
    @classmethod
    def update(cls, market_data, minute, low_price):
        global candle_price
        candle_price[market_data.code][minute]['low_price'] = low_price


class HighPriceUpdater:
    @classmethod
    def update(cls, market_data, minute, high_price):
        global candle_price
        candle_price[market_data.code][minute]['high_price'] = high_price


class MessageParser:
    @classmethod
    def parse(cls, message) -> ParsedMarketData:
        message = json.loads(message.decode('utf-8'))
        code = message['code']
        trade_time = message['trade_time']
        trade_date = message['trade_date']
        trade_price = message['trade_price']

        hour = trade_time.split(":")[0]
        minute = trade_time.split(":")[1]

        year, month, days = trade_date.split("-")
        stream_type = message['stream_type']
        return ParsedMarketData.create(code, int(trade_price), int(year), int(month), int(days), hour, minute, stream_type)


class CandleGenerator:
    @classmethod
    def create(cls, market_data, minute):
        minute_candle_price = candle_price[market_data.code][minute]
        Candle(code=market_data.code, date_time=f'{market_data.year}{market_data.month}{market_data.days}{market_data.hour}{market_data.minute}',
               minute=minute, open_price=minute_candle_price['open_price'], close_price=minute_candle_price['close_price'],
               high_price=minute_candle_price['high_price'], low_price=minute_candle_price['low_price'], created_at=arrow.now()).save()


class CandleCloseChecker:
    @classmethod
    def is_1m_candle_close(cls, market_data: ParsedMarketData):
        if trade_time[market_data.code]['minute'] != market_data.minute:
            return True
        else:
            return False

    @classmethod
    def is_3m_candle_close(cls, market_data: ParsedMarketData):
        if (trade_time[market_data.code]['minute'] != market_data.minute) and int(market_data.minute) % 3 == 0:
            return True
        else:
            return False

    @classmethod
    def is_5m_candle_close(cls, market_data: ParsedMarketData):
        if (trade_time[market_data.code]['minute'] != market_data.minute) and int(market_data.minute) % 5 == 0:
            return True
        else:
            return False

    @classmethod
    def is_10m_candle_close(cls, market_data: ParsedMarketData):
        if (trade_time[market_data.code]['minute'] != market_data.minute) and int(market_data.minute) % 10 == 0:
            return True
        else:
            return False

    @classmethod
    def is_15m_candle_close(cls, market_data: ParsedMarketData):
        if (trade_time[market_data.code]['minute'] != market_data.minute) and int(market_data.minute) % 15 == 0:
            return True
        else:
            return False

    @classmethod
    def is_30m_candle_close(cls, market_data: ParsedMarketData):
        if (trade_time[market_data.code]['minute'] != market_data.minute) and int(market_data.minute) % 30 == 0:
            return True
        else:
            return False

    @classmethod
    def is_60m_candle_close(cls, market_data: ParsedMarketData):
        if trade_time[market_data.code]['hour'] != market_data.hour:
            return True
        else:
            return False

    @classmethod
    def is_240m_candle_close(cls, market_data: ParsedMarketData):
        if trade_time[market_data.code]['hour'] != market_data.hour and int(market_data.hour) % 4 == 1:
            return True
        else:
            return False


class CandleManager:
    @classmethod
    def manage(cls, market_data: ParsedMarketData):
        for minute in ['1m', '3m', '5m', '10m', '15m', '30m', '60m', '240m']:
            LowHighPriceUpdater.update(market_data, minute=minute)

        if CandleCloseChecker.is_1m_candle_close(market_data):
            cls._create_candle(market_data, minute='1m')

        if CandleCloseChecker.is_3m_candle_close(market_data):
            cls._create_candle(market_data, minute='3m')

        if CandleCloseChecker.is_5m_candle_close(market_data):
            cls._create_candle(market_data, minute='5m')

        if CandleCloseChecker.is_10m_candle_close(market_data):
            cls._create_candle(market_data, minute='10m')

        if CandleCloseChecker.is_15m_candle_close(market_data):
            cls._create_candle(market_data, minute='15m')

        if CandleCloseChecker.is_30m_candle_close(market_data):
            cls._create_candle(market_data, minute='30m')

        if CandleCloseChecker.is_60m_candle_close(market_data):
            cls._create_candle(market_data, minute='60m')

        if CandleCloseChecker.is_240m_candle_close(market_data):
            cls._create_candle(market_data, minute='240m')

    @classmethod
    def _create_candle(cls, market_data, minute):
        ClosePriceUpdater.update(market_data=market_data, minute=minute, close_price=market_data.trade_price)

        CandleGenerator.create(market_data, minute=minute)

        OpenPriceUpdater.update(market_data=market_data, minute=minute, open_price=market_data.trade_price)
        ClosePriceUpdater.update(market_data=market_data, minute=minute, close_price=market_data.trade_price)
        LowPriceUpdater.update(market_data=market_data, minute=minute, low_price=market_data.trade_price)
        HighPriceUpdater.update(market_data=market_data, minute=minute, high_price=market_data.trade_price)


class HistoricalCandleCollector:
    endpoint = "https://api.upbit.com/v1/candles/minutes/"

    @classmethod
    def _collect_latest_candle(cls, code, minute, count):
        querystring = {"market": code, 'count': count}
        url = cls.endpoint + f'{minute}'
        response = requests.request("GET", url, params=querystring)

        res_json = response.json()

        candle_date_time = res_json[0]['candle_date_time_utc']
        date = candle_date_time.split('T')[0]
        time = candle_date_time.split('T')[1]

        year = date.split('-')[0]
        month = date.split('-')[1]
        days = date.split('-')[2]

        hour = time.split(':')[0]
        minutes = time.split(':')[1]

        open_price = res_json[0]['opening_price']
        close_price = res_json[0]['trade_price']
        high_price = res_json[0]['high_price']
        low_price = res_json[0]['low_price']

        Candle(code=code, date_time=f'{year}{month}{days}{hour}{minutes}',
               minute=f'{minute}m', open_price=open_price, close_price=close_price,
               high_price=high_price, low_price=low_price, created_at=arrow.now()).save()



    @classmethod
    def collect_latest_candles(cls, code, count=1):
        for minute in [1, 3, 5, 10, 15, 30, 60, 240]:
            cls._collect_latest_candle(code=code, minute=minute, count=count)
            time.sleep(0.1)


def on_message(ws, message):
    try:
        parsed_market_data: ParsedMarketData = MessageParser.parse(message)
        if parsed_market_data.stream_type == "SNAPSHOT":
            CandlePriceInitializer.initialize(parsed_market_data)
            TradeTimeInitializer.initialize(parsed_market_data)
            HistoricalCandleCollector.collect_latest_candles(code=parsed_market_data.code)

        CandleManager.manage(parsed_market_data)
        TradeTimeUpdater.update(parsed_market_data)
    except Exception as e:
        logging.error(e, exc_info=True)


def on_error(ws, error):
    print(error)


def on_close(ws):
    print("### Closed ###")


def on_open(ws):
    def run(*args):
        send_data = '[{"ticket":"test"},{"type":"trade","codes":["KRW-BTC", "KRW-BCH"]}]'
        ws.send(send_data)

    thread.start_new_thread(run, ())


if __name__ == "__main__":
    mongoengine.connect(host='mongodb://localhost:27017/trading?connect=false')
    ws = websocket.WebSocketApp(endpoint,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close,
                                on_open=on_open)

    ws.run_forever(ping_interval=30, ping_timeout=25)
"""