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
    def __init__(self, initial_balance, market_code, target_minute, buy_percentage, start_date, end_date):
        self.market_code = market_code
        self.target_minute = target_minute
        self.target_candles = CandleDataLoader.load(market_code=market_code, target_minute=target_minute, start_date=start_date, end_date=end_date)
        self.is_open_position = False
        self.krw_balance = initial_balance
        self.currency_balance = 0
        self.buy_percentage = buy_percentage
        self.avg_price = None

    def _trade(self, target_candle, open_position_rsi):
        if self.is_open_position:
            return
        current_rsi = RsiCalculator.get_latest_candle_rsi(market_code=self.market_code, target_candle_minute=self.target_minute, target_date_time=target_candle.date_time)

        if self._is_satisfy_open_position_condition(current_rsi=current_rsi, open_position_rsi=open_position_rsi):
            buy_volume = self._get_volume(target_candle=target_candle)
            self._buy(target_candle=target_candle, volume=buy_volume)
            message = f"== 포지션 진입 == \n" \
                      f"진입 시점: {target_candle.date_time} \n" \
                      f"진입 시 캔들의 rsi: {current_rsi} \n" \
                      f"진입 시 코인 가격: {target_candle.close_price} \n" \
                      f"구매한 코인 개수: {buy_volume} \n" \
                      f"현재 KRW 잔액: {self.krw_balance} \n" \
                      f"코인 잔액: {self.currency_balance}"

            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

    def _get_volume(self, target_candle):
        close_price = target_candle.close_price
        krw_amount_for_buy = self.krw_balance * self.buy_percentage / 100.0
        available_volume = krw_amount_for_buy / close_price
        return available_volume

    def _get_profit_percentage(self, target_candle):
        margin = target_candle.close_price - self.avg_price
        profit_percentage = margin / self.avg_price * 100.0
        return profit_percentage

    def _get_loss_percentage(self, target_candle):
        loss = self.avg_price - target_candle.close_price
        loss_percentage = loss / self.avg_price * 100.0
        return loss_percentage

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
        #self.avg_price = None
        self.is_open_position = False

    def _take_profit(self, target_candle, take_profit_rsi, take_profit_percentage, volume=1):
        if not self.is_open_position:
            return
        if self._is_satisfy_take_profit_percentage_condition(target_candle=target_candle, take_profit_percentage=take_profit_percentage):
            self._sell(target_candle, volume=volume)
            message = f"== 포지션 청산 == \n" \
                      f"진입 시점: {target_candle.date_time} \n" \
                      f"수익률: {self._get_profit_percentage(target_candle)} \n" \
                      f"청산 발동 조건: 목표 익절 퍼센티지에 도달 \n" \
                      f"청산 시 코인 가격: {target_candle.close_price} \n" \
                      f"현재 KRW 잔액: {self.krw_balance}"

            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

        current_rsi = RsiCalculator.get_latest_candle_rsi(market_code=self.market_code, target_candle_minute=self.target_minute,
                                                          target_date_time=target_candle.date_time)
        if self._is_satisfy_take_profit_rsi_condition(current_rsi=current_rsi, take_profit_rsi=take_profit_rsi):
            self._sell(target_candle=target_candle, volume=volume)
            message = f"== 포지션 청산 == \n" \
                      f"진입 시점: {target_candle.date_time} \n" \
                      f"수익률: {self._get_profit_percentage(target_candle)} \n" \
                      f"청산 발동 조건: 익절 RSI 도달 \n" \
                      f"청산 시 캔들의 RSI: {current_rsi} \n" \
                      f"청산 시 코인 가격: {target_candle.close_price} \n" \
                      f"현재 KRW 잔액: {self.krw_balance}"
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

    def _stop_loss(self, target_candle, stop_loss_percentage, volume=1):
        if not self.is_open_position:
            return
        if self._is_satisfy_stop_loss_percentage_condition(target_candle=target_candle, stop_loss_percentage=stop_loss_percentage):
            message = f"== 포지션 청산 == \n" \
                      f"진입 시점: {target_candle.date_time} \n" \
                      f"손실률: {self._get_loss_percentage(target_candle)} \n" \
                      f"청산 발동 조건: 손실 퍼센티지에 도달함 \n" \
                      f"청산 시 코인 가격: {target_candle.close_price} \n" \
                      f"현재 KRW 잔액: {self.krw_balance}"
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)
            self._sell(target_candle=target_candle, volume=volume)

    def run(self, open_position_rsi, take_profit_percentage, take_profit_rsi, stop_loss_percentage):
        for target_candle in self.target_candles:
            self._trade(target_candle=target_candle, open_position_rsi=open_position_rsi)
            self._take_profit(target_candle=target_candle, take_profit_rsi=take_profit_rsi, take_profit_percentage=take_profit_percentage,
                              volume=self.currency_balance)
            self._stop_loss(target_candle=target_candle, stop_loss_percentage=stop_loss_percentage, volume=self.currency_balance)

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
    initial_balance_param = 5000000

    open_position_rsi_param = 35
    take_profit_percentage_param = 10
    take_profit_rsi_param = 75
    stop_loss_percentage_param = 10
    buy_percentage = 50

    back_tester = BackTester(initial_balance=initial_balance_param, market_code=market_code_param, target_minute=target_minute_param,
                             buy_percentage=buy_percentage, start_date=start_date_param, end_date=end_date_param)

    message = f"== 백테스팅을 시작합니다 ==\n\n" \
              f"코인 종류: {market_code_param} \n" \
              f"시작 KRW 잔액: {initial_balance_param} \n" \
              f"대상 캔들 분봉: {target_minute_param} \n" \
              f"백테스팅 시작 기간: {start_date_param} \n" \
              f"백테스팅 종료 기간: {end_date_param} \n" \

    TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

    back_tester.run(open_position_rsi=open_position_rsi_param, take_profit_rsi=take_profit_rsi_param,
                    take_profit_percentage=take_profit_percentage_param, stop_loss_percentage=stop_loss_percentage_param)

    print(f"매매 종료 후 금액: {back_tester.krw_balance}")
