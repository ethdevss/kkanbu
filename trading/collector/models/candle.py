import arrow
import datetime

from mongoengine import Document, IntField, DateTimeField, StringField


class ArrowField(DateTimeField):
    def to_mongo(self, value):
        if isinstance(value, arrow.arrow.Arrow):
            return value.datetime
        return super().to_mongo(value)

    def to_python(self, value):
        value = super().to_python(value)
        if isinstance(value, datetime.datetime):
            return arrow.get(value)
        return value


class Candle(Document):
    meta = {
        'indexes': [
            {'fields': ('code', 'date_time', 'minute'), 'unique': True}
        ]
    }
    code = StringField(required=True)
    date_time = StringField(required=True)
    minute = StringField(required=True)
    open_price = IntField(required=True)
    close_price = IntField(required=True)
    high_price = IntField(required=True)
    low_price = IntField(required=True)
    created_at = ArrowField(required=True)
