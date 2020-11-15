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

import os, sys, inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from collector.scheduler.candle_scheduler import CandleScheduler
from collector.models.candle import Candle
from dataclasses import dataclass
from pymongo import InsertOne
from pymongo.errors import BulkWriteError


minute_endpoint = "wss://api.upbit.com/websocket/v1"
trade_time = {}
candle_price = {}
current_price = {}
target_market_codes = []
remain_request_at_minute = None
remain_request_at_second = None


@dataclass
class ParsedMarketData:
    code: str
    trade_price: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    stream_type: str

    @classmethod
    def create(cls, code: str, trade_price: int, year: int, month: int, day: int, hour: int, minute: int, stream_type: str):
        return cls(code=code, trade_price=trade_price, year=year, month=month, day=day, hour=hour, minute=minute, stream_type=stream_type)


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

        year, month, day = trade_date.split("-")
        stream_type = message['stream_type']
        return ParsedMarketData.create(code, int(trade_price), int(year), int(month), int(day), hour, minute, stream_type)


class HistoricalCandleCollector:
    minute_endpoint = "https://api.upbit.com/v1/candles/minutes/"
    day_endpoint = "https://api.upbit.com/v1/candles/days"

    @classmethod
    def _collect_recently_minute_candle(cls, code, minute, count):
        querystring = {"market": code, 'count': count}
        url = cls.minute_endpoint + f'{minute}'
        response = requests.request("GET", url, params=querystring)

        #remain_request_at_minute = int(response.headers['Remaining-Req'].split(';')[2].strip().split('=')[1])
        #remain_request_at_second = int(response.headers['Remaining-Req'].split(';')[1].strip().split('=')[1])

        res_json = response.json()

        operations = []

        for item in res_json:
            candle_date_time = item['candle_date_time_kst']

            candle_date = candle_date_time.split('T')[0]
            candle_time = candle_date_time.split('T')[1]

            candle_year = candle_date.split('-')[0]
            candle_month = candle_date.split('-')[1]
            candle_day = candle_date.split('-')[2]

            candle_hour = candle_time.split(':')[0]
            candle_minute = candle_time.split(':')[1]

            open_price = item['opening_price']
            close_price = item['trade_price']
            high_price = item['high_price']
            low_price = item['low_price']

            candle = Candle(code=code, date_time=f'{candle_year}{candle_month}{candle_day}{candle_hour}{candle_minute}',
                            minute=f'{minute}', open_price=open_price, close_price=close_price,
                            high_price=high_price, low_price=low_price, created_at=arrow.now().to('local'))

            operations.append(InsertOne(candle.to_mongo()))

        try:
            Candle._get_collection().bulk_write(operations, ordered=False)
        except BulkWriteError as e:
            pass

        latest_candle = Candle.objects(minute=f'{minute}').order_by('-date_time').first()

        OpenPriceUpdater.update(market_code=code, minute=f'{minute}', open_price=latest_candle.open_price)
        ClosePriceUpdater.update(market_code=code, minute=f'{minute}', close_price=latest_candle.close_price)
        HighPriceUpdater.update(market_code=code, minute=f'{minute}', high_price=latest_candle.high_price)
        LowPriceUpdater.update(market_code=code, minute=f'{minute}', low_price=latest_candle.low_price)

    @classmethod
    def collect_recently_minute_candles(cls, code, count=200):
        for minute in [1, 3, 5, 10, 15, 30, 60, 240]:
            cls._collect_recently_minute_candle(code=code, minute=minute, count=count)
            time.sleep(0.11)

    @classmethod
    def collect_recently_day_candles(cls, code, count=100):
        querystring = {'market': code, 'count': count}
        url = cls.day_endpoint
        response = requests.request("GET", url, params=querystring)
        res_json = response.json()

        operations = []

        for item in res_json:
            candle_date_time = item['candle_date_time_kst']
            candle_date = candle_date_time.split('T')[0]
            candle_time = candle_date_time.split('T')[1]

            candle_year = candle_date.split('-')[0]
            candle_month = candle_date.split('-')[1]
            candle_day = candle_date.split('-')[2]

            candle_hour = candle_time.split(':')[0]
            candle_minute = candle_time.split(':')[1]

            open_price = item['opening_price']
            close_price = item['trade_price']
            high_price = item['high_price']
            low_price = item['low_price']

            candle = Candle(code=code, date_time=f'{candle_year}{candle_month}{candle_day}{candle_hour}{candle_minute}',
                            minute=f'{1440}', open_price=open_price, close_price=close_price,
                            high_price=high_price, low_price=low_price, created_at=arrow.now().to('local'))

            operations.append(InsertOne(candle.to_mongo()))

        try:
            Candle._get_collection().bulk_write(operations, ordered=False)
        except BulkWriteError as e:
            pass

        latest_candle = Candle.objects(minute=f'{1440}').order_by('-date_time').first()

        OpenPriceUpdater.update(market_code=code, minute=f'{1440}', open_price=latest_candle.open_price)
        ClosePriceUpdater.update(market_code=code, minute=f'{1440}', close_price=latest_candle.close_price)
        HighPriceUpdater.update(market_code=code, minute=f'{1440}', high_price=latest_candle.high_price)
        LowPriceUpdater.update(market_code=code, minute=f'{1440}', low_price=latest_candle.low_price)


