import requests
import mongoengine
import arrow
import time
import os, sys, inspect

from pymongo import InsertOne
from pymongo.errors import BulkWriteError

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from collector.models.candle import Candle


class HistoricalMinuteCandleCollector:
    minute_endpoint = "https://api.upbit.com/v1/candles/minutes/"

    @classmethod
    def run(cls, start_date, market_code, minute, count=200):
        is_reach_end_date = False
        while True:
            time.sleep(0.11)
            if start_date.shift(minutes=minute*count) >= arrow.now().to('local'):
                is_reach_end_date = True
            querystring = {"market": market_code, 'count': count, 'to': start_date.shift(minutes=minute*count).format('YYYY-MM-DD HH:mm:ss')}
            url = cls.minute_endpoint + f'{minute}'
            response = requests.request("GET", url, params=querystring)
            start_date = start_date.shift(minutes=minute*count)

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

                candle = Candle(code=market_code, date_time=f'{candle_year}{candle_month}{candle_day}{candle_hour}{candle_minute}',
                                minute=f'{minute}', open_price=open_price, close_price=close_price,
                                high_price=high_price, low_price=low_price, created_at=arrow.now().to('local'))

                operations.append(InsertOne(candle.to_mongo()))

            try:
                Candle._get_collection().bulk_write(operations, ordered=False)
            except BulkWriteError as e:
                pass

            if is_reach_end_date:
                break


class HistoricalDayCandleCollector:
    day_endpoint = "https://api.upbit.com/v1/candles/days"

    @classmethod
    def run(cls, start_date, market_code, count=200):
        is_reach_end_date = False
        while True:
            time.sleep(0.11)
            if start_date.shift(days=count) >= arrow.now().to('local'):
                is_reach_end_date = True
            querystring = {'market': market_code, 'count': count, 'to': start_date.shift(days=count).format('YYYY-MM-DD HH:mm:ss')}
            url = cls.day_endpoint
            response = requests.request("GET", url, params=querystring)
            res_json = response.json()

            start_date = start_date.shift(days=count)

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

                candle = Candle(code=market_code, date_time=f'{candle_year}{candle_month}{candle_day}{candle_hour}{candle_minute}',
                                minute=f'{1440}', open_price=open_price, close_price=close_price,
                                high_price=high_price, low_price=low_price, created_at=arrow.now().to('local'))

                operations.append(InsertOne(candle.to_mongo()))

            try:
                Candle._get_collection().bulk_write(operations, ordered=False)
            except BulkWriteError as e:
                pass

            if is_reach_end_date:
                break


if __name__ == "__main__":
    mongoengine.connect(host='mongodb://localhost:27017/trading?connect=false')

    start_date = arrow.get('2019-01-01 00:00:00', 'YYYY-MM-DD HH:mm:ss')
    HistoricalMinuteCandleCollector.run(start_date=start_date, market_code="KRW-BTC", minute=240, count=200)
    #HistoricalDayCandleCollector.run(start_date=start_date, market_code="KRW-BTC", count=200)
