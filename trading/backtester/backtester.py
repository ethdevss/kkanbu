import os, sys, inspect
import numpy as np
import pandas as pd
import mongoengine

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from collector.models.candle import Candle
from bot.telegram_bot import TelegramBot

telegram_chat_id = "784845620"


class CandleDataLoader:
    @classmethod
    def load(cls, market_code, target_minute, start_date, end_date):
        candles = Candle.objects(code=market_code, minute=target_minute, date_time__gt=start_date, date_time__lt=end_date).order_by('date_time').all()
        return candles


class RsiCalculator:
    @classmethod
    def _create_rsi_df(cls, close_prices, rsi_period=14):
        df = pd.DataFrame(close_prices, columns=['close'])
        chg = df['close'].diff(1)

        gain = chg.mask(chg < 0, 0)
        df['gain'] = gain

        loss = chg.mask(chg > 0, 0)
        df['loss'] = loss

        avg_gain = gain.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()
        avg_loss = loss.ewm(com=rsi_period - 1, min_periods=rsi_period).mean()

        df['avg_gain'] = avg_gain
        df['avg_loss'] = avg_loss

        rs = abs(avg_gain / avg_loss)
        rsi = 100 - (100 / (1 + rs))

        df['rsi'] = rsi
        return df

    @classmethod
    def get_latest_candle_rsi(cls, market_code, target_candle_minute, target_date_time):
        candles = Candle.objects(code=market_code, minute=f'{target_candle_minute}', date_time__lte=target_date_time).order_by('-date_time')[:100]

        close_prices = [float(candle.close_price) for candle in candles]
        close_prices = np.asarray(close_prices)[::-1]

        rsi_df = cls._create_rsi_df(close_prices=close_prices)
        last_df_row = rsi_df.tail(1)

        return last_df_row['rsi'].values[0]