class CandlePriceInitializer:
    @classmethod
    def initialize(cls, market_data: ParsedMarketData):
        global candle_price
        candle_price[market_data.code] = {}
        candle_price[market_data.code]['1'] = {}
        candle_price[market_data.code]['3'] = {}
        candle_price[market_data.code]['5'] = {}
        candle_price[market_data.code]['10'] = {}
        candle_price[market_data.code]['15'] = {}
        candle_price[market_data.code]['30'] = {}
        candle_price[market_data.code]['60'] = {}
        candle_price[market_data.code]['240'] = {}
        candle_price[market_data.code]['1440'] = {}

        cls._initialize(market_data, candle_price[market_data.code]['1'])
        cls._initialize(market_data, candle_price[market_data.code]['3'])
        cls._initialize(market_data, candle_price[market_data.code]['5'])
        cls._initialize(market_data, candle_price[market_data.code]['10'])
        cls._initialize(market_data, candle_price[market_data.code]['15'])
        cls._initialize(market_data, candle_price[market_data.code]['30'])
        cls._initialize(market_data, candle_price[market_data.code]['60'])
        cls._initialize(market_data, candle_price[market_data.code]['240'])
        cls._initialize(market_data, candle_price[market_data.code]['1440'])

    @classmethod
    def _initialize(cls, market_data: ParsedMarketData, candle):
        candle['open_price'] = market_data.trade_price
        candle['close_price'] = market_data.trade_price
        candle['high_price'] = market_data.trade_price
        candle['low_price'] = market_data.trade_price


class CurrentPriceInitializer:
    @classmethod
    def initialize(cls, market_data: ParsedMarketData):
        global current_price
        current_price[market_data.code] = market_data.trade_price


class CurrentPriceUpdater:
    @classmethod
    def update(cls, market_data: ParsedMarketData):
        current_price[market_data.code] = market_data.trade_price


class TradeTimeInitializer:
    @classmethod
    def initialize(cls, current_time):
        global trade_time
        trade_time['year'] = current_time.year
        trade_time['month'] = current_time.month
        trade_time['day'] = current_time.day
        trade_time['hour'] = current_time.hour
        trade_time['minute'] = current_time.minute


class TradeTimeUpdater:
    @classmethod
    def update(cls, current_time):
        global trade_time
        trade_time['year'] = current_time.year
        trade_time['month'] = current_time.month
        trade_time['day'] = current_time.day
        trade_time['hour'] = current_time.hour
        trade_time['minute'] = current_time.minute


class OpenPriceUpdater:
    @classmethod
    def update(cls, market_code, minute, open_price):
        global candle_price
        candle_price[market_code][minute]['open_price'] = open_price


class ClosePriceUpdater:
    @classmethod
    def update(cls, market_code, minute, close_price):
        global candle_price
        candle_price[market_code][minute]['close_price'] = close_price


class LowPriceUpdater:
    @classmethod
    def update(cls, market_code, minute, low_price):
        global candle_price
        candle_price[market_code][minute]['low_price'] = low_price


class HighPriceUpdater:
    @classmethod
    def update(cls, market_code, minute, high_price):
        global candle_price
        candle_price[market_code][minute]['high_price'] = high_price


class LowHighPriceUpdater:
    @classmethod
    def update(cls, market_data: ParsedMarketData, minute):
        if candle_price[market_data.code][minute]['low_price'] > market_data.trade_price:
            LowPriceUpdater.update(market_data.code, minute=minute, low_price=market_data.trade_price)
        if candle_price[market_data.code][minute]['high_price'] < market_data.trade_price:
            HighPriceUpdater.update(market_data.code, minute=minute, high_price=market_data.trade_price)


class CandleCreator:
    @classmethod
    def create(cls, market_code, current_time, minute):
        ClosePriceUpdater.update(market_code=market_code, minute=minute, close_price=current_price[market_code])
        minute_candle_price = candle_price[market_code][minute]
        if Candle.objects(code=market_code, date_time=f'{current_time.year:04}{current_time.month:02}{current_time.day:02}{current_time.hour:02}{current_time.minute:02}', minute=minute):
            Candle.objects(code=market_code, date_time=f'{current_time.year:04}{current_time.month:02}{current_time.day:02}{current_time.hour:02}{current_time.minute:02}',
                           minute=minute).update(open_price=minute_candle_price['open_price'],
                                                 close_price=minute_candle_price['close_price'],
                                                 high_price=minute_candle_price['high_price'],
                                                 low_price=minute_candle_price['low_price'],
                                                 created_at=arrow.now())
        else:
            Candle(code=market_code, date_time=f'{current_time.year:04}{current_time.month:02}{current_time.day:02}{current_time.hour:02}{current_time.minute:02}',
                   minute=minute, open_price=minute_candle_price['open_price'], close_price=minute_candle_price['close_price'],
                   high_price=minute_candle_price['high_price'], low_price=minute_candle_price['low_price'], created_at=arrow.now()).save()

        OpenPriceUpdater.update(market_code=market_code, minute=minute, open_price=minute_candle_price['close_price'])
        ClosePriceUpdater.update(market_code=market_code, minute=minute, close_price=minute_candle_price['close_price'])
        LowPriceUpdater.update(market_code=market_code, minute=minute, low_price=minute_candle_price['close_price'])
        HighPriceUpdater.update(market_code=market_code, minute=minute, high_price=minute_candle_price['close_price'])


