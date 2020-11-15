from mongoengine import StringField, Document


class ApiKey(Document):
    meta = {
        'indexes': [
            {'fields': ('user_email', 'access_key', 'secret_key'), 'unique': True}
        ]
    }
    user_email = StringField(required=True)
    access_key = StringField(required=True)
    secret_key = StringField(required=True)