class BackTester:
    def __init__(self, initial_balance, market_code, target_minute, start_date, end_date):
        self.market_code = market_code
        self.target_minute = target_minute
        self.target_candles = CandleDataLoader.load(market_code=market_code, target_minute=target_minute, start_date=start_date, end_date=end_date)
        self.is_open_position = False
        self.krw_balance = initial_balance
        self.currency_balance = 0
        self.avg_price = None

    def _trade(self, target_candle, open_position_rsi):
        if self.is_open_position:
            return
        current_rsi = RsiCalculator.get_latest_candle_rsi(market_code=self.market_code, target_candle_minute=self.target_minute, target_date_time=target_candle.date_time)

        if self._is_satisfy_open_position_condition(current_rsi=current_rsi, open_position_rsi=open_position_rsi):
            self._buy(target_candle=target_candle)
            message = f'RSI 진입 조건에 만족하여 매수를 진행합니다. market_code: {target_candle.code}, 매수 진입 가격: {target_candle.close_price}, 현재 KRW 잔액: {self.krw_balance},' \
                      f'진입 시 캔들 날짜: {target_candle.date_time}, 현재 RSI: {current_rsi}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

    def _buy(self, target_candle, volume=1):
        if self.is_open_position:
            return

        if self.krw_balance < target_candle.close_price * volume:
            return
        self.krw_balance = self.krw_balance - (target_candle.close_price * volume)
        self.currency_balance = self.currency_balance + volume
        self.avg_price = target_candle.close_price
        self.is_open_position = True

    def _sell(self, target_candle, volume=1):
        if not self.is_open_position:
            return

        if self.currency_balance - volume < 0:
            return

        self.currency_balance = self.currency_balance - volume
        self.krw_balance = self.krw_balance + (target_candle.close_price * volume)
        self.avg_price = None
        self.is_open_position = False

    def _take_profit(self, target_candle, take_profit_rsi, take_profit_percentage, volume=1):
        if not self.is_open_position:
            return
        if self._is_satisfy_take_profit_percentage_condition(target_candle=target_candle, take_profit_percentage=take_profit_percentage):
            self._sell(target_candle, volume=volume)
            message = f'수익 퍼센트 조건에 도달하여 포지션을 정리합니다. market_code: {target_candle.code}, 매도 가격: {target_candle.close_price}, 현재 KRW 잔액: {self.krw_balance}, ' \
                      f'진입 시 캔들 날짜: {target_candle.date_time}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

        current_rsi = RsiCalculator.get_latest_candle_rsi(market_code=self.market_code, target_candle_minute=self.target_minute,
                                                          target_date_time=target_candle.date_time)
        if self._is_satisfy_take_profit_rsi_condition(current_rsi=current_rsi, take_profit_rsi=take_profit_rsi):
            self._sell(target_candle=target_candle, volume=volume)
            message = f'수익 RSI 조건에 도달하여 포지션을 정리합니다. market_code: {target_candle.code}, 매도 가격: {target_candle.close_price}, 현재 KRW 잔액: {self.krw_balance},' \
                      f'진입 시 캔들 날짜: {target_candle.date_time}, 현재 RSI: {current_rsi}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

    def _stop_loss(self, target_candle, stop_loss_percentage, volume=1):
        if not self.is_open_position:
            return
        if self._is_satisfy_stop_loss_percentage_condition(target_candle=target_candle, stop_loss_percentage=stop_loss_percentage):
            message = f'손절 퍼센트 조건에 도달하여 포지션을 정리합니다. market_code: {target_candle.code}, 매도 가격: {target_candle.close_price}, 현재 KRW 잔액: {self.krw_balance}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)
            self._sell(target_candle=target_candle, volume=volume)

    def run(self, open_position_rsi, take_profit_percentage, take_profit_rsi, stop_loss_percentage):
        for target_candle in self.target_candles:
            self._trade(target_candle=target_candle, open_position_rsi=open_position_rsi)
            self._take_profit(target_candle=target_candle, take_profit_rsi=take_profit_rsi, take_profit_percentage=take_profit_percentage)
            self._stop_loss(target_candle=target_candle, stop_loss_percentage=stop_loss_percentage)

    @staticmethod
    def _is_satisfy_open_position_condition(current_rsi, open_position_rsi):
        if current_rsi <= open_position_rsi:
            return True
        else:
            return False

    @staticmethod
    def _is_satisfy_take_profit_rsi_condition(current_rsi, take_profit_rsi):
        condition = False
        if take_profit_rsi:
            if current_rsi >= take_profit_rsi:
                condition = True
            else:
                condition = False

        return condition

    def _is_satisfy_take_profit_percentage_condition(self, target_candle, take_profit_percentage):
        target_profit_price = self.avg_price + (self.avg_price * take_profit_percentage / 100.0)

        if self.avg_price < target_candle.close_price and target_candle.close_price >= target_profit_price:
            return True
        else:
            return False

    def _is_satisfy_stop_loss_percentage_condition(self, target_candle, stop_loss_percentage):
        target_stop_loss_price = self.avg_price - (self.avg_price * stop_loss_percentage / 100.0)

        if self.avg_price > target_candle.close_price and target_candle.close_price <= target_stop_loss_price:
            return True
        else:
            return False


if __name__ == "__main__":
    mongoengine.connect(host='mongodb://localhost:27017/trading?connect=false')

    market_code_param = "KRW-BTC"
    target_minute_param = "240"

    start_date_param = "201901041700" # 2019년년 1월 04일 17시 00분
    end_date_param = "202010282100" # 2020년 10월 28일 21시 00분
    initial_balance_param = 100000000

    open_position_rsi_param = 35
    take_profit_percentage_param = 10
    take_profit_rsi_param = 75
    stop_loss_percentage_param = 10

    back_tester = BackTester(initial_balance=initial_balance_param, market_code=market_code_param, target_minute=target_minute_param,
                             start_date=start_date_param, end_date=end_date_param)

    print(f"초기 시작 금액: {initial_balance_param}")

    back_tester.run(open_position_rsi=open_position_rsi_param, take_profit_rsi=take_profit_rsi_param,
                    take_profit_percentage=take_profit_percentage_param, stop_loss_percentage=stop_loss_percentage_param)

    print(f"매매 종료 후 금액: {back_tester.krw_balance}")