class CandleCloseChecker:
    @classmethod
    def check(cls):
        current_time = arrow.now().to('local')
        for target_market_code in target_market_codes:
            if CandleCloseChecker._is_1m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-1), minute='1')

            if CandleCloseChecker._is_3m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-3), minute='3')

            if CandleCloseChecker._is_5m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-5), minute='5')

            if CandleCloseChecker._is_10m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-10), minute='10')

            if CandleCloseChecker._is_15m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-15), minute='15')

            if CandleCloseChecker._is_30m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-30), minute='30')

            if CandleCloseChecker._is_60m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-60), minute='60')

            if CandleCloseChecker._is_240m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-240), minute='240')

            if CandleCloseChecker._is_1440m_candle_close(current_time):
                CandleCreator.create(market_code=target_market_code, current_time=current_time.shift(minutes=-1440), minute='1440')
        TradeTimeUpdater.update(current_time)

    @classmethod
    def _is_1m_candle_close(cls, current_time):
        if trade_time['minute'] != current_time.minute:
            return True
        else:
            return False

    @classmethod
    def _is_3m_candle_close(cls, current_time):
        if (trade_time['minute'] != current_time.minute) and int(current_time.minute) % 3 == 0:
            return True
        else:
            return False

    @classmethod
    def _is_5m_candle_close(cls, current_time):
        if (trade_time['minute'] != current_time.minute) and int(current_time.minute) % 5 == 0:
            return True
        else:
            return False

    @classmethod
    def _is_10m_candle_close(cls, current_time):
        if (trade_time['minute'] != current_time.minute) and int(current_time.minute) % 10 == 0:
            return True
        else:
            return False

    @classmethod
    def _is_15m_candle_close(cls, current_time):
        if (trade_time['minute'] != current_time.minute) and int(current_time.minute) % 15 == 0:
            return True
        else:
            return False

    @classmethod
    def _is_30m_candle_close(cls, current_time):
        if (trade_time['minute'] != current_time.minute) and int(current_time.minute) % 30 == 0:
            return True
        else:
            return False

    @classmethod
    def _is_60m_candle_close(cls, current_time):
        if trade_time['hour'] != current_time.hour:
            return True
        else:
            return False

    @classmethod
    def _is_240m_candle_close(cls, current_time):
        if trade_time['hour'] != current_time.hour and int(current_time.hour) % 4 == 1:
            return True
        else:
            return False

    @classmethod
    def _is_1440m_candle_close(cls, current_time):
        if trade_time['day'] != current_time.day:
            return True
        else:
            return False


def on_message(ws, message):
    try:
        parsed_market_data: ParsedMarketData = MessageParser.parse(message)
        if parsed_market_data.stream_type == "SNAPSHOT":
            CandlePriceInitializer.initialize(parsed_market_data)
            CurrentPriceInitializer.initialize(parsed_market_data)
            TradeTimeInitializer.initialize(arrow.now().to('local'))
            HistoricalCandleCollector.collect_recently_minute_candles(code=parsed_market_data.code)
            HistoricalCandleCollector.collect_recently_day_candles(code=parsed_market_data.code)
            if parsed_market_data.code not in target_market_codes:
                target_market_codes.append(parsed_market_data.code)

        CurrentPriceUpdater.update(parsed_market_data)
        for minute in ['1', '3', '5', '10', '15', '30', '60', '240', '1440']:
            LowHighPriceUpdater.update(parsed_market_data, minute=minute)
    except Exception as e:
        logging.error(e, exc_info=True)


def on_error(ws, error):
    print(error)


def on_close(ws):
    print("### Closed ###")


def on_open(ws):
    def run(*args):
        send_data = '[{"ticket":"test"},{"type":"trade","codes":["KRW-BTC", "KRW-XRP", "KRW-CVC", "KRW-ETH", "KRW-BCH", "KRW-EOS", "KRW-TON"]}]'
        ws.send(send_data)

    thread.start_new_thread(run, ())


if __name__ == "__main__":
    mongoengine.connect(host='mongodb://localhost:27017/trading?connect=false')
    ws = websocket.WebSocketApp(minute_endpoint,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close,
                                on_open=on_open)

    scheduler = CandleScheduler()
    scheduler.start()
    scheduler.add_job(job_id="2", func=CandleCloseChecker.check)
    ws.run_forever(ping_interval=30, ping_timeout=25)
