import numpy as np
import pandas as pd

from bot.oms.order_manager import OrderManager
from bot.telegram_bot import TelegramBot
from collector.models.candle import Candle


telegram_chat_id = "784845620"


class Rsi:
    account = {}
    current_market_prices = {}

    @classmethod
    def run(cls, target_major_market_codes, target_minor_market_codes,
            major_crypto_buy_percentage, minor_crypto_buy_percentage,
            open_position_rsi, take_profit_percentage, take_profit_rsi,
            stop_loss_percentage, target_candle_minute, access_key, secret_key):

        cls._get_account_balances(access_key=access_key, secret_key=secret_key)
        cls._get_current_target_market_prices(target_major_market_codes=target_major_market_codes, target_minor_market_codes=target_minor_market_codes)

        cls._trades(target_major_market_codes=target_major_market_codes, target_minor_market_codes=target_minor_market_codes,
                    major_crypto_buy_percentage=major_crypto_buy_percentage, minor_crypto_buy_percentage=minor_crypto_buy_percentage,
                    open_position_rsi=open_position_rsi, target_candle_minute=target_candle_minute, access_key=access_key, secret_key=secret_key)

        cls._get_account_balances(access_key=access_key, secret_key=secret_key)

        cls._take_profit(market_codes=target_major_market_codes, target_candle_minute=target_candle_minute, take_profit_percentage=take_profit_percentage,
                         take_profit_rsi=take_profit_rsi, access_key=access_key, secret_key=secret_key)
        cls._take_profit(market_codes=target_minor_market_codes, target_candle_minute=target_candle_minute, take_profit_percentage=take_profit_percentage,
                         take_profit_rsi=take_profit_rsi, access_key=access_key, secret_key=secret_key)

        cls._stop_loss(market_codes=target_major_market_codes, stop_loss_percentage=stop_loss_percentage, access_key=access_key, secret_key=secret_key)
        cls._stop_loss(market_codes=target_minor_market_codes, stop_loss_percentage=stop_loss_percentage, access_key=access_key, secret_key=secret_key)

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
    def _get_latest_candle_rsi(cls, market_code, target_candle_minute):
        candles = Candle.objects(code=market_code, minute=f'{target_candle_minute}').order_by('-date_time')[:100]

        close_prices = [float(candle.close_price) for candle in candles]
        close_prices = np.asarray(close_prices)[::-1]

        rsi_df = cls._create_rsi_df(close_prices)
        last_df_row = rsi_df.tail(1)
        return last_df_row['rsi'].values[0]

    @classmethod
    def _get_account_balances(cls, access_key, secret_key):
        res = OrderManager.get_accounts(access_key=access_key, secret_key=secret_key)
        cls.account = {} # 초기화
        for item in res:
            if item['currency'] not in cls.account:
                cls.account[item['currency']] = {}
            cls.account[item['currency']]['balance'] = float(item['balance'])
            cls.account[item['currency']]['avg_buy_price'] = float(item['avg_buy_price'])

    @classmethod
    def _increase_account_balance(cls, currency, balance):
        if currency not in cls.account:
            cls.account[currency] = {}
            cls.account[currency]['balance'] = balance
        else:
            cls.account[currency]['balance'] = cls.account[currency]['balance'] + balance

    @classmethod
    def _decrease_account_balance(cls, currency, balance):
        cls.account[currency]['balance'] = cls.account[currency]['balance'] - balance
        if cls.account[currency]['balance'] <= 0:
            del cls.account[currency]

    @classmethod
    def _get_current_currency_balance(cls, currency):
        return cls.account[currency]['balance']

    @classmethod
    def _get_current_currency_avg_price(cls, currency):
        return cls.account[currency]['avg_buy_price']

    @classmethod
    def _update_current_currency_avg_price(cls, currency, avg_buy_price):
        cls.account[currency]['avg_buy_price'] = avg_buy_price

    @classmethod
    def _get_current_target_market_prices(cls, target_major_market_codes, target_minor_market_codes):
        market_codes = []
        market_codes.extend(target_major_market_codes)
        market_codes.extend(target_minor_market_codes)

        res = OrderManager.get_current_prices(market_codes=market_codes)
        cls.current_market_prices = {} # 초기화
        for item in res:
            if item['market'] not in cls.current_market_prices:
                cls.current_market_prices[item['market']] = {}
            cls.current_market_prices[item['market']]['trade_price'] = float(item['trade_price'])

    @classmethod
    def _get_current_market_price(cls, market_code):
        if market_code in cls.current_market_prices:
            return cls.current_market_prices[market_code]['trade_price']
        else:
            return None

    @classmethod
    def _is_satisfy_base_close_condition(cls, currency):
        if currency not in cls.account:
            return False

        return True

    @classmethod
    def _is_satisfy_base_open_condition(cls, currency):
        if currency in cls.account:
            return False

        return True

    @classmethod
    def _is_satisfy_open_position_condition(cls, currency, current_rsi, open_position_rsi):
        if not cls._is_satisfy_base_open_condition(currency):
            return False

        if current_rsi <= open_position_rsi:
            return True
        else:
            return False

    @classmethod
    def _is_satisfy_take_profit_rsi_condition(cls, currency, current_rsi, take_profit_rsi):
        if not cls._is_satisfy_base_close_condition(currency):
            return False

        condition = False
        if take_profit_rsi:
            if current_rsi >= take_profit_rsi:
                condition = True
            else:
                condition = False

        return condition

    @classmethod
    def _is_satisfy_take_profit_percentage_condition(cls, market_code, take_profit_percentage):
        unit_currency, currency = market_code.split('-')
        if not cls._is_satisfy_base_close_condition(currency):
            return False

        current_currency_buy_avg_price = cls._get_current_currency_avg_price(currency)
        current_market_price = cls._get_current_market_price(market_code)

        target_profit_price = current_currency_buy_avg_price + (current_currency_buy_avg_price * take_profit_percentage / 100.0)

        if current_currency_buy_avg_price < current_market_price and current_market_price >= target_profit_price:
            return True
        else:
            return False

    @classmethod
    def _is_satisfy_stop_loss_percentage_condition(cls, market_code, stop_loss_percentage):
        unit_currency, currency = market_code.split('-')
        if not cls._is_satisfy_base_close_condition(currency):
            return False

        current_currency_buy_avg_price = cls._get_current_currency_avg_price(currency)
        current_market_price = cls._get_current_market_price(market_code)

        target_stop_loss_price = current_currency_buy_avg_price - (current_currency_buy_avg_price * stop_loss_percentage / 100.0)

        if current_currency_buy_avg_price > current_market_price and current_market_price <= target_stop_loss_price:
            return True
        else:
            return False

    @classmethod
    def _market_price_buy_order(cls, market_code, buy_percentage, access_key, secret_key):
        price = cls._calculate_market_buy_order_price(krw_balance=cls.account['KRW']['balance'], buy_percentage=buy_percentage)
        res = OrderManager.send_order(market_code=market_code, side='bid', price=price, ord_type='price', access_key=access_key, secret_key=secret_key)

        unit_currency, currency = market_code.split('-')

        if res.ok:
            cls._decrease_account_balance(currency='KRW', balance=price)
            cls._increase_account_balance(currency=currency, balance=cls._calculate_market_buy_order_volume(price, market_code))
            message = f'marketCode: {market_code}, price: {price} 시장가 매수가 완료되었습니다.'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)
        else:
            message = f'marketCode: {market_code}, price: {price} 시장가 매수에 실패하였습니다. status_code: {res.status_code}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

    @classmethod
    def _market_price_sell_order(cls, market_code, access_key, secret_key):
        unit_currency, currency = market_code.split('-')
        volume = cls._get_current_currency_balance(currency=currency)
        res = OrderManager.send_order(market_code=market_code, side='ask', volume=volume, ord_type='market', access_key=access_key, secret_key=secret_key)

        if res.ok:
            avg_price = cls._get_current_currency_avg_price(currency)
            cls._increase_account_balance(currency='KRW', balance=avg_price*volume)
            cls._decrease_account_balance(currency=currency, balance=volume)
            message = f'marketCode: {market_code}, volume: {volume}, average_price: {avg_price}, volume: {volume} 시장가 매도가 완료되었습니다.'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)
        else:
            message = f'marketCode: {market_code}, volume: {volume} 시장가 매도에 실패하였습니다. status_code: {res.status_code}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)

    @classmethod
    def _calculate_market_buy_order_price(cls, krw_balance, buy_percentage):
        order_balance = int(float(krw_balance)) * buy_percentage / 100.0
        return order_balance

    @classmethod
    def _calculate_market_buy_order_volume(cls, price, market_code):
        volume = price / cls.current_market_prices[market_code]['trade_price']
        return volume

    @classmethod
    def _trades(cls, target_major_market_codes, target_minor_market_codes,
                major_crypto_buy_percentage, minor_crypto_buy_percentage,
                open_position_rsi, target_candle_minute, access_key, secret_key):
        for target_major_market_code in target_major_market_codes:
            cls._trade(market_code=target_major_market_code, buy_percentage=major_crypto_buy_percentage,
                       open_position_rsi=open_position_rsi, target_candle_minute=target_candle_minute,
                       access_key=access_key, secret_key=secret_key)

        for target_minor_market_code in target_minor_market_codes:
            cls._trade(market_code=target_minor_market_code, buy_percentage=minor_crypto_buy_percentage,
                       open_position_rsi=open_position_rsi, target_candle_minute=target_candle_minute,
                       access_key=access_key, secret_key=secret_key)

    @classmethod
    def _trade(cls, market_code, buy_percentage, open_position_rsi, target_candle_minute,
               access_key, secret_key):
        target_crypto_latest_rsi = cls._get_latest_candle_rsi(market_code=market_code, target_candle_minute=target_candle_minute)

        # 현재 해당 코인에 대한 포지션이 존재하지 않고, open_position_rsi 조건에 만족한다면 trade를 진행한다.
        unit_currency, currency = market_code.split('-')
        if cls._is_satisfy_open_position_condition(currency=currency, current_rsi=target_crypto_latest_rsi, open_position_rsi=open_position_rsi):
            message = f'포지션 진입 조건에 만족하였습니다. 시장가 매수를 잰항합니다. market_code: {market_code}, current_rsi: {target_crypto_latest_rsi},' \
                      f'open_position_rsi: {open_position_rsi}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)
            cls._market_price_buy_order(market_code=market_code, buy_percentage=buy_percentage, access_key=access_key, secret_key=secret_key)

    @classmethod
    def _take_profit(cls, market_codes, target_candle_minute, take_profit_percentage, take_profit_rsi, access_key, secret_key):
        for market_code in market_codes:
            cls._is_need_take_profit(market_code=market_code, target_candle_minute=target_candle_minute, take_profit_percentage=take_profit_percentage,
                                     take_profit_rsi=take_profit_rsi, access_key=access_key, secret_key=secret_key)

    @classmethod
    def _is_need_take_profit(cls, market_code, target_candle_minute, take_profit_percentage, take_profit_rsi, access_key, secret_key):
        target_crypto_latest_rsi = cls._get_latest_candle_rsi(market_code=market_code, target_candle_minute=target_candle_minute)

        unit_currency, currency = market_code.split('-')
        if cls._is_satisfy_take_profit_rsi_condition(currency=currency, current_rsi=target_crypto_latest_rsi, take_profit_rsi=take_profit_rsi):
            message = f'포지션 익절 RSI 조건에 만족하였습니다. 시장가 매도를 통해 포지션을 정리합니다. market_ode: {market_code}, current_rsi: {target_crypto_latest_rsi}, ' \
                      f'take_profit_rsi: {take_profit_rsi}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)
            cls._market_price_sell_order(market_code=market_code, access_key=access_key, secret_key=secret_key)

        if cls._is_satisfy_take_profit_percentage_condition(market_code=market_code, take_profit_percentage=take_profit_percentage):
            message = f'포지션 익절 percentage 조건에 만족하였습니다. 시장가 매도를 통해 포지션을 정리합니다. market_code: {market_code}, take_profit_percentage: {take_profit_percentage}'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)
            cls._market_price_sell_order(market_code=market_code, access_key=access_key, secret_key=secret_key)

    @classmethod
    def _stop_loss(cls, market_codes, stop_loss_percentage, access_key, secret_key):
        for market_code in market_codes:
            cls._is_need_stop_loss(market_code=market_code, stop_loss_percentage=stop_loss_percentage, access_key=access_key, secret_key=secret_key)

    @classmethod
    def _is_need_stop_loss(cls, market_code, stop_loss_percentage, access_key, secret_key):
        if cls._is_satisfy_stop_loss_percentage_condition(market_code=market_code, stop_loss_percentage=stop_loss_percentage):
            message = f'포지션 stop loss percentage 조건에 만족하였습니다. 시장가 매도를 통해 포지션을 정리합니다.'
            TelegramBot.send_message(chat_id=telegram_chat_id, message=message)
            cls._market_price_sell_order(market_code=market_code, access_key=access_key, secret_key=secret_key)
