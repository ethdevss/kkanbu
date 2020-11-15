import arrow

from mongoengine import Document, IntField, DateTimeField, StringField, ListField, BooleanField

from collector.models.candle import ArrowField


class RsiStrategy(Document):
    target_major_market_codes = ListField(StringField(), default=list)
    target_minor_market_codes = ListField(StringField(), default=list)
    major_crypto_buy_percentage = IntField(required=True)
    minor_crypto_buy_percentage = IntField(required=True)
    open_position_rsi = IntField(required=True)
    take_profit_percentage = IntField(required=True)
    take_profit_rsi = IntField(required=True)
    stop_loss_percentage = IntField(required=True)
    balance = IntField(default=0)
    target_candle_minute = IntField(required=True)
    created_at = ArrowField(required=True, default=arrow.now)
    is_running = BooleanField(required=True, default=False)
